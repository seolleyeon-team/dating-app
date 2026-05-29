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
  cohortStartAt?: Timestamp;
  profileTasteLockAt: Timestamp;
  batchRecommendationsAt: Timestamp;
  recommendationsRevealAt: Timestamp;
  batchCompletedAt?: Timestamp;
  title?: string;
}

function kstNow(): Date {
  return new Date(Date.now() + 9 * 60 * 60 * 1000);
}

function kstDayStartIso(dateStr: string): string {
  return `${dateStr}T00:00:00+09:00`;
}

function readTimestamp(value: unknown): Timestamp | null {
  return value instanceof Timestamp ? value : null;
}

function isWithinCohortWindow(
  timestamp: Timestamp | null,
  startAt: Timestamp,
  lockAt: Timestamp
): boolean {
  if (!timestamp) return false;
  const ms = timestamp.toMillis();
  return ms >= startAt.toMillis() && ms <= lockAt.toMillis();
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
  const schedule = await loadFestivalEventSchedule();
  if (!schedule) return { success: 0, total: 0 };

  const aiSample = await db.collection("festivalAiEmbeddings").doc("f1").get();
  if (!aiSample.exists) {
    logger.info("AI embeddings missing — running full seed before batch");
    await seedAllFestivalEmbeddings();
  }

  const cohortStartAt =
    schedule.cohortStartAt ??
    Timestamp.fromDate(
      new Date(kstDayStartIso(kstNow().toISOString().slice(0, 10)))
    );
  const lockAt = schedule.profileTasteLockAt;
  const ticketsSnap = await db
    .collection("festivalTickets")
    .where("tasteCompleted", "==", true)
    .get();

  const eligibleTicketIds = new Set<string>();
  for (const doc of ticketsSnap.docs) {
    const data = doc.data();
    const profileCompletedAt = readTimestamp(data.profileCompletedAt);
    const tasteCompletedAt = readTimestamp(data.tasteCompletedAt);
    if (
      isWithinCohortWindow(profileCompletedAt, cohortStartAt, lockAt) &&
      isWithinCohortWindow(tasteCompletedAt, cohortStartAt, lockAt)
    ) {
      eligibleTicketIds.add(doc.id);
    }
  }

  let success = 0;
  for (const doc of ticketsSnap.docs) {
    if (!eligibleTicketIds.has(doc.id)) continue;
    const profileSnap = await db
      .collection("festivalProfiles")
      .doc(doc.id)
      .get();
    const photoUrl = String(profileSnap.data()?.photoUrl ?? "").trim();
    if (!profileSnap.exists || !photoUrl) continue;

    try {
      const result = await generateRecommendationsForTicket(
        doc.id,
        "scheduled_event_batch",
        { eligibleCandidateTicketIds: eligibleTicketIds }
      );
      if (result.success) success += 1;
    } catch (error) {
      logger.warn("Event batch rec failed", {
        ticketId: doc.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { success, total: eligibleTicketIds.size };
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
    const cohortStart = body.cohortStart ?? "00:00";
    const lock = body.lock ?? "20:30";
    const batch = body.batch ?? "20:31";
    const reveal = body.reveal ?? "21:00";

    try {
      await db.doc(SCHEDULE_PATH).set(
        {
          enabled: true,
          title: body.title ?? "디버그 일정",
          cohortStartAt: Timestamp.fromDate(new Date(kstIso(date, cohortStart))),
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
        cohortStartAt: kstIso(date, cohortStart),
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
