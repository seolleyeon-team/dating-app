/**
 * SEC-P1-08 phase 2 — social residuals on account_deletion.
 *
 * Policy (dating-app safe):
 * - Owned preference / graph edges → hard delete
 * - Shared 1:1 match/chat → deactivate + scrub display PII (keep ids for other party)
 * - Community posts/comments authored by uid → soft-delete content
 * - Invites → scrub email metadata
 * - Event teams → remove from acceptedUserIds/leader/pending + invite cancel
 * - Chat message authors → anonymize immediately; body retained until TTL purge
 */

import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { anonymizeChatMessagesForDeletedUser } from "./accountDeletionChatLifecycle";
import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";
import {
  applyEventTeamMemberRemoval,
  loadEventTeamInviteIdsForUser,
  loadEventTeamSetupIdsForUser,
} from "./accountDeletionEventTeamCleanup";

export { DELETED_USER_DISPLAY_NAME };

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
  // SEC-04. 비공개 소유권 매핑 문서 자체도 지운다. 남겨두면 계정을 지운 뒤에도
  // uid -> 작성글 연결이 그대로 남는다.
  bambooPostMappingIds: string[];
  bambooCommentMappingIds: string[];
  friendInviteIds: string[];
  eventTeamSetupIds: string[];
  eventTeamInviteIds: string[];
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
  bambooOwnershipMappingsDeleted: number;
  friendInvitesScrubbed: number;
  eventTeamMembershipsRemoved: number;
  eventTeamInvitesCancelled: number;
  chatMessagesAnonymized: number;
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
  | {
      kind: "deleteBambooOwnershipMapping";
      collection: "bamboo_post_authors" | "bamboo_comment_authors";
      id: string;
    }
  | { kind: "scrubFriendInvite"; id: string }
  | { kind: "removeEventTeamMember"; id: string }
  | { kind: "cancelEventTeamInvite"; id: string }
  | { kind: "anonymizeChatMessages"; id: string };

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
    bambooPostMappingIds: [],
    bambooCommentMappingIds: [],
    friendInviteIds: [],
    eventTeamSetupIds: [],
    eventTeamInviteIds: [],
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
    bambooOwnershipMappingsDeleted: 0,
    friendInvitesScrubbed: 0,
    eventTeamMembershipsRemoved: 0,
    eventTeamInvitesCancelled: 0,
    chatMessagesAnonymized: 0,
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
    bambooOwnershipMappingsDeleted:
      docs.bambooPostMappingIds.length + docs.bambooCommentMappingIds.length,
    friendInvitesScrubbed: docs.friendInviteIds.length,
    eventTeamMembershipsRemoved: docs.eventTeamSetupIds.length,
    eventTeamInvitesCancelled: docs.eventTeamInviteIds.length,
    chatMessagesAnonymized: 0,
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
    operations.push({ kind: "anonymizeChatMessages", id });
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
  // 매핑은 내용 정리가 끝난 다음에 지운다. 먼저 지우면 중간에 실패했을 때
  // 어떤 글이 이 사용자 것이었는지 다시 찾을 방법이 사라진다.
  for (const id of docs.bambooPostMappingIds) {
    operations.push({
      kind: "deleteBambooOwnershipMapping",
      collection: "bamboo_post_authors",
      id,
    });
  }
  for (const id of docs.bambooCommentMappingIds) {
    operations.push({
      kind: "deleteBambooOwnershipMapping",
      collection: "bamboo_comment_authors",
      id,
    });
  }
  for (const id of docs.friendInviteIds) {
    operations.push({ kind: "scrubFriendInvite", id });
  }
  for (const id of docs.eventTeamSetupIds) {
    operations.push({ kind: "removeEventTeamMember", id });
  }
  for (const id of docs.eventTeamInviteIds) {
    operations.push({ kind: "cancelEventTeamInvite", id });
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
    bambooPostMapSnap,
    bambooCommentMapSnap,
    invitesSnap,
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
    // SEC-04 전환기. 새 글은 비공개 매핑에도 소유자가 적히고, 이관 전 글은
    // public authorId 에만 있다. 어느 쪽으로 들어왔든 빠뜨리면 안 되므로
    // 두 경로를 모두 읽어 합집합으로 처리한다. public authorId 를 제거하는
    // 단계가 끝나면 위의 legacy 스캔만 걷어내면 된다.
    firestore
      .collection("bamboo_post_authors")
      .where("ownerUid", "==", safeUid)
      .get(),
    firestore
      .collection("bamboo_comment_authors")
      .where("ownerUid", "==", safeUid)
      .get(),
    queryIds(firestore, "friendInvites", "inviterUserId", safeUid),
  ]);

  const [eventTeamSetupIds, eventTeamInviteIds] = await Promise.all([
    loadEventTeamSetupIdsForUser(firestore, safeUid),
    loadEventTeamInviteIdsForUser(firestore, safeUid),
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
  const seenComments = new Set<string>();
  const pushComment = (postId: string, commentId: string) => {
    if (!postId || !commentId) return;
    const key = `${postId}/${commentId}`;
    if (seenComments.has(key)) return;
    seenComments.add(key);
    bambooComments.push({ postId, commentId });
  };
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
    pushComment(postId, commentId);
  }

  const bambooPostMappingIds: string[] = [];
  for (const doc of bambooPostMapSnap.docs) {
    const postId = asString(doc.data()?.postId) || asString(doc.id);
    if (!postId) continue;
    bambooPostMappingIds.push(doc.id);
  }

  const bambooCommentMappingIds: string[] = [];
  for (const doc of bambooCommentMapSnap.docs) {
    const data = doc.data() ?? {};
    const postId = asString(data.postId);
    const commentId = asString(data.commentId);
    // 매핑 본문이 깨져 있으면 어느 댓글인지 알 수 없다. 그래도 매핑 문서
    // 자체는 uid 를 담고 있으니 삭제 대상에는 넣는다.
    pushComment(postId, commentId);
    bambooCommentMappingIds.push(doc.id);
  }

  return {
    interactionIds: [...new Set([...interactionsFrom, ...interactionsTo])],
    askIds: [...new Set([...asksFrom, ...asksTo])],
    friendshipIds,
    friendOtherUids,
    matchIds: matchesSnap.docs.map((doc) => doc.id),
    chatRoomIds: roomsSnap.docs.map((doc) => doc.id),
    recEventIds: recEventsSnap.docs.map((doc) => doc.id),
    bambooPostIds: [
      ...new Set([
        ...bambooSnap,
        ...bambooPostMapSnap.docs.map((doc) => doc.id),
      ]),
    ],
    bambooComments,
    bambooPostMappingIds,
    bambooCommentMappingIds,
    friendInviteIds: invitesSnap,
    eventTeamSetupIds,
    eventTeamInviteIds,
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
      const ownEdgeRef = firestore
        .collection("users")
        .doc(safeUid)
        .collection("friends")
        .doc(other);
      const otherUserRef = firestore.collection("users").doc(other);
      const otherEdgeRef = otherUserRef.collection("friends").doc(safeUid);
      // The surviving friend's denormalised users.friendsCount must follow
      // their users/{uid}/friends edges (it is incremented together with
      // the edge in friendInvites.ts). Decrement it exactly once, in the
      // same transaction that removes the edge, and never below zero.
      await firestore.runTransaction(async (transaction) => {
        const otherEdgeSnap = await transaction.get(otherEdgeRef);
        const otherUserSnap = await transaction.get(otherUserRef);
        transaction.delete(ownEdgeRef);
        if (!otherEdgeSnap.exists) return;
        transaction.delete(otherEdgeRef);
        if (!otherUserSnap.exists) return;
        const current = otherUserSnap.get("friendsCount");
        const next =
          typeof current === "number" && Number.isFinite(current) && current > 0
            ? current - 1
            : 0;
        transaction.set(
          otherUserRef,
          { friendsCount: next, updatedAt: now },
          { merge: true }
        );
      });
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
    case "deleteBambooOwnershipMapping": {
      // 이미 없으면 delete 는 조용히 성공한다 — 재시도해도 안전하다.
      const id = requirePathSegment(operation.id, "mappingId");
      await firestore.collection(operation.collection).doc(id).delete();
      return;
    }
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
      await applyEventTeamMemberRemoval(firestore, safeUid, operation.id);
      return;
    }
    case "cancelEventTeamInvite": {
      await firestore.collection("eventTeamInvites").doc(operation.id).set(
        {
          status: "cancelled",
          cancelledReason: "account_deletion",
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    }
    case "anonymizeChatMessages": {
      await anonymizeChatMessagesForDeletedUser(firestore, {
        uid: safeUid,
        roomId: operation.id,
      });
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
  let chatMessagesAnonymized = 0;
  for (const operation of operations) {
    if (operation.kind === "anonymizeChatMessages") {
      const result = await anonymizeChatMessagesForDeletedUser(firestore, {
        uid,
        roomId: operation.id,
      });
      chatMessagesAnonymized += result.anonymized;
      continue;
    }
    await applySocialCleanupOperation(firestore, uid, operation);
  }
  return {
    ...socialCountsFromDocs(docs),
    chatMessagesAnonymized,
  };
}
