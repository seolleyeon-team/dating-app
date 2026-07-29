/**
 * SEC-P1-08 phase 2 — social residuals on account_deletion.
 *
 * Policy (dating-app safe):
 * - Owned preference / graph edges → hard delete
 * - Shared 1:1 match/chat → deactivate + scrub display PII (keep ids for other party)
 * - Community posts/comments authored by uid → soft-delete content
 * - Invites → scrub email metadata
 * - Event teams → remove uid from memberUids only
 *
 * Message history is intentionally retained (other-party UX / dispute).
 */

import { FieldValue, type Firestore } from "firebase-admin/firestore";

export const DELETED_USER_DISPLAY_NAME = "탈퇴한 사용자";

export type AccountDeletionSocialDocs = {
  interactionIds: string[];
  askIds: string[];
  friendshipIds: string[];
  friendOtherUids: string[];
  matchIds: string[];
  chatRoomIds: string[];
  recEventIds: string[];
  bambooPostIds: string[];
  bambooComments: Array<{ postId: string; commentId: string }>;
  friendInviteIds: string[];
  eventTeamSetupIds: string[];
};

export type AccountDeletionSocialCounts = {
  interactionsDeleted: number;
  asksDeleted: number;
  friendshipsDeleted: number;
  friendEdgesDeleted: number;
  matchesEnded: number;
  chatRoomsClosed: number;
  recEventsDeleted: number;
  bambooPostsSoftDeleted: number;
  bambooCommentsSoftDeleted: number;
  friendInvitesScrubbed: number;
  eventTeamMembershipsRemoved: number;
};

export type SocialCleanupOperation =
  | { kind: "deleteInteraction"; id: string }
  | { kind: "deleteAsk"; id: string }
  | { kind: "deleteFriendship"; id: string }
  | { kind: "deleteFriendEdge"; otherUid: string }
  | { kind: "endMatch"; id: string }
  | { kind: "closeChatRoom"; id: string }
  | { kind: "deleteRecEvent"; id: string }
  | { kind: "deleteRecEventsParent" }
  | { kind: "softDeleteBambooPost"; id: string }
  | { kind: "softDeleteBambooComment"; postId: string; commentId: string }
  | { kind: "scrubFriendInvite"; id: string }
  | { kind: "removeEventTeamMember"; id: string };

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function requirePathSegment(value: string, field: string): string {
  const segment = value.trim();
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(segment)) {
    throw new Error(`${field} is invalid`);
  }
  return segment;
}

export function buildFriendPairId(userA: string, userB: string): string {
  const ids = [userA.trim(), userB.trim()].filter(Boolean).sort();
  if (ids.length !== 2 || ids[0] === ids[1]) {
    throw new Error("friend pair requires two distinct uids");
  }
  // Must match functions/src/index.ts buildFriendPairId.
  return `${ids[0]}_${ids[1]}`;
}

export function emptySocialDocs(): AccountDeletionSocialDocs {
  return {
    interactionIds: [],
    askIds: [],
    friendshipIds: [],
    friendOtherUids: [],
    matchIds: [],
    chatRoomIds: [],
    recEventIds: [],
    bambooPostIds: [],
    bambooComments: [],
    friendInviteIds: [],
    eventTeamSetupIds: [],
  };
}

export function emptySocialCounts(): AccountDeletionSocialCounts {
  return {
    interactionsDeleted: 0,
    asksDeleted: 0,
    friendshipsDeleted: 0,
    friendEdgesDeleted: 0,
    matchesEnded: 0,
    chatRoomsClosed: 0,
    recEventsDeleted: 0,
    bambooPostsSoftDeleted: 0,
    bambooCommentsSoftDeleted: 0,
    friendInvitesScrubbed: 0,
    eventTeamMembershipsRemoved: 0,
  };
}

export function socialCountsFromDocs(
  docs: AccountDeletionSocialDocs
): AccountDeletionSocialCounts {
  return {
    interactionsDeleted: docs.interactionIds.length,
    asksDeleted: docs.askIds.length,
    friendshipsDeleted: docs.friendshipIds.length,
    friendEdgesDeleted: docs.friendOtherUids.length * 2,
    matchesEnded: docs.matchIds.length,
    chatRoomsClosed: docs.chatRoomIds.length,
    recEventsDeleted: docs.recEventIds.length,
    bambooPostsSoftDeleted: docs.bambooPostIds.length,
    bambooCommentsSoftDeleted: docs.bambooComments.length,
    friendInvitesScrubbed: docs.friendInviteIds.length,
    eventTeamMembershipsRemoved: docs.eventTeamSetupIds.length,
  };
}

export function planAccountDeletionSocialOperations(params: {
  uid: string;
  docs: AccountDeletionSocialDocs;
}): SocialCleanupOperation[] {
  const uid = requirePathSegment(params.uid, "uid");
  const docs = params.docs;
  const operations: SocialCleanupOperation[] = [];

  for (const id of docs.interactionIds) {
    operations.push({ kind: "deleteInteraction", id });
  }
  for (const id of docs.askIds) {
    operations.push({ kind: "deleteAsk", id });
  }
  for (const id of docs.friendshipIds) {
    operations.push({ kind: "deleteFriendship", id });
  }
  for (const otherUid of docs.friendOtherUids) {
    if (otherUid === uid) continue;
    operations.push({ kind: "deleteFriendEdge", otherUid });
  }
  for (const id of docs.matchIds) {
    operations.push({ kind: "endMatch", id });
  }
  for (const id of docs.chatRoomIds) {
    operations.push({ kind: "closeChatRoom", id });
  }
  for (const id of docs.recEventIds) {
    operations.push({ kind: "deleteRecEvent", id });
  }
  if (docs.recEventIds.length > 0) {
    operations.push({ kind: "deleteRecEventsParent" });
  }
  for (const id of docs.bambooPostIds) {
    operations.push({ kind: "softDeleteBambooPost", id });
  }
  for (const comment of docs.bambooComments) {
    operations.push({
      kind: "softDeleteBambooComment",
      postId: comment.postId,
      commentId: comment.commentId,
    });
  }
  for (const id of docs.friendInviteIds) {
    operations.push({ kind: "scrubFriendInvite", id });
  }
  for (const id of docs.eventTeamSetupIds) {
    operations.push({ kind: "removeEventTeamMember", id });
  }
  return operations;
}

async function queryIds(
  firestore: Firestore,
  collection: string,
  field: string,
  uid: string
): Promise<string[]> {
  const snap = await firestore
    .collection(collection)
    .where(field, "==", uid)
    .get();
  return snap.docs.map((doc) => doc.id);
}

export async function loadAccountDeletionSocialDocs(
  firestore: Firestore,
  uid: string
): Promise<AccountDeletionSocialDocs> {
  const safeUid = requirePathSegment(uid, "uid");
  const [
    interactionsFrom,
    interactionsTo,
    asksFrom,
    asksTo,
    friendsSnap,
    matchesSnap,
    roomsSnap,
    recEventsSnap,
    bambooSnap,
    bambooCommentsSnap,
    invitesSnap,
    teamsSnap,
  ] = await Promise.all([
    queryIds(firestore, "interactions", "fromUserId", safeUid),
    queryIds(firestore, "interactions", "toUserId", safeUid),
    queryIds(firestore, "asks", "fromUserId", safeUid),
    queryIds(firestore, "asks", "toUserId", safeUid),
    firestore.collection("users").doc(safeUid).collection("friends").get(),
    firestore
      .collection("matches")
      .where("userIds", "array-contains", safeUid)
      .get(),
    firestore
      .collection("chat_rooms")
      .where("participantIds", "array-contains", safeUid)
      .get(),
    firestore.collection("recEvents").doc(safeUid).collection("events").get(),
    queryIds(firestore, "bamboo_posts", "authorId", safeUid),
    firestore
      .collectionGroup("comments")
      .where("authorId", "==", safeUid)
      .get(),
    queryIds(firestore, "friendInvites", "inviterUserId", safeUid),
    firestore
      .collection("eventTeamSetups")
      .where("memberUids", "array-contains", safeUid)
      .get(),
  ]);

  const friendOtherUids = friendsSnap.docs.map((doc) => doc.id);
  const friendshipIds = [
    ...new Set(
      friendOtherUids
        .filter((other) => other && other !== safeUid)
        .map((other) => buildFriendPairId(safeUid, other))
    ),
  ];

  const bambooComments: Array<{ postId: string; commentId: string }> = [];
  for (const doc of bambooCommentsSnap.docs) {
    // Expected path: bamboo_posts/{postId}/comments/{commentId}
    const parts = doc.ref.path.split("/");
    if (
      parts.length !== 4 ||
      parts[0] !== "bamboo_posts" ||
      parts[2] !== "comments"
    ) {
      continue;
    }
    const postId = asString(parts[1]);
    const commentId = asString(parts[3]);
    if (!postId || !commentId) continue;
    if (doc.data()?.isDeleted === true) continue;
    bambooComments.push({ postId, commentId });
  }

  return {
    interactionIds: [...new Set([...interactionsFrom, ...interactionsTo])],
    askIds: [...new Set([...asksFrom, ...asksTo])],
    friendshipIds,
    friendOtherUids,
    matchIds: matchesSnap.docs.map((doc) => doc.id),
    chatRoomIds: roomsSnap.docs.map((doc) => doc.id),
    recEventIds: recEventsSnap.docs.map((doc) => doc.id),
    bambooPostIds: bambooSnap,
    bambooComments,
    friendInviteIds: invitesSnap,
    eventTeamSetupIds: teamsSnap.docs.map((doc) => doc.id),
  };
}

export async function applySocialCleanupOperation(
  firestore: Firestore,
  uid: string,
  operation: SocialCleanupOperation
): Promise<void> {
  const safeUid = requirePathSegment(uid, "uid");
  const now = FieldValue.serverTimestamp();

  switch (operation.kind) {
    case "deleteInteraction":
      await firestore.collection("interactions").doc(operation.id).delete();
      return;
    case "deleteAsk":
      await firestore.collection("asks").doc(operation.id).delete();
      return;
    case "deleteFriendship":
      await firestore.collection("friendships").doc(operation.id).delete();
      return;
    case "deleteFriendEdge": {
      const other = requirePathSegment(operation.otherUid, "otherUid");
      await Promise.all([
        firestore
          .collection("users")
          .doc(safeUid)
          .collection("friends")
          .doc(other)
          .delete(),
        firestore
          .collection("users")
          .doc(other)
          .collection("friends")
          .doc(safeUid)
          .delete(),
      ]);
      return;
    }
    case "endMatch":
      await firestore.collection("matches").doc(operation.id).set(
        {
          status: "ended",
          endedReason: "account_deletion",
          endedAt: now,
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    case "closeChatRoom":
      await firestore
        .collection("chat_rooms")
        .doc(operation.id)
        .set(
          {
            status: "closed",
            [`participantInfo.${safeUid}`]: {
              nickname: DELETED_USER_DISPLAY_NAME,
              avatarUrl: null,
            },
            accountDeletedUserIds: FieldValue.arrayUnion(safeUid),
            updatedAt: now,
          },
          { merge: true }
        );
      return;
    case "deleteRecEvent":
      await firestore
        .collection("recEvents")
        .doc(safeUid)
        .collection("events")
        .doc(operation.id)
        .delete();
      return;
    case "deleteRecEventsParent":
      await firestore.collection("recEvents").doc(safeUid).delete();
      return;
    case "softDeleteBambooPost":
      await firestore.collection("bamboo_posts").doc(operation.id).set(
        {
          isDeleted: true,
          content: "[삭제된 게시글]",
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    case "softDeleteBambooComment": {
      const postId = requirePathSegment(operation.postId, "postId");
      const commentId = requirePathSegment(operation.commentId, "commentId");
      const postRef = firestore.collection("bamboo_posts").doc(postId);
      const commentRef = postRef.collection("comments").doc(commentId);
      await firestore.runTransaction(async (tx) => {
        const snap = await tx.get(commentRef);
        if (!snap.exists) return;
        const data = snap.data() ?? {};
        if (data.isDeleted === true) return;
        tx.set(
          commentRef,
          {
            isDeleted: true,
            content: "[삭제된 댓글]",
            updatedAt: now,
          },
          { merge: true }
        );
        tx.set(
          postRef,
          {
            commentCount: FieldValue.increment(-1),
            updatedAt: now,
          },
          { merge: true }
        );
      });
      return;
    }
    case "scrubFriendInvite":
      await firestore.collection("friendInvites").doc(operation.id).set(
        {
          "metadata.inviterEmail": FieldValue.delete(),
          inviterEmail: FieldValue.delete(),
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    case "removeEventTeamMember": {
      const ref = firestore.collection("eventTeamSetups").doc(operation.id);
      const snap = await ref.get();
      if (!snap.exists) return;
      const data = snap.data() ?? {};
      const memberUids = Array.isArray(data.memberUids)
        ? data.memberUids
            .map((v) => asString(v))
            .filter((v) => v && v !== safeUid)
        : [];
      await ref.set(
        {
          memberUids,
          memberCount: memberUids.length,
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    }
  }
}

export async function executeAccountDeletionSocialCleanup(
  firestore: Firestore,
  uid: string
): Promise<AccountDeletionSocialCounts> {
  const docs = await loadAccountDeletionSocialDocs(firestore, uid);
  const operations = planAccountDeletionSocialOperations({ uid, docs });
  for (const operation of operations) {
    await applySocialCleanupOperation(firestore, uid, operation);
  }
  return socialCountsFromDocs(docs);
}
