import type { Firestore } from "firebase-admin/firestore";

export type PushSkipReason =
  | "missing_user"
  | "deleted_or_suspended"
  | "blocked_with_actor";

export type PushRecipientDecision =
  | { allow: true }
  | { allow: false; reason: PushSkipReason };

const INACTIVE_ACCOUNT_STATUSES = new Set([
  "blocked",
  "deleted",
  "suspended",
]);

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function isInactivePushRecipient(
  userDoc: Record<string, unknown>
): boolean {
  if (userDoc.deleted === true || userDoc.isDeleted === true) return true;
  if (userDoc.suspended === true || userDoc.isSuspended === true) return true;

  const accountStatus = asString(userDoc.accountStatus).toLowerCase();
  if (INACTIVE_ACCOUNT_STATUSES.has(accountStatus)) return true;

  const status = asString(userDoc.status).toLowerCase();
  return INACTIVE_ACCOUNT_STATUSES.has(status);
}

/**
 * Decide whether a recipient may receive a push for an optional actor.
 *
 * Block checks are mutual: if either side has a `blocks/{from}/targets/{to}`
 * edge, the recipient must not be notified about the actor's activity.
 */
export function classifyPushRecipient(params: {
  recipientUid: string;
  recipientDoc: Record<string, unknown> | null;
  actorUid?: string | null;
  recipientBlockedActor?: boolean;
  actorBlockedRecipient?: boolean;
}): PushRecipientDecision {
  if (!params.recipientDoc) {
    return { allow: false, reason: "missing_user" };
  }
  if (isInactivePushRecipient(params.recipientDoc)) {
    return { allow: false, reason: "deleted_or_suspended" };
  }

  const actorUid = asString(params.actorUid);
  const recipientUid = asString(params.recipientUid);
  if (!actorUid || !recipientUid || actorUid === recipientUid) {
    return { allow: true };
  }

  if (params.recipientBlockedActor || params.actorBlockedRecipient) {
    return { allow: false, reason: "blocked_with_actor" };
  }
  return { allow: true };
}

export type PushRecipientLoader = {
  loadUserDoc: (uid: string) => Promise<Record<string, unknown> | null>;
  hasBlockEdge: (fromUid: string, toUid: string) => Promise<boolean>;
};

export async function filterPushRecipientIds(
  recipientIds: string[],
  options: PushRecipientLoader & { actorUserId?: string | null }
): Promise<{
  allowed: string[];
  skipped: Array<{ uid: string; reason: PushSkipReason }>;
}> {
  const unique = [...new Set(recipientIds.map(asString).filter(Boolean))];
  const actorUid = asString(options.actorUserId);
  const allowed: string[] = [];
  const skipped: Array<{ uid: string; reason: PushSkipReason }> = [];

  for (const uid of unique) {
    const recipientDoc = await options.loadUserDoc(uid);
    let recipientBlockedActor = false;
    let actorBlockedRecipient = false;
    if (actorUid && actorUid !== uid) {
      [recipientBlockedActor, actorBlockedRecipient] = await Promise.all([
        options.hasBlockEdge(uid, actorUid),
        options.hasBlockEdge(actorUid, uid),
      ]);
    }

    const decision = classifyPushRecipient({
      recipientUid: uid,
      recipientDoc,
      actorUid,
      recipientBlockedActor,
      actorBlockedRecipient,
    });
    if (decision.allow) {
      allowed.push(uid);
    } else {
      skipped.push({ uid, reason: decision.reason });
    }
  }

  return { allowed, skipped };
}

export function createFirestorePushRecipientLoader(
  db: Firestore
): PushRecipientLoader {
  return {
    async loadUserDoc(uid) {
      const snap = await db.collection("users").doc(uid).get();
      if (!snap.exists) return null;
      return (snap.data() ?? {}) as Record<string, unknown>;
    },
    async hasBlockEdge(fromUid, toUid) {
      const snap = await db
        .collection("blocks")
        .doc(fromUid)
        .collection("targets")
        .doc(toUid)
        .get();
      return snap.exists;
    },
  };
}
