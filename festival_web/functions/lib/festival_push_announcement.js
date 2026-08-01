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
exports.sendFestivalRevealAnnouncementHttp = exports.festivalRevealCompletePushTick = exports.REVEAL_COMPLETE_PUSH_BODY = void 0;
exports.sendFestivalBroadcastPush = sendFestivalBroadcastPush;
const https_1 = require("firebase-functions/v2/https");
const scheduler_1 = require("firebase-functions/v2/scheduler");
const logger = __importStar(require("firebase-functions/logger"));
const firestore_1 = require("firebase-admin/firestore");
const messaging_1 = require("firebase-admin/messaging");
const db = (0, firestore_1.getFirestore)();
const SCHEDULE_PATH = "festivalSettings/schedule";
const SEED_HTTP_KEY = "seolleyeon-festival-clip-init";
const PUSH_TITLE = "설레연";
const DEFAULT_BODY = "추천 풀 확보를 위해 9시에 추천 결과가 공개됩니다";
exports.REVEAL_COMPLETE_PUSH_BODY = "설레연 추천이 완료되었습니다! 맘에 드시는 분과 이야기를 나눠보세요!";
function asString(v, fallback = "") {
    if (typeof v === "string")
        return v;
    if (typeof v === "number" || typeof v === "boolean")
        return String(v);
    return fallback;
}
async function collectAllPushTokens() {
    const snap = await db.collectionGroup("tokens").get();
    const tokens = new Set();
    for (const doc of snap.docs) {
        const path = doc.ref.path;
        if (!path.startsWith("festivalPushTokens/"))
            continue;
        if (doc.data().notificationsEnabled === false)
            continue;
        const token = asString(doc.data().token ?? doc.id).trim();
        if (token)
            tokens.add(token);
    }
    return [...tokens];
}
async function sendFestivalBroadcastPush(body, title = PUSH_TITLE) {
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
        const response = await (0, messaging_1.getMessaging)().sendEachForMulticast({
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
function kstDateKey(date = new Date()) {
    const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
    const y = kst.getUTCFullYear();
    const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
    const d = String(kst.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}
function readTimestamp(value) {
    if (value instanceof firestore_1.Timestamp)
        return value.toDate();
    if (value instanceof Date)
        return value;
    return null;
}
/** 21:05 KST — 추천 공개 완료 푸시 (하루 1회). */
exports.festivalRevealCompletePushTick = (0, scheduler_1.onSchedule)({
    schedule: "5 21 * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
}, async () => {
    const scheduleRef = db.doc(SCHEDULE_PATH);
    const snap = await scheduleRef.get();
    if (!snap.exists || snap.data()?.enabled !== true)
        return;
    const data = snap.data() ?? {};
    const revealAt = readTimestamp(data.recommendationsRevealAt);
    if (!revealAt || Date.now() < revealAt.getTime())
        return;
    const sentAt = readTimestamp(data.revealCompletePushSentAt);
    const todayKey = kstDateKey();
    if (sentAt && kstDateKey(sentAt) === todayKey)
        return;
    const result = await sendFestivalBroadcastPush(exports.REVEAL_COMPLETE_PUSH_BODY);
    await scheduleRef.set({
        revealCompletePushSentAt: firestore_1.FieldValue.serverTimestamp(),
        revealCompletePushSuccessCount: result.success,
        revealCompletePushTotalCount: result.total,
        updatedAt: firestore_1.FieldValue.serverTimestamp(),
    }, { merge: true });
    logger.info("Festival reveal-complete push scheduled send", result);
});
exports.sendFestivalRevealAnnouncementHttp = (0, https_1.onRequest)({
    region: "asia-northeast3",
    invoker: "public",
}, async (req, res) => {
    if (req.get("x-seed-key") !== SEED_HTTP_KEY) {
        res.status(403).json({ error: "forbidden" });
        return;
    }
    let bodyText = DEFAULT_BODY;
    try {
        const body = typeof req.body === "string" && req.body.trim()
            ? JSON.parse(req.body)
            : (req.body ?? {});
        if (body.type === "reveal_complete")
            bodyText = exports.REVEAL_COMPLETE_PUSH_BODY;
        if (body.message?.trim())
            bodyText = body.message.trim();
        if (body.body?.trim())
            bodyText = body.body.trim();
    }
    catch {
        // use default
    }
    try {
        const title = typeof req.body === "object" &&
            req.body &&
            "title" in req.body
            ? asString(req.body.title, PUSH_TITLE)
            : PUSH_TITLE;
        const result = await sendFestivalBroadcastPush(bodyText, title);
        res.json({ ok: true, ...result, body: bodyText });
    }
    catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        logger.error("sendFestivalRevealAnnouncementHttp failed", { error: message });
        res.status(500).json({ error: message });
    }
});
//# sourceMappingURL=festival_push_announcement.js.map