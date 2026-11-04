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
 *     finds. A token with no registry record yet (pre-backfill legacy) is
 *     delivered and logged; `runTokenOwnershipBackfill` creates the records.
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

export type BackfillResult = {
  registrationsScanned: number;
  tokens: number;
  conflicts: number;
  registryWrites: number;
  staleDeletes: number;
  applied: boolean;
};

/**
 * Reads every registration (collection group, paged), plans and — with
 * `apply` — writes registry records that are missing or disagree, deleting
 * the losing registrations. Existing registry records that already name the
 * planned owner are left untouched, so a re-run writes nothing.
 */
export async function runTokenOwnershipBackfill(
  db: Firestore,
  options: { apply: boolean; pageSize?: number; log?: (line: string) => void }
): Promise<BackfillResult> {
  const pageSize = options.pageSize ?? 500;
  const log = options.log ?? (() => undefined);
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

  const plan = planTokenOwnershipBackfill(records);
  const result: BackfillResult = {
    registrationsScanned: records.length,
    tokens: plan.owners.length,
    conflicts: plan.conflicts.length,
    registryWrites: 0,
    staleDeletes: 0,
    applied: options.apply,
  };
  for (const conflict of plan.conflicts) {
    log(`conflict token=${tokenFingerprint(conflict.token).slice(0, 12)} accounts=${conflict.uids.length}`);
  }

  const registryRefs = plan.owners.map((o) => db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(o.token)));
  const existing = new Map<string, string>();
  for (let i = 0; i < registryRefs.length; i += 100) {
    const chunk = registryRefs.slice(i, i + 100);
    const snaps = await db.getAll(...chunk);
    snaps.forEach((snap, j) => {
      if (snap.exists) existing.set(plan.owners[i + j].token, String(snap.get("ownerUid") ?? ""));
    });
  }

  let batch = db.batch();
  let ops = 0;
  const flush = async () => {
    if (ops === 0) return;
    if (options.apply) await batch.commit();
    batch = db.batch();
    ops = 0;
  };
  for (const owner of plan.owners) {
    if (existing.get(owner.token) === owner.ownerUid) continue;
    result.registryWrites += 1;
    batch.set(db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(owner.token)), {
      ownerUid: owner.ownerUid,
      registeredAt: Timestamp.fromMillis(owner.registeredAtMs),
      platform: null,
      updatedAt: FieldValue.serverTimestamp(),
      backfilledAt: FieldValue.serverTimestamp(),
    });
    if (++ops >= 400) await flush();
  }
  for (const stale of plan.staleRegistrations) {
    result.staleDeletes += 1;
    batch.delete(db.collection("users").doc(stale.uid).collection("deviceTokens").doc(stale.token));
    if (++ops >= 400) await flush();
  }
  await flush();
  return result;
}
