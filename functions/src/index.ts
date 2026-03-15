/**
 * 설레연 Cloud Functions
 *
 * 트리거 목록:
 *   1) onRecEventCreated        — recEvents 이벤트 로깅 + 매치 체크
 *   2) onInteractionCreated     — interactions like/super_like → 매치 생성 + 채팅방
 *   3) onChatMessageCreated     — 새 채팅 메시지 푸시 알림
 *   4) onBambooCommentCreated   — 대나무숲 댓글/답글 푸시 알림
 *   5) onMatchUpdated           — 매치 해제 시 채팅방 비활성화
 */

import { setGlobalOptions } from "firebase-functions/v2";
import { onDocumentCreated, onDocumentUpdated } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";
import { initializeApp } from "firebase-admin/app";
import { getFirestore, FieldValue } from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";

// Firebase Admin 초기화
initializeApp();
const db = getFirestore();

// 전역 옵션
setGlobalOptions({
  region: "asia-northeast3",
  maxInstances: 10,
});

// =============================================================================
// 공통 헬퍼
// =============================================================================
function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asNonEmptyString(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.trim();
  return s.length > 0 ? s : null;
}

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (v == null) return fallback;
  // Firestore Timestamp/objects/etc → 안전하게 기본값
  return fallback;
}

function asStringOrNull(v: unknown): string | null {
  const s = asString(v, "").trim();
  return s.length > 0 ? s : null;
}

function buildDirectRoomId(userA: string, userB: string): string {
  const ids = [userA, userB].sort();
  return `dm_${ids[0]}_${ids[1]}`;
}

async function getUserDisplayInfo(userId: string): Promise<{
  nickname: string;
  avatarUrl: string | null;
}> {
  const snap = await db.collection("users").doc(userId).get();
  const data = (snap.data() ?? {}) as Record<string, unknown>;
  const onboardingRaw = data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};

  const nickname = asString(
    onboarding.nickname ?? data.nickname ?? "유저",
    "유저"
  );

  const avatarUrl =
    asStringOrNull(
      onboarding.profileImageUrl ??
        onboarding.representativeImageUrl ??
        data.profileImageUrl
    ) ?? null;

  return {
    nickname,
    avatarUrl,
  };
}

async function fetchUserTokens(userId: string): Promise<string[]> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("deviceTokens")
    .get();

  return snap.docs.map((d) => d.id).filter((t) => t.length > 0);
}

async function sendPushToUsers(
  userIds: string[],
  payload: {
    title: string;
    body: string;
    data: Record<string, string>;
  }
): Promise<void> {
  const uniqueUserIds = [...new Set(userIds.filter((u) => u.length > 0))];
  if (uniqueUserIds.length === 0) return;

  const tokenLists = await Promise.all(uniqueUserIds.map(fetchUserTokens));
  const tokens = tokenLists.flat().filter(Boolean);

  if (tokens.length === 0) {
    logger.info("No device tokens found for users", { userIds: uniqueUserIds });
    return;
  }

  const response = await getMessaging().sendEachForMulticast({
    tokens,
    notification: {
      title: payload.title,
      body: payload.body,
    },
    data: payload.data,
    android: {
      priority: "high",
      notification: {
        channelId: "seolleyeon_high_importance",
      },
    },
    apns: {
      headers: {
        "apns-priority": "10",
      },
      payload: {
        aps: {
          sound: "default",
        },
      },
    },
  });

  const invalidTokens: string[] = [];
  response.responses.forEach((r, i) => {
    if (!r.success) {
      const token = tokens[i];
      if (token) invalidTokens.push(token);
      logger.warn("Push send failed", {
        token,
        error: r.error?.message,
      });
    }
  });

  if (invalidTokens.length > 0) {
    for (const uid of uniqueUserIds) {
      const batch = db.batch();
      for (const token of invalidTokens) {
        batch.delete(
          db.collection("users").doc(uid).collection("deviceTokens").doc(token)
        );
      }
      await batch.commit();
    }
  }
}

// =============================================================================
// 1) recEvents onCreate 트리거
//    rules 기준: recEvents/{userId}/events/{eventId}
// =============================================================================
export const onRecEventCreated = onDocumentCreated(
  "recEvents/{userId}/events/{eventId}",
  async (event) => {
    const snap = event.data;
    if (!snap) {
      logger.warn("No data in recEvent document");
      return;
    }

    const data = snap.data();
    const userId = asString(data.userId ?? event.params.userId ?? "");
    const targetUserId = asString(data.targetUserId ?? "");
    const eventType = asString(data.eventType ?? "");
    const source = asString(data.source ?? "");

    logger.info("recEvent created", {
      eventId: event.params.eventId,
      userId,
      targetUserId,
      eventType,
      source,
    });

    if (!userId || !targetUserId) return;

    if (eventType === "like" || eventType === "swipe_right") {
      await checkAndCreateRecMatch(userId, targetUserId, eventType);
    }
  }
);

// =============================================================================
// 2) interactions 기반 매치 판정 + 채팅방 생성
// =============================================================================
export const onInteractionCreated = onDocumentCreated(
  "interactions/{interactionId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const data = snap.data();
    const fromUserId = asString(data.fromUserId ?? "");
    const toUserId = asString(data.toUserId ?? "");
    const action = asString(data.action ?? "");

    if (!fromUserId || !toUserId) return;
    if (action !== "like" && action !== "super_like") return;

    // 상대방도 나를 like/super_like 했는지 확인
    const reverseQuery = await db
      .collection("interactions")
      .where("fromUserId", "==", toUserId)
      .where("toUserId", "==", fromUserId)
      .where("action", "in", ["like", "super_like"])
      .limit(1)
      .get();

    if (reverseQuery.empty) return;

    // 이미 매치 존재 여부 확인
    const existingMatches = await db
      .collection("matches")
      .where("userIds", "array-contains", fromUserId)
      .get();

    for (const doc of existingMatches.docs) {
      const ids = (doc.data().userIds || []) as string[];
      if (ids.includes(toUserId)) {
        logger.info("Match already exists", { matchId: doc.id });
        return;
      }
    }

    const roomId = buildDirectRoomId(fromUserId, toUserId);
    const matchRef = db.collection("matches").doc();
    const roomRef = db.collection("chat_rooms").doc(roomId);

    const [userA, userB] = await Promise.all([
      getUserDisplayInfo(fromUserId),
      getUserDisplayInfo(toUserId),
    ]);

    const participantInfo = {
      [fromUserId]: {
        nickname: userA.nickname,
        avatarUrl: userA.avatarUrl,
      },
      [toUserId]: {
        nickname: userB.nickname,
        avatarUrl: userB.avatarUrl,
      },
    };

    const batch = db.batch();

    batch.set(matchRef, {
      userIds: [fromUserId, toUserId],
      matchType: "mutual_like",
      matchedAt: FieldValue.serverTimestamp(),
      status: "active",
      chatRoomId: roomId,
    });

    batch.set(roomRef, {
      roomId,
      type: "one_to_one",
      status: "active",
      participantIds: [fromUserId, toUserId],
      participantInfo,
      matchId: matchRef.id,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
      lastMessage: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
      lastMessageAt: FieldValue.serverTimestamp(),
    }, { merge: true });

    const msgRef = roomRef.collection("messages").doc();
    batch.set(msgRef, {
      senderId: "system",
      text: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
      content: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
      type: "system",
      createdAt: FieldValue.serverTimestamp(),
      readBy: [],
    });

    await batch.commit();

    logger.info("Match created", {
      matchId: matchRef.id,
      roomId,
      fromUserId,
      toUserId,
    });
  }
);

// =============================================================================
// 3) 새 채팅 메시지 → 푸시 알림
// =============================================================================
export const onChatMessageCreated = onDocumentCreated(
  "chat_rooms/{roomId}/messages/{messageId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const roomId = event.params.roomId;
    const message = snap.data();

    const senderId = asString(message.senderId ?? "");
    if (!senderId || senderId === "system") return;

    const roomSnap = await db.collection("chat_rooms").doc(roomId).get();
    if (!roomSnap.exists) return;

    const room = (roomSnap.data() ?? {}) as Record<string, unknown>;
    const participantIdsRaw = room.participantIds;
    const participantIds = Array.isArray(participantIdsRaw)
      ? participantIdsRaw.map((v) => asString(v)).filter((v) => v.length > 0)
      : [];
    const targetUserIds = participantIds.filter((id) => id !== senderId);

    if (targetUserIds.length === 0) return;

    const participantInfoRaw = room.participantInfo;
    const participantInfo = isRecord(participantInfoRaw) ? participantInfoRaw : {};
    const senderInfo = participantInfo[senderId];
    const senderName = asString(
      isRecord(senderInfo) ? senderInfo.nickname : undefined,
      "새 메시지"
    );

    const body = asString(message.text ?? message.content ?? "메시지가 도착했어요.")
      .trim();

    await sendPushToUsers(targetUserIds, {
      title: senderName,
      body: body || "메시지가 도착했어요.",
      data: {
        type: "chat",
        roomId,
      },
    });

    logger.info("Chat push sent", {
      roomId,
      senderId,
      targets: targetUserIds,
    });
  }
);

// =============================================================================
// 4) 대나무숲 댓글/답글 푸시 알림
// =============================================================================
export const onBambooCommentCreated = onDocumentCreated(
  "bamboo_posts/{postId}/comments/{commentId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const comment = snap.data();

    const authorId = asString(comment.authorId ?? "");
    const content = asString(comment.content ?? "").trim();
    const parentCommentId = asNonEmptyString(comment.parentCommentId) ?? "";

    if (!authorId) return;

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = asString(post.authorId ?? "");

    // 일반 댓글: 글 작성자에게 알림
    if (!parentCommentId) {
      if (postAuthorId && postAuthorId !== authorId) {
        await sendPushToUsers([postAuthorId], {
          title: "내 글에 새 댓글이 달렸어요",
          body: content || "댓글이 도착했어요.",
          data: {
            type: "community_comment",
            postId,
          },
        });

        logger.info("Community comment push sent", {
          postId,
          target: postAuthorId,
          authorId,
        });
      }
      return;
    }

    // 답글: 부모 댓글 작성자에게 알림
    const parentSnap = await db
      .collection("bamboo_posts")
      .doc(postId)
      .collection("comments")
      .doc(parentCommentId)
      .get();

    if (!parentSnap.exists) return;

    const parent = (parentSnap.data() ?? {}) as Record<string, unknown>;
    const parentAuthorId = asString(parent.authorId ?? "");

    const targets = [parentAuthorId].filter((uid) => uid && uid !== authorId);

    if (targets.length > 0) {
      await sendPushToUsers(targets, {
        title: "내 댓글에 답글이 달렸어요",
        body: content || "답글이 도착했어요.",
        data: {
          type: "community_reply",
          postId,
        },
      });

      logger.info("Community reply push sent", {
        postId,
        parentCommentId,
        targets,
        authorId,
      });
    }
  }
);

// =============================================================================
// 5) 매치 해제 시 채팅방 비활성화
// =============================================================================
export const onMatchUpdated = onDocumentUpdated(
  "matches/{matchId}",
  async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();

    if (!before || !after) return;

    if (before.status === "active" && after.status === "unmatched") {
      const chatRoomId = asString((after as Record<string, unknown>).chatRoomId ?? "");
      if (!chatRoomId) return;

      await db.collection("chat_rooms").doc(chatRoomId).set({
        status: "closed",
        closedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });

      await db
        .collection("chat_rooms")
        .doc(chatRoomId)
        .collection("messages")
        .add({
          senderId: "system",
          text: "매칭이 해제되었습니다.",
          content: "매칭이 해제되었습니다.",
          type: "system",
          readBy: [],
          createdAt: FieldValue.serverTimestamp(),
        });

      logger.info("Match closed and chat room updated", {
        matchId: event.params.matchId,
        chatRoomId,
      });
    }
  }
);

// =============================================================================
// recEvents 기반 매치 체크 헬퍼
// =============================================================================
async function checkAndCreateRecMatch(
  userA: string,
  userB: string,
  matchType: string
): Promise<string | null> {
  const reverseQuery = await db
    .collectionGroup("events")
    .where("userId", "==", userB)
    .where("targetUserId", "==", userA)
    .where("eventType", "in", ["like", "swipe_right"])
    .limit(1)
    .get();

  if (reverseQuery.empty) {
    logger.info("No mutual like found", { userA, userB });
    return null;
  }

  const existingMatches = await db
    .collection("matches")
    .where("userIds", "array-contains", userA)
    .get();

  for (const doc of existingMatches.docs) {
    const raw = (doc.data() as Record<string, unknown>).userIds;
    const ids = Array.isArray(raw)
      ? raw.map((v) => asString(v)).filter((v) => v.length > 0)
      : [];
    if (ids.includes(userB)) {
      logger.info("Match already exists", { matchId: doc.id });
      return doc.id;
    }
  }

  const matchRef = await db.collection("matches").add({
    userIds: [userA, userB],
    matchType,
    matchedAt: FieldValue.serverTimestamp(),
    status: "active",
    chatRoomId: null,
  });

  logger.info("Rec match created", {
    matchId: matchRef.id,
    userA,
    userB,
    matchType,
  });

  return matchRef.id;
}