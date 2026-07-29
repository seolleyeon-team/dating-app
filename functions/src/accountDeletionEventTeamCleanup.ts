/**
 * Event team cleanup for account deletion.
 *
 * Real schema (eventTeamSetups):
 * - leaderUserId
 * - acceptedUserIds
 * - pendingInviteeIds
 *
 * Legacy / derived fields (memberUids) must NOT be the sole query key.
 */

import { FieldValue, type Firestore } from "firebase-admin/firestore";

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";

export { DELETED_USER_DISPLAY_NAME };

export type EventTeamLifecycleStatus =
  | "forming"
  | "active"
  | "cancelled"
  | "completed"
  | "empty"
  | "archived"
  | "purge_pending"
  | "purged";

export type EventTeamCleanupPlan = {
  teamSetupId: string;
  acceptedUserIds: string[];
  pendingInviteeIds: string[];
  leaderUserId: string;
  status: EventTeamLifecycleStatus;
  invalidateInviteIds: string[];
  empty: boolean;
};

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => asString(v)).filter(Boolean);
}

function requirePathSegment(value: string, field: string): string {
  const segment = value.trim();
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(segment)) {
    throw new Error(`${field} is invalid`);
  }
  return segment;
}

export function planEventTeamMemberRemoval(params: {
  uid: string;
  teamSetupId: string;
  data: Record<string, unknown>;
  inviteIds?: string[];
}): EventTeamCleanupPlan {
  const uid = requirePathSegment(params.uid, "uid");
  const acceptedUserIds = asStringList(params.data.acceptedUserIds).filter(
    (id) => id !== uid
  );
  const pendingInviteeIds = asStringList(params.data.pendingInviteeIds).filter(
    (id) => id !== uid
  );
  let leaderUserId = asString(params.data.leaderUserId);
  if (leaderUserId === uid) {
    leaderUserId = acceptedUserIds[0] ?? "";
  }
  const empty = acceptedUserIds.length === 0;
  const priorStatus = asString(params.data.status);
  let status: EventTeamLifecycleStatus;
  if (empty) {
    status = "empty";
  } else if (priorStatus === "completed" || priorStatus === "cancelled") {
    status = priorStatus;
  } else if (acceptedUserIds.length >= 3) {
    status = "active";
  } else {
    status = "forming";
  }

  return {
    teamSetupId: params.teamSetupId,
    acceptedUserIds,
    pendingInviteeIds,
    leaderUserId,
    status: empty ? "purge_pending" : status,
    invalidateInviteIds: params.inviteIds ?? [],
    empty,
  };
}

export function buildEventTeamCleanupPatch(
  plan: EventTeamCleanupPlan
): Record<string, unknown> {
  const patch: Record<string, unknown> = {
    acceptedUserIds: plan.acceptedUserIds,
    pendingInviteeIds: plan.pendingInviteeIds,
    leaderUserId: plan.leaderUserId,
    memberUids: plan.acceptedUserIds,
    memberCount: plan.acceptedUserIds.length,
    status: plan.status,
    updatedAt: FieldValue.serverTimestamp(),
  };
  if (plan.empty) {
    patch.lifecycleStatus = "purge_pending";
    patch.purgeAfter = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    patch.emptyReason = "account_deletion_last_member";
  }
  return patch;
}

export async function loadEventTeamSetupIdsForUser(
  firestore: Firestore,
  uid: string
): Promise<string[]> {
  const safeUid = requirePathSegment(uid, "uid");
  const [byAccepted, byLeader, byPending] = await Promise.all([
    firestore
      .collection("eventTeamSetups")
      .where("acceptedUserIds", "array-contains", safeUid)
      .get(),
    firestore
      .collection("eventTeamSetups")
      .where("leaderUserId", "==", safeUid)
      .get(),
    firestore
      .collection("eventTeamSetups")
      .where("pendingInviteeIds", "array-contains", safeUid)
      .get(),
  ]);
  return [
    ...new Set([
      ...byAccepted.docs.map((d) => d.id),
      ...byLeader.docs.map((d) => d.id),
      ...byPending.docs.map((d) => d.id),
    ]),
  ];
}

export async function loadEventTeamInviteIdsForUser(
  firestore: Firestore,
  uid: string
): Promise<string[]> {
  const safeUid = requirePathSegment(uid, "uid");
  const [asInviter, asInvitee] = await Promise.all([
    firestore
      .collection("eventTeamInvites")
      .where("inviterUserId", "==", safeUid)
      .get(),
    firestore
      .collection("eventTeamInvites")
      .where("inviteeUserId", "==", safeUid)
      .get(),
  ]);
  return [
    ...new Set([
      ...asInviter.docs.map((d) => d.id),
      ...asInvitee.docs.map((d) => d.id),
    ]),
  ];
}

export async function applyEventTeamMemberRemoval(
  firestore: Firestore,
  uid: string,
  teamSetupId: string,
  options: { dryRun?: boolean } = {}
): Promise<EventTeamCleanupPlan> {
  const safeUid = requirePathSegment(uid, "uid");
  const safeTeamId = requirePathSegment(teamSetupId, "teamSetupId");
  const ref = firestore.collection("eventTeamSetups").doc(safeTeamId);
  const snap = await ref.get();
  if (!snap.exists) {
    return {
      teamSetupId: safeTeamId,
      acceptedUserIds: [],
      pendingInviteeIds: [],
      leaderUserId: "",
      status: "purged",
      invalidateInviteIds: [],
      empty: true,
    };
  }

  const inviteSnap = await firestore
    .collection("eventTeamInvites")
    .where("teamSetupId", "==", safeTeamId)
    .where("status", "==", "pending")
    .get();
  const relatedInviteIds = inviteSnap.docs
    .filter((doc) => {
      const data = doc.data() ?? {};
      return (
        asString(data.inviterUserId) === safeUid ||
        asString(data.inviteeUserId) === safeUid ||
        // Empty team: invalidate all pending invites
        true
      );
    })
    .map((doc) => doc.id);

  const plan = planEventTeamMemberRemoval({
    uid: safeUid,
    teamSetupId: safeTeamId,
    data: (snap.data() ?? {}) as Record<string, unknown>,
    inviteIds: relatedInviteIds,
  });

  // Only invalidate invites involving the deleted user unless team becomes empty.
  const inviteIdsToInvalidate = plan.empty
    ? relatedInviteIds
    : inviteSnap.docs
        .filter((doc) => {
          const data = doc.data() ?? {};
          return (
            asString(data.inviterUserId) === safeUid ||
            asString(data.inviteeUserId) === safeUid
          );
        })
        .map((doc) => doc.id);
  plan.invalidateInviteIds = inviteIdsToInvalidate;

  if (options.dryRun) return plan;

  await firestore.runTransaction(async (tx) => {
    const fresh = await tx.get(ref);
    if (!fresh.exists) return;
    const freshPlan = planEventTeamMemberRemoval({
      uid: safeUid,
      teamSetupId: safeTeamId,
      data: (fresh.data() ?? {}) as Record<string, unknown>,
      inviteIds: inviteIdsToInvalidate,
    });
    freshPlan.invalidateInviteIds = inviteIdsToInvalidate;
    const patch = buildEventTeamCleanupPatch(freshPlan);
    // Scrub deleted user snapshot entries if present.
    const membersSnapshot = Array.isArray(fresh.data()?.membersSnapshot)
      ? (fresh.data()?.membersSnapshot as unknown[])
          .map((item) => {
            if (!item || typeof item !== "object") return item;
            const row = item as Record<string, unknown>;
            if (asString(row.uid) !== safeUid && asString(row.userId) !== safeUid) {
              return item;
            }
            return {
              ...row,
              displayName: DELETED_USER_DISPLAY_NAME,
              nickname: DELETED_USER_DISPLAY_NAME,
              avatarUrl: null,
              photoUrl: null,
            };
          })
          .filter((item) => {
            if (!item || typeof item !== "object") return true;
            const row = item as Record<string, unknown>;
            // Drop snapshot entirely when team empty; otherwise keep anonymized row removed
            return (
              asString(row.uid) !== safeUid && asString(row.userId) !== safeUid
            );
          })
      : undefined;
    if (membersSnapshot) {
      patch.membersSnapshot = membersSnapshot;
    }
    tx.set(ref, patch, { merge: true });
    for (const inviteId of inviteIdsToInvalidate) {
      tx.set(
        firestore.collection("eventTeamInvites").doc(inviteId),
        {
          status: "cancelled",
          cancelledReason: "account_deletion",
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    }
  });

  return plan;
}

export function shouldPurgeEmptyEventTeam(doc: {
  status?: unknown;
  lifecycleStatus?: unknown;
  legalHold?: unknown;
  purgeAfter?: { toDate?: () => Date } | Date | string | null;
  now?: Date;
}): boolean {
  if (doc.legalHold === true) return false;
  const status = asString(doc.status);
  const lifecycle = asString(doc.lifecycleStatus);
  if (status !== "empty" && status !== "purge_pending" && lifecycle !== "purge_pending") {
    return false;
  }
  const now = doc.now ?? new Date();
  const raw = doc.purgeAfter;
  let purgeAfter: Date | null = null;
  if (raw instanceof Date) purgeAfter = raw;
  else if (raw && typeof raw === "object" && typeof raw.toDate === "function") {
    purgeAfter = raw.toDate();
  } else if (typeof raw === "string" && raw.trim()) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) purgeAfter = parsed;
  }
  if (!purgeAfter) return false;
  return purgeAfter.getTime() <= now.getTime();
}

export async function purgeEmptyEventTeams(
  firestore: Firestore,
  options: { limit?: number; now?: Date; dryRun?: boolean } = {}
): Promise<{ scanned: number; purged: number }> {
  const limit = options.limit ?? 100;
  const now = options.now ?? new Date();
  const snap = await firestore
    .collection("eventTeamSetups")
    .where("status", "in", ["empty", "purge_pending"])
    .limit(limit)
    .get();
  const candidates = snap.docs.filter((doc) =>
    shouldPurgeEmptyEventTeam({
      status: doc.data()?.status,
      lifecycleStatus: doc.data()?.lifecycleStatus,
      legalHold: doc.data()?.legalHold,
      purgeAfter: doc.data()?.purgeAfter ?? null,
      now,
    })
  );
  if (!options.dryRun) {
    for (const doc of candidates) {
      await doc.ref.set(
        {
          status: "purged",
          lifecycleStatus: "purged",
          acceptedUserIds: [],
          pendingInviteeIds: [],
          leaderUserId: "",
          memberUids: [],
          memberCount: 0,
          membersSnapshot: [],
          purgedAt: FieldValue.serverTimestamp(),
          purgedReason: "empty_team_ttl",
        },
        { merge: true }
      );
    }
  }
  return { scanned: snap.size, purged: candidates.length };
}
