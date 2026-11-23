/**
 * AUD-11 — one verified identity ↔ one account, decided atomically.
 *
 * `verifyAdultIdentityAfterLogin` used to look for another account holding
 * the same CI / DI / PortOne customer key with plain queries BEFORE its
 * transaction. Two accounts verifying the same person concurrently both saw
 * "nobody has it" and both committed. A query result cannot be locked against
 * a document that does not exist yet, so the claim is now a document:
 *
 *   adultIdentityOwners/{kind}_{hash}  { userId, kind, claimedAt, updatedAt }
 *
 * read and written in the SAME transaction as the verification record. Two
 * concurrent claims of one identity contend on that document; exactly one
 * commits and the other is retried and refused.
 *
 * Invariant: the ownership documents of an account are exactly the keys
 * derivable from its `userPrivateVerifications/{uid}` record (the four fields
 * below). That record stays the authority:
 *   - a claim whose owner no longer has a matching record (account deleted,
 *     identity replaced) is stale and is taken over, so a missing cleanup can
 *     never turn into a silent re-join block;
 *   - records written before this change have no ownership documents yet, so
 *     the transaction also runs the old lookup on the records (now inside the
 *     transaction) until the backfill has been applied.
 *
 * Only hashes are stored and nothing here is ever logged. The collection is
 * server-only (firestore.rules default deny).
 */
import { createHash } from "node:crypto";

import {
  FieldValue,
  type DocumentReference,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

import { assertActiveAccountState } from "./accountStatePolicy";
import { isAdultVerifiedUserData } from "./adultEligibility";
import { dataPartitionOf } from "./playReviewAccess";

export const ADULT_IDENTITY_OWNERS_COLLECTION = "adultIdentityOwners";
export const PRIVATE_VERIFICATIONS_COLLECTION = "userPrivateVerifications";

export type AdultIdentityKeyKind = "ci" | "di" | "uniqueKey" | "session";

export type AdultIdentityKey = {
  kind: AdultIdentityKeyKind;
  /** sha256 hex; the ownership document id is `${kind}_${hash}`. */
  hash: string;
  /** Field of the private verification record that carries this key. */
  recordField: "ciHash" | "diHash" | "uniqueKeyHash" | "identityVerificationId";
  /** Value stored in that field (the raw session id for `session`). */
  recordValue: string;
};

/** The identity fields of a `userPrivateVerifications/{uid}` record. */
export type AdultIdentityRecord = {
  ciHash?: unknown;
  diHash?: unknown;
  uniqueKeyHash?: unknown;
  identityVerificationId?: unknown;
};

const SHA256_HEX = /^[a-f0-9]{64}$/;

function nonEmpty(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

/** Keys an account holds according to its private verification record. */
export function adultIdentityKeysOf(
  record: AdultIdentityRecord | null | undefined
): AdultIdentityKey[] {
  const keys: AdultIdentityKey[] = [];
  const hashed = [
    ["ci", "ciHash"],
    ["di", "diHash"],
    ["uniqueKey", "uniqueKeyHash"],
  ] as const;
  for (const [kind, field] of hashed) {
    const value = nonEmpty(record?.[field]);
    // A malformed hash is not an identity; it can neither claim nor block.
    if (value && SHA256_HEX.test(value)) {
      keys.push({ kind, hash: value, recordField: field, recordValue: value });
    }
  }
  const sessionId = nonEmpty(record?.identityVerificationId);
  if (sessionId) {
    keys.push({
      kind: "session",
      hash: sha256Hex(sessionId),
      recordField: "identityVerificationId",
      recordValue: sessionId,
    });
  }
  return keys;
}

export function adultIdentityOwnerDocId(key: Pick<AdultIdentityKey, "kind" | "hash">): string {
  return `${key.kind}_${key.hash}`;
}

function ownerRef(db: Firestore, key: AdultIdentityKey): DocumentReference {
  return db
    .collection(ADULT_IDENTITY_OWNERS_COLLECTION)
    .doc(adultIdentityOwnerDocId(key));
}

function identityConflict(kind: AdultIdentityKeyKind): HttpsError {
  return new HttpsError(
    "already-exists",
    kind === "session"
      ? "이미 다른 계정에 연결된 본인인증 세션입니다."
      : "이미 다른 계정에 연결된 본인인증 정보입니다."
  );
}

/**
 * Who may run identity verification: an existing, active, production
 * account. The Play-review partition is eligible by construction
 * (adultEligibility.ts) and must never claim a production identity.
 */
export function assertAdultVerificationAccount(
  data: Record<string, unknown>
): void {
  assertActiveAccountState(data);
  if (dataPartitionOf(data) !== "production") {
    throw new HttpsError(
      "failed-precondition",
      "이 계정은 본인인증 대상이 아니에요."
    );
  }
}

/** Pre-check before the provider is contacted or anything is written. */
export async function requireAdultVerificationAccount(
  db: Firestore,
  uid: string
): Promise<void> {
  const snapshot = await db.collection("users").doc(uid).get();
  if (!snapshot.exists) {
    throw new HttpsError("failed-precondition", "사용자 계정을 찾을 수 없어요.");
  }
  assertAdultVerificationAccount(
    (snapshot.data() ?? {}) as Record<string, unknown>
  );
}

export type AdultIdentityClaim = {
  /** Queue the ownership writes; call after every read of the transaction. */
  apply(transaction: Transaction): void;
};

/**
 * READ phase of the claim, inside the caller's transaction: refuses with
 * `already-exists` when any key of `next` belongs to another account, and
 * returns the writes that record `uid` as the owner (and release the keys of
 * `previous` that `next` no longer carries).
 *
 * Same account, same identity → idempotent. Nothing is written when it throws.
 */
export async function planAdultIdentityClaim(
  db: Firestore,
  transaction: Transaction,
  params: {
    uid: string;
    previous: AdultIdentityRecord | null | undefined;
    next: AdultIdentityRecord;
  }
): Promise<AdultIdentityClaim> {
  const { uid } = params;
  const nextKeys = adultIdentityKeysOf(params.next);
  const nextIds = new Set(nextKeys.map(adultIdentityOwnerDocId));
  const releasedKeys = adultIdentityKeysOf(params.previous).filter(
    (key) => !nextIds.has(adultIdentityOwnerDocId(key))
  );
  const allKeys = [...nextKeys, ...releasedKeys];
  const snapshots =
    allKeys.length > 0
      ? await transaction.getAll(...allKeys.map((key) => ownerRef(db, key)))
      : [];
  const ownerOf = (index: number): string | null =>
    snapshots[index].exists ? nonEmpty(snapshots[index].get("userId")) : null;

  for (let index = 0; index < nextKeys.length; index += 1) {
    const key = nextKeys[index];
    const owner = ownerOf(index);
    if (owner && owner !== uid) {
      // The record is the authority: an owner without a matching record is a
      // leftover (deleted account, replaced identity) and is taken over.
      const ownerRecord = await transaction.get(
        db.collection(PRIVATE_VERIFICATIONS_COLLECTION).doc(owner)
      );
      const stillHeld =
        ownerRecord.exists &&
        adultIdentityKeysOf(ownerRecord.data()).some(
          (held) => held.kind === key.kind && held.hash === key.hash
        );
      if (stillHeld) throw identityConflict(key.kind);
    }
    // Records written before ownership documents existed.
    const legacy = await transaction.get(
      db
        .collection(PRIVATE_VERIFICATIONS_COLLECTION)
        .where(key.recordField, "==", key.recordValue)
        .limit(2)
    );
    if (legacy.docs.some((doc) => doc.id !== uid)) {
      throw identityConflict(key.kind);
    }
  }

  return {
    apply(tx: Transaction): void {
      const now = FieldValue.serverTimestamp();
      nextKeys.forEach((key, index) => {
        if (ownerOf(index) === uid) {
          tx.set(ownerRef(db, key), { updatedAt: now }, { merge: true });
        } else {
          tx.set(ownerRef(db, key), {
            userId: uid,
            kind: key.kind,
            claimedAt: now,
            updatedAt: now,
          });
        }
      });
      releasedKeys.forEach((key, offset) => {
        if (ownerOf(nextKeys.length + offset) === uid) {
          tx.delete(ownerRef(db, key));
        }
      });
    },
  };
}

export type IncompleteAdultVerificationOutcome =
  | "no_account"
  | "kept_verified"
  | "marked_required";

/**
 * A verification the provider did not complete (cancelled, failed, pending).
 * It is evidence of nothing: an account that already holds a completed adult
 * verification keeps it, and no account document is created for a session
 * that has none. Only a not-yet-verified account is (re)marked as requiring
 * verification, as before.
 */
export async function recordIncompleteAdultVerification(
  db: Firestore,
  uid: string
): Promise<IncompleteAdultVerificationOutcome> {
  const userRef = db.collection("users").doc(uid);
  return db.runTransaction(async (transaction) => {
    const snapshot = await transaction.get(userRef);
    if (!snapshot.exists) return "no_account";
    const data = (snapshot.data() ?? {}) as Record<string, unknown>;
    if (isAdultVerifiedUserData(data)) return "kept_verified";
    transaction.set(
      userRef,
      {
        adultVerified: false,
        realNameVerified: false,
        registrationStatus: "adult_verification_required",
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    return "marked_required";
  });
}

/**
 * Account deletion: remove every ownership document of `uid`. Idempotent and
 * independent of the private record, so it also works on a retried deletion
 * whose record is already gone.
 */
export async function releaseAdultIdentityOwnership(
  db: Firestore,
  uid: string
): Promise<number> {
  const owned = await db
    .collection(ADULT_IDENTITY_OWNERS_COLLECTION)
    .where("userId", "==", uid)
    .get();
  if (owned.empty) return 0;
  const batch = db.batch();
  owned.docs.forEach((doc) => batch.delete(doc.ref));
  await batch.commit();
  return owned.size;
}

// =============================================================================
// Backfill for records written before ownership documents existed.
// The audit is read-only; the apply step is a separate call.
// =============================================================================

export type AdultIdentityOwnershipAudit = {
  privateRecords: number;
  expectedOwnerDocs: number;
  ownerDocs: number;
  /** Expected ownership documents that do not exist yet. */
  missing: number;
  /** Ownership documents naming an account other than the record holder. */
  ownedByAnotherAccount: number;
  /** Ownership documents no current record backs (taken over on next claim). */
  stale: number;
  /** Identity keys held by more than one record: pre-existing duplicates. */
  sharedIdentityKeys: number;
  accountsSharingAnIdentity: number;
  ok: boolean;
};

const RECORD_FIELDS = ["ciHash", "diHash", "uniqueKeyHash", "identityVerificationId"];

async function loadOwnershipState(db: Firestore) {
  const [records, owners] = await Promise.all([
    // Projection: the name / phone / birth date of a record are never read.
    db.collection(PRIVATE_VERIFICATIONS_COLLECTION).select(...RECORD_FIELDS).get(),
    db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).select("userId").get(),
  ]);
  const holders = new Map<string, Set<string>>();
  for (const record of records.docs) {
    for (const key of adultIdentityKeysOf(record.data())) {
      const id = adultIdentityOwnerDocId(key);
      holders.set(id, (holders.get(id) ?? new Set()).add(record.id));
    }
  }
  const ownerById = new Map<string, string | null>(
    owners.docs.map((doc) => [doc.id, nonEmpty(doc.get("userId"))])
  );
  return { records, holders, ownerById };
}

/** READ-ONLY. Counts only; no identifier leaves this function. */
export async function auditAdultIdentityOwnership(
  db: Firestore
): Promise<AdultIdentityOwnershipAudit> {
  const { records, holders, ownerById } = await loadOwnershipState(db);
  let missing = 0;
  let ownedByAnotherAccount = 0;
  let sharedIdentityKeys = 0;
  const sharing = new Set<string>();
  for (const [id, uids] of holders) {
    if (uids.size > 1) {
      sharedIdentityKeys += 1;
      uids.forEach((uid) => sharing.add(uid));
      continue;
    }
    const owner = ownerById.get(id);
    if (owner === undefined) missing += 1;
    else if (owner === null || !uids.has(owner)) ownedByAnotherAccount += 1;
  }
  let stale = 0;
  for (const [id, owner] of ownerById) {
    const uids = holders.get(id);
    if (!uids || owner === null || !uids.has(owner)) stale += 1;
  }
  return {
    privateRecords: records.size,
    expectedOwnerDocs: holders.size,
    ownerDocs: ownerById.size,
    missing,
    ownedByAnotherAccount,
    stale,
    sharedIdentityKeys,
    accountsSharingAnIdentity: sharing.size,
    ok: missing === 0 && ownedByAnotherAccount === 0 && sharedIdentityKeys === 0,
  };
}

export type AdultIdentityOwnershipBackfill = {
  applied: boolean;
  recordsScanned: number;
  created: number;
  alreadyOwned: number;
  /** Left for a human: the key is held by more than one record. */
  skippedShared: number;
  /** Left alone: another account's still-valid claim. */
  skippedOwnedByAnotherAccount: number;
};

/**
 * Creates the missing ownership documents. Each record is reconciled in its
 * own transaction against the CURRENT record and claims, with `create`
 * semantics, so it is safe while the callable is live and a re-run writes
 * nothing. It never modifies a users document or a verification record, and
 * it never resolves a duplicate: a shared key is reported and skipped.
 */
export async function backfillAdultIdentityOwnership(
  db: Firestore,
  options: { apply: boolean }
): Promise<AdultIdentityOwnershipBackfill> {
  const { records, holders } = await loadOwnershipState(db);
  const result: AdultIdentityOwnershipBackfill = {
    applied: options.apply,
    recordsScanned: records.size,
    created: 0,
    alreadyOwned: 0,
    skippedShared: 0,
    skippedOwnedByAnotherAccount: 0,
  };
  for (const record of records.docs) {
    const uid = record.id;
    const counts = await db.runTransaction(async (transaction) => {
      const local = { created: 0, alreadyOwned: 0, skippedShared: 0, skippedOwnedByAnotherAccount: 0 };
      const current = await transaction.get(record.ref);
      if (!current.exists) return local;
      const keys = adultIdentityKeysOf(current.data());
      if (keys.length === 0) return local;
      const snapshots = await transaction.getAll(...keys.map((key) => ownerRef(db, key)));
      const creates: AdultIdentityKey[] = [];
      keys.forEach((key, index) => {
        const sharedBy = holders.get(adultIdentityOwnerDocId(key))?.size ?? 0;
        const owner = snapshots[index].exists ? nonEmpty(snapshots[index].get("userId")) : null;
        if (owner === uid) local.alreadyOwned += 1;
        else if (sharedBy > 1) local.skippedShared += 1;
        else if (snapshots[index].exists) local.skippedOwnedByAnotherAccount += 1;
        else creates.push(key);
      });
      local.created = creates.length;
      if (options.apply) {
        const now = FieldValue.serverTimestamp();
        for (const key of creates) {
          transaction.create(ownerRef(db, key), {
            userId: uid,
            kind: key.kind,
            claimedAt: now,
            updatedAt: now,
            source: "backfill",
          });
        }
      }
      return local;
    });
    result.created += counts.created;
    result.alreadyOwned += counts.alreadyOwned;
    result.skippedShared += counts.skippedShared;
    result.skippedOwnedByAnotherAccount += counts.skippedOwnedByAnotherAccount;
  }
  return result;
}
