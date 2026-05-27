import { onSchedule } from "firebase-functions/v2/scheduler";
import { onRequest } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import {
  DocumentReference,
  FieldValue,
  getFirestore,
  Timestamp,
} from "firebase-admin/firestore";
import { generateRecommendationsForTicket } from "./festival_recommendations";
import { seedAllFestivalEmbeddings } from "./festival_embeddings";

const db = getFirestore();
const SCHEDULE_PATH = "festivalSettings/schedule";
const SEED_HTTP_KEY = "seolleyeon-festival-clip-init";

function kstIso(dateStr: string, timeStr: string): string {
  return `${dateStr}T${timeStr}:00+09:00`;
}

interface FestivalSchedule {
  enabled: boolean;
  profileTasteLockAt: Timestamp;
  batchRecommendationsAt: Timestamp;
  recommendationsRevealAt: Timestamp;
  batchCompletedAt?: Timestamp;
  title?: string;
}

function kstNow(): Date {
  return new Date(Date.now() + 9 * 60 * 60 * 1000);
}

export async function loadFestivalEventSchedule(): Promise<
  (FestivalSchedule & { ref: DocumentReference }) | null
> {
  const ref = db.doc(SCHEDULE_PATH);
  const snap = await ref.get();
  if (!snap.exists) return null;
  const data = snap.data() as FestivalSchedule | undefined;
  if (!data?.enabled) return null;
  if (!data.batchRecommendationsAt) return null;
  return { ...data, ref };
}

/** 이벤트 일정이 켜져 있으면 개별 트리거 추천·임베딩 갱신을 막고 스케줄러만 사용. */
export async function isFestivalEventScheduleActive(): Promise<boolean> {
  const schedule = await loadFestivalEventSchedule();
  return schedule != null;
}

/** 공개 시각 이후에는 CLIP·추천 갱신을 하지 않음. */
export async function areFestivalRecommendationsFrozen(): Promise<boolean> {
  const schedule = await loadFestivalEventSchedule();
  if (!schedule) return false;
  return Date.now() >= schedule.recommendationsRevealAt.toMillis();
}

export async function runEventBatchRecommendations(): Promise<{
  success: number;
  total: number;
}> {
  const aiSample = await db.collection("festivalAiEmbeddings").doc("f1").get();
  if (!aiSample.exists) {
    logger.info("AI embeddings missing — running full seed before batch");
    await seedAllFestivalEmbeddings();
  }

  const ticketsSnap = await db
    .collection("festivalTickets")
    .where("tasteCompleted", "==", true)
    .get();

  let success = 0;
  for (const doc of ticketsSnap.docs) {
    const profileSnap = await db
      .collection("festivalProfiles")
      .doc(doc.id)
      .get();
    const photoUrl = String(profileSnap.data()?.photoUrl ?? "").trim();
    if (!profileSnap.exists || !photoUrl) continue;

    try {
      const result = await generateRecommendationsForTicket(
        doc.id,
        "scheduled_event_batch"
      );
      if (result.success) success += 1;
    } catch (error) {
      logger.warn("Event batch rec failed", {
        ticketId: doc.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { success, total: ticketsSnap.size };
}

/** Set event schedule via HTTP (debug / ops). */
export const setFestivalEventScheduleHttp = onRequest(
  {
    region: "asia-northeast3",
    invoker: "public",
  },
  async (req, res) => {
    if (req.get("x-seed-key") !== SEED_HTTP_KEY) {
      res.status(403).json({ error: "forbidden" });
      return;
    }

    let body: Record<string, string> = {};
    try {
      if (typeof req.body === "string" && req.body.trim()) {
        body = JSON.parse(req.body) as Record<string, string>;
      } else if (req.body && typeof req.body === "object") {
        body = req.body as Record<string, string>;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      res.status(400).json({ error: "invalid_json", message });
      return;
    }
    const date = body.date ?? "2026-05-27";
    const lock = body.lock ?? "19:30";
    const batch = body.batch ?? "19:31";
    const reveal = body.reveal ?? "20:00";

    try {
      await db.doc(SCHEDULE_PATH).set(
        {
          enabled: true,
          title: body.title ?? "디버그 일정",
          profileTasteLockAt: Timestamp.fromDate(new Date(kstIso(date, lock))),
          batchRecommendationsAt: Timestamp.fromDate(
            new Date(kstIso(date, batch))
          ),
          recommendationsRevealAt: Timestamp.fromDate(
            new Date(kstIso(date, reveal))
          ),
          batchCompletedAt: FieldValue.delete(),
          batchSuccessCount: FieldValue.delete(),
          batchTotalCount: FieldValue.delete(),
          batchLastError: FieldValue.delete(),
          batchLastRunAt: FieldValue.delete(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );

      res.json({
        ok: true,
        profileTasteLockAt: kstIso(date, lock),
        batchRecommendationsAt: kstIso(date, batch),
        recommendationsRevealAt: kstIso(date, reveal),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logger.error("setFestivalEventScheduleHttp failed", { error: message });
      res.status(500).json({ error: message });
    }
  }
);

/** Every minute KST: run CLIP batch between batchRecommendationsAt and recommendationsRevealAt. */
export const festivalEventScheduleTick = onSchedule(
  {
    schedule: "* * * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
    memory: "2GiB",
    timeoutSeconds: 540,
    maxInstances: 1,
  },
  async () => {
    const schedule = await loadFestivalEventSchedule();
    if (!schedule) return;

    const now = Date.now();
    const batchAt = schedule.batchRecommendationsAt.toMillis();
    const revealAt = schedule.recommendationsRevealAt.toMillis();
    if (now < batchAt) return;
    if (now >= revealAt) return;

    logger.info("Festival event batch starting", {
      kst: kstNow().toISOString(),
      title: schedule.title,
    });

    try {
      const result = await runEventBatchRecommendations();
      await schedule.ref.set(
        {
          batchLastRunAt: FieldValue.serverTimestamp(),
          batchSuccessCount: result.success,
          batchTotalCount: result.total,
          batchLastError: FieldValue.delete(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      logger.info("Festival event batch completed", result);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await schedule.ref.set(
        {
          batchLastError: message,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      logger.error("Festival event batch failed", { error: message });
    }
  }
);
