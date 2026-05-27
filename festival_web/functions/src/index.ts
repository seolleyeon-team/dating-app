import { setGlobalOptions } from "firebase-functions/v2";
import { onDocumentCreated } from "firebase-functions/v2/firestore";
import { HttpsError, type CallableRequest } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { initializeApp } from "firebase-admin/app";
import { FieldValue, Timestamp, getFirestore } from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";
import { createUploadAvatarSourcePhotoFunction } from "./avatarMedia";
import {
  createApproveAvatarCandidateFunction,
  createGetAvatarJobCandidatesFunction,
} from "./avatarApproval";

initializeApp();

const db = getFirestore();

setGlobalOptions({
  region: "asia-northeast3",
  maxInstances: 10,
});

const PUSH_TITLE = "설레연";
const PUSH_BODY = "새 메시지가 왔습니다";

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((item) => asString(item, "").trim()).filter(Boolean);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function readMap(v: unknown): Record<string, unknown> {
  return isRecord(v) ? v : {};
}

function isExpiredTimestamp(v: unknown): boolean {
  if (!(v instanceof Timestamp)) return false;
  return v.toDate().getTime() <= Date.now();
}

async function resolveFestivalAvatarUser(
  auth: CallableRequest<unknown>["auth"]
): Promise<{ userId: string; email: string; data: Record<string, unknown> }> {
  const uid = asString(auth?.uid ?? "").trim();
  if (!uid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const sessionSnap = await db.collection("festivalSessions").doc(uid).get();
  if (!sessionSnap.exists) {
    throw new HttpsError(
      "failed-precondition",
      "입장 세션을 찾을 수 없어요."
    );
  }
  const session = sessionSnap.data() ?? {};
  if (isExpiredTimestamp(session.sessionExpiresAt)) {
    throw new HttpsError(
      "failed-precondition",
      "입장 세션이 만료되었어요."
    );
  }

  const ticketId = asString(session.ticketId ?? session.code ?? "").trim();
  const [profileSnap, ticketSnap, userSnap] = await Promise.all([
    ticketId ? db.collection("festivalProfiles").doc(ticketId).get() : null,
    ticketId ? db.collection("festivalTickets").doc(ticketId).get() : null,
    db.collection("users").doc(uid).get(),
  ]);
  const ticketData = ticketSnap?.data() ?? {};
  const draft = readMap(ticketData.profileDraft);
  const profileData = profileSnap?.data() ?? draft;
  const previousUserData = userSnap.data() ?? {};
  const previousOnboarding = readMap(previousUserData.onboarding);
  const gender = asString(profileData.gender ?? previousOnboarding.gender);

  const userPatch: Record<string, unknown> = {
    uid,
    festivalTicketId: ticketId,
    profileImageMode: "avatar",
    onboarding: {
      ...previousOnboarding,
      ...(gender ? { gender } : {}),
    },
    updatedAt: FieldValue.serverTimestamp(),
  };

  await db.collection("users").doc(uid).set(userPatch, { merge: true });
  const mergedUserSnap = await db.collection("users").doc(uid).get();
  return {
    userId: uid,
    email: "",
    data: mergedUserSnap.data() ?? userPatch,
  };
}

async function fetchFestivalPushTokens(uid: string): Promise<string[]> {
  const snap = await db
    .collection("festivalPushTokens")
    .doc(uid)
    .collection("tokens")
    .get();

  return snap.docs
    .filter((doc) => doc.data().notificationsEnabled !== false)
    .map((doc) => asString(doc.data().token ?? doc.id))
    .filter((token) => token.length > 0);
}

async function deleteInvalidTokens(
  uid: string,
  tokens: string[]
): Promise<void> {
  if (tokens.length === 0) return;
  const batch = db.batch();
  for (const token of tokens) {
    batch.delete(
      db.collection("festivalPushTokens").doc(uid).collection("tokens").doc(token)
    );
  }
  await batch.commit();
}

async function sendFestivalChatPush(
  targetUserIds: string[],
  roomId: string
): Promise<void> {
  const uniqueUserIds = [...new Set(targetUserIds.filter((uid) => uid.length > 0))];
  if (uniqueUserIds.length === 0) return;

  const tokenLists = await Promise.all(
    uniqueUserIds.map((uid) => fetchFestivalPushTokens(uid))
  );
  const tokens = tokenLists.flat();
  if (tokens.length === 0) {
    logger.info("No festival push tokens", { targetUserIds: uniqueUserIds, roomId });
    return;
  }

  const response = await getMessaging().sendEachForMulticast({
    tokens,
    notification: {
      title: PUSH_TITLE,
      body: PUSH_BODY,
    },
    data: {
      type: "festival_chat",
      roomId,
    },
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
    webpush: {
      headers: {
        Urgency: "high",
      },
      notification: {
        title: PUSH_TITLE,
        body: PUSH_BODY,
        icon: "https://seolleyeon-festival.web.app/icons/Icon-192.png",
      },
      fcmOptions: {
        link: "https://seolleyeon-festival.web.app/",
      },
    },
  });

  const invalidTokens: string[] = [];
  response.responses.forEach((result, index) => {
    if (!result.success) {
      const token = tokens[index];
      if (token) invalidTokens.push(token);
      logger.warn("Festival push send failed", {
        token,
        error: result.error?.message,
      });
    }
  });

  if (invalidTokens.length > 0) {
    for (const uid of uniqueUserIds) {
      const userTokens = await fetchFestivalPushTokens(uid);
      const stale = userTokens.filter((token) => invalidTokens.includes(token));
      await deleteInvalidTokens(uid, stale);
    }
  }

  logger.info("Festival chat push sent", {
    roomId,
    targets: uniqueUserIds,
    tokenCount: tokens.length,
    successCount: response.successCount,
  });
}

export {
  generateFestivalDailyRecommendations,
  onFestivalRecommendationJobCreated,
  onFestivalTasteCompleted,
  refreshFestivalRecommendations,
} from "./festival_recommendations";

export {
  onFestivalProfilePhotoUpdated,
  seedFestivalEmbeddings,
  seedFestivalEmbeddingsHttp,
} from "./festival_embeddings";

export {
  festivalEventScheduleTick,
  setFestivalEventScheduleHttp,
} from "./festival_event_schedule";

export const uploadAvatarSourcePhoto =
  createUploadAvatarSourcePhotoFunction(db, resolveFestivalAvatarUser);

export const getAvatarJobCandidates =
  createGetAvatarJobCandidatesFunction(db, resolveFestivalAvatarUser);

export const approveAvatarCandidate =
  createApproveAvatarCandidateFunction(db, resolveFestivalAvatarUser);

export const onFestivalChatMessageCreated = onDocumentCreated(
  "festivalChatRooms/{roomId}/messages/{messageId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const roomId = event.params.roomId;
    const message = snap.data();
    const senderUid = asString(message.senderUid ?? "");
    if (!senderUid) return;

    const roomSnap = await db.collection("festivalChatRooms").doc(roomId).get();
    if (!roomSnap.exists) return;

    const room = roomSnap.data() ?? {};
    const participantUids = asStringArray(room.participantUids);
    const targetUserIds = participantUids.filter((uid) => uid !== senderUid);
    if (targetUserIds.length === 0) return;

    await sendFestivalChatPush(targetUserIds, roomId);
  }
);
