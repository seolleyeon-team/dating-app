/**
 * 알림 공용 모듈
 * 경로: functions/src/shared/notify.ts
 *
 * FCM 푸시와 인앱 알림 생성을 한 곳에서 관리한다.
 * index.ts와 blindMeeting 모듈이 같은 구현을 공유하므로
 * 알림 설정(users/{uid}.notificationSettings)과 idempotency 규칙이 어긋나지 않는다.
 */

import { getFirestore, FieldValue } from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";
import * as logger from "firebase-functions/logger";

function db() {
  return getFirestore();
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

/** 알림 타입 → 사용자 알림 설정 카테고리 */
export function notificationCategoryForType(type: string): string | null {
  switch (type) {
    case "chat":
    case "chat_digest":
      return "chat";
    case "profile_like":
      return "matching";
    case "community_post_like":
    case "community_comment":
    case "community_reply":
      return "community";
    case "ask_received":
      return "asks";
    case "event_team_invite":
      return "events";
    case "safety_stamp_follow_up":
      return "safety";
    default:
      if (type.startsWith("blind_meeting_")) {
        // 블라인드 취향 미팅 알림은 이벤트 카테고리를 따른다.
        return "events";
      }
      return null;
  }
}

export function isPushEnabledForType(
  settingsRaw: unknown,
  notificationType: string
): boolean {
  if (!isRecord(settingsRaw)) return true;
  if (settingsRaw.all === false) return false;

  const category = notificationCategoryForType(notificationType);
  if (category == null) return true;
  return settingsRaw[category] !== false;
}

export async function fetchUserTokens(
  userId: string,
  notificationType: string
): Promise<string[]> {
  const userRef = db().collection("users").doc(userId);
  const userSnap = await userRef.get();
  const userSettings = userSnap.data()?.notificationSettings;

  if (!isPushEnabledForType(userSettings, notificationType)) {
    return [];
  }

  const snap = await userRef.collection("deviceTokens").get();

  return snap.docs
    .filter((doc) => {
      const data = doc.data();
      if (data.notificationsEnabled === false) return false;
      const tokenSettings = data.notificationSettings ?? userSettings;
      return isPushEnabledForType(tokenSettings, notificationType);
    })
    .map((d) => d.id)
    .filter((t) => t.length > 0);
}

export type InAppNotificationType =
  | "chat_digest"
  | "community_post_like"
  | "community_comment"
  | "community_reply"
  | "profile_like"
  | "ask_received"
  | "safety_stamp_follow_up"
  | "event_team_invite"
  | "blind_meeting_matched"
  | "blind_meeting_acceptance_request"
  | "blind_meeting_deposit_request"
  | "blind_meeting_confirmed"
  | "blind_meeting_chat_created"
  | "blind_meeting_schedule_vote"
  | "blind_meeting_schedule_confirmed"
  | "blind_meeting_attendance_check"
  | "blind_meeting_replacement_offer"
  | "blind_meeting_replacement_confirmed"
  | "blind_meeting_checkin"
  | "blind_meeting_checkout"
  | "blind_meeting_follow_up"
  | "blind_meeting_follow_up_reminder"
  | "blind_meeting_mutual_match"
  | "blind_meeting_cancelled"
  | "blind_meeting_refunded";

export type InAppNotificationDeeplinkType =
  | "chat"
  | "community_post"
  | "received_like"
  | "asks_inbox"
  | "safety_stamp_follow_up"
  | "event_team_invite"
  | "blind_meeting"
  | "blind_meeting_follow_up";

export type InAppNotificationPayload = {
  type: InAppNotificationType;
  title: string;
  body: string;
  deeplinkType: InAppNotificationDeeplinkType;
  deeplinkId?: string;
  actorId?: string;
  actorName?: string;
  postId?: string;
  commentId?: string;
  roomId?: string;
  digestDate?: string;
  teamSetupId?: string;
  inviteId?: string;
  meetingId?: string;
};

/**
 * 인앱 알림 생성.
 *
 * [notificationId]를 주면 같은 id로 두 번 만들지 않는다 (idempotent).
 */
export async function createInAppNotification(
  userId: string,
  payload: InAppNotificationPayload,
  notificationId?: string
): Promise<boolean> {
  if (!userId) return false;

  const collection = db()
    .collection("users")
    .doc(userId)
    .collection("notifications");
  const notifRef = notificationId
    ? collection.doc(notificationId)
    : collection.doc();

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
    teamSetupId: payload.teamSetupId ?? null,
    inviteId: payload.inviteId ?? null,
    meetingId: payload.meetingId ?? null,
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

/** 여러 사용자에게 FCM 푸시 발송. 실패한 토큰은 정리한다. */
export async function sendPushToUsers(
  userIds: string[],
  payload: {
    title: string;
    body: string;
    data: Record<string, string>;
  }
): Promise<void> {
  const uniqueUserIds = [...new Set(userIds.filter((u) => u.length > 0))];
  if (uniqueUserIds.length === 0) return;

  const notificationType = asString(payload.data.type, "");
  const tokenLists = await Promise.all(
    uniqueUserIds.map((uid) => fetchUserTokens(uid, notificationType))
  );
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
      const batch = db().batch();
      for (const token of invalidTokens) {
        batch.delete(
          db()
            .collection("users")
            .doc(uid)
            .collection("deviceTokens")
            .doc(token)
        );
      }
      await batch.commit();
    }
  }
}

/**
 * 알림 중복 발송을 막는 idempotency key.
 *
 * 같은 이벤트에 대해 같은 key가 만들어지므로 재시도해도 한 번만 발송된다.
 */
export function buildNotificationIdempotencyKey(
  parts: (string | number | null | undefined)[]
): string {
  return parts
    .filter((p) => p !== null && p !== undefined && `${p}`.length > 0)
    .join("_");
}

/**
 * idempotency key 기준으로 한 번만 푸시를 보낸다.
 *
 * 발송 기록은 notificationDispatchLog/{key} 에 남기고, 이미 있으면 건너뛴다.
 */
export async function sendPushOnce(
  userIds: string[],
  payload: { title: string; body: string; data: Record<string, string> },
  idempotencyKey: string
): Promise<boolean> {
  if (!idempotencyKey) {
    await sendPushToUsers(userIds, payload);
    return true;
  }

  const ref = db().collection("notificationDispatchLog").doc(idempotencyKey);
  const created = await db().runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    if (snap.exists) return false;
    tx.set(ref, {
      key: idempotencyKey,
      type: asString(payload.data.type, ""),
      userIds,
      createdAt: FieldValue.serverTimestamp(),
    });
    return true;
  });

  if (!created) {
    logger.info("Push already dispatched, skipping (idempotent)", {
      idempotencyKey,
    });
    return false;
  }

  await sendPushToUsers(userIds, payload);
  return true;
}
