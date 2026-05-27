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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.chatProfilePhotoBucket = chatProfilePhotoBucket;
exports.buildAvatarSourceRecoveryUserFields = buildAvatarSourceRecoveryUserFields;
exports.buildChatProfilePhotoStoragePath = buildChatProfilePhotoStoragePath;
exports.shouldSupersedeAvatarJobStatus = shouldSupersedeAvatarJobStatus;
exports.upsertSourcePhotoEntry = upsertSourcePhotoEntry;
exports.buildChatRealPhotoMetadata = buildChatRealPhotoMetadata;
exports.buildDisabledChatRealPhotoMetadata = buildDisabledChatRealPhotoMetadata;
exports.buildPrivateMediaPayload = buildPrivateMediaPayload;
exports.buildAvatarPayload = buildAvatarPayload;
exports.buildClipPayload = buildClipPayload;
exports.hasLockedAvatarSource = hasLockedAvatarSource;
exports.avatarPresentationGenderFromUserData = avatarPresentationGenderFromUserData;
exports.planAvatarUploadState = planAvatarUploadState;
exports.queueMode = queueMode;
exports.buildDeterministicCloudTaskName = buildDeterministicCloudTaskName;
exports.isCloudTasksAlreadyExistsError = isCloudTasksAlreadyExistsError;
exports.summarizeQueueWriteState = summarizeQueueWriteState;
exports.buildCloudTaskHttpRequest = buildCloudTaskHttpRequest;
exports.cloudTaskDispatchDeadlineSeconds = cloudTaskDispatchDeadlineSeconds;
exports.createUploadAvatarSourcePhotoFunction = createUploadAvatarSourcePhotoFunction;
const pubsub_1 = require("@google-cloud/pubsub");
const tasks_1 = require("@google-cloud/tasks");
const crypto_1 = require("crypto");
const storage_1 = require("firebase-admin/storage");
const firestore_1 = require("firebase-admin/firestore");
const https_1 = require("firebase-functions/v2/https");
const logger = __importStar(require("firebase-functions/logger"));
const sharp_1 = __importDefault(require("sharp"));
const DEFAULT_REGION = "asia-northeast3";
const DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos";
const DEFAULT_CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-chat-profile-photos";
const DEFAULT_AVATAR_MODEL_ID = "black-forest-labs/FLUX.2-klein-4B";
const AVATAR_MODEL_VERSION = "flux2_klein_4b_v1";
const CLIP_EMBEDDING_VERSION = "clip-vit-large-patch14_v1";
const CHAT_REAL_PHOTO_CONSENT_VERSION = "chat_real_photo_visibility_v1";
const MAX_IMAGE_BYTES = Number(process.env.MAX_SOURCE_PHOTO_BYTES ?? 10 * 1024 * 1024);
const MAX_INPUT_PIXELS = Number(process.env.MAX_SOURCE_PHOTO_PIXELS ?? 40_000_000);
function envValue(name, fallback) {
    const value = process.env[name]?.trim();
    return value && value.length > 0 ? value : fallback;
}
function truthyEnv(name) {
    return ["1", "true", "yes", "y", "on"].includes(process.env[name]?.trim().toLowerCase() ?? "");
}
function isProductionEnvironment() {
    const environment = process.env.ENVIRONMENT?.trim().toLowerCase();
    return (environment === "production" ||
        environment === "prod" ||
        process.env.NODE_ENV === "production");
}
function isLocalEnvironment() {
    const environment = process.env.ENVIRONMENT?.trim().toLowerCase();
    return (environment === "local" ||
        environment === "development" ||
        environment === "dev");
}
function allowInsecureLocalWorkerInvocation() {
    return (isLocalEnvironment() &&
        (truthyEnv("ALLOW_INSECURE_WORKER_LOCAL") ||
            truthyEnv("AVATAR_WORKER_ALLOW_INSECURE_LOCAL")));
}
function clipEmbeddingQueueEnabled() {
    const raw = process.env.CLIP_EMBEDDING_QUEUE_ENABLED?.trim().toLowerCase();
    if (!raw)
        return true;
    return ["1", "true", "yes", "y", "on"].includes(raw);
}
function sourcePhotoBucket() {
    return envValue("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET);
}
function chatProfilePhotoBucket() {
    return envValue("CHAT_PROFILE_PHOTO_BUCKET", DEFAULT_CHAT_PROFILE_PHOTO_BUCKET);
}
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function readMap(value) {
    return isRecord(value) ? value : {};
}
function asString(value) {
    return typeof value === "string" ? value.trim() : "";
}
function safeDecodeUriComponent(value) {
    try {
        return decodeURIComponent(value);
    }
    catch {
        return value;
    }
}
function requirePathSegment(value, label) {
    const normalized = value.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
        throw new https_1.HttpsError("invalid-argument", `${label} is not a safe path segment.`);
    }
    return normalized;
}
function sha256Hex(bytes) {
    return (0, crypto_1.createHash)("sha256").update(bytes).digest("hex");
}
function buildPhotoId(imageSha256) {
    if (!/^[a-f0-9]{64}$/i.test(imageSha256)) {
        throw new https_1.HttpsError("invalid-argument", "Invalid image digest.");
    }
    return `src_${imageSha256.slice(0, 16)}`;
}
function buildNewAvatarSourcePhotoId(imageSha256) {
    return `${buildPhotoId(imageSha256)}_${(0, crypto_1.randomUUID)().replace(/-/g, "").slice(0, 12)}`;
}
function buildAvatarJobId(uid, photoId) {
    const digest = sha256Hex(`${uid}:${photoId}:avatar_generation_v1`);
    return `avatar_job_${digest.slice(0, 24)}`;
}
function buildAvatarSourceRecoveryUserFields(jobId, sourceSelectionVersion) {
    return {
        "onboarding.avatarGenerationJobId": requirePathSegment(jobId, "jobId"),
        "onboarding.avatarSourceSelectionVersion": sourceSelectionVersion,
    };
}
function buildSourcePhotoStoragePath(uid, photoId) {
    return `users/${requirePathSegment(uid, "uid")}/source/${requirePathSegment(photoId, "photoId")}.jpg`;
}
function buildChatProfilePhotoStoragePath(uid, photoId) {
    return `users/${requirePathSegment(uid, "uid")}/chat-profile/${requirePathSegment(photoId, "photoId")}.jpg`;
}
function buildGcsUri(bucket, storagePath) {
    return `gs://${bucket}/${storagePath}`;
}
function normalizeContentType(value) {
    const raw = asString(value).toLowerCase().split(";")[0].trim();
    if (raw === "image/jpg" || raw === "image/jpeg")
        return "image/jpeg";
    if (raw === "image/png")
        return "image/png";
    if (raw === "image/webp")
        return "image/webp";
    throw new https_1.HttpsError("invalid-argument", "Unsupported image content type.");
}
function parseImagePayload(data) {
    const rawImage = asString(data.imageBase64 ?? data.base64Image ?? data.imageBytesBase64 ?? data.image);
    if (!rawImage) {
        throw new https_1.HttpsError("invalid-argument", "imageBase64 is required.");
    }
    let declaredContentType = asString(data.contentType);
    let base64 = rawImage;
    const dataUrlMatch = rawImage.match(/^data:([^;,]+);base64,([\s\S]+)$/);
    if (dataUrlMatch) {
        declaredContentType = dataUrlMatch[1];
        base64 = dataUrlMatch[2];
    }
    const contentType = normalizeContentType(declaredContentType);
    const compactBase64 = base64.replace(/\s/g, "");
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(compactBase64)) {
        throw new https_1.HttpsError("invalid-argument", "Image payload must be base64.");
    }
    const imageBytes = Buffer.from(compactBase64, "base64");
    if (imageBytes.length <= 0) {
        throw new https_1.HttpsError("invalid-argument", "Image payload is empty.");
    }
    if (imageBytes.length > MAX_IMAGE_BYTES) {
        throw new https_1.HttpsError("resource-exhausted", "Image payload is too large.");
    }
    return { imageBytes, contentType };
}
async function stripExifAndNormalizeImage(imageBytes) {
    try {
        const normalized = await (0, sharp_1.default)(imageBytes, {
            failOn: "error",
            limitInputPixels: MAX_INPUT_PIXELS,
        })
            .rotate()
            .flatten({ background: { r: 255, g: 255, b: 255 } })
            .jpeg({ quality: 92, mozjpeg: true })
            .toBuffer();
        if (normalized.length <= 0) {
            throw new https_1.HttpsError("invalid-argument", "Image normalization failed.");
        }
        if (normalized.length > MAX_IMAGE_BYTES) {
            throw new https_1.HttpsError("resource-exhausted", "Normalized image is too large.");
        }
        return normalized;
    }
    catch (error) {
        if (error instanceof https_1.HttpsError)
            throw error;
        throw new https_1.HttpsError("invalid-argument", "Invalid or unsupported image.");
    }
}
function readSourcePhotos(value) {
    if (!Array.isArray(value))
        return [];
    return value.filter(isRecord).map((entry) => ({ ...entry }));
}
function findCurrentDuplicateSource(sourcePhotos, imageSha256, currentAvatarSourcePhotoId) {
    const currentPhotoId = asString(currentAvatarSourcePhotoId);
    if (!currentPhotoId)
        return null;
    return (sourcePhotos.find((entry) => entry.status === "active" &&
        entry.avatarGenerationState === "current" &&
        entry.sha256 === imageSha256 &&
        entry.photoId === currentPhotoId) ?? null);
}
function nextAvatarSourceSelectionVersion(value) {
    const parsed = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(parsed) || parsed < 0)
        return 1;
    return Math.floor(parsed) + 1;
}
function shouldSupersedeAvatarJobStatus(value) {
    const status = asString(value).toLowerCase();
    return ![
        "",
        "approved",
        "failed",
        "cancelled",
        "canceled",
        "superseded",
    ].includes(status);
}
function upsertSourcePhotoEntry(sourcePhotos, sourceEntry, currentAvatarSourcePhotoId) {
    let replaced = false;
    const updated = sourcePhotos.map((entry) => {
        const entryPhotoId = asString(entry.photoId);
        if (entryPhotoId && entryPhotoId === sourceEntry.photoId) {
            replaced = true;
            return {
                ...entry,
                ...sourceEntry,
                uploadedAt: entry.uploadedAt ?? sourceEntry.uploadedAt,
            };
        }
        if (entryPhotoId === currentAvatarSourcePhotoId) {
            return {
                ...entry,
                avatarGenerationState: "superseded",
                updatedAt: sourceEntry.updatedAt ?? entry.updatedAt,
            };
        }
        return entry;
    });
    if (!replaced)
        updated.push(sourceEntry);
    return updated;
}
function activeSourcePhotoIds(sourcePhotos) {
    return Array.from(new Set(sourcePhotos
        .filter((entry) => entry.status === "active")
        .map((entry) => asString(entry.photoId))
        .filter(Boolean))).sort();
}
function buildChatRealPhotoMetadata(params) {
    const storageBucket = chatProfilePhotoBucket();
    const storagePath = buildChatProfilePhotoStoragePath(params.uid, params.photoId);
    return {
        photoId: params.photoId,
        enabled: true,
        consentVersion: CHAT_REAL_PHOTO_CONSENT_VERSION,
        sourcePhotoId: params.photoId,
        storageBucket,
        storagePath,
        gcsUri: buildGcsUri(storageBucket, storagePath),
        contentType: "image/jpeg",
        sizeBytes: params.sizeBytes,
        exifStripped: true,
        updatedAt: params.updatedAt,
    };
}
function buildDisabledChatRealPhotoMetadata(updatedAt) {
    return {
        photoId: "",
        enabled: false,
        consentVersion: CHAT_REAL_PHOTO_CONSENT_VERSION,
        sourcePhotoId: "",
        updatedAt,
    };
}
function buildPrivateMediaPayload(sourcePhotos, params = {}) {
    const payload = {
        sourcePhotos,
        photoConsent: {
            avatarGeneration: true,
            clipRecommendation: true,
            profileDisplayOriginalPhoto: false,
            chatPartnerRealPhotoDisclosure: params.chatPartnerRealPhotoDisclosure === true,
            sourcePhotoRetention: true,
            consentedAt: firestore_1.FieldValue.serverTimestamp(),
            version: "photo_consent_v3",
        },
        chatRealPhoto: params.chatRealPhoto ??
            buildDisabledChatRealPhotoMetadata(firestore_1.FieldValue.serverTimestamp()),
        clip: {
            embeddingStatus: "pending",
            embeddingVersion: CLIP_EMBEDDING_VERSION,
            sourcePhotoIds: activeSourcePhotoIds(sourcePhotos),
            updatedAt: firestore_1.FieldValue.serverTimestamp(),
        },
        updatedAt: firestore_1.FieldValue.serverTimestamp(),
    };
    if (params.currentAvatarSourcePhotoId !== undefined) {
        payload.currentAvatarSourcePhotoId = params.currentAvatarSourcePhotoId;
    }
    if (params.currentAvatarJobId !== undefined) {
        payload.currentAvatarJobId = params.currentAvatarJobId;
    }
    if (params.avatarSourceSelectionVersion !== undefined) {
        payload.avatarSourceSelectionVersion = params.avatarSourceSelectionVersion;
    }
    return payload;
}
function buildAvatarPayload(uid, photoId, gcsUri, jobId, avatarPresentationGender = "unknown") {
    const idempotencyKey = `${uid}:${photoId}:avatar_generation_v1`;
    return {
        jobId,
        uid,
        sourcePhotoIds: [photoId],
        sourcePhotoRefs: [gcsUri],
        avatarPresentationGender: normalizeAvatarPresentationGender(avatarPresentationGender),
        candidateCount: 4,
        modelId: DEFAULT_AVATAR_MODEL_ID,
        jobType: "avatar_generation",
        schemaVersion: "avatar_job_v1",
        idempotencyKey,
    };
}
function buildClipPayload(uid, photoId, gcsUri) {
    return {
        uid,
        sourcePhotoIds: [photoId],
        sourcePhotoRefs: [gcsUri],
        embeddingVersion: CLIP_EMBEDDING_VERSION,
        jobType: "clip_embedding",
        schemaVersion: "clip_job_v1",
        idempotencyKey: `${uid}:${photoId}:clip_embedding_v1`,
    };
}
function buildAvatarJobDoc(payload, preserveCreatedAt = false) {
    const doc = {
        jobId: payload.jobId,
        uid: payload.uid,
        model: {
            provider: "local_cloud_run",
            modelId: payload.modelId,
            version: AVATAR_MODEL_VERSION,
        },
        sourcePhotoIds: payload.sourcePhotoIds,
        sourcePhotoRefs: payload.sourcePhotoRefs,
        avatarPresentationGender: normalizeAvatarPresentationGender(payload.avatarPresentationGender),
        candidateCount: payload.candidateCount,
        status: "queued",
        createdAt: firestore_1.FieldValue.serverTimestamp(),
        updatedAt: firestore_1.FieldValue.serverTimestamp(),
        privacyMode: {
            preserveBroadCues: true,
            preserveExactIdentity: false,
            beautification: 0.0,
            target: "medium_resemblance_not_biometric_copy",
        },
        idempotencyKey: payload.idempotencyKey,
        schemaVersion: payload.schemaVersion,
    };
    if (preserveCreatedAt) {
        delete doc.createdAt;
    }
    return doc;
}
const NON_REGRESSING_AVATAR_JOB_STATUSES = new Set([
    "queued",
    "running",
    "qa_pending",
    "preview_ready",
    "approved",
    "completed",
]);
const RETRYABLE_AVATAR_JOB_STATUSES = new Set(["", "failed", "cancelled"]);
function isSafeApprovedAvatarUrl(value) {
    const url = asString(value);
    if (!url)
        return false;
    const decodedLower = safeDecodeUriComponent(url).toLowerCase();
    const privateBucketPattern = /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/;
    if (decodedLower.startsWith("gs://") ||
        decodedLower.startsWith("gcs://") ||
        privateBucketPattern.test(decodedLower) ||
        decodedLower.includes("x-goog-") ||
        decodedLower.includes("x-amz-") ||
        decodedLower.includes("googleaccessid") ||
        decodedLower.includes("signature=") ||
        decodedLower.includes("expires=") ||
        decodedLower.includes("awsaccesskeyid") ||
        decodedLower.includes("signedurl") ||
        /\/source\//.test(decodedLower) ||
        /\/jobs\//.test(decodedLower) ||
        /\/candidates\//.test(decodedLower)) {
        return false;
    }
    try {
        const parsed = new URL(url);
        const host = parsed.hostname.toLowerCase();
        const path = safeDecodeUriComponent(parsed.pathname).toLowerCase();
        const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
            ? host.replace(".storage.googleapis.com", "")
            : "";
        return (!privateBucketPattern.test(bucketFromVirtualHost) &&
            !/\/source\//.test(path) &&
            !/\/jobs\//.test(path) &&
            !/\/candidates\//.test(path));
    }
    catch {
        return false;
    }
}
function hasApprovedAvatarLock(userAvatar) {
    const avatar = readMap(userAvatar);
    return (asString(avatar.status).toLowerCase() === "approved" ||
        asString(avatar.approvedAvatarUrl).length > 0);
}
function hasLockedAvatarSource(privateData) {
    const data = readMap(privateData);
    return (asString(data.currentAvatarSourcePhotoId).length > 0 &&
        asString(data.currentAvatarJobId).length > 0);
}
function normalizeAvatarPresentationGender(value) {
    const raw = asString(value).toLowerCase();
    if (["male", "m", "man", "남성", "남자"].includes(raw))
        return "male";
    if (["female", "f", "woman", "여성", "여자"].includes(raw))
        return "female";
    if (["other", "non_binary", "non-binary", "nonbinary"].includes(raw))
        return "non_binary";
    if (["prefer_not_to_say", "prefer-not-to-say", "unknown", ""].includes(raw)) {
        return raw === "prefer_not_to_say" || raw === "prefer-not-to-say"
            ? "prefer_not_to_say"
            : "unknown";
    }
    return "unknown";
}
function avatarPresentationGenderFromUserData(userData) {
    const onboarding = readMap(userData.onboarding);
    return normalizeAvatarPresentationGender(onboarding.gender);
}
function isUndispatchedQueuedJob(params) {
    if (!params.existingJobExists)
        return false;
    const existingStatus = asString(params.existingJobStatus).toLowerCase();
    if (existingStatus !== "queued")
        return false;
    const existingQueueMode = asString(params.existingQueueMode).toLowerCase();
    const existingQueueStatus = asString(params.existingQueueStatus).toLowerCase();
    return (existingQueueMode === "dry_run" ||
        existingQueueStatus === "dry_run" ||
        existingQueueStatus === "enqueue_failed");
}
function planAvatarUploadState(params) {
    const existingStatus = asString(params.existingJobStatus).toLowerCase();
    const userAvatar = readMap(params.userAvatar);
    const userAvatarStatus = asString(userAvatar.status).toLowerCase();
    const avatarAlreadyApproved = hasApprovedAvatarLock(userAvatar);
    const isRetryableExistingJob = params.existingJobExists &&
        RETRYABLE_AVATAR_JOB_STATUSES.has(existingStatus);
    const shouldReenqueueExistingJob = isUndispatchedQueuedJob(params);
    const shouldWriteQueuedJob = !params.existingJobExists || isRetryableExistingJob;
    const responseAvatarStatus = shouldWriteQueuedJob
        ? "queued"
        : existingStatus || "queued";
    const rawApprovedAvatarUrl = asString(userAvatar.approvedAvatarUrl);
    const approvedAvatarUrl = avatarAlreadyApproved && isSafeApprovedAvatarUrl(rawApprovedAvatarUrl)
        ? rawApprovedAvatarUrl
        : undefined;
    if (params.existingJobExists &&
        existingStatus &&
        !NON_REGRESSING_AVATAR_JOB_STATUSES.has(existingStatus) &&
        !RETRYABLE_AVATAR_JOB_STATUSES.has(existingStatus)) {
        logger.warn("Avatar upload found unknown existing job status; preserving job", {
            existingStatus,
            duplicate: params.duplicate,
        });
    }
    if (avatarAlreadyApproved) {
        return {
            shouldWriteQueuedJob: false,
            shouldEnqueue: false,
            shouldSetUserAvatarQueued: false,
            responseAvatarStatus: "approved",
            responseMessage: "avatar_already_approved",
            approvedAvatarUrl,
        };
    }
    if (params.sourceLocked) {
        return {
            shouldWriteQueuedJob: false,
            shouldEnqueue: false,
            shouldSetUserAvatarQueued: false,
            responseAvatarStatus: userAvatarStatus || existingStatus || "locked",
            responseMessage: "avatar_source_locked",
            approvedAvatarUrl,
        };
    }
    return {
        shouldWriteQueuedJob,
        shouldEnqueue: shouldWriteQueuedJob || shouldReenqueueExistingJob,
        shouldSetUserAvatarQueued: (shouldWriteQueuedJob || shouldReenqueueExistingJob) &&
            userAvatarStatus !== "approved",
        responseAvatarStatus,
        responseMessage: responseAvatarStatus === "queued"
            ? "avatar_generation_queued"
            : `avatar_generation_${responseAvatarStatus}`,
        approvedAvatarUrl,
    };
}
function redactQueuePayload(payload) {
    const jobId = "jobId" in payload ? payload.jobId : "";
    return {
        ...payload,
        uid: "<redacted>",
        uidHash: sha256Hex(payload.uid).slice(0, 12),
        ...("jobId" in payload
            ? {
                jobId: "<redacted>",
                jobIdHash: sha256Hex(jobId).slice(0, 12),
            }
            : {}),
        sourcePhotoIds: payload.sourcePhotoIds.map(() => "<source-photo-id-redacted>"),
        sourcePhotoRefs: payload.sourcePhotoRefs.map(() => "gs://<private-source-photo-redacted>"),
        idempotencyKey: "<redacted>",
    };
}
function queueMode() {
    const configured = process.env.JOB_QUEUE_MODE?.trim().toLowerCase();
    if (!configured) {
        if (isProductionEnvironment()) {
            throw new https_1.HttpsError("failed-precondition", "JOB_QUEUE_MODE must be explicitly configured in production.");
        }
        return "dry_run";
    }
    if (configured === "dry_run" && isProductionEnvironment()) {
        throw new https_1.HttpsError("failed-precondition", "JOB_QUEUE_MODE=dry_run is not allowed in production.");
    }
    return configured;
}
function taskQueueName(kind) {
    const envName = kind === "avatar_generation"
        ? "AVATAR_GENERATION_QUEUE_NAME"
        : "CLIP_EMBEDDING_QUEUE_NAME";
    const fallback = kind === "avatar_generation" ? "avatar-generation" : "clip-embedding";
    const configured = envValue(envName, fallback);
    if (configured.startsWith("projects/"))
        return configured;
    const location = envValue("GCP_LOCATION", DEFAULT_REGION);
    const project = envValue("CLOUD_TASKS_PROJECT", process.env.GCLOUD_PROJECT ?? process.env.GCP_PROJECT ?? "");
    if (!project) {
        throw new https_1.HttpsError("failed-precondition", "CLOUD_TASKS_PROJECT is required for Cloud Tasks mode.");
    }
    return `projects/${project}/locations/${location}/queues/${configured}`;
}
function taskTargetUrl(kind) {
    const envName = kind === "avatar_generation"
        ? "AVATAR_GENERATION_TASK_URL"
        : "CLIP_EMBEDDING_TASK_URL";
    const url = process.env[envName]?.trim();
    if (!url) {
        throw new https_1.HttpsError("failed-precondition", `${envName} is required for Cloud Tasks mode.`);
    }
    return url;
}
function pubsubTopic(kind) {
    const envName = kind === "avatar_generation"
        ? "AVATAR_GENERATION_TOPIC"
        : "CLIP_EMBEDDING_TOPIC";
    return envValue(envName, kind === "avatar_generation" ? "avatar-generation" : "clip-embedding");
}
function buildDeterministicCloudTaskName(queueName, kind, idempotencyKey) {
    const prefix = kind === "avatar_generation" ? "avatar-generation" : "clip-embedding";
    return `${queueName}/tasks/${prefix}-${sha256Hex(idempotencyKey).slice(0, 32)}`;
}
function isCloudTasksAlreadyExistsError(error) {
    if (!isRecord(error))
        return false;
    return (error.code === 6 ||
        error.code === "6" ||
        asString(error.message).includes("ALREADY_EXISTS"));
}
function summarizeQueueWriteState(queueResults) {
    const avatar = readMap(queueResults.avatar);
    const clip = readMap(queueResults.clip);
    const avatarStatus = asString(avatar.status);
    const clipStatus = asString(clip.status);
    const queueModeValue = asString(avatar.mode) || asString(clip.mode) || queueMode();
    if (avatarStatus === "dry_run" || clipStatus === "dry_run") {
        return { queueMode: queueModeValue, queueStatus: "dry_run" };
    }
    const dispatchedStatuses = new Set([
        "enqueued",
        "already_exists",
        "published",
    ]);
    const optionalSkippedStatuses = new Set([
        "skipped_disabled",
        "skipped_existing_job",
    ]);
    if (dispatchedStatuses.has(avatarStatus) &&
        (dispatchedStatuses.has(clipStatus) ||
            optionalSkippedStatuses.has(clipStatus))) {
        return { queueMode: queueModeValue, queueStatus: "enqueued" };
    }
    if (avatarStatus || clipStatus) {
        return {
            queueMode: queueModeValue,
            queueStatus: [avatarStatus, clipStatus].filter(Boolean).join("+"),
        };
    }
    return { queueMode: queueModeValue, queueStatus: "unknown" };
}
function buildCloudTaskHttpRequest(url, payload) {
    const httpRequest = {
        httpMethod: tasks_1.protos.google.cloud.tasks.v2.HttpMethod.POST,
        url,
        headers: {
            "Content-Type": "application/json",
        },
        body: Buffer.from(JSON.stringify(payload)),
    };
    const serviceAccountEmail = process.env.TASK_INVOKER_SERVICE_ACCOUNT?.trim();
    if (!serviceAccountEmail) {
        if (allowInsecureLocalWorkerInvocation()) {
            return httpRequest;
        }
        const suffix = isProductionEnvironment()
            ? "production Cloud Tasks mode."
            : "Cloud Tasks mode unless ENVIRONMENT=local and ALLOW_INSECURE_WORKER_LOCAL=true.";
        throw new https_1.HttpsError("failed-precondition", `TASK_INVOKER_SERVICE_ACCOUNT is required for ${suffix}`);
    }
    httpRequest.oidcToken = {
        serviceAccountEmail,
        audience: process.env.TASK_OIDC_AUDIENCE?.trim() || url,
    };
    return httpRequest;
}
function cloudTaskDispatchDeadlineSeconds() {
    const raw = process.env.AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS?.trim();
    if (!raw)
        return 900;
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed))
        return 900;
    return Math.min(1800, Math.max(60, parsed));
}
async function enqueueQueuePayload(kind, payload) {
    const mode = queueMode();
    if (mode === "dry_run") {
        logger.info("Avatar media queue dry-run", {
            kind,
            payload: redactQueuePayload(payload),
        });
        return { mode, status: "dry_run" };
    }
    if (mode === "cloud_tasks") {
        const queueName = taskQueueName(kind);
        const url = taskTargetUrl(kind);
        const taskName = buildDeterministicCloudTaskName(queueName, kind, payload.idempotencyKey);
        const client = new tasks_1.CloudTasksClient();
        const httpRequest = buildCloudTaskHttpRequest(url, payload);
        try {
            const [task] = await client.createTask({
                parent: queueName,
                task: {
                    name: taskName,
                    httpRequest,
                    dispatchDeadline: { seconds: cloudTaskDispatchDeadlineSeconds() },
                },
            });
            return { mode, status: "enqueued", queueName, taskName: task.name };
        }
        catch (error) {
            if (isCloudTasksAlreadyExistsError(error)) {
                logger.info("Avatar media Cloud Task already exists; treating as idempotent success", {
                    kind,
                    taskName,
                });
                return { mode, status: "already_exists", queueName, taskName };
            }
            throw error;
        }
    }
    if (mode === "pubsub") {
        const topicName = pubsubTopic(kind);
        const pubsub = new pubsub_1.PubSub({
            projectId: process.env.CLOUD_TASKS_PROJECT ||
                process.env.GCLOUD_PROJECT ||
                undefined,
        });
        const messageId = await pubsub.topic(topicName).publishMessage({
            json: payload,
            attributes: {
                jobType: payload.jobType,
                schemaVersion: payload.schemaVersion,
            },
        });
        return { mode, status: "published", topicName, messageId };
    }
    throw new https_1.HttpsError("failed-precondition", "JOB_QUEUE_MODE must be dry_run, cloud_tasks, or pubsub.");
}
async function enqueueUploadQueuePayloads(avatarPayload, clipPayload) {
    const avatarQueue = await enqueueQueuePayload("avatar_generation", avatarPayload);
    if (!clipEmbeddingQueueEnabled()) {
        logger.info("Avatar media CLIP enqueue skipped by configuration", {
            jobId: avatarPayload.jobId,
        });
        return { avatar: avatarQueue, clip: { status: "skipped_disabled" } };
    }
    const clipQueue = await enqueueQueuePayload("clip_embedding", clipPayload);
    return { avatar: avatarQueue, clip: clipQueue };
}
async function savePrivateSourceObject(params) {
    await (0, storage_1.getStorage)()
        .bucket(sourcePhotoBucket())
        .file(params.storagePath)
        .save(params.imageBytes, {
        resumable: false,
        metadata: {
            contentType: "image/jpeg",
            cacheControl: "private, max-age=0, no-store",
            metadata: {
                sha256: params.imageSha256,
                exifStripped: "true",
                purpose: "avatar_generation_clip_recommendation",
            },
        },
    });
}
async function saveChatProfilePhotoObject(params) {
    await (0, storage_1.getStorage)()
        .bucket(chatProfilePhotoBucket())
        .file(params.storagePath)
        .save(params.imageBytes, {
        resumable: false,
        metadata: {
            contentType: "image/jpeg",
            cacheControl: "private, max-age=0, no-store",
            metadata: {
                sha256: params.imageSha256,
                exifStripped: "true",
                purpose: "chat_partner_real_profile_photo",
            },
        },
    });
}
async function storageObjectExists(bucketName, storagePath) {
    const [exists] = await (0, storage_1.getStorage)()
        .bucket(bucketName)
        .file(storagePath)
        .exists();
    return Boolean(exists);
}
async function deleteStorageObjectIfExists(params) {
    try {
        await (0, storage_1.getStorage)()
            .bucket(params.bucketName)
            .file(params.storagePath)
            .delete({
            ignoreNotFound: true,
        });
    }
    catch (error) {
        logger.warn("Avatar upload cleanup failed", {
            reason: params.reason,
            objectHash: sha256Hex(`${params.bucketName}/${params.storagePath}`).slice(0, 12),
            error: error instanceof Error ? error.message : String(error),
        });
    }
}
function createUploadAvatarSourcePhotoFunction(firestore, resolveUploadUser) {
    return (0, https_1.onCall)({
        timeoutSeconds: 120,
        memory: "1GiB",
        invoker: "public",
    }, async (request) => {
        const user = await resolveUploadUser(request.auth);
        const uid = requirePathSegment(user.userId, "uid");
        const data = isRecord(request.data) ? request.data : {};
        const requestedUid = asString(data.uid);
        if (requestedUid && requestedUid !== uid) {
            throw new https_1.HttpsError("permission-denied", "uid does not match authenticated user.");
        }
        const chatPartnerRealPhotoDisclosure = data.chatPartnerRealPhotoDisclosure === true;
        const userRef = firestore.collection("users").doc(uid);
        const privateRef = firestore.collection("userPrivateMedia").doc(uid);
        const existingUserSnap = await userRef.get();
        if (!existingUserSnap.exists) {
            throw new https_1.HttpsError("failed-precondition", "User profile was not found.");
        }
        const existingUserData = (existingUserSnap.data() ?? {});
        if (hasApprovedAvatarLock(existingUserData.avatar)) {
            throw new https_1.HttpsError("failed-precondition", "avatar_already_approved");
        }
        const avatarPresentationGender = avatarPresentationGenderFromUserData(existingUserData);
        const privateSnap = await privateRef.get();
        const privateData = (privateSnap.data() ?? {});
        if (hasLockedAvatarSource(privateData)) {
            throw new https_1.HttpsError("failed-precondition", "avatar_source_locked");
        }
        const { imageBytes, contentType } = parseImagePayload(data);
        normalizeContentType(contentType);
        const cleanedImage = await stripExifAndNormalizeImage(imageBytes);
        const imageSha256 = sha256Hex(cleanedImage);
        const existingSourcePhotos = readSourcePhotos(privateData.sourcePhotos);
        const duplicate = findCurrentDuplicateSource(existingSourcePhotos, imageSha256, privateData.currentAvatarSourcePhotoId);
        const photoId = duplicate?.photoId
            ? requirePathSegment(duplicate.photoId, "photoId")
            : buildNewAvatarSourcePhotoId(imageSha256);
        const storagePath = duplicate?.storagePath
            ? asString(duplicate.storagePath)
            : buildSourcePhotoStoragePath(uid, photoId);
        const gcsUri = duplicate?.gcsUri
            ? asString(duplicate.gcsUri)
            : buildGcsUri(sourcePhotoBucket(), storagePath);
        const currentJobId = asString(privateData.currentAvatarJobId);
        const jobId = duplicate?.photoId && currentJobId
            ? requirePathSegment(currentJobId, "currentAvatarJobId")
            : buildAvatarJobId(uid, photoId);
        const avatarPayload = buildAvatarPayload(uid, photoId, gcsUri, jobId, avatarPresentationGender);
        const clipPayload = buildClipPayload(uid, photoId, gcsUri);
        const jobRef = firestore.collection("avatarJobs").doc(jobId);
        let sourceObjectWritten = false;
        let chatObjectWritten = false;
        let chatObjectExistedBeforeWrite = true;
        if (!duplicate) {
            await savePrivateSourceObject({
                storagePath,
                imageBytes: cleanedImage,
                imageSha256,
            });
            sourceObjectWritten = true;
        }
        const chatRealPhotoStoragePath = buildChatProfilePhotoStoragePath(uid, photoId);
        if (chatPartnerRealPhotoDisclosure) {
            const chatBucket = chatProfilePhotoBucket();
            chatObjectExistedBeforeWrite = await storageObjectExists(chatBucket, chatRealPhotoStoragePath);
            await saveChatProfilePhotoObject({
                storagePath: chatRealPhotoStoragePath,
                imageBytes: cleanedImage,
                imageSha256,
            });
            chatObjectWritten = true;
        }
        let uploadResult;
        let uploadTransactionCommitted = false;
        try {
            uploadResult = await firestore.runTransaction(async (tx) => {
                const [freshPrivateSnap, freshUserSnap, freshJobSnap] = await Promise.all([
                    tx.get(privateRef),
                    tx.get(userRef),
                    tx.get(jobRef),
                ]);
                if (!freshUserSnap.exists) {
                    throw new https_1.HttpsError("failed-precondition", "User profile was not found.");
                }
                const freshPrivateData = (freshPrivateSnap.data() ?? {});
                const freshUserData = (freshUserSnap.data() ?? {});
                if (hasApprovedAvatarLock(freshUserData.avatar)) {
                    throw new https_1.HttpsError("failed-precondition", "avatar_already_approved");
                }
                if (hasLockedAvatarSource(freshPrivateData)) {
                    throw new https_1.HttpsError("failed-precondition", "avatar_source_locked");
                }
                const freshSourcePhotos = readSourcePhotos(freshPrivateData.sourcePhotos);
                const previousCurrentSourceId = asString(freshPrivateData.currentAvatarSourcePhotoId);
                const previousCurrentJobId = asString(freshPrivateData.currentAvatarJobId);
                const previousCurrentDuplicate = findCurrentDuplicateSource(freshSourcePhotos, imageSha256, previousCurrentSourceId);
                const sameCurrentSelection = previousCurrentDuplicate?.photoId === photoId &&
                    previousCurrentJobId === jobId;
                const previousJobRef = previousCurrentJobId && previousCurrentJobId !== jobId
                    ? firestore
                        .collection("avatarJobs")
                        .doc(requirePathSegment(previousCurrentJobId, "currentAvatarJobId"))
                    : null;
                const previousJobSnap = previousJobRef
                    ? await tx.get(previousJobRef)
                    : null;
                const now = firestore_1.Timestamp.now();
                const sourceEntry = {
                    photoId,
                    gcsUri,
                    storageBucket: sourcePhotoBucket(),
                    storagePath,
                    contentType: "image/jpeg",
                    sizeBytes: cleanedImage.length,
                    sha256: imageSha256,
                    exifStripped: true,
                    encrypted: true,
                    status: "active",
                    avatarGenerationState: "current",
                    purpose: {
                        avatarGeneration: true,
                        clipRecommendation: true,
                    },
                    uploadedAt: previousCurrentDuplicate?.uploadedAt ??
                        duplicate?.uploadedAt ??
                        now,
                    updatedAt: now,
                };
                const chatRealPhoto = chatPartnerRealPhotoDisclosure
                    ? buildChatRealPhotoMetadata({
                        uid,
                        photoId,
                        sizeBytes: cleanedImage.length,
                        updatedAt: now,
                    })
                    : buildDisabledChatRealPhotoMetadata(now);
                const updatedSourcePhotos = upsertSourcePhotoEntry(freshSourcePhotos, sourceEntry, previousCurrentSourceId);
                const selectionVersion = sameCurrentSelection
                    ? Number(freshPrivateData.avatarSourceSelectionVersion ?? 0) || 0
                    : nextAvatarSourceSelectionVersion(freshPrivateData.avatarSourceSelectionVersion);
                const existingJobStatus = freshJobSnap.exists
                    ? asString(freshJobSnap.get("status"))
                    : "";
                const plan = sameCurrentSelection
                    ? planAvatarUploadState({
                        existingJobExists: freshJobSnap.exists,
                        existingJobStatus,
                        existingQueueMode: freshJobSnap.exists
                            ? asString(freshJobSnap.get("queueMode"))
                            : "",
                        existingQueueStatus: freshJobSnap.exists
                            ? asString(freshJobSnap.get("queueStatus"))
                            : "",
                        userAvatar: readMap(freshUserData.avatar),
                        duplicate: true,
                    })
                    : {
                        shouldWriteQueuedJob: true,
                        shouldEnqueue: true,
                        shouldSetUserAvatarQueued: true,
                        responseAvatarStatus: "queued",
                        responseMessage: "avatar_generation_queued",
                    };
                const userUpdate = {
                    ...buildAvatarSourceRecoveryUserFields(jobId, selectionVersion),
                    profileImageMode: "avatar",
                    "onboarding.sourcePhotoUploadStatus": plan.responseMessage,
                    "onboarding.sourcePhotoUploadCount": activeSourcePhotoIds(updatedSourcePhotos).length,
                    "onboarding.photoUrls": firestore_1.FieldValue.delete(),
                    photoUrls: firestore_1.FieldValue.delete(),
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                };
                if (plan.shouldEnqueue) {
                    userUpdate["onboarding.sourcePhotoLastQueuedAt"] =
                        firestore_1.FieldValue.serverTimestamp();
                }
                if (plan.shouldSetUserAvatarQueued) {
                    userUpdate["avatar.status"] = "queued";
                    userUpdate["avatar.updatedAt"] = firestore_1.FieldValue.serverTimestamp();
                }
                tx.set(privateRef, buildPrivateMediaPayload(updatedSourcePhotos, {
                    chatPartnerRealPhotoDisclosure,
                    chatRealPhoto,
                    currentAvatarSourcePhotoId: photoId,
                    currentAvatarJobId: jobId,
                    avatarSourceSelectionVersion: selectionVersion,
                }), { merge: true });
                tx.update(userRef, userUpdate);
                if (previousJobRef &&
                    previousJobSnap?.exists &&
                    shouldSupersedeAvatarJobStatus(previousJobSnap.get("status"))) {
                    tx.set(previousJobRef, {
                        status: "superseded",
                        supersededByJobId: jobId,
                        supersededByPhotoId: photoId,
                        errorCode: "avatar_job_superseded",
                        updatedAt: firestore_1.FieldValue.serverTimestamp(),
                    }, { merge: true });
                }
                if (plan.shouldWriteQueuedJob) {
                    tx.set(jobRef, {
                        ...buildAvatarJobDoc(avatarPayload, freshJobSnap.exists),
                        avatarPresentationGender: avatarPresentationGenderFromUserData(freshUserData),
                        avatarSourceSelectionVersion: selectionVersion,
                    }, { merge: true });
                }
                return {
                    ...plan,
                    duplicate: Boolean(sameCurrentSelection && (previousCurrentDuplicate ?? duplicate)),
                    sourceSelectionVersion: selectionVersion,
                };
            });
            uploadTransactionCommitted = true;
        }
        catch (error) {
            if (!uploadTransactionCommitted) {
                if (sourceObjectWritten) {
                    await deleteStorageObjectIfExists({
                        bucketName: sourcePhotoBucket(),
                        storagePath,
                        reason: "avatar-upload-transaction-failed-source",
                    });
                }
                if (chatObjectWritten && !chatObjectExistedBeforeWrite) {
                    await deleteStorageObjectIfExists({
                        bucketName: chatProfilePhotoBucket(),
                        storagePath: chatRealPhotoStoragePath,
                        reason: "avatar-upload-transaction-failed-chat",
                    });
                }
            }
            throw error;
        }
        let queueResults = {
            avatar: { status: "skipped_existing_job" },
            clip: { status: "skipped_existing_job" },
        };
        if (uploadResult.shouldEnqueue) {
            try {
                queueResults = await enqueueUploadQueuePayloads(avatarPayload, clipPayload);
                const queueWriteState = summarizeQueueWriteState(queueResults);
                await jobRef.set({
                    queueStatus: queueWriteState.queueStatus,
                    queueMode: queueWriteState.queueMode,
                    queuedAt: firestore_1.FieldValue.serverTimestamp(),
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
            }
            catch (error) {
                logger.error("Avatar source upload enqueue failed", {
                    uidHash: sha256Hex(uid).slice(0, 12),
                    jobIdHash: sha256Hex(jobId).slice(0, 12),
                    error: error instanceof Error ? error.message : String(error),
                });
                await jobRef.set({
                    status: "failed",
                    errorCode: "avatar_queue_enqueue_failed",
                    queueStatus: "enqueue_failed",
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
                await userRef.set({
                    "avatar.status": "failed",
                    "avatar.errorCode": "avatar_queue_enqueue_failed",
                    "avatar.updatedAt": firestore_1.FieldValue.serverTimestamp(),
                    "onboarding.sourcePhotoUploadStatus": "avatar_queue_enqueue_failed",
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
                if (error instanceof https_1.HttpsError)
                    throw error;
                throw new https_1.HttpsError("internal", "Avatar processing could not be queued.");
            }
        }
        logger.info("Avatar source photo uploaded", {
            uidHash: sha256Hex(uid).slice(0, 12),
            jobIdHash: sha256Hex(jobId).slice(0, 12),
            duplicate: uploadResult.duplicate,
            photoIdHash: sha256Hex(photoId).slice(0, 12),
            sourcePathHash: sha256Hex(storagePath).slice(0, 12),
            sourceSha256Prefix: imageSha256.slice(0, 12),
            sourceSelectionVersion: uploadResult.sourceSelectionVersion,
            queueResults,
        });
        const response = {
            jobId,
            photoId,
            avatarStatus: uploadResult.responseAvatarStatus,
            message: uploadResult.responseMessage,
            duplicate: uploadResult.duplicate,
            sourceSelectionVersion: uploadResult.sourceSelectionVersion,
        };
        if (uploadResult.approvedAvatarUrl) {
            response.approvedAvatarUrl = uploadResult.approvedAvatarUrl;
        }
        return response;
    });
}
//# sourceMappingURL=avatarMedia.js.map