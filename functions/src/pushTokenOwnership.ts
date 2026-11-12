/**
 * P1-3 — server-authoritative FCM token ownership.
 *
 * A device token is registered by the client under
 * `users/{uid}/deviceTokens/{token}`. On a shared device the previous
 * account's registration can survive a logout (offline logout, crash,
 * old build), so without a server-side owner the same token stays eligible
 * for push delivery under two unrelated accounts and the device receives the
 * previous user's private chat and match notifications.
 *
 * The private registry `pushTokenOwners/{sha256(token)}` holds exactly one
 * owner per token. It is maintained by a Firestore trigger on the client
 * registration path and consulted before every push:
 *
 *   - a new registration claims the token: an older registration under a
 *     different account is deleted; a registration that is OLDER than the
 *     current owner's (late-arriving stale event) is itself deleted;
 *   - a deleted registration releases the token only if it was the owner's;
 *   - fetchUserTokenRecords (shared/notify.ts) delivers only to tokens the
 *     registry assigns to the recipient and deletes stale registrations it
 *     finds. A token with no registry record is not delivered (fail closed);
 *     `runTokenOwnershipBackfill` creates the records for registrations that
 *     predate the trigger, and the rollout completes it before the senders
 *     carrying this check are deployed.
 *
 * Raw tokens are never written to the registry or to logs — the document id
 * is a non-reversible fingerprint.
 */
import { createHash } from "node:crypto";

import {
  FieldPath,
  FieldValue,
  Timestamp,
  type DocumentSnapshot,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";

export const PUSH_TOKEN_OWNER_COLLECTION = "pushTokenOwners";

export function tokenFingerprint(token: string): string {
  return createHash("sha256").update(`seolleyeon-push-token-v1:${token}`).digest("hex");
}

function millisOf(value: unknown, fallback: number): number {
  if (value instanceof Timestamp) return value.toMillis();
  if (value && typeof value === "object" && "toMillis" in value) {
    const fn = (value as { toMillis?: unknown }).toMillis;
    if (typeof fn === "function") {
      const ms = fn.call(value);
      if (typeof ms === "number" && Number.isFinite(ms)) return ms;
    }
  }
  return fallback;
}

export type ReconcileOutcome =
  | "claimed"
  | "refreshed"
  | "stale_registration_deleted"
  | "transferred"
  | "released"
  | "release_ignored"
  | "noop";

/**
 * Applies one registration event (create / update / delete of
 * users/{uid}/deviceTokens/{token}) to the registry, in one transaction.
 */
export async function reconcileTokenRegistration(
  db: Firestore,
  params: {
    uid: string;
    token: string;
    /** The registration document after the event, or null when deleted. */
    registration: Record<string, unknown> | null;
    /** Event time (ms) used when the registration has no updatedAt. */
    eventTimeMs: number;
  }
): Promise<ReconcileOutcome> {
  const { uid, token } = params;
  if (!uid || !token) return "noop";
  const registryRef = db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(token));
  const registrationRef = (owner: string) =>
    db.collection("users").doc(owner).collection("deviceTokens").doc(token);

  return db.runTransaction(async (tx) => {
    const registry = await tx.get(registryRef);
    const currentOwner = registry.exists ? String(registry.get("ownerUid") ?? "") : "";
    const currentRegisteredAt = registry.exists ? millisOf(registry.get("registeredAt"), 0) : 0;

    if (params.registration === null) {
      if (registry.exists && currentOwner === uid) {
        tx.delete(registryRef);
        return "released";
      }
      return registry.exists ? "release_ignored" : "noop";
    }

    const registeredAt = millisOf(params.registration.updatedAt, params.eventTimeMs);
    const record = {
      ownerUid: uid,
      registeredAt: Timestamp.fromMillis(registeredAt),
      platform: typeof params.registration.platform === "string" ? params.registration.platform : null,
      updatedAt: FieldValue.serverTimestamp(),
    };

    if (!registry.exists) {
      tx.set(registryRef, record);
      return "claimed";
    }
    if (currentOwner === uid) {
      tx.set(registryRef, record, { merge: true });
      return "refreshed";
    }
    if (currentRegisteredAt > registeredAt) {
      // A late event for an older registration: the token already moved on.
      tx.delete(registrationRef(uid));
      return "stale_registration_deleted";
    }
    tx.set(registryRef, record);
    tx.delete(registrationRef(currentOwner));
    return "transferred";
  });
}

export function createDeviceTokenOwnershipTrigger(db: Firestore) {
  return onDocumentWritten(
    {
      document: "users/{uid}/deviceTokens/{token}",
      // A lost event would leave the registry behind the registration; the
      // reconcile is idempotent, so a retry is always safe.
      retry: true,
    },
    async (event) => {
      const after = event.data?.after;
      const registration = after?.exists ? ((after.data() ?? {}) as Record<string, unknown>) : null;
      const outcome = await reconcileTokenRegistration(db, {
        uid: event.params.uid,
        token: event.params.token,
        registration,
        eventTimeMs: Date.parse(event.time) || Date.now(),
      });
      logger.info("push token ownership reconciled", {
        uid: event.params.uid,
        tokenFingerprint: tokenFingerprint(event.params.token).slice(0, 12),
        outcome,
      });
    }
  );
}

export type OwnershipVerdict = {
  /** Tokens the registry assigns to this user. */
  owned: string[];
  /** Tokens the registry assigns to a different user (stale registration). */
  stale: string[];
  /** Tokens with no registry record yet (legacy, pre-backfill). */
  unregistered: string[];
};

/** Classifies a user's registered tokens against the registry (read-only). */
export async function verifyTokenOwnership(
  db: Firestore,
  uid: string,
  tokens: string[]
): Promise<OwnershipVerdict> {
  const verdict: OwnershipVerdict = { owned: [], stale: [], unregistered: [] };
  const unique = [...new Set(tokens.filter((t) => t.length > 0))];
  if (unique.length === 0) return verdict;
  const refs = unique.map((token) => db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(token)));
  const snaps = await db.getAll(...refs);
  snaps.forEach((snap: DocumentSnapshot, index) => {
    const token = unique[index];
    if (!snap.exists) verdict.unregistered.push(token);
    else if (String(snap.get("ownerUid") ?? "") === uid) verdict.owned.push(token);
    else verdict.stale.push(token);
  });
  return verdict;
}

/** Removes a token everywhere it is known (registration of `uid` and registry). */
export async function forgetToken(db: Firestore, uid: string, token: string): Promise<void> {
  const batch = db.batch();
  batch.delete(db.collection("users").doc(uid).collection("deviceTokens").doc(token));
  const registryRef = db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(token));
  const registry = await registryRef.get();
  if (registry.exists && String(registry.get("ownerUid") ?? "") === uid) batch.delete(registryRef);
  await batch.commit();
}

// ---------------------------------------------------------------------------
// Historical backfill (one-time, idempotent, dry-run first)
// ---------------------------------------------------------------------------

export type RegistrationRecord = { uid: string; token: string; updatedAtMs: number };

export type BackfillPlan = {
  /** Registry records to write: one per token. */
  owners: Array<{ token: string; ownerUid: string; registeredAtMs: number }>;
  /** Registrations under a non-winning account, to delete. */
  staleRegistrations: Array<{ uid: string; token: string }>;
  /** Tokens registered under more than one account (reported). */
  conflicts: Array<{ token: string; uids: string[] }>;
};

/** Pure: the newest registration wins; ties resolve by uid for determinism. */
export function planTokenOwnershipBackfill(records: RegistrationRecord[]): BackfillPlan {
  const byToken = new Map<string, RegistrationRecord[]>();
  for (const record of records) {
    if (!record.uid || !record.token) continue;
    const list = byToken.get(record.token) ?? [];
    list.push(record);
    byToken.set(record.token, list);
  }
  const plan: BackfillPlan = { owners: [], staleRegistrations: [], conflicts: [] };
  for (const [token, list] of byToken) {
    const sorted = [...list].sort((a, b) => b.updatedAtMs - a.updatedAtMs || a.uid.localeCompare(b.uid));
    const winner = sorted[0];
    plan.owners.push({ token, ownerUid: winner.uid, registeredAtMs: winner.updatedAtMs });
    const uids = [...new Set(list.map((r) => r.uid))];
    if (uids.length > 1) {
      plan.conflicts.push({ token, uids: uids.sort() });
      for (const loser of sorted.slice(1)) {
        if (loser.uid !== winner.uid) plan.staleRegistrations.push({ uid: loser.uid, token });
      }
    }
  }
  plan.owners.sort((a, b) => a.token.localeCompare(b.token));
  return plan;
}

export type BackfillTokenOutcome =
  /** No registry record: created for the newest current registration. */
  | "created"
  /** A registry record already exists (the live trigger wrote it); trusted, never overwritten. */
  | "already_recorded"
  /** Every registration seen by the scan has since disappeared: nothing to own. */
  | "no_registration"
  /** The record names an owner whose registration is gone: left for the trigger, not guessed. */
  | "owner_registration_missing";

export type BackfillResult = {
  registrationsScanned: number;
  tokens: number;
  /** Tokens registered under more than one account in the scan. */
  conflicts: number;
  created: number;
  alreadyRecorded: number;
  noRegistration: number;
  ownerRegistrationMissing: number;
  /** Registrations under a non-owner account, not newer than the owner's: deleted. */
  staleDeletes: number;
  /** Non-owner registrations NEWER than the record: their trigger event is pending; untouched. */
  pendingNewer: number;
  /** Tokens left unprocessed because the canary limit was reached. */
  deferredByLimit: number;
  /** Registry records written (== created when applied, 0 in dry-run). */
  registryWrites: number;
  applied: boolean;
};

async function scanRegistrations(db: Firestore, pageSize: number): Promise<RegistrationRecord[]> {
  const records: RegistrationRecord[] = [];
  let last: DocumentSnapshot | null = null;
  for (;;) {
    let query = db.collectionGroup("deviceTokens").orderBy(FieldPath.documentId()).limit(pageSize);
    if (last) query = query.startAfter(last);
    const page = await query.get();
    for (const doc of page.docs) {
      const parts = doc.ref.path.split("/");
      if (parts.length !== 4 || parts[0] !== "users") continue;
      records.push({ uid: parts[1], token: doc.id, updatedAtMs: millisOf(doc.get("updatedAt"), 0) });
    }
    if (page.size < pageSize) break;
    last = page.docs[page.docs.length - 1];
  }
  return records;
}

type TokenReconcile = { outcome: BackfillTokenOutcome; staleDeletes: number; pendingNewer: number };

/**
 * One token, one transaction, current state only (the scan only says which
 * accounts to look at). Mirrors the trigger's rules so the backfill can run
 * while the trigger is live:
 *   - an existing registry record is authoritative and never overwritten; a
 *     registration under another account that is not newer than the record
 *     is stale and deleted (the trigger's `stale_registration_deleted`); a
 *     newer one is left for its pending trigger event;
 *   - without a record, the newest current registration (ties by uid) gets a
 *     record (`create`: a concurrent trigger claim aborts and retries the
 *     transaction instead of being overwritten) and the others are deleted.
 * Dry-run runs the same decisions in a read-only transaction.
 */
async function backfillOneToken(
  db: Firestore,
  token: string,
  uids: string[],
  apply: boolean
): Promise<TokenReconcile> {
  const registryRef = db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(token));
  const regRefs = uids.map((uid) => db.collection("users").doc(uid).collection("deviceTokens").doc(token));
  const body = async (tx: Transaction): Promise<TokenReconcile> => {
    const [registry, ...regs] = await tx.getAll(registryRef, ...regRefs);
    const current = regs
      .map((snap, i) => ({ uid: uids[i], snap }))
      .filter((r) => r.snap.exists)
      .map((r) => ({ uid: r.uid, ref: r.snap.ref, updatedAtMs: millisOf(r.snap.get("updatedAt"), 0) }));
    if (registry.exists) {
      const owner = String(registry.get("ownerUid") ?? "");
      const ownerAt = millisOf(registry.get("registeredAt"), 0);
      if (!current.some((r) => r.uid === owner)) {
        return { outcome: "owner_registration_missing", staleDeletes: 0, pendingNewer: 0 };
      }
      const others = current.filter((r) => r.uid !== owner);
      const stale = others.filter((r) => r.updatedAtMs <= ownerAt);
      if (apply) for (const r of stale) tx.delete(r.ref);
      return { outcome: "already_recorded", staleDeletes: stale.length, pendingNewer: others.length - stale.length };
    }
    if (current.length === 0) return { outcome: "no_registration", staleDeletes: 0, pendingNewer: 0 };
    const sorted = [...current].sort((a, b) => b.updatedAtMs - a.updatedAtMs || a.uid.localeCompare(b.uid));
    const winner = sorted[0];
    const losers = sorted.slice(1).filter((r) => r.uid !== winner.uid);
    if (apply) {
      tx.create(registryRef, {
        ownerUid: winner.uid,
        registeredAt: Timestamp.fromMillis(winner.updatedAtMs),
        platform: null,
        updatedAt: FieldValue.serverTimestamp(),
        backfilledAt: FieldValue.serverTimestamp(),
      });
      for (const r of losers) tx.delete(r.ref);
    }
    return { outcome: "created", staleDeletes: losers.length, pendingNewer: 0 };
  };
  return apply ? db.runTransaction(body) : db.runTransaction(body, { readOnly: true });
}

/**
 * Reads every registration (collection group, paged) and reconciles each
 * token in its own transaction (backfillOneToken). Idempotent: a re-run finds
 * every token `already_recorded` with nothing stale. `maxTokens` bounds a run
 * (canary): tokens are processed in fingerprint order, the rest are reported
 * as deferred. Output never carries raw tokens or account ids.
 */
export async function runTokenOwnershipBackfill(
  db: Firestore,
  options: { apply: boolean; pageSize?: number; maxTokens?: number; log?: (line: string) => void }
): Promise<BackfillResult> {
  const log = options.log ?? (() => undefined);
  const records = await scanRegistrations(db, options.pageSize ?? 500);
  const plan = planTokenOwnershipBackfill(records);
  const uidsByToken = new Map<string, string[]>();
  for (const record of records) {
    if (!record.uid || !record.token) continue;
    const list = uidsByToken.get(record.token) ?? [];
    if (!list.includes(record.uid)) list.push(record.uid);
    uidsByToken.set(record.token, list);
  }
  const result: BackfillResult = {
    registrationsScanned: records.length,
    tokens: uidsByToken.size,
    conflicts: plan.conflicts.length,
    created: 0,
    alreadyRecorded: 0,
    noRegistration: 0,
    ownerRegistrationMissing: 0,
    staleDeletes: 0,
    pendingNewer: 0,
    deferredByLimit: 0,
    registryWrites: 0,
    applied: options.apply,
  };
  const ordered = [...uidsByToken.entries()]
    .map(([token, uids]) => ({ token, uids: [...uids].sort(), fp: tokenFingerprint(token) }))
    .sort((a, b) => a.fp.localeCompare(b.fp));
  const limit = options.maxTokens ?? Number.POSITIVE_INFINITY;
  let processed = 0;
  for (const item of ordered) {
    if (processed >= limit) {
      result.deferredByLimit += 1;
      continue;
    }
    processed += 1;
    const r = await backfillOneToken(db, item.token, item.uids, options.apply);
    result.staleDeletes += r.staleDeletes;
    result.pendingNewer += r.pendingNewer;
    if (r.outcome === "created") {
      result.created += 1;
      if (options.apply) result.registryWrites += 1;
    } else if (r.outcome === "already_recorded") result.alreadyRecorded += 1;
    else if (r.outcome === "no_registration") result.noRegistration += 1;
    else result.ownerRegistrationMissing += 1;
    log(`token=${item.fp.slice(0, 12)} accounts=${item.uids.length} outcome=${r.outcome} stale=${r.staleDeletes} pending=${r.pendingNewer}`);
  }
  return result;
}

export type RegistryVerification = {
  registrations: number;
  distinctTokens: number;
  tokensWithRecord: number;
  /** Registered tokens without a registry record (refused at delivery). */
  tokensWithoutRecord: number;
  /** Tokens registered under more than one account. */
  tokensUnderMultipleAccounts: number;
  /** Registrations under an account the registry does not name (stale). */
  registrationsNotOwned: number;
  /** Registry records whose owner has no registration for that token. */
  recordsWithoutOwnerRegistration: number;
  records: number;
  ok: boolean;
};

/**
 * Read-only consistency check of the registrations against the registry.
 * `ok` = every registered token has a record, each token is registered under
 * exactly one account, and that account is the recorded owner.
 */
export async function verifyTokenOwnershipRegistry(
  db: Firestore,
  options: { pageSize?: number } = {}
): Promise<RegistryVerification> {
  const pageSize = options.pageSize ?? 500;
  const records = await scanRegistrations(db, pageSize);
  const uidsByFingerprint = new Map<string, Set<string>>();
  for (const r of records) {
    const fp = tokenFingerprint(r.token);
    const set = uidsByFingerprint.get(fp) ?? new Set<string>();
    set.add(r.uid);
    uidsByFingerprint.set(fp, set);
  }
  const owners = new Map<string, string>();
  let last: DocumentSnapshot | null = null;
  for (;;) {
    let query = db.collection(PUSH_TOKEN_OWNER_COLLECTION).orderBy(FieldPath.documentId()).limit(pageSize);
    if (last) query = query.startAfter(last);
    const page = await query.get();
    for (const doc of page.docs) owners.set(doc.id, String(doc.get("ownerUid") ?? ""));
    if (page.size < pageSize) break;
    last = page.docs[page.docs.length - 1];
  }
  const v: RegistryVerification = {
    registrations: records.length,
    distinctTokens: uidsByFingerprint.size,
    tokensWithRecord: 0,
    tokensWithoutRecord: 0,
    tokensUnderMultipleAccounts: 0,
    registrationsNotOwned: 0,
    recordsWithoutOwnerRegistration: 0,
    records: owners.size,
    ok: false,
  };
  for (const [fp, uids] of uidsByFingerprint) {
    if (uids.size > 1) v.tokensUnderMultipleAccounts += 1;
    const owner = owners.get(fp);
    if (owner === undefined) {
      v.tokensWithoutRecord += 1;
      continue;
    }
    v.tokensWithRecord += 1;
    for (const uid of uids) if (uid !== owner) v.registrationsNotOwned += 1;
  }
  for (const [fp, owner] of owners) {
    if (!uidsByFingerprint.get(fp)?.has(owner)) v.recordsWithoutOwnerRegistration += 1;
  }
  v.ok = v.tokensWithoutRecord === 0 && v.tokensUnderMultipleAccounts === 0 && v.registrationsNotOwned === 0;
  return v;
}
