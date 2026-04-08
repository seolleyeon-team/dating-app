/**
 * 설레연 Cloud Functions
 *
 * 트리거 목록:
 *   1) onRecEventCreated         — recEvents 이벤트 로깅 + 매치 체크
 *   2) onInteractionCreated      — interactions like/super_like → 프로필 좋아요 알림 + 매치 생성 + 채팅방
 *   3) onChatMessageCreated      — 새 채팅 메시지 푸시 알림
 *   4) onBambooCommentCreated    — 대나무숲 댓글/답글 푸시 + 인앱 알림
 *   5) onBambooPostLikeCreated   — 대나무숲 글 좋아요 푸시 + 인앱 알림
 *   6) onAskCreated              — 무물(ask) 생성 시 알림 + 푸시
 *   7) onMatchUpdated            — 매치 해제 시 채팅방 비활성화
 *   8) sendDailyUnreadChatDigests — 매일 오후 1시 unread chat digest 푸시 + 인앱 알림
 */

import { setGlobalOptions } from "firebase-functions/v2";
import {
  onDocumentCreated,
  onDocumentUpdated,
} from "firebase-functions/v2/firestore";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore, FieldValue, Timestamp } from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";
import { createHash, randomBytes } from "crypto";
import { onDocumentWritten } from "firebase-functions/v2/firestore";

// Firebase Admin 초기화
initializeApp();
const db = getFirestore();
const FRIEND_INVITE_HOST = "seolleyeon.web.app";
const FRIEND_INVITE_PATH = "/invite/friend";
const FRIEND_INVITE_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000;

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

function getKstDateKey(now = new Date()): string {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
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

type InAppNotificationPayload = {
  type:
    | "chat_digest"
    | "community_post_like"
    | "community_comment"
    | "community_reply"
    | "profile_like"
    | "ask_received";
  title: string;
  body: string;
  deeplinkType: "chat" | "community_post" | "received_like" | "asks_inbox";
  deeplinkId?: string;
  actorId?: string;
  actorName?: string;
  postId?: string;
  commentId?: string;
  roomId?: string;
  digestDate?: string;
};

async function createInAppNotification(
  userId: string,
  payload: InAppNotificationPayload,
  notificationId?: string
): Promise<boolean> {
  if (!userId) return false;

  const notifRef = notificationId
    ? db
        .collection("users")
        .doc(userId)
        .collection("notifications")
        .doc(notificationId)
    : db
        .collection("users")
        .doc(userId)
        .collection("notifications")
        .doc();

  if (notificationId) {
    const existing = await notifRef.get();
    if (existing.exists) {
      logger.info("Notification already exists, skipping (idempotent)", {
        userId,
        notificationId,
      });
      return false;
    }
  }

  await notifRef.set({
    type: payload.type,
    title: payload.title,
    body: payload.body,
    isRead: false,
    createdAt: FieldValue.serverTimestamp(),

    actorId: payload.actorId ?? null,
    actorName: payload.actorName ?? null,
    postId: payload.postId ?? null,
    commentId: payload.commentId ?? null,
    roomId: payload.roomId ?? null,
    deeplinkType: payload.deeplinkType,
    deeplinkId: payload.deeplinkId ?? null,
    digestDate: payload.digestDate ?? null,
  });

  logger.info("In-app notification created", {
    userId,
    notificationId: notifRef.id,
    type: payload.type,
    deeplinkType: payload.deeplinkType,
    deeplinkId: payload.deeplinkId ?? null,
  });

  return true;
}

async function countPostLikeNotificationsForPost(
  userId: string,
  postId: string
): Promise<number> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("notifications")
    .where("type", "==", "community_post_like")
    .where("postId", "==", postId)
    .get();

  return snap.size;
}

async function hasChatDigestForDate(
  userId: string,
  digestDate: string
): Promise<boolean> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("notifications")
    .where("type", "==", "chat_digest")
    .where("digestDate", "==", digestDate)
    .limit(1)
    .get();

  return !snap.empty;
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

async function getUnreadChatDigestForUser(userId: string): Promise<{
  unreadCount: number;
  previewSenderName: string | null;
}> {
  const roomsSnap = await db
    .collection("chat_rooms")
    .where("participantIds", "array-contains", userId)
    .where("status", "==", "active")
    .get();

  let unreadCount = 0;
  let previewSenderName: string | null = null;

  for (const roomDoc of roomsSnap.docs) {
    const roomData = (roomDoc.data() ?? {}) as Record<string, unknown>;
    const participantInfoRaw = roomData.participantInfo;
    const participantInfo = isRecord(participantInfoRaw)
      ? participantInfoRaw
      : {};

    const messagesSnap = await roomDoc.ref.collection("messages").get();

    for (const msgDoc of messagesSnap.docs) {
      const msg = (msgDoc.data() ?? {}) as Record<string, unknown>;
      const senderId = asString(msg.senderId ?? "");
      if (!senderId || senderId === "system" || senderId === userId) continue;

      const readByRaw = msg.readBy;
      const readBy = Array.isArray(readByRaw)
        ? readByRaw.map((v) => asString(v)).filter((v) => v.length > 0)
        : [];

      if (!readBy.includes(userId)) {
        unreadCount += 1;

        if (!previewSenderName) {
          const senderInfo = participantInfo[senderId];
          previewSenderName = isRecord(senderInfo)
            ? asString(senderInfo.nickname ?? "", "")
            : "";
          if (!previewSenderName) {
            previewSenderName = "누군가";
          }
        }
      }
    }
  }

  return {
    unreadCount,
    previewSenderName,
  };
}

type ResolvedAppUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
  profileSnapshot: Record<string, unknown>;
};

function buildFriendPairId(userA: string, userB: string): string {
  const ids = [userA, userB].sort();
  return `${ids[0]}_${ids[1]}`;
}

function hashInviteToken(rawToken: string): string {
  return createHash("sha256").update(rawToken).digest("hex");
}

function buildFriendInviteUrl(rawToken: string): string {
  const url = new URL(`https://${FRIEND_INVITE_HOST}${FRIEND_INVITE_PATH}`);
  url.searchParams.set("token", rawToken);
  return url.toString();
}

function buildFriendProfileSnapshot(
  userId: string,
  data: Record<string, unknown>
): Record<string, unknown> {
  const onboardingRaw = data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};
  const photoUrlsRaw = onboarding.photoUrls;
  const photoUrls = Array.isArray(photoUrlsRaw)
    ? photoUrlsRaw.map((value) => asString(value)).filter((value) => value)
    : [];

  const profileImageUrl = asStringOrNull(
    onboarding.profileImageUrl ??
      onboarding.representativeImageUrl ??
      (photoUrls.length > 0 ? photoUrls[0] : null) ??
      data.profileImageUrl
  );
  const universityName = asStringOrNull(
    onboarding.university ?? data.universityName
  );
  const major = asStringOrNull(onboarding.major ?? data.major);
  const nickname = asString(
    onboarding.nickname ?? data.nickname ?? userId,
    userId
  );

  return {
    uid: userId,
    nickname,
    profileImageUrl,
    universityName,
    major,
  };
}

async function verifyKakaoAccessToken(
  accessToken: string
): Promise<{ userId: string }> {
  const response = await fetch("https://kapi.kakao.com/v2/user/me", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    logger.warn("Kakao access token verification failed", {
      status: response.status,
    });
    throw new HttpsError(
      "unauthenticated",
      "카카오 로그인 세션을 확인할 수 없어요."
    );
  }

  const data = (await response.json()) as Record<string, unknown>;
  const userId = asString(data.id ?? "").trim();
  if (!userId) {
    throw new HttpsError(
      "unauthenticated",
      "카카오 사용자 정보를 확인할 수 없어요."
    );
  }

  return { userId };
}

function emailFromAuthToken(
  token: Record<string, unknown> | undefined
): string | null {
  if (!token) return null;
  const raw = asNonEmptyString(token.email);
  return raw ? raw.toLowerCase() : null;
}

/**
 * Callable 인증 사용자 → Firestore users 문서.
 * - 커스텀 토큰(UID = 카카오 ID): users/{uid} 직접 조회
 * - 이메일 링크 로그인(UID ≠ 카카오 ID): JWT의 email로 studentEmail 일치 문서 조회
 */
async function resolveAuthedAppUser(
  auth: { uid?: string; token?: Record<string, unknown> } | null | undefined
): Promise<ResolvedAppUser> {
  const authUid = asNonEmptyString(auth?.uid);
  if (!authUid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const token = auth?.token as Record<string, unknown> | undefined;

  let doc = await db.collection("users").doc(authUid).get();

  if (!doc.exists) {
    const email = emailFromAuthToken(token);
    if (email && email.endsWith("@yonsei.ac.kr")) {
      const q = await db
        .collection("users")
        .where("studentEmail", "==", email)
        .limit(1)
        .get();
      if (!q.empty) {
        doc = q.docs[0];
        logger.info(
          "resolveAuthedAppUser: matched user by studentEmail (email-link auth uid differs from kakao doc id)",
          { authUid, resolvedUserId: doc.id }
        );
      }
    }
  }

  if (!doc.exists) {
    throw new HttpsError(
      "failed-precondition",
      "가입 정보를 찾을 수 없어 친구 초대를 처리할 수 없어요."
    );
  }

  const userId = doc.id;
  const data = (doc.data() ?? {}) as Record<string, unknown>;
  const studentEmail = asNonEmptyString(data.studentEmail)?.toLowerCase() ?? "";
  const isStudentVerified = data.isStudentVerified === true;
  if (!isStudentVerified || !studentEmail.endsWith("@yonsei.ac.kr")) {
    throw new HttpsError(
      "failed-precondition",
      "학생 인증이 완료된 계정으로 다시 로그인해주세요."
    );
  }

  return {
    userId,
    email: studentEmail,
    data,
    profileSnapshot: buildFriendProfileSnapshot(userId, data),
  };
}

function getCallableData(request: {
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
}): Record<string, unknown> {
  const direct = request.data;
  if (isRecord(direct)) {
    return direct;
  }

  const rawBody = request.rawRequest?.body;
  if (isRecord(rawBody)) {
    const nested = rawBody.data;
    if (isRecord(nested)) {
      return nested;
    }
    return rawBody;
  }

  return {};
}

/** Firebase Auth 없이 호출될 때: 클라이언트가 검증된 카카오 액세스 토큰을 넘김 */
async function resolveVerifiedUserByKakaoId(
  kakaoUserId: string
): Promise<ResolvedAppUser> {
  const doc = await db.collection("users").doc(kakaoUserId).get();
  if (!doc.exists) {
    throw new HttpsError(
      "failed-precondition",
      "가입 정보를 찾을 수 없어 친구 초대를 처리할 수 없어요."
    );
  }
  const data = (doc.data() ?? {}) as Record<string, unknown>;
  const studentEmail = asNonEmptyString(data.studentEmail)?.toLowerCase() ?? "";
  const isStudentVerified = data.isStudentVerified === true;
  if (!isStudentVerified || !studentEmail.endsWith("@yonsei.ac.kr")) {
    throw new HttpsError(
      "failed-precondition",
      "학생 인증이 완료된 계정으로 다시 로그인해주세요."
    );
  }
  return {
    userId: kakaoUserId,
    email: studentEmail,
    data,
    profileSnapshot: buildFriendProfileSnapshot(kakaoUserId, data),
  };
}

/**
 * 친구 초대 Callable: Firebase 세션(request.auth) 또는 카카오 액세스 토큰으로 본인 확인
 */
async function resolveUserForFriendCallable(request: {
  auth?: { uid?: string; token?: Record<string, unknown> } | null;
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
}): Promise<ResolvedAppUser> {
  if (request.auth?.uid) {
    return await resolveAuthedAppUser(request.auth);
  }
  const data = getCallableData(request);
  const accessToken = asNonEmptyString(data.kakaoAccessToken);
  logger.info("resolveUserForFriendCallable fallback auth", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(data),
    hasKakaoAccessToken: !!accessToken,
  });
  if (!accessToken) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }
  const kakaoUser = await verifyKakaoAccessToken(accessToken);
  return await resolveVerifiedUserByKakaoId(kakaoUser.userId);
}

function readFriendName(
  snapshot: Record<string, unknown>,
  fallback: string
): string {
  return asString(snapshot.nickname ?? fallback, fallback);
}

export const createFirebaseCustomToken = onCall(async (request) => {
  logger.info("createFirebaseCustomToken invoked", {
    hasAccessToken: !!asNonEmptyString(request.data?.accessToken),
  });
  const accessToken = asNonEmptyString(request.data?.accessToken);
  if (!accessToken) {
    throw new HttpsError("invalid-argument", "카카오 액세스 토큰이 필요해요.");
  }

  const kakaoUser = await verifyKakaoAccessToken(accessToken);
  const userRef = db.collection("users").doc(kakaoUser.userId);
  const userSnap = await userRef.get();

  if (!userSnap.exists) {
    throw new HttpsError(
      "failed-precondition",
      "가입 정보를 찾을 수 없어요. 다시 로그인해주세요."
    );
  }

  const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
  const customToken = await getAuth().createCustomToken(kakaoUser.userId, {
    kakaoUserId: kakaoUser.userId,
  });

  return {
    customToken,
    userId: kakaoUser.userId,
    isStudentVerified: userData.isStudentVerified === true,
  };
});

export const createFriendInvite = onCall(async (request) => {
  const requestData = getCallableData(request);
  logger.info("createFriendInvite request", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(requestData),
    hasKakaoAccessToken: !!asNonEmptyString(requestData.kakaoAccessToken),
  });
  const inviter = await resolveUserForFriendCallable(request);
  const inviteRef = db.collection("friendInvites").doc();
  const inviteToken = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + FRIEND_INVITE_EXPIRY_MS);
  const shareChannel = asStringOrNull(requestData.shareChannel) ?? "kakaotalk";

  await inviteRef.set({
    inviterUserId: inviter.userId,
    inviterProfileSnapshot: inviter.profileSnapshot,
    tokenHash: hashInviteToken(inviteToken),
    status: "pending",
    shareChannel,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    expiresAt: Timestamp.fromDate(expiresAt),
    acceptedByUserId: null,
    acceptedAt: null,
    friendshipPairId: null,
    metadata: {
      inviterEmail: inviter.email,
    },
  });

  return {
    inviteId: inviteRef.id,
    inviteToken,
    inviteUrl: buildFriendInviteUrl(inviteToken),
    deepLinkPath: FRIEND_INVITE_PATH,
    expiresAt: expiresAt.toISOString(),
  };
});

export const acceptFriendInvite = onCall(async (request) => {
  const data = getCallableData(request);
  const rawToken = asNonEmptyString(data.token);
  if (!rawToken) {
    return {
      status: "invalid",
      message: "친구 초대 링크가 올바르지 않아요.",
    };
  }

  const acceptor = await resolveUserForFriendCallable(request);
  const tokenHash = hashInviteToken(rawToken);
  const inviteQuery = await db
    .collection("friendInvites")
    .where("tokenHash", "==", tokenHash)
    .limit(1)
    .get();

  if (inviteQuery.empty) {
    return {
      status: "invalid",
      message: "유효하지 않은 친구 초대 링크예요.",
    };
  }

  const inviteRef = inviteQuery.docs[0].ref;
  const inviteId = inviteQuery.docs[0].id;
  const inviteData = (inviteQuery.docs[0].data() ?? {}) as Record<string, unknown>;
  const inviterUserId = asString(inviteData.inviterUserId ?? "");

  if (!inviterUserId) {
    return {
      status: "invalid",
      message: "친구 초대 정보가 올바르지 않아요.",
    };
  }

  if (inviterUserId === acceptor.userId) {
    return {
      status: "self_invite",
      message: "내가 만든 초대 링크로는 친구를 추가할 수 없어요.",
    };
  }

  const inviterSnapshotRaw = inviteData.inviterProfileSnapshot;
  const inviterSnapshot = isRecord(inviterSnapshotRaw)
    ? inviterSnapshotRaw
    : {};
  const otherUserName = readFriendName(inviterSnapshot, inviterUserId);
  const pairId = buildFriendPairId(inviterUserId, acceptor.userId);
  const friendshipRef = db.collection("friendships").doc(pairId);
  const inviterFriendRef = db
    .collection("users")
    .doc(inviterUserId)
    .collection("friends")
    .doc(acceptor.userId);
  const acceptorFriendRef = db
    .collection("users")
    .doc(acceptor.userId)
    .collection("friends")
    .doc(inviterUserId);

  const transactionResult = await db.runTransaction(async (transaction) => {
    const freshInviteSnap = await transaction.get(inviteRef);
    if (!freshInviteSnap.exists) {
      return {
        status: "invalid",
        message: "유효하지 않은 친구 초대 링크예요.",
      };
    }

    const freshInvite = (freshInviteSnap.data() ?? {}) as Record<string, unknown>;
    const currentStatus = asString(freshInvite.status ?? "pending", "pending");
    const acceptedByUserId = asStringOrNull(freshInvite.acceptedByUserId);
    const expiresAtRaw = freshInvite.expiresAt;
    const expiresAt =
      expiresAtRaw instanceof Timestamp ? expiresAtRaw.toDate() : null;
    const now = new Date();
    const existingFriendshipSnap = await transaction.get(friendshipRef);

    if (existingFriendshipSnap.exists) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          {
            status: "accepted",
            updatedAt: FieldValue.serverTimestamp(),
            acceptedByUserId: acceptor.userId,
            acceptedAt: FieldValue.serverTimestamp(),
            friendshipPairId: pairId,
          },
          { merge: true }
        );
      }

      return {
        status: "already_friends",
        pairId,
        otherUserId: inviterUserId,
        otherUserName,
      };
    }

    if (expiresAt && expiresAt.getTime() <= now.getTime()) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          {
            status: "expired",
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }
      return {
        status: "expired",
        message: "친구 초대 링크가 만료되었어요.",
      };
    }

    if (currentStatus !== "pending") {
      if (currentStatus === "accepted" && acceptedByUserId === acceptor.userId) {
        return {
          status: "already_friends",
          pairId,
          otherUserId: inviterUserId,
          otherUserName,
        };
      }

      if (currentStatus === "expired") {
        return {
          status: "expired",
          message: "친구 초대 링크가 만료되었어요.",
        };
      }

      return {
        status: "invalid",
        message: "이미 사용된 친구 초대 링크예요.",
      };
    }

    const sortedUserIds = [inviterUserId, acceptor.userId].sort();
    const inviterUserRef = db.collection("users").doc(inviterUserId);
    const acceptorUserRef = db.collection("users").doc(acceptor.userId);

    transaction.set(friendshipRef, {
      pairId,
      userIds: sortedUserIds,
      createdAt: FieldValue.serverTimestamp(),
      createdFrom: "invite",
      inviteId,
      status: "active",
      createdByUserId: acceptor.userId,
    });

    transaction.set(inviterFriendRef, {
      friendUserId: acceptor.userId,
      pairId,
      createdAt: FieldValue.serverTimestamp(),
      source: "invite",
      friendProfileSnapshot: acceptor.profileSnapshot,
      inviteId,
    });

    transaction.set(acceptorFriendRef, {
      friendUserId: inviterUserId,
      pairId,
      createdAt: FieldValue.serverTimestamp(),
      source: "invite",
      friendProfileSnapshot: inviterSnapshot,
      inviteId,
    });

    transaction.set(
      inviteRef,
      {
        status: "accepted",
        updatedAt: FieldValue.serverTimestamp(),
        acceptedByUserId: acceptor.userId,
        acceptedAt: FieldValue.serverTimestamp(),
        friendshipPairId: pairId,
      },
      { merge: true }
    );

    transaction.set(
      inviterUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    transaction.set(
      acceptorUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    return {
      status: "accepted",
      pairId,
      otherUserId: inviterUserId,
      otherUserName,
    };
  });

  logger.info("Friend invite processed", {
    inviteId,
    inviterUserId,
    acceptorUserId: acceptor.userId,
    pairId,
    status: transactionResult.status,
  });

  return transactionResult;
});

// =============================================================================
// 이벤트 3인 팀 초대 (친구 선택 → 푸시 → 수락 시 팀 반영)
// =============================================================================

async function assertUsersAreFriends(
  userIdA: string,
  userIdB: string
): Promise<boolean> {
  const a = await db
    .collection("users")
    .doc(userIdA)
    .collection("friends")
    .doc(userIdB)
    .get();
  return a.exists;
}

async function writeEventTeamInviteNotification(params: {
  inviteeUserId: string;
  inviterUserId: string;
  inviterName: string;
  inviteId: string;
  teamSetupId: string;
}): Promise<void> {
  const notifId = `event_team_invite_${params.inviteId}`;
  const notifRef = db
    .collection("users")
    .doc(params.inviteeUserId)
    .collection("notifications")
    .doc(notifId);
  const existing = await notifRef.get();
  if (existing.exists) return;

  await notifRef.set({
    type: "event_team_invite",
    title: "팀 초대가 도착했어요",
    body: `${params.inviterName}님이 3인 팀 참여를 요청했어요.`,
    isRead: false,
    createdAt: FieldValue.serverTimestamp(),
    actorId: params.inviterUserId,
    actorName: params.inviterName,
    deeplinkType: "event_team_invite",
    deeplinkId: params.inviteId,
    teamSetupId: params.teamSetupId,
    inviteId: params.inviteId,
  });
}

export const ensureEventTeamSetup = onCall(async (request) => {
  const data = getCallableData(request);
  const leader = await resolveUserForFriendCallable(request);
  let teamSetupId = asNonEmptyString(data.teamSetupId);
  if (!teamSetupId) {
    teamSetupId = randomBytes(16).toString("hex");
  }

  const ref = db.collection("eventTeamSetups").doc(teamSetupId);
  const snap = await ref.get();
  if (!snap.exists) {
    await ref.set({
      leaderUserId: leader.userId,
      acceptedUserIds: [leader.userId],
      pendingInviteeIds: [],
      updatedAt: FieldValue.serverTimestamp(),
      createdAt: FieldValue.serverTimestamp(),
    });
  } else {
    const d = (snap.data() ?? {}) as Record<string, unknown>;
    const lid = asString(d.leaderUserId ?? "");
    if (lid !== leader.userId) {
      throw new HttpsError(
        "permission-denied",
        "이 팀 설정에 접근할 수 없어요."
      );
    }
  }

  return { teamSetupId };
});

export const createEventTeamInvite = onCall(async (request) => {
  const data = getCallableData(request);
  const inviter = await resolveUserForFriendCallable(request);
  const teamSetupId = asNonEmptyString(data.teamSetupId);
  const inviteeUserId = asNonEmptyString(data.inviteeUserId);
  if (!teamSetupId || !inviteeUserId) {
    throw new HttpsError(
      "invalid-argument",
      "teamSetupId와 inviteeUserId가 필요해요."
    );
  }
  if (inviteeUserId === inviter.userId) {
    throw new HttpsError("invalid-argument", "자기 자신은 초대할 수 없어요.");
  }

  const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
  const teamSnap = await teamRef.get();
  if (!teamSnap.exists) {
    throw new HttpsError("not-found", "팀 정보를 찾을 수 없어요.");
  }
  const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
  const leaderUserId = asString(team.leaderUserId ?? "");
  if (leaderUserId !== inviter.userId) {
    throw new HttpsError("permission-denied", "팀 리더만 초대할 수 있어요.");
  }

  const acceptedRaw = team.acceptedUserIds;
  const acceptedUserIds = Array.isArray(acceptedRaw)
    ? acceptedRaw.map((u) => asString(u)).filter((u) => u.length > 0)
    : [];
  const pendingRaw = team.pendingInviteeIds;
  const pendingInviteeIds = Array.isArray(pendingRaw)
    ? pendingRaw.map((u) => asString(u)).filter((u) => u.length > 0)
    : [];

  if (acceptedUserIds.includes(inviteeUserId)) {
    throw new HttpsError(
      "failed-precondition",
      "이미 팀에 참여한 친구예요."
    );
  }
  if (pendingInviteeIds.includes(inviteeUserId)) {
    throw new HttpsError(
      "failed-precondition",
      "이미 초대를 보낸 친구예요."
    );
  }
  if (acceptedUserIds.length + pendingInviteeIds.length >= 3) {
    throw new HttpsError(
      "failed-precondition",
      "팀 정원이 찼어요."
    );
  }

  const friendsOk = await assertUsersAreFriends(inviter.userId, inviteeUserId);
  if (!friendsOk) {
    throw new HttpsError(
      "failed-precondition",
      "친구로 연결된 사용자만 초대할 수 있어요."
    );
  }

  const dup = await db
    .collection("eventTeamInvites")
    .where("teamSetupId", "==", teamSetupId)
    .where("inviteeUserId", "==", inviteeUserId)
    .where("status", "==", "pending")
    .limit(1)
    .get();
  if (!dup.empty) {
    throw new HttpsError(
      "failed-precondition",
      "이미 진행 중인 초대가 있어요."
    );
  }

  const inviteRef = db.collection("eventTeamInvites").doc();
  const inviteId = inviteRef.id;
  const inviterInfo = await getUserDisplayInfo(inviter.userId);

  await db.runTransaction(async (tx) => {
    const fresh = await tx.get(teamRef);
    if (!fresh.exists) {
      throw new HttpsError("not-found", "팀 정보를 찾을 수 없어요.");
    }
    const t = (fresh.data() ?? {}) as Record<string, unknown>;
    const acc = Array.isArray(t.acceptedUserIds)
      ? t.acceptedUserIds.map((u) => asString(u))
      : [];
    const pend = Array.isArray(t.pendingInviteeIds)
      ? t.pendingInviteeIds.map((u) => asString(u))
      : [];
    if (acc.length + pend.length >= 3) {
      throw new HttpsError("failed-precondition", "팀 정원이 찼어요.");
    }
    tx.set(inviteRef, {
      teamSetupId,
      inviterUserId: inviter.userId,
      inviteeUserId,
      status: "pending",
      createdAt: FieldValue.serverTimestamp(),
      respondedAt: null,
    });
    tx.update(teamRef, {
      pendingInviteeIds: FieldValue.arrayUnion(inviteeUserId),
      updatedAt: FieldValue.serverTimestamp(),
    });
  });

  await writeEventTeamInviteNotification({
    inviteeUserId,
    inviterUserId: inviter.userId,
    inviterName: inviterInfo.nickname,
    inviteId,
    teamSetupId,
  });

  await sendPushToUsers([inviteeUserId], {
    title: "팀 초대",
    body: `${inviterInfo.nickname}님이 3인 팀 참여를 요청했어요.`,
    data: {
      type: "event_team_invite",
      inviteId,
      teamSetupId,
      inviterUserId: inviter.userId,
      inviterName: inviterInfo.nickname,
    },
  });

  logger.info("createEventTeamInvite ok", { inviteId, teamSetupId, inviteeUserId });

  return { inviteId, teamSetupId };
});

export const respondEventTeamInvite = onCall(async (request) => {
  const data = getCallableData(request);
  const user = await resolveUserForFriendCallable(request);
  const inviteId = asNonEmptyString(data.inviteId);
  const accept = data.accept === true;
  if (!inviteId) {
    throw new HttpsError("invalid-argument", "inviteId가 필요해요.");
  }

  const inviteRef = db.collection("eventTeamInvites").doc(inviteId);
  const invitePreview = await inviteRef.get();
  if (!invitePreview.exists) {
    return { ok: false, code: "not_found" };
  }
  const invPre = (invitePreview.data() ?? {}) as Record<string, unknown>;
  const inviterUid = asString(invPre.inviterUserId ?? "");
  const inviteeUserId = asString(invPre.inviteeUserId ?? "");
  if (inviteeUserId !== user.userId) {
    throw new HttpsError("permission-denied", "초대를 받은 본인만 응답할 수 있어요.");
  }
  let friendsStill = true;
  if (accept && inviterUid.length > 0) {
    friendsStill = await assertUsersAreFriends(inviterUid, inviteeUserId);
  }

  const result = await db.runTransaction(async (tx) => {
    const invSnap = await tx.get(inviteRef);
    if (!invSnap.exists) {
      return { ok: false as const, code: "not_found" as const };
    }
    const inv = (invSnap.data() ?? {}) as Record<string, unknown>;
    const status = asString(inv.status ?? "", "pending");
    const invitee = asString(inv.inviteeUserId ?? "");
    const teamSetupId = asString(inv.teamSetupId ?? "");

    if (invitee !== user.userId) {
      throw new HttpsError("permission-denied", "초대를 받은 본인만 응답할 수 있어요.");
    }
    if (status !== "pending") {
      return { ok: false as const, code: "already_responded" as const };
    }

    const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
    const teamSnap = await tx.get(teamRef);
    if (!teamSnap.exists) {
      return { ok: false as const, code: "team_missing" as const };
    }

    if (!accept) {
      tx.update(inviteRef, {
        status: "declined",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: true as const, status: "declined" as const };
    }

    if (!friendsStill) {
      tx.update(inviteRef, {
        status: "cancelled",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "not_friends" as const };
    }

    const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
    const acc = Array.isArray(team.acceptedUserIds)
      ? team.acceptedUserIds.map((u) => asString(u))
      : [];
    const pend = Array.isArray(team.pendingInviteeIds)
      ? team.pendingInviteeIds.map((u) => asString(u))
      : [];

    if (!pend.includes(inviteeUserId)) {
      tx.update(inviteRef, {
        status: "cancelled",
        respondedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "stale_invite" as const };
    }

    if (acc.length >= 3) {
      tx.update(inviteRef, {
        status: "expired",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "team_full" as const };
    }

    if (acc.includes(inviteeUserId)) {
      tx.update(inviteRef, {
        status: "accepted",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: true as const, status: "accepted" as const };
    }

    const nextAccepted = [...acc];
    if (!nextAccepted.includes(inviteeUserId)) {
      nextAccepted.push(inviteeUserId);
    }
    if (nextAccepted.length > 3) {
      tx.update(inviteRef, {
        status: "expired",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "team_full" as const };
    }

    tx.update(inviteRef, {
      status: "accepted",
      respondedAt: FieldValue.serverTimestamp(),
    });
    tx.update(teamRef, {
      acceptedUserIds: nextAccepted,
      pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
      updatedAt: FieldValue.serverTimestamp(),
    });

    return { ok: true as const, status: "accepted" as const };
  });

  return result;
});

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
// 2) interactions 기반 프로필 좋아요 알림 + 매치 판정 + 채팅방 생성
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

    // -----------------------------------------------------------------------
    // 프로필 좋아요 알림: 상대방에게 인앱 알림(idempotent) + 푸시
    // -----------------------------------------------------------------------
    if (fromUserId !== toUserId) {
      const interactionId = event.params.interactionId;
      const notificationId = `like_${interactionId}`;

      const actorInfo = await getUserDisplayInfo(fromUserId);
      const title = "새로운 관심이 도착했어요";
      const body = `${actorInfo.nickname}님이 좋아요를 보냈어요`;

      const created = await createInAppNotification(
        toUserId,
        {
          type: "profile_like",
          title,
          body,
          deeplinkType: "received_like",
          deeplinkId: fromUserId,
          actorId: fromUserId,
          actorName: actorInfo.nickname,
        },
        notificationId
      );

      if (created) {
        await sendPushToUsers([toUserId], {
          title,
          body,
          data: {
            type: "profile_like",
            notificationId,
            deepLinkType: "received_like",
            actorUserId: fromUserId,
            sourceDocId: interactionId,
          },
        });

        logger.info("Profile like push + in-app notification sent", {
          fromUserId,
          toUserId,
          action,
          notificationId,
        });
      }
    }

    // -----------------------------------------------------------------------
    // 기존 mutual like 체크 → 매치 생성
    // -----------------------------------------------------------------------
    const reverseQuery = await db
      .collection("interactions")
      .where("fromUserId", "==", toUserId)
      .where("toUserId", "==", fromUserId)
      .where("action", "in", ["like", "super_like"])
      .limit(1)
      .get();

    if (reverseQuery.empty) return;

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

    batch.set(
      roomRef,
      {
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
      },
      { merge: true }
    );

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
    const participantInfo = isRecord(participantInfoRaw)
      ? participantInfoRaw
      : {};
    const senderInfo = participantInfo[senderId];
    const senderName = asString(
      isRecord(senderInfo) ? senderInfo.nickname : undefined,
      "새 메시지"
    );

    const body = asString(
      message.text ?? message.content ?? "메시지가 도착했어요."
    ).trim();

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
// 4) 대나무숲 댓글/답글 푸시 + 인앱 알림
// =============================================================================
export const onBambooCommentCreated = onDocumentCreated(
  "bamboo_posts/{postId}/comments/{commentId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const commentId = event.params.commentId;
    const comment = snap.data();

    const authorId = asString(comment.authorId ?? "");
    const content = asString(comment.content ?? "").trim();
    const parentCommentId = asNonEmptyString(comment.parentCommentId) ?? "";

    if (!authorId) return;

    const authorInfo = await getUserDisplayInfo(authorId);

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = asString(post.authorId ?? "");

    // 일반 댓글: 글 작성자에게 푸시 + 인앱 알림
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

        await createInAppNotification(postAuthorId, {
          type: "community_comment",
          title: "내 글에 새 댓글이 달렸어요",
          body: content || "누군가가 회원님의 글에 댓글을 남겼습니다.",
          deeplinkType: "community_post",
          deeplinkId: postId,
          actorId: authorId,
          actorName: authorInfo.nickname,
          postId,
          commentId,
        });

        logger.info("Community comment push + in-app notification sent", {
          postId,
          commentId,
          target: postAuthorId,
          authorId,
        });
      }
      return;
    }

    // 답글: 부모 댓글 작성자에게 푸시 + 인앱 알림
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

      await createInAppNotification(parentAuthorId, {
        type: "community_reply",
        title: "내 댓글에 답글이 달렸어요",
        body: content || "누군가가 회원님의 댓글에 답글을 남겼습니다.",
        deeplinkType: "community_post",
        deeplinkId: postId,
        actorId: authorId,
        actorName: authorInfo.nickname,
        postId,
        commentId,
      });

      logger.info("Community reply push + in-app notification sent", {
        postId,
        commentId,
        parentCommentId,
        targets,
        authorId,
      });
    }
  }
);

// =============================================================================
// 5) 대나무숲 글 좋아요 푸시 + 인앱 알림
// =============================================================================
export const onBambooPostLikeCreated = onDocumentCreated(
  "bamboo_posts/{postId}/likes/{userId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const likerUserId = event.params.userId;

    if (!postId || !likerUserId) return;

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = asString(post.authorId ?? "");

    if (!postAuthorId || postAuthorId === likerUserId) {
      return;
    }

    const existingCount = await countPostLikeNotificationsForPost(
      postAuthorId,
      postId
    );

    if (existingCount >= 5) {
      logger.info("Skipped post like notification due to 5-notification limit", {
        postId,
        postAuthorId,
        likerUserId,
        existingCount,
      });
      return;
    }

    const likerInfo = await getUserDisplayInfo(likerUserId);

    await sendPushToUsers([postAuthorId], {
      title: "내 글에 좋아요가 눌렸어요",
      body: "누군가가 회원님의 글을 좋아합니다.",
      data: {
        type: "community_post_like",
        postId,
      },
    });

    await createInAppNotification(postAuthorId, {
      type: "community_post_like",
      title: "내 글에 좋아요가 눌렸어요",
      body: "누군가가 회원님의 글을 좋아합니다.",
      deeplinkType: "community_post",
      deeplinkId: postId,
      actorId: likerUserId,
      actorName: likerInfo.nickname,
      postId,
    });

    logger.info("Community post like push + in-app notification sent", {
      postId,
      postAuthorId,
      likerUserId,
      existingCount: existingCount + 1,
    });
  }
);

// =============================================================================
// 6) 무물(ask) 생성 시 알림 + 푸시
// =============================================================================
export const onAskCreated = onDocumentCreated(
  "asks/{askId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const askId = event.params.askId;
    const data = snap.data();
    const fromUserId = asString(data.fromUserId ?? "");
    const toUserId = asString(data.toUserId ?? "");

    if (!fromUserId || !toUserId || fromUserId === toUserId) return;

    const notificationId = `ask_${askId}`;
    const actorInfo = await getUserDisplayInfo(fromUserId);
    const title = "새 무물이 도착했어요";
    const body = `${actorInfo.nickname}님이 질문을 보냈어요`;

    const created = await createInAppNotification(
      toUserId,
      {
        type: "ask_received",
        title,
        body,
        deeplinkType: "asks_inbox",
        deeplinkId: askId,
        actorId: fromUserId,
        actorName: actorInfo.nickname,
      },
      notificationId
    );

    if (created) {
      await sendPushToUsers([toUserId], {
        title,
        body,
        data: {
          type: "ask_received",
          notificationId,
          deepLinkType: "asks_inbox",
          actorUserId: fromUserId,
          sourceDocId: askId,
        },
      });

      logger.info("Ask notification + push sent", {
        askId,
        fromUserId,
        toUserId,
        notificationId,
      });
    }
  }
);

// =============================================================================
// 7) 매치 해제 시 채팅방 비활성화 (onMatchUpdated)
// =============================================================================
export const onMatchUpdated = onDocumentUpdated(
  "matches/{matchId}",
  async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();

    if (!before || !after) return;

    if (before.status === "active" && after.status === "unmatched") {
      const chatRoomId = asString(
        (after as Record<string, unknown>).chatRoomId ?? ""
      );
      if (!chatRoomId) return;

      await db
        .collection("chat_rooms")
        .doc(chatRoomId)
        .set(
          {
            status: "closed",
            closedAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );

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
// 8) 매일 오후 1시 unread chat digest 푸시 + 인앱 알림
// =============================================================================
export const sendDailyUnreadChatDigests = onSchedule(
  {
    schedule: "0 13 * * *",
    timeZone: "Asia/Seoul",
  },
  async () => {
    const digestDate = getKstDateKey();

    logger.info("sendDailyUnreadChatDigests started", { digestDate });

    const usersSnap = await db.collection("users").get();

    for (const userDoc of usersSnap.docs) {
      const userId = userDoc.id;

      try {
        const alreadySent = await hasChatDigestForDate(userId, digestDate);
        if (alreadySent) {
          logger.info("Skipped chat digest: already sent today", {
            userId,
            digestDate,
          });
          continue;
        }

        const { unreadCount, previewSenderName } =
          await getUnreadChatDigestForUser(userId);

        if (unreadCount <= 0) {
          continue;
        }

        const title = "읽지 않은 메시지가 있어요";
        const body = previewSenderName
          ? `${previewSenderName}님 외 읽지 않은 메시지가 ${unreadCount}개 있습니다.`
          : `읽지 않은 메시지가 ${unreadCount}개 있습니다.`;

        await sendPushToUsers([userId], {
          title,
          body,
          data: {
            type: "chat_digest",
          },
        });

        await createInAppNotification(userId, {
          type: "chat_digest",
          title,
          body,
          deeplinkType: "chat",
          digestDate,
        });

        logger.info("Daily unread chat digest sent", {
          userId,
          unreadCount,
          digestDate,
        });
      } catch (error) {
        logger.error("Failed to send daily unread chat digest", {
          userId,
          digestDate,
          error,
        });
      }
    }

    logger.info("sendDailyUnreadChatDigests finished", { digestDate });
  }
);

// =============================================================================
// 전화번호 정규화 + 해시 (클라이언트와 동일 알고리즘)
// =============================================================================
export function normalizeKoreanPhone(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const hasPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/[^\d]/g, "");
  if (digits.length < 7) return null;

  if ((hasPlus || !digits.startsWith("0")) && digits.startsWith("82")) {
    const local = digits.substring(2);
    if (local.startsWith("10") && local.length >= 9 && local.length <= 11) {
      return `+82${local}`;
    }
    if (local.startsWith("0") && local.length >= 10 && local.length <= 12) {
      return `+82${local.substring(1)}`;
    }
    return null;
  }
  if (digits.startsWith("0")) {
    if (digits.length >= 10 && digits.length <= 11) {
      return `+82${digits.substring(1)}`;
    }
    return null;
  }
  if (digits.startsWith("10") && digits.length >= 9 && digits.length <= 11) {
    return `+82${digits}`;
  }
  return null;
}

export function hashPhoneNumber(normalized: string): string {
  return createHash("sha256").update(normalized).digest("hex");
}

// =============================================================================
// syncContactBlocks — 연락처 차단 동기화 Callable
// =============================================================================
const MAX_CONTACT_HASHES = 5000;

export const syncContactBlocks = onCall(async (request) => {
  const callerUid = request.auth?.uid;
  if (!callerUid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const data = getCallableData(request);
  const rawHashes = data.contactHashes;
  if (!Array.isArray(rawHashes)) {
    throw new HttpsError(
      "invalid-argument",
      "contactHashes 배열이 필요합니다."
    );
  }

  // dedupe + validate (64-char hex SHA-256)
  const hexPattern = /^[a-f0-9]{64}$/;
  const seen = new Set<string>();
  const validHashes: string[] = [];
  let invalidCount = 0;

  for (const h of rawHashes) {
    if (typeof h !== "string" || !hexPattern.test(h)) {
      invalidCount++;
      continue;
    }
    if (seen.has(h)) continue;
    seen.add(h);
    validHashes.push(h);
    if (validHashes.length >= MAX_CONTACT_HASHES) break;
  }

  let matchedUserCount = 0;
  let newlyBlockedPairCount = 0;
  let alreadyBlockedPairCount = 0;
  let skippedSelfCount = 0;
  const now = FieldValue.serverTimestamp();

  // process in chunks of 400 (Firestore batch limit 500)
  const CHUNK = 400;
  for (let i = 0; i < validHashes.length; i += CHUNK) {
    const chunk = validHashes.slice(i, i + CHUNK);
    const batch = db.batch();

    for (const phoneHash of chunk) {
      // 1. contactBlockedHashes/{hash}
      const cbRef = db
        .collection("users")
        .doc(callerUid)
        .collection("contactBlockedHashes")
        .doc(phoneHash);
      batch.set(
        cbRef,
        {
          phoneHash,
          source: "device_contacts",
          updatedAt: now,
          lastSeenInSyncAt: now,
        },
        { merge: true }
      );

      // 2. contactBlockedHashIndex/{hash}/owners/{uid}
      const idxRef = db
        .collection("contactBlockedHashIndex")
        .doc(phoneHash)
        .collection("owners")
        .doc(callerUid);
      batch.set(
        idxRef,
        { ownerUserId: callerUid, updatedAt: now },
        { merge: true }
      );
    }
    await batch.commit();

    // 3. phoneHashIndex lookup + mutual block
    for (const phoneHash of chunk) {
      const phiSnap = await db
        .collection("phoneHashIndex")
        .doc(phoneHash)
        .get();
      if (!phiSnap.exists) continue;

      const matchedUid = asNonEmptyString(
        (phiSnap.data() as Record<string, unknown>)?.userId
      );
      if (!matchedUid) continue;
      if (matchedUid === callerUid) {
        skippedSelfCount++;
        continue;
      }
      matchedUserCount++;

      // update contactBlockedHashes doc
      await db
        .collection("users")
        .doc(callerUid)
        .collection("contactBlockedHashes")
        .doc(phoneHash)
        .set(
          { isMatchedToAppUser: true, matchedUserId: matchedUid },
          { merge: true }
        );

      // mutual block
      const created = await ensureMutualContactBlock(
        callerUid,
        matchedUid,
        phoneHash
      );
      if (created) {
        newlyBlockedPairCount++;
      } else {
        alreadyBlockedPairCount++;
      }
    }
  }

  logger.info("syncContactBlocks completed", {
    callerUid,
    submittedHashCount: rawHashes.length,
    storedHashCount: validHashes.length,
    matchedUserCount,
    newlyBlockedPairCount,
    alreadyBlockedPairCount,
    skippedSelfCount,
    invalidCount,
  });

  return {
    submittedHashCount: rawHashes.length,
    storedHashCount: validHashes.length,
    matchedUserCount,
    newlyBlockedPairCount,
    alreadyBlockedPairCount,
    skippedSelfCount,
    invalidHashCount: invalidCount,
  };
});

/**
 * A↔B 상호 block을 blocks/{uid}/targets/{targetUid}에 생성.
 * 이미 양쪽 다 있으면 false 반환(이미 차단).
 */
async function ensureMutualContactBlock(
  uidA: string,
  uidB: string,
  phoneHash: string
): Promise<boolean> {
  const refAB = db
    .collection("blocks")
    .doc(uidA)
    .collection("targets")
    .doc(uidB);
  const refBA = db
    .collection("blocks")
    .doc(uidB)
    .collection("targets")
    .doc(uidA);

  const [snapAB, snapBA] = await Promise.all([refAB.get(), refBA.get()]);
  if (snapAB.exists && snapBA.exists) return false;

  const now = FieldValue.serverTimestamp();
  const batch = db.batch();
  if (!snapAB.exists) {
    batch.set(refAB, {
      fromUserId: uidA,
      toUserId: uidB,
      reason: "contact_block",
      source: "contacts",
      viaPhoneHash: true,
      createdAt: now,
    });
  }
  if (!snapBA.exists) {
    batch.set(refBA, {
      fromUserId: uidB,
      toUserId: uidA,
      reason: "contact_block",
      source: "contacts",
      viaPhoneHash: true,
      createdAt: now,
    });
  }
  await batch.commit();
  return true;
}

// =============================================================================
// onUserPhoneHashUpsert — phoneHash가 생기면 기존 연락처 차단과 상호 block
// =============================================================================
export const onUserPhoneHashUpsert = onDocumentWritten(
  "userPrivate/{uid}",
  async (event) => {
    const uid = event.params.uid;
    const after = event.data?.after?.data() as
      | Record<string, unknown>
      | undefined;
    const before = event.data?.before?.data() as
      | Record<string, unknown>
      | undefined;
    if (!after) return; // deleted

    const newHash = asNonEmptyString(after.phoneHash);
    const oldHash = asNonEmptyString(before?.phoneHash);
    if (!newHash || newHash === oldHash) return;

    // 1. phoneHashIndex upsert
    await db.collection("phoneHashIndex").doc(newHash).set(
      { userId: uid, updatedAt: FieldValue.serverTimestamp() },
      { merge: true }
    );

    // 2. old hash cleanup
    if (oldHash && oldHash !== newHash) {
      await db.collection("phoneHashIndex").doc(oldHash).delete();
    }

    // 3. contactBlockedHashIndex에서 이 해시를 가진 owner 찾기
    const ownersSnap = await db
      .collection("contactBlockedHashIndex")
      .doc(newHash)
      .collection("owners")
      .get();

    if (ownersSnap.empty) return;

    for (const ownerDoc of ownersSnap.docs) {
      const ownerUid = ownerDoc.id;
      if (ownerUid === uid) continue;

      await ensureMutualContactBlock(ownerUid, uid, newHash);

      // mark matched in owner's contactBlockedHashes
      await db
        .collection("users")
        .doc(ownerUid)
        .collection("contactBlockedHashes")
        .doc(newHash)
        .set(
          { isMatchedToAppUser: true, matchedUserId: uid },
          { merge: true }
        );
    }

    logger.info("onUserPhoneHashUpsert: processed", {
      uid,
      phoneHash: newHash,
      ownerCount: ownersSnap.size,
    });
  }
);

// =============================================================================
// saveUserPhoneHash — 카카오 로그인 후 전화번호 해시 저장 Callable
// =============================================================================
export const saveUserPhoneHash = onCall(async (request) => {
  const data = getCallableData(request);
  const phoneHash = asNonEmptyString(data.phoneHash);
  const phoneSource = asNonEmptyString(data.phoneSource) ?? "kakao";

  // auth 또는 kakaoAccessToken으로 uid 결정
  let uid = request.auth?.uid;
  if (!uid) {
    const accessToken = asNonEmptyString(data.kakaoAccessToken);
    if (!accessToken) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }
    const kakaoUser = await verifyKakaoAccessToken(accessToken);
    uid = kakaoUser.userId;
  }

  if (!phoneHash) {
    throw new HttpsError("invalid-argument", "phoneHash가 필요합니다.");
  }

  await db
    .collection("userPrivate")
    .doc(uid)
    .set(
      {
        phoneHash,
        phoneSource,
        phoneUpdatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  return { success: true };
});

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
