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
exports.onFestivalChatMessageCreated = exports.seedFestivalEmbeddingsHttp = exports.seedFestivalEmbeddings = exports.onFestivalProfilePhotoUpdated = exports.refreshFestivalRecommendations = exports.onFestivalTasteCompleted = exports.onFestivalRecommendationJobCreated = exports.generateFestivalDailyRecommendations = void 0;
const v2_1 = require("firebase-functions/v2");
const firestore_1 = require("firebase-functions/v2/firestore");
const logger = __importStar(require("firebase-functions/logger"));
const app_1 = require("firebase-admin/app");
const firestore_2 = require("firebase-admin/firestore");
const messaging_1 = require("firebase-admin/messaging");
(0, app_1.initializeApp)();
const db = (0, firestore_2.getFirestore)();
(0, v2_1.setGlobalOptions)({
    region: "asia-northeast3",
    maxInstances: 10,
});
const PUSH_TITLE = "설레연";
const PUSH_BODY = "새 메시지가 왔습니다";
function asString(v, fallback = "") {
    if (typeof v === "string")
        return v;
    if (typeof v === "number" || typeof v === "boolean")
        return String(v);
    return fallback;
}
function asStringArray(v) {
    if (!Array.isArray(v))
        return [];
    return v.map((item) => asString(item, "").trim()).filter(Boolean);
}
async function fetchFestivalPushTokens(uid) {
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
async function deleteInvalidTokens(uid, tokens) {
    if (tokens.length === 0)
        return;
    const batch = db.batch();
    for (const token of tokens) {
        batch.delete(db.collection("festivalPushTokens").doc(uid).collection("tokens").doc(token));
    }
    await batch.commit();
}
async function sendFestivalChatPush(targetUserIds, roomId) {
    const uniqueUserIds = [...new Set(targetUserIds.filter((uid) => uid.length > 0))];
    if (uniqueUserIds.length === 0)
        return;
    const tokenLists = await Promise.all(uniqueUserIds.map((uid) => fetchFestivalPushTokens(uid)));
    const tokens = tokenLists.flat();
    if (tokens.length === 0) {
        logger.info("No festival push tokens", { targetUserIds: uniqueUserIds, roomId });
        return;
    }
    const response = await (0, messaging_1.getMessaging)().sendEachForMulticast({
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
    const invalidTokens = [];
    response.responses.forEach((result, index) => {
        if (!result.success) {
            const token = tokens[index];
            if (token)
                invalidTokens.push(token);
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
var festival_recommendations_1 = require("./festival_recommendations");
Object.defineProperty(exports, "generateFestivalDailyRecommendations", { enumerable: true, get: function () { return festival_recommendations_1.generateFestivalDailyRecommendations; } });
Object.defineProperty(exports, "onFestivalRecommendationJobCreated", { enumerable: true, get: function () { return festival_recommendations_1.onFestivalRecommendationJobCreated; } });
Object.defineProperty(exports, "onFestivalTasteCompleted", { enumerable: true, get: function () { return festival_recommendations_1.onFestivalTasteCompleted; } });
Object.defineProperty(exports, "refreshFestivalRecommendations", { enumerable: true, get: function () { return festival_recommendations_1.refreshFestivalRecommendations; } });
var festival_embeddings_1 = require("./festival_embeddings");
Object.defineProperty(exports, "onFestivalProfilePhotoUpdated", { enumerable: true, get: function () { return festival_embeddings_1.onFestivalProfilePhotoUpdated; } });
Object.defineProperty(exports, "seedFestivalEmbeddings", { enumerable: true, get: function () { return festival_embeddings_1.seedFestivalEmbeddings; } });
Object.defineProperty(exports, "seedFestivalEmbeddingsHttp", { enumerable: true, get: function () { return festival_embeddings_1.seedFestivalEmbeddingsHttp; } });
exports.onFestivalChatMessageCreated = (0, firestore_1.onDocumentCreated)("festivalChatRooms/{roomId}/messages/{messageId}", async (event) => {
    const snap = event.data;
    if (!snap)
        return;
    const roomId = event.params.roomId;
    const message = snap.data();
    const senderUid = asString(message.senderUid ?? "");
    if (!senderUid)
        return;
    const roomSnap = await db.collection("festivalChatRooms").doc(roomId).get();
    if (!roomSnap.exists)
        return;
    const room = roomSnap.data() ?? {};
    const participantUids = asStringArray(room.participantUids);
    const targetUserIds = participantUids.filter((uid) => uid !== senderUid);
    if (targetUserIds.length === 0)
        return;
    await sendFestivalChatPush(targetUserIds, roomId);
});
//# sourceMappingURL=index.js.map