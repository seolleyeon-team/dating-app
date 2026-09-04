/**
 * 알림 공용 모듈
 * 경로: functions/src/shared/notify.ts
 *
 * FCM 푸시와 인앱 알림 생성을 한 곳에서 관리한다.
 * index.ts와 blindMeeting 모듈이 같은 구현을 공유하므로
 * 알림 설정(users/{uid}.notificationSettings)과 idempotency 규칙이 어긋나지 않는다.
 */

import { getFirestore, FieldValue } from "firebase-admin/firestore";
import {
  getMessaging,
  type AndroidConfig,
  type ApnsConfig,
} from "firebase-admin/messaging";
import * as logger from "firebase-functions/logger";

/**
 * 기본 알림 채널 (소리 + 진동 + heads-up).
 *
 * 앱의 PushNotificationService가 같은 id로 채널을 만든다.
 */
export const DEFAULT_PUSH_CHANNEL_ID = "seolleyeon_high_importance";

/**
 * 조용한 알림 채널 (소리·진동 없음, 낮은 우선순위).
 *
 * 미팅 아이스브레이킹 룰렛처럼 15분마다 반복되는 안내에 사용한다.
 * 알림 센터에는 문구가 남지만 소리·진동·강한 heads-up은 발생하지 않는다.
 * 중요 채팅·안전 알림 채널과 분리되어 있어 사용자가 따로 끌 수 있다.
 */
export const QUIET_PUSH_CHANNEL_ID = "meeting_icebreaker_quiet";

/**
 * 푸시 전달 방식.
 *
 *  - default: 기존 알림 (소리 + 진동 + 높은 우선순위)
 *  - quiet:   소리·진동 없음, 낮은 우선순위, 같은 collapseKey는 알림을 교체
 */
export type PushDeliveryStyle = "default" | "quiet";

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
    case "promise_reminder":
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
    case "meeting_icebreaker_roulette":
      // 3:3 미팅 진행 중 아이스브레이킹 안내. 이벤트 카테고리를 따른다.
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
  const records = await fetchUserTokenRecords(userId, notificationType);
  return records.map((record) => record.token);
}

export type PushTokenRecord = {
  token: string;
  deliveryContext: Record<string, unknown> | null;
};

/**
 * Device-token records eligible for this notification category.
 *
 * Delivery context is kept per device: if the chat list is open on one device,
 * another backgrounded signed-in device can still receive the message.
 */
export async function fetchUserTokenRecords(
  userId: string,
  notificationType: string
): Promise<PushTokenRecord[]> {
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
    .map((doc) => {
      const data = doc.data();
      return {
        token: doc.id,
        deliveryContext: isRecord(data.deliveryContext)
          ? data.deliveryContext
          : null,
      };
    })
    .filter((record) => record.token.length > 0);
}

const CHAT_DELIVERY_CONTEXT_MAX_AGE_MS = 90 * 1000;

function contextUpdatedAtMs(context: Record<string, unknown>): number | null {
  const value = context.updatedAt;
  if (value && typeof value === "object" && "toMillis" in value) {
    const toMillis = (value as { toMillis?: unknown }).toMillis;
    if (typeof toMillis === "function") {
      const millis = toMillis.call(value);
      return typeof millis === "number" && Number.isFinite(millis)
        ? millis
        : null;
    }
  }
  return null;
}

/** Whether a device already showing relevant chat UI should skip this push. */
export function shouldSuppressPushForDevice(params: {
  notificationType: string;
  roomId?: string;
  deliveryContext: Record<string, unknown> | null;
  nowMs?: number;
}): boolean {
  if (params.notificationType !== "chat" || !params.deliveryContext) {
    return false;
  }
  const context = params.deliveryContext;
  if (context.appState !== "foreground") return false;

  const updatedAtMs = contextUpdatedAtMs(context);
  const nowMs = params.nowMs ?? Date.now();
  if (
    updatedAtMs == null ||
    updatedAtMs > nowMs + 10 * 1000 ||
    nowMs - updatedAtMs > CHAT_DELIVERY_CONTEXT_MAX_AGE_MS
  ) {
    return false;
  }

  const screen = asString(context.screen, "");
  if (screen === "chat_list") return true;
  return (
    screen === "chat_room" &&
    !!params.roomId &&
    asString(context.chatRoomId, "") === params.roomId
  );
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
  | "blind_meeting_party_invite"
  | "blind_meeting_party_joined"
  | "blind_meeting_party_locked"
  | "blind_meeting_party_member_completed"
  | "blind_meeting_party_ready"
  | "blind_meeting_matched"
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
  | "meeting_icebreaker_roulette";

export type InAppNotificationDeeplinkType =
  | "chat"
  | "community_post"
  | "received_like"
  | "asks_inbox"
  | "safety_stamp_follow_up"
  | "event_team_invite"
  | "blind_meeting_party"
  | "blind_meeting"
  | "blind_meeting_follow_up"
  | "meeting_icebreaker_roulette";

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
  partyId?: string;
  inviteId?: string;
  meetingId?: string;
  /** 미팅 아이스브레이킹 세션 식별자 (서버 검증용) */
  sessionId?: string;
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
    sessionId: payload.sessionId ?? null,
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

function buildAndroidConfig(
  style: PushDeliveryStyle,
  collapseKey?: string
): AndroidConfig {
  if (style === "quiet") {
    return {
      priority: "normal",
      ...(collapseKey ? { collapseKey } : {}),
      notification: {
        channelId: QUIET_PUSH_CHANNEL_ID,
        // defaultSound=false + sound 미지정 → 소리 없음
        defaultSound: false,
        // defaultVibrateTimings=false + vibrateTimings 미지정 → 진동 없음
        defaultVibrateTimings: false,
        // 알림 자체의 우선순위도 낮춘다 (heads-up 방지).
        priority: "low",
        // 같은 tag는 알림을 쌓지 않고 교체한다 (같은 미팅 알림 누적 방지).
        ...(collapseKey ? { tag: collapseKey } : {}),
      },
    };
  }

  return {
    priority: "high",
    notification: {
      channelId: DEFAULT_PUSH_CHANNEL_ID,
    },
  };
}

function buildApnsConfig(
  style: PushDeliveryStyle,
  collapseKey?: string
): ApnsConfig {
  if (style === "quiet") {
    const headers: Record<string, string> = {
      // 5 = throttled. 즉시 깨우지 않는다.
      "apns-priority": "5",
    };
    if (collapseKey) headers["apns-collapse-id"] = collapseKey;

    // sound를 지정하지 않아 무음이고, badge도 올리지 않는다.
    // interruption-level=passive는 iOS 15+에서 heads-up 배너 없이
    // 알림 센터에만 조용히 표시되게 한다.
    // admin SDK의 Aps 타입에 명시되지 않은 키라서 캐스팅해서 넣는다.
    return {
      headers,
      payload: {
        aps: { "interruption-level": "passive" },
      },
    } as unknown as ApnsConfig;
  }

  return {
    headers: {
      "apns-priority": "10",
    },
    payload: {
      aps: {
        sound: "default",
      },
    },
  };
}

/** 여러 사용자에게 FCM 푸시 발송. 실패한 토큰은 정리한다. */
export async function sendPushToUsers(
  userIds: string[],
  payload: {
    title: string;
    body: string;
    data: Record<string, string>;
    /** 기본값 default. quiet는 소리·진동 없는 조용한 알림. */
    style?: PushDeliveryStyle;
    /** 같은 키의 알림을 교체한다 (Android tag / apns-collapse-id). */
    collapseKey?: string;
  }
): Promise<void> {
  const uniqueUserIds = [...new Set(userIds.filter((u) => u.length > 0))];
  if (uniqueUserIds.length === 0) return;

  const notificationType = asString(payload.data.type, "");
  const tokenLists = await Promise.all(
    uniqueUserIds.map((uid) => fetchUserTokenRecords(uid, notificationType))
  );
  const roomId = asString(payload.data.roomId, "");
  const tokenRecords = tokenLists.flat();
  const suppressedTokens = tokenRecords.filter((record) =>
    shouldSuppressPushForDevice({
      notificationType,
      roomId,
      deliveryContext: record.deliveryContext,
    })
  );
  const tokens = tokenRecords
    .filter(
      (record) =>
        !shouldSuppressPushForDevice({
          notificationType,
          roomId,
          deliveryContext: record.deliveryContext,
        })
    )
    .map((record) => record.token);

  if (suppressedTokens.length > 0) {
    logger.info("Suppressed redundant foreground chat pushes", {
      notificationType,
      roomId,
      suppressedDeviceCount: suppressedTokens.length,
    });
  }

  if (tokens.length === 0) {
    logger.info("No device tokens found for users", { userIds: uniqueUserIds });
    return;
  }

  const style: PushDeliveryStyle = payload.style ?? "default";
  const response = await getMessaging().sendEachForMulticast({
    tokens,
    notification: {
      title: payload.title,
      body: payload.body,
    },
    data: payload.data,
    android: buildAndroidConfig(style, payload.collapseKey),
    apns: buildApnsConfig(style, payload.collapseKey),
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
  payload: {
    title: string;
    body: string;
    data: Record<string, string>;
    style?: PushDeliveryStyle;
    collapseKey?: string;
  },
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
