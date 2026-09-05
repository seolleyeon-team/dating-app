import {
  FieldValue,
  type DocumentSnapshot,
  type Firestore,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

import { nextAcceptedUserIds } from "./eventTeamInviteAcceptPolicy";
import {
  readFriendUserEligibility,
  type FriendInviteParticipant,
} from "./friendInvites";

// =============================================================================
// 3:3 event team membership — the ONLY place membership is committed.
//
// respondEventTeamInvite is the authority that turns a pending
// eventTeamInvites record into team membership. It is reached from two
// sources with identical semantics: an in-app invitation created by the
// leader (createEventTeamInvite) and a share-link redemption
// (redeemEventTeamShareInvite). Both only create the PENDING record.
//
// Contract enforced here, inside one transaction (all reads before writes):
//   - caller is the invitee (Firebase-authenticated canonical app user)
//   - invite is still pending and listed on the team
//   - leader ↔ invitee are still Seolleyeon friends
//   - no block in either direction (re-checked at commit time, so a block
//     created after the invitation was issued still wins)
//   - capacity is a hard postcondition of the same write
// A denied acceptance releases the pending slot so blocked or stale
// invitations never reduce team capacity.
// =============================================================================

export const EVENT_TEAM_CAPACITY = 3;

export type TeamInviteResponseCode =
  | "not_found"
  | "already_responded"
  | "team_missing"
  | "not_friends"
  | "blocked"
  | "stale_invite"
  | "team_full"
  | "ineligible";

export type TeamInviteResponseResult =
  | { ok: true; status: "accepted" | "declined" }
  | { ok: false; code: TeamInviteResponseCode };

const MESSAGES = {
  notInvitee: "초대를 받은 본인만 응답할 수 있어요.",
  blockedInvite: "초대할 수 없는 사용자예요.",
} as const;

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v)
    ? v.map((item) => asString(item)).filter((item) => item.length > 0)
    : [];
}

/** blocks/{owner}/targets/{target} — the app's single block schema. */
export function blockRef(db: Firestore, ownerUserId: string, targetUserId: string) {
  return db
    .collection("blocks")
    .doc(ownerUserId)
    .collection("targets")
    .doc(targetUserId);
}

export function isBlockedEitherWay(
  forward: DocumentSnapshot,
  reverse: DocumentSnapshot,
): boolean {
  return forward.exists || reverse.exists;
}

/** Non-transactional pre-check used before issuing invitations. */
export async function assertNotBlockedEitherWay(
  db: Firestore,
  userA: string,
  userB: string,
): Promise<void> {
  const [ab, ba] = await Promise.all([
    blockRef(db, userA, userB).get(),
    blockRef(db, userB, userA).get(),
  ]);
  if (isBlockedEitherWay(ab, ba)) {
    throw new HttpsError("failed-precondition", MESSAGES.blockedInvite);
  }
}

export interface RespondTeamInviteParams {
  db: Firestore;
  user: FriendInviteParticipant;
  inviteId: string | null | undefined;
  accept: boolean;
}

export async function respondTeamInviteCore(
  params: RespondTeamInviteParams,
): Promise<TeamInviteResponseResult> {
  const { db, user, accept } = params;
  const inviteId = asString(params.inviteId).trim();
  if (!inviteId) {
    throw new HttpsError("invalid-argument", "inviteId가 필요해요.");
  }
  if (user.data && readFriendUserEligibility(user.data) !== "ok") {
    return { ok: false, code: "ineligible" };
  }

  const inviteRef = db.collection("eventTeamInvites").doc(inviteId);
  const previewSnap = await inviteRef.get();
  if (!previewSnap.exists) {
    return { ok: false, code: "not_found" };
  }
  const preview = (previewSnap.data() ?? {}) as Record<string, unknown>;
  const inviterUserId = asString(preview.inviterUserId);
  const inviteeUserId = asString(preview.inviteeUserId);
  const teamSetupId = asString(preview.teamSetupId);
  if (inviteeUserId !== user.userId) {
    throw new HttpsError("permission-denied", MESSAGES.notInvitee);
  }

  const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
  const friendEdgeRef = db
    .collection("users")
    .doc(inviterUserId)
    .collection("friends")
    .doc(inviteeUserId);
  const inviterBlocksInviteeRef = blockRef(db, inviterUserId, inviteeUserId);
  const inviteeBlocksInviterRef = blockRef(db, inviteeUserId, inviterUserId);

  return await db.runTransaction(async (tx) => {
    // ---- reads (all before the first write) --------------------------------
    const invSnap = await tx.get(inviteRef);
    const teamSnap = await tx.get(teamRef);
    const friendEdgeSnap = await tx.get(friendEdgeRef);
    const forwardBlock = await tx.get(inviterBlocksInviteeRef);
    const reverseBlock = await tx.get(inviteeBlocksInviterRef);

    if (!invSnap.exists) {
      return { ok: false, code: "not_found" };
    }
    const inv = (invSnap.data() ?? {}) as Record<string, unknown>;
    if (asString(inv.inviteeUserId) !== user.userId) {
      throw new HttpsError("permission-denied", MESSAGES.notInvitee);
    }
    if (
      asString(inv.inviterUserId) !== inviterUserId ||
      asString(inv.teamSetupId) !== teamSetupId
    ) {
      return { ok: false, code: "stale_invite" };
    }
    const status = asString(inv.status, "pending");
    if (status !== "pending") {
      return { ok: false, code: "already_responded" };
    }
    if (!teamSnap.exists) {
      return { ok: false, code: "team_missing" };
    }

    const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
    const accepted = asStringArray(team.acceptedUserIds);
    const pending = asStringArray(team.pendingInviteeIds);
    const pendingWithoutMe = pending.filter((id) => id !== user.userId);

    const releaseSlot = (inviteStatus: string, extra: Record<string, unknown> = {}) => {
      tx.update(inviteRef, {
        status: inviteStatus,
        respondedAt: FieldValue.serverTimestamp(),
        ...extra,
      });
      tx.update(teamRef, {
        pendingInviteeIds: pendingWithoutMe,
        updatedAt: FieldValue.serverTimestamp(),
      });
    };

    if (!accept) {
      releaseSlot("declined");
      return { ok: true, status: "declined" };
    }

    // Commit-time re-validation: the world may have changed since the
    // invitation (or the share-link redemption) was created.
    if (isBlockedEitherWay(forwardBlock, reverseBlock)) {
      releaseSlot("cancelled", { cancelReason: "blocked" });
      return { ok: false, code: "blocked" };
    }
    if (!friendEdgeSnap.exists) {
      releaseSlot("cancelled", { cancelReason: "not_friends" });
      return { ok: false, code: "not_friends" };
    }
    if (!pending.includes(user.userId)) {
      tx.update(inviteRef, {
        status: "cancelled",
        cancelReason: "stale_invite",
        respondedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false, code: "stale_invite" };
    }

    const gate = nextAcceptedUserIds({
      acceptedUserIds: accepted,
      inviteeUserId: user.userId,
      capacity: EVENT_TEAM_CAPACITY,
    });
    if (!gate.ok && gate.reason === "already_accepted") {
      releaseSlot("accepted");
      return { ok: true, status: "accepted" };
    }
    if (!gate.ok) {
      releaseSlot("expired");
      return { ok: false, code: "team_full" };
    }

    // Write the exact membership array so capacity is a hard postcondition;
    // concurrent accepts conflict on teamRef and retry.
    tx.update(inviteRef, {
      status: "accepted",
      respondedAt: FieldValue.serverTimestamp(),
    });
    tx.update(teamRef, {
      acceptedUserIds: gate.acceptedUserIds,
      memberCount: gate.memberCount,
      pendingInviteeIds: pendingWithoutMe,
      updatedAt: FieldValue.serverTimestamp(),
    });
    return { ok: true, status: "accepted" };
  });
}
