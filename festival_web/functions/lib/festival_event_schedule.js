"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.festivalEventScheduleTick = exports.setFestivalEventScheduleHttp = void 0;
exports.loadFestivalEventSchedule = loadFestivalEventSchedule;
exports.isFestivalEventScheduleActive = isFestivalEventScheduleActive;
exports.areFestivalRecommendationsFrozen = areFestivalRecommendationsFrozen;
exports.runEventBatchRecommendations = runEventBatchRecommendations;
const scheduler_1 = require("firebase-functions/v2/scheduler");
const https_1 = require("firebase-functions/v2/https");
const logger = __importStar(require("firebase-functions/logger"));
const firestore_1 = require("firebase-admin/firestore");
const festival_recommendations_1 = require("./festival_recommendations");
const festival_embeddings_1 = require("./festival_embeddings");
const db = (0, firestore_1.getFirestore)();
const SCHEDULE_PATH = "festivalSettings/schedule";
const SEED_HTTP_KEY = "seolleyeon-festival-clip-init";
function kstIso(dateStr, timeStr) {
    return `${dateStr}T${timeStr}:00+09:00`;
}
function kstNow() {
    return new Date(Date.now() + 9 * 60 * 60 * 1000);
}
function kstDayStartIso(dateStr) {
    return `${dateStr}T00:00:00+09:00`;
}
function readTimestamp(value) {
    return value instanceof firestore_1.Timestamp ? value : null;
}
function isWithinCohortWindow(timestamp, startAt, lockAt) {
    if (!timestamp)
        return false;
    const ms = timestamp.toMillis();
    return ms >= startAt.toMillis() && ms <= lockAt.toMillis();
}
async function loadFestivalEventSchedule() {
    const ref = db.doc(SCHEDULE_PATH);
    const snap = await ref.get();
    if (!snap.exists)
        return null;
    const data = snap.data();
    if (!data?.enabled)
        return null;
    if (!data.batchRecommendationsAt)
        return null;
    return { ...data, ref };
}
/** 이벤트 일정이 켜져 있으면 개별 트리거 추천·임베딩 갱신을 막고 스케줄러만 사용. */
async function isFestivalEventScheduleActive() {
    const schedule = await loadFestivalEventSchedule();
    return schedule != null;
}
/** 공개 시각 이후에는 CLIP·추천 갱신을 하지 않음. */
async function areFestivalRecommendationsFrozen() {
    const schedule = await loadFestivalEventSchedule();
    if (!schedule)
        return false;
    return Date.now() >= schedule.recommendationsRevealAt.toMillis();
}
async function runEventBatchRecommendations() {
    const schedule = await loadFestivalEventSchedule();
    if (!schedule)
        return { success: 0, total: 0 };
    const aiSample = await db.collection("festivalAiEmbeddings").doc("f1").get();
    if (!aiSample.exists) {
        logger.info("AI embeddings missing — running full seed before batch");
        await (0, festival_embeddings_1.seedAllFestivalEmbeddings)();
    }
    const cohortStartAt = schedule.cohortStartAt ??
        firestore_1.Timestamp.fromDate(new Date(kstDayStartIso(kstNow().toISOString().slice(0, 10))));
    const lockAt = schedule.profileTasteLockAt;
    const ticketsSnap = await db
        .collection("festivalTickets")
        .where("tasteCompleted", "==", true)
        .get();
    const eligibleTicketIds = new Set();
    for (const doc of ticketsSnap.docs) {
        const data = doc.data();
        const profileCompletedAt = readTimestamp(data.profileCompletedAt);
        const tasteCompletedAt = readTimestamp(data.tasteCompletedAt);
        if (isWithinCohortWindow(profileCompletedAt, cohortStartAt, lockAt) &&
            isWithinCohortWindow(tasteCompletedAt, cohortStartAt, lockAt)) {
            eligibleTicketIds.add(doc.id);
        }
    }
    let success = 0;
    for (const doc of ticketsSnap.docs) {
        if (!eligibleTicketIds.has(doc.id))
            continue;
        const profileSnap = await db
            .collection("festivalProfiles")
            .doc(doc.id)
            .get();
        const photoUrl = String(profileSnap.data()?.photoUrl ?? "").trim();
        if (!profileSnap.exists || !photoUrl)
            continue;
        try {
            const result = await (0, festival_recommendations_1.generateRecommendationsForTicket)(doc.id, "scheduled_event_batch", { eligibleCandidateTicketIds: eligibleTicketIds });
            if (result.success)
                success += 1;
        }
        catch (error) {
            logger.warn("Event batch rec failed", {
                ticketId: doc.id,
                error: error instanceof Error ? error.message : String(error),
            });
        }
    }
    return { success, total: eligibleTicketIds.size };
}
/** Set event schedule via HTTP (debug / ops). */
exports.setFestivalEventScheduleHttp = (0, https_1.onRequest)({
    region: "asia-northeast3",
    invoker: "public",
}, async (req, res) => {
    if (req.get("x-seed-key") !== SEED_HTTP_KEY) {
        res.status(403).json({ error: "forbidden" });
        return;
    }
    let body = {};
    try {
        if (typeof req.body === "string" && req.body.trim()) {
            body = JSON.parse(req.body);
        }
        else if (req.body && typeof req.body === "object") {
            body = req.body;
        }
    }
    catch (error) {
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
        await db.doc(SCHEDULE_PATH).set({
            enabled: true,
            title: body.title ?? "디버그 일정",
            cohortStartAt: firestore_1.Timestamp.fromDate(new Date(kstIso(date, cohortStart))),
            profileTasteLockAt: firestore_1.Timestamp.fromDate(new Date(kstIso(date, lock))),
            batchRecommendationsAt: firestore_1.Timestamp.fromDate(new Date(kstIso(date, batch))),
            recommendationsRevealAt: firestore_1.Timestamp.fromDate(new Date(kstIso(date, reveal))),
            batchCompletedAt: firestore_1.FieldValue.delete(),
            batchSuccessCount: firestore_1.FieldValue.delete(),
            batchTotalCount: firestore_1.FieldValue.delete(),
            batchLastError: firestore_1.FieldValue.delete(),
            batchLastRunAt: firestore_1.FieldValue.delete(),
            updatedAt: firestore_1.FieldValue.serverTimestamp(),
        }, { merge: true });
        res.json({
            ok: true,
            cohortStartAt: kstIso(date, cohortStart),
            profileTasteLockAt: kstIso(date, lock),
            batchRecommendationsAt: kstIso(date, batch),
            recommendationsRevealAt: kstIso(date, reveal),
        });
    }
    catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        logger.error("setFestivalEventScheduleHttp failed", { error: message });
        res.status(500).json({ error: message });
    }
});
/** Every minute KST: run CLIP batch between batchRecommendationsAt and recommendationsRevealAt. */
exports.festivalEventScheduleTick = (0, scheduler_1.onSchedule)({
    schedule: "* * * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
    memory: "2GiB",
    timeoutSeconds: 540,
    maxInstances: 1,
}, async () => {
    const schedule = await loadFestivalEventSchedule();
    if (!schedule)
        return;
    const now = Date.now();
    const batchAt = schedule.batchRecommendationsAt.toMillis();
    const revealAt = schedule.recommendationsRevealAt.toMillis();
    if (now < batchAt)
        return;
    if (now >= revealAt)
        return;
    logger.info("Festival event batch starting", {
        kst: kstNow().toISOString(),
        title: schedule.title,
    });
    try {
        const result = await runEventBatchRecommendations();
        await schedule.ref.set({
            batchLastRunAt: firestore_1.FieldValue.serverTimestamp(),
            batchSuccessCount: result.success,
            batchTotalCount: result.total,
            batchLastError: firestore_1.FieldValue.delete(),
            updatedAt: firestore_1.FieldValue.serverTimestamp(),
        }, { merge: true });
        logger.info("Festival event batch completed", result);
    }
    catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        await schedule.ref.set({
            batchLastError: message,
            updatedAt: firestore_1.FieldValue.serverTimestamp(),
        }, { merge: true });
        logger.error("Festival event batch failed", { error: message });
    }
});
//# sourceMappingURL=festival_event_schedule.js.map