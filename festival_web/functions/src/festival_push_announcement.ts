import { onRequest } from "firebase-functions/v2/https";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { FieldValue, getFirestore, Timestamp } from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";

const db = getFirestore();
const SCHEDULE_PATH = "festivalSettings/schedule";
const SEED_HTTP_KEY = "seolleyeon-festival-clip-init";
const PUSH_TITLE = "설레연";
const DEFAULT_BODY =
  "추천 풀 확보를 위해 9시에 추천 결과가 공개됩니다";
export const REVEAL_COMPLETE_PUSH_BODY =
  "설레연 추천이 완료되었습니다! 맘에 드시는 분과 이야기를 나눠보세요!";

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

async function collectAllPushTokens(): Promise<string[]> {
  const snap = await db.collectionGroup("tokens").get();
  const tokens = new Set<string>();
  for (const doc of snap.docs) {
    const path = doc.ref.path;
    if (!path.startsWith("festivalPushTokens/")) continue;
    if (doc.data().notificationsEnabled === false) continue;
    const token = asString(doc.data().token ?? doc.id).trim();
    if (token) tokens.add(token);
  }
  return [...tokens];
}

export async function sendFestivalBroadcastPush(
  body: string,
  title: string = PUSH_TITLE
): Promise<{ success: number; failure: number; total: number }> {
  const tokens = await collectAllPushTokens();
  if (tokens.length === 0) {
    logger.info("Festival broadcast push skipped — no tokens");
    return { success: 0, failure: 0, total: 0 };
  }

  let success = 0;
  let failure = 0;
  const chunkSize = 500;

  for (let i = 0; i < tokens.length; i += chunkSize) {
    const chunk = tokens.slice(i, i + chunkSize);
    const response = await getMessaging().sendEachForMulticast({
      tokens: chunk,
      notification: { title, body },
      data: {
        type: "festival_announcement",
      },
      android: {
        priority: "high",
        notification: {
          channelId: "seolleyeon_high_importance",
        },
      },
      apns: {
        headers: { "apns-priority": "10" },
        payload: { aps: { sound: "default" } },
      },
      webpush: {
        headers: { Urgency: "high" },
        notification: {
          title,
          body,
          icon: "https://seolleyeon-festival.web.app/icons/Icon-192.png",
        },
        fcmOptions: {
          link: "https://seolleyeon-festival.web.app/",
        },
      },
    });
    success += response.successCount;
    failure += response.failureCount;
  }

  logger.info("Festival broadcast push sent", {
    title,
    body,
    total: tokens.length,
    success,
    failure,
  });

  return { success, failure, total: tokens.length };
}

/** Ops: broadcast announcement to all registered push tokens. */
function kstDateKey(date = new Date()): string {
  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function readTimestamp(value: unknown): Date | null {
  if (value instanceof Timestamp) return value.toDate();
  if (value instanceof Date) return value;
  return null;
}

/** 21:05 KST — 추천 공개 완료 푸시 (하루 1회). */
export const festivalRevealCompletePushTick = onSchedule(
  {
    schedule: "5 21 * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
  },
  async () => {
    const scheduleRef = db.doc(SCHEDULE_PATH);
    const snap = await scheduleRef.get();
    if (!snap.exists || snap.data()?.enabled !== true) return;

    const data = snap.data() ?? {};
    const revealAt = readTimestamp(data.recommendationsRevealAt);
    if (!revealAt || Date.now() < revealAt.getTime()) return;

    const sentAt = readTimestamp(data.revealCompletePushSentAt);
    const todayKey = kstDateKey();
    if (sentAt && kstDateKey(sentAt) === todayKey) return;

    const result = await sendFestivalBroadcastPush(REVEAL_COMPLETE_PUSH_BODY);
    await scheduleRef.set(
      {
        revealCompletePushSentAt: FieldValue.serverTimestamp(),
        revealCompletePushSuccessCount: result.success,
        revealCompletePushTotalCount: result.total,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    logger.info("Festival reveal-complete push scheduled send", result);
  }
);

export const sendFestivalRevealAnnouncementHttp = onRequest(
  {
    region: "asia-northeast3",
    invoker: "public",
  },
  async (req, res) => {
    if (req.get("x-seed-key") !== SEED_HTTP_KEY) {
      res.status(403).json({ error: "forbidden" });
      return;
    }

    let bodyText = DEFAULT_BODY;
    try {
      const body =
        typeof req.body === "string" && req.body.trim()
          ? (JSON.parse(req.body) as Record<string, string>)
          : ((req.body ?? {}) as Record<string, string>);
      if (body.type === "reveal_complete") bodyText = REVEAL_COMPLETE_PUSH_BODY;
      if (body.message?.trim()) bodyText = body.message.trim();
      if (body.body?.trim()) bodyText = body.body.trim();
    } catch {
      // use default
    }

    try {
      const title =
        typeof req.body === "object" &&
        req.body &&
        "title" in (req.body as object)
          ? asString((req.body as Record<string, string>).title, PUSH_TITLE)
          : PUSH_TITLE;
      const result = await sendFestivalBroadcastPush(bodyText, title);
      res.json({ ok: true, ...result, body: bodyText });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logger.error("sendFestivalRevealAnnouncementHttp failed", { error: message });
      res.status(500).json({ error: message });
    }
  }
);
