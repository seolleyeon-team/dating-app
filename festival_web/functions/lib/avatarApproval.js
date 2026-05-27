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
exports.parseGcsUri = parseGcsUri;
exports.buildApprovedAvatarPath = buildApprovedAvatarPath;
exports.buildApprovedAvatarStoragePath = buildApprovedAvatarStoragePath;
exports.buildApprovedAvatarPublicUrl = buildApprovedAvatarPublicUrl;
exports.buildAvatarId = buildAvatarId;
exports.canPreviewCandidate = canPreviewCandidate;
exports.checkCurrentAvatarJobContract = checkCurrentAvatarJobContract;
exports.planAvatarApprovalState = planAvatarApprovalState;
exports.avatarPreviewResponseStatus = avatarPreviewResponseStatus;
exports.createGetAvatarJobCandidatesFunction = createGetAvatarJobCandidatesFunction;
exports.createApproveAvatarCandidateFunction = createApproveAvatarCandidateFunction;
const storage_1 = require("firebase-admin/storage");
const crypto_1 = require("crypto");
const firestore_1 = require("firebase-admin/firestore");
const https_1 = require("firebase-functions/v2/https");
const logger = __importStar(require("firebase-functions/logger"));
const sharp_1 = __importDefault(require("sharp"));
const DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp";
const DEFAULT_APPROVED_AVATAR_BUCKET = "seolleyeon-approved-avatars";
const DEFAULT_PREVIEW_IMAGE_SIZE = 512;
function envValue(name, fallback) {
    const value = process.env[name]?.trim();
    return value && value.length > 0 ? value : fallback;
}
function avatarTempBucket() {
    return envValue("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET);
}
function approvedAvatarBucket() {
    return envValue("APPROVED_AVATAR_BUCKET", DEFAULT_APPROVED_AVATAR_BUCKET);
}
function writeLegacyOnboardingPhotoUrls() {
    return process.env.WRITE_LEGACY_ONBOARDING_PHOTO_URLS === "true";
}
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function asString(value) {
    return typeof value === "string" ? value.trim() : "";
}
function logIdentifier(label, value) {
    const digest = (0, crypto_1.createHash)("sha256").update(value).digest("hex").slice(0, 12);
    return `${label}:${digest}`;
}
function readMap(value) {
    return isRecord(value) ? value : {};
}
function normalizeStringList(value) {
    if (!Array.isArray(value))
        return [];
    return Array.from(new Set(value.map((item) => asString(item)).filter((item) => item.length > 0)));
}
function safeDecodeUriComponent(value) {
    try {
        return decodeURIComponent(value);
    }
    catch {
        return value;
    }
}
function isSafePublicApprovedAvatarUrl(value) {
    if (typeof value !== "string")
        return false;
    const trimmed = value.trim();
    if (!trimmed)
        return false;
    const decodedLower = safeDecodeUriComponent(trimmed).toLowerCase();
    if (decodedLower.startsWith("gs://") ||
        decodedLower.startsWith("gcs://") ||
        /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/.test(decodedLower) ||
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
        const parsed = new URL(trimmed);
        const host = parsed.hostname.toLowerCase();
        const path = safeDecodeUriComponent(parsed.pathname).toLowerCase();
        const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
            ? host.replace(".storage.googleapis.com", "")
            : "";
        if (/seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/.test(bucketFromVirtualHost) ||
            /\/source\//.test(path) ||
            /\/jobs\//.test(path) ||
            /\/candidates\//.test(path)) {
            return false;
        }
    }
    catch {
        return false;
    }
    return true;
}
function requirePathSegment(value, label) {
    const normalized = value.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
        throw new https_1.HttpsError("invalid-argument", `${label} is not a safe path segment.`);
    }
    return normalized;
}
function getCallableData(request) {
    return isRecord(request.data) ? request.data : {};
}
function parseGcsUri(source, label = "imageRef") {
    const match = source.match(/^(?:gs|gcs):\/\/([^/]+)\/(.+)$/);
    if (!match) {
        throw new https_1.HttpsError("invalid-argument", `${label} must be a gs:// or gcs:// URI.`);
    }
    const bucket = match[1].trim();
    const path = match[2].trim();
    if (!bucket || !path || path.startsWith("/") || path.includes("..")) {
        throw new https_1.HttpsError("invalid-argument", `${label} is not a safe GCS object ref.`);
    }
    return { bucket, path };
}
function encodeStoragePath(path) {
    return path
        .split("/")
        .map((segment) => encodeURIComponent(segment))
        .join("/");
}
function buildApprovedAvatarPath(uid, avatarId) {
    return `users/${requirePathSegment(uid, "uid")}/avatar/${requirePathSegment(avatarId, "avatarId")}.png`;
}
function buildApprovedAvatarStoragePath(uid, avatarId) {
    return `gs://${approvedAvatarBucket()}/${buildApprovedAvatarPath(uid, avatarId)}`;
}
function approvedAvatarPublicBaseUrl() {
    return process.env.APPROVED_AVATAR_PUBLIC_BASE_URL?.trim() ?? "";
}
function buildApprovedAvatarPublicUrl(bucket, path, downloadToken) {
    const configuredBase = approvedAvatarPublicBaseUrl();
    if (configuredBase && configuredBase.length > 0) {
        const base = configuredBase.replace(/\/+$/, "");
        return `${base}/${encodeStoragePath(path)}`;
    }
    if (!downloadToken) {
        throw new https_1.HttpsError("internal", "Approved avatar download token was not created.");
    }
    return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(bucket)}/o/${encodeURIComponent(path)}?alt=media&token=${encodeURIComponent(downloadToken)}`;
}
function buildAvatarId(candidateId) {
    return `avatar_${requirePathSegment(candidateId, "candidateId").replace(/^cand_/, "")}`;
}
function timestampMillis(value) {
    if (value instanceof firestore_1.Timestamp)
        return value.toMillis();
    if (value instanceof Date)
        return value.getTime();
    if (typeof value === "number" && Number.isFinite(value))
        return value;
    if (typeof value === "string" && value.trim().length > 0) {
        const parsed = Date.parse(value);
        return Number.isNaN(parsed) ? null : parsed;
    }
    if (isRecord(value) && typeof value.toMillis === "function") {
        const millis = value.toMillis();
        return typeof millis === "number" && Number.isFinite(millis)
            ? millis
            : null;
    }
    return null;
}
function isExpired(value, nowMs) {
    const expiresAtMs = timestampMillis(value);
    return expiresAtMs != null && expiresAtMs <= nowMs;
}
function assertTempCandidateRef(imageRef) {
    const parsed = parseGcsUri(imageRef, "candidate imageRef");
    if (parsed.bucket !== avatarTempBucket()) {
        throw new https_1.HttpsError("failed-precondition", "Candidate image is not in the avatar temp bucket.");
    }
    return parsed;
}
function qaPreviewAllowed(candidate) {
    const qa = readMap(candidate.qa);
    return qa.previewAllowed === true;
}
function canPreviewCandidate(candidate, nowMs = Date.now()) {
    return (asString(candidate.status) === "preview_ready" &&
        qaPreviewAllowed(candidate) &&
        !isExpired(candidate.expiresAt, nowMs));
}
function sourcePhotoIdsForJob(jobData) {
    const sourcePhotoIds = normalizeStringList(jobData.sourcePhotoIds);
    const legacySourcePhotoId = asString(jobData.sourcePhotoId);
    return legacySourcePhotoId && !sourcePhotoIds.includes(legacySourcePhotoId)
        ? [...sourcePhotoIds, legacySourcePhotoId]
        : sourcePhotoIds;
}
function currentSourceEntry(privateData, currentAvatarSourcePhotoId) {
    const sourcePhotos = Array.isArray(privateData.sourcePhotos)
        ? privateData.sourcePhotos
        : [];
    for (const entry of sourcePhotos) {
        if (isRecord(entry) &&
            asString(entry.photoId) === currentAvatarSourcePhotoId) {
            return entry;
        }
    }
    return null;
}
function numericValue(value) {
    const parsed = typeof value === "number" ? value : value == null ? NaN : Number(value);
    return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}
function checkCurrentAvatarJobContract(params) {
    const currentAvatarJobId = asString(params.privateData.currentAvatarJobId);
    if (currentAvatarJobId !== params.jobId) {
        return {
            ok: false,
            errorCode: "avatar_job_superseded",
            reason: "current_job_mismatch",
        };
    }
    const currentAvatarSourcePhotoId = asString(params.privateData.currentAvatarSourcePhotoId);
    if (!currentAvatarSourcePhotoId) {
        return {
            ok: false,
            errorCode: "avatar_job_superseded",
            reason: "missing_current_source",
        };
    }
    if (!sourcePhotoIdsForJob(params.jobData).includes(currentAvatarSourcePhotoId)) {
        return {
            ok: false,
            errorCode: "avatar_job_superseded",
            reason: "job_source_mismatch",
        };
    }
    const sourceEntry = currentSourceEntry(params.privateData, currentAvatarSourcePhotoId);
    if (!sourceEntry ||
        asString(sourceEntry.status) !== "active" ||
        asString(sourceEntry.avatarGenerationState) !== "current") {
        return {
            ok: false,
            errorCode: "avatar_job_superseded",
            reason: "source_not_current",
        };
    }
    const privateSelectionVersion = numericValue(params.privateData.avatarSourceSelectionVersion);
    const jobSelectionVersion = numericValue(params.jobData.avatarSourceSelectionVersion);
    if (privateSelectionVersion !== null &&
        jobSelectionVersion !== null &&
        privateSelectionVersion !== jobSelectionVersion) {
        return {
            ok: false,
            errorCode: "avatar_job_superseded",
            reason: "selection_version_mismatch",
        };
    }
    return { ok: true, currentAvatarSourcePhotoId };
}
function assertCurrentAvatarJobContract(result) {
    if (result.ok)
        return;
    throw new https_1.HttpsError("failed-precondition", result.errorCode);
}
function isAvatarJobSupersededError(error) {
    return (error instanceof https_1.HttpsError &&
        error.code === "failed-precondition" &&
        error.message.includes("avatar_job_superseded"));
}
const APPROVAL_LOCK_STATUSES = new Set([
    "approved",
    "approval_copying",
    "approval_copy_failed",
]);
function planAvatarApprovalState(userData, candidateId) {
    const avatar = readMap(userData.avatar);
    const status = asString(avatar.status);
    const selectedCandidateId = asString(avatar.selectedCandidateId);
    const approvedAvatarUrl = asString(avatar.approvedAvatarUrl);
    if (status === "approved" &&
        selectedCandidateId === candidateId &&
        isSafePublicApprovedAvatarUrl(approvedAvatarUrl)) {
        return {
            action: "return_existing",
            approvedAvatarUrl,
            avatarId: asString(avatar.avatarId),
            selectedCandidateId: candidateId,
            sourceJobId: asString(avatar.sourceJobId) || undefined,
        };
    }
    if ((status === "approved" && selectedCandidateId !== candidateId) ||
        (selectedCandidateId &&
            selectedCandidateId !== candidateId &&
            APPROVAL_LOCK_STATUSES.has(status))) {
        return {
            action: "conflict",
            errorCode: "avatar_already_approved",
            selectedCandidateId,
        };
    }
    return {
        action: "reserve",
        avatarId: selectedCandidateId === candidateId && asString(avatar.avatarId)
            ? requirePathSegment(asString(avatar.avatarId), "avatarId")
            : buildAvatarId(candidateId),
        selectedCandidateId: candidateId,
        approvalDownloadToken: selectedCandidateId === candidateId &&
            asString(avatar.approvalDownloadToken)
            ? asString(avatar.approvalDownloadToken)
            : undefined,
    };
}
function assertCandidateOwnedByUser(candidate, uid) {
    if (asString(candidate.uid) !== uid) {
        throw new https_1.HttpsError("permission-denied", "Avatar candidate does not belong to this user.");
    }
}
function assertJobOwnedByUser(job, uid) {
    if (asString(job.uid) !== uid) {
        throw new https_1.HttpsError("permission-denied", "Avatar job does not belong to this user.");
    }
}
function previewImageSize() {
    const value = Number(process.env.AVATAR_PREVIEW_IMAGE_SIZE ?? DEFAULT_PREVIEW_IMAGE_SIZE);
    return Number.isFinite(value) && value >= 128
        ? Math.min(value, 768)
        : DEFAULT_PREVIEW_IMAGE_SIZE;
}
async function runtimePreviewImagePayload(ref) {
    const [sourceBytes] = await (0, storage_1.getStorage)()
        .bucket(ref.bucket)
        .file(ref.path)
        .download();
    const size = previewImageSize();
    const previewBytes = await (0, sharp_1.default)(sourceBytes, {
        limitInputPixels: 16_777_216,
    })
        .rotate()
        .resize(size, size, { fit: "cover" })
        .jpeg({ quality: 84, mozjpeg: true })
        .toBuffer();
    return {
        previewImageBase64: previewBytes.toString("base64"),
        previewMimeType: "image/jpeg",
    };
}
function safeAvatarJobErrorCode(value) {
    const raw = asString(value).trim();
    return /^[a-z0-9_]{1,80}$/.test(raw) ? raw : "";
}
function avatarPreviewResponseStatus(params) {
    if (!params.currentContractOk &&
        !["approved", "failed", "cancelled", "canceled"].includes(params.jobStatus)) {
        return "superseded";
    }
    if (params.jobStatus === "preview_ready" &&
        params.candidateCount > 0 &&
        params.previewableCandidateCount === 0) {
        return "no_previewable_candidates";
    }
    return params.jobStatus;
}
function createGetAvatarJobCandidatesFunction(firestore, resolveUser) {
    return (0, https_1.onCall)({
        timeoutSeconds: 60,
        memory: "512MiB",
        invoker: "public",
    }, async (request) => {
        const user = await resolveUser(request.auth);
        const uid = requirePathSegment(user.userId, "uid");
        const data = getCallableData(request);
        const jobId = requirePathSegment(asString(data.jobId), "jobId");
        const jobSnap = await firestore.collection("avatarJobs").doc(jobId).get();
        if (!jobSnap.exists) {
            throw new https_1.HttpsError("not-found", "Avatar job was not found.");
        }
        const jobData = (jobSnap.data() ?? {});
        assertJobOwnedByUser(jobData, uid);
        const jobStatus = asString(jobData.status);
        const privateSnap = await firestore
            .collection("userPrivateMedia")
            .doc(uid)
            .get();
        const currentContract = checkCurrentAvatarJobContract({
            jobId,
            jobData,
            privateData: (privateSnap.data() ?? {}),
        });
        const canReturnCandidates = jobStatus === "preview_ready" && currentContract.ok;
        const candidateDocs = canReturnCandidates
            ? (await firestore
                .collection("avatarCandidates")
                .where("jobId", "==", jobId)
                .where("uid", "==", uid)
                .get()).docs
            : [];
        const nowMs = Date.now();
        const candidates = canReturnCandidates
            ? await Promise.all(candidateDocs
                .map((doc) => ({
                id: doc.id,
                data: (doc.data() ?? {}),
            }))
                .filter(({ data: candidate }) => canPreviewCandidate(candidate, nowMs))
                .map(async ({ id, data: candidate }) => {
                const candidateId = asString(candidate.candidateId) || id;
                const imageRef = assertTempCandidateRef(asString(candidate.imageRef));
                return {
                    candidateId,
                    ...(await runtimePreviewImagePayload(imageRef)),
                    qaSummary: {
                        status: "pass",
                    },
                };
            }))
            : [];
        const responseStatus = avatarPreviewResponseStatus({
            jobStatus,
            currentContractOk: currentContract.ok,
            candidateCount: candidateDocs.length,
            previewableCandidateCount: candidates.length,
        });
        const errorCode = responseStatus === "superseded" && !currentContract.ok
            ? currentContract.errorCode
            : safeAvatarJobErrorCode(jobData.errorCode);
        logger.info("Avatar preview candidates fetched", {
            uid: logIdentifier("uid", uid),
            jobId: logIdentifier("job", jobId),
            status: responseStatus,
            candidateCount: candidateDocs.length,
            previewableCandidateCount: candidates.length,
        });
        return {
            jobId,
            status: responseStatus,
            ...(errorCode ? { errorCode } : {}),
            candidates,
        };
    });
}
function createApproveAvatarCandidateFunction(firestore, resolveUser) {
    return (0, https_1.onCall)({
        timeoutSeconds: 120,
        memory: "512MiB",
        invoker: "public",
    }, async (request) => {
        const user = await resolveUser(request.auth);
        const uid = requirePathSegment(user.userId, "uid");
        const data = getCallableData(request);
        const candidateId = requirePathSegment(asString(data.candidateId), "candidateId");
        const candidateRef = firestore
            .collection("avatarCandidates")
            .doc(candidateId);
        const userRef = firestore.collection("users").doc(uid);
        const privateRef = firestore.collection("userPrivateMedia").doc(uid);
        const [candidateSnap, userSnap] = await Promise.all([
            candidateRef.get(),
            userRef.get(),
        ]);
        if (!candidateSnap.exists) {
            throw new https_1.HttpsError("not-found", "Avatar candidate was not found.");
        }
        if (!userSnap.exists) {
            throw new https_1.HttpsError("failed-precondition", "User profile was not found.");
        }
        const candidateData = (candidateSnap.data() ?? {});
        assertCandidateOwnedByUser(candidateData, uid);
        if (!canPreviewCandidate(candidateData)) {
            throw new https_1.HttpsError("failed-precondition", "Avatar candidate is not approved for user preview.");
        }
        const jobId = requirePathSegment(asString(candidateData.jobId), "jobId");
        const jobRef = firestore.collection("avatarJobs").doc(jobId);
        const jobSnap = await jobRef.get();
        if (!jobSnap.exists) {
            throw new https_1.HttpsError("failed-precondition", "Avatar job was not found.");
        }
        const jobData = (jobSnap.data() ?? {});
        assertJobOwnedByUser(jobData, uid);
        const privateSnap = await privateRef.get();
        assertCurrentAvatarJobContract(checkCurrentAvatarJobContract({
            jobId,
            jobData,
            privateData: (privateSnap.data() ?? {}),
        }));
        const sourceImage = assertTempCandidateRef(asString(candidateData.imageRef));
        const reservation = await firestore.runTransaction(async (tx) => {
            const [freshCandidate, freshUser, freshJob, freshPrivate] = await Promise.all([
                tx.get(candidateRef),
                tx.get(userRef),
                tx.get(jobRef),
                tx.get(privateRef),
            ]);
            if (!freshCandidate.exists || !freshUser.exists || !freshJob.exists) {
                throw new https_1.HttpsError("failed-precondition", "Avatar approval state changed.");
            }
            const freshCandidateData = (freshCandidate.data() ?? {});
            const freshUserData = (freshUser.data() ?? {});
            const freshJobData = (freshJob.data() ?? {});
            assertCandidateOwnedByUser(freshCandidateData, uid);
            assertJobOwnedByUser(freshJobData, uid);
            assertCurrentAvatarJobContract(checkCurrentAvatarJobContract({
                jobId,
                jobData: freshJobData,
                privateData: (freshPrivate.data() ?? {}),
            }));
            const plan = planAvatarApprovalState(freshUserData, candidateId);
            if (plan.action === "return_existing") {
                return {
                    action: "return_existing",
                    approvedAvatarUrl: plan.approvedAvatarUrl,
                    avatarId: plan.avatarId,
                };
            }
            if (plan.action === "conflict") {
                throw new https_1.HttpsError("failed-precondition", "avatar_already_approved: A different avatar candidate has already been approved.");
            }
            if (!canPreviewCandidate(freshCandidateData)) {
                throw new https_1.HttpsError("failed-precondition", "Avatar candidate is no longer available for approval.");
            }
            const jobStatus = asString(freshJobData.status);
            if (jobStatus !== "preview_ready" && jobStatus !== "approval_copying") {
                throw new https_1.HttpsError("failed-precondition", "Avatar job is not ready for candidate approval.");
            }
            const avatarId = plan.avatarId;
            const destinationPath = buildApprovedAvatarPath(uid, avatarId);
            const destinationBucket = approvedAvatarBucket();
            const downloadToken = approvedAvatarPublicBaseUrl()
                ? undefined
                : (0, crypto_1.randomUUID)();
            const approvedAvatarUrl = buildApprovedAvatarPublicUrl(destinationBucket, destinationPath, downloadToken);
            const approvedAvatarStoragePath = buildApprovedAvatarStoragePath(uid, avatarId);
            tx.update(userRef, {
                profileImageMode: "avatar",
                "avatar.status": "approval_copying",
                "avatar.approvedAvatarUrl": firestore_1.FieldValue.delete(),
                "avatar.approvedAvatarStoragePath": approvedAvatarStoragePath,
                "avatar.avatarId": avatarId,
                "avatar.selectedCandidateId": candidateId,
                "avatar.sourceJobId": jobId,
                "avatar.updatedAt": firestore_1.FieldValue.serverTimestamp(),
                updatedAt: firestore_1.FieldValue.serverTimestamp(),
            });
            tx.set(jobRef, {
                status: "approval_copying",
                selectedCandidateId: candidateId,
                updatedAt: firestore_1.FieldValue.serverTimestamp(),
            }, { merge: true });
            tx.set(candidateRef, {
                status: "approval_copying",
                updatedAt: firestore_1.FieldValue.serverTimestamp(),
            }, { merge: true });
            return {
                action: "reserved",
                avatarId,
                destinationPath,
                destinationBucket,
                downloadToken,
                approvedAvatarUrl,
                approvedAvatarStoragePath,
            };
        });
        if (reservation.action === "return_existing") {
            return {
                avatarStatus: "approved",
                approvedAvatarUrl: reservation.approvedAvatarUrl,
                avatarId: reservation.avatarId,
                selectedCandidateId: candidateId,
                duplicate: true,
            };
        }
        const sourceFile = (0, storage_1.getStorage)()
            .bucket(sourceImage.bucket)
            .file(sourceImage.path);
        const destinationFile = (0, storage_1.getStorage)()
            .bucket(reservation.destinationBucket)
            .file(reservation.destinationPath);
        let copiedApprovedObject = false;
        let finalTransactionReturnedExisting = false;
        let finalExistingApproval = null;
        const objectMetadata = {
            sourceCandidateId: candidateId,
            sourceJobId: jobId,
            purpose: "approved_avatar_display",
        };
        if (reservation.downloadToken) {
            objectMetadata.firebaseStorageDownloadTokens =
                reservation.downloadToken;
        }
        try {
            await sourceFile.copy(destinationFile);
            copiedApprovedObject = true;
            await destinationFile.setMetadata({
                contentType: "image/png",
                cacheControl: "public, max-age=3600",
                metadata: objectMetadata,
            });
            await firestore.runTransaction(async (tx) => {
                const [freshCandidate, freshUser, freshJob, freshPrivate] = await Promise.all([
                    tx.get(candidateRef),
                    tx.get(userRef),
                    tx.get(jobRef),
                    tx.get(privateRef),
                ]);
                if (!freshCandidate.exists || !freshUser.exists || !freshJob.exists) {
                    throw new https_1.HttpsError("failed-precondition", "Avatar approval state changed.");
                }
                const freshCandidateData = (freshCandidate.data() ?? {});
                const freshUserData = (freshUser.data() ?? {});
                const freshJobData = (freshJob.data() ?? {});
                assertCandidateOwnedByUser(freshCandidateData, uid);
                assertJobOwnedByUser(freshJobData, uid);
                assertCurrentAvatarJobContract(checkCurrentAvatarJobContract({
                    jobId,
                    jobData: freshJobData,
                    privateData: (freshPrivate.data() ?? {}),
                }));
                const plan = planAvatarApprovalState(freshUserData, candidateId);
                if (plan.action === "return_existing") {
                    finalTransactionReturnedExisting = true;
                    finalExistingApproval = {
                        approvedAvatarUrl: plan.approvedAvatarUrl,
                        avatarId: plan.avatarId,
                    };
                    return;
                }
                if (plan.action === "conflict") {
                    throw new https_1.HttpsError("failed-precondition", "avatar_already_approved: A different avatar candidate has already been approved.");
                }
                const currentAvatar = readMap(freshUserData.avatar);
                if (asString(currentAvatar.status) !== "approval_copying" ||
                    asString(currentAvatar.selectedCandidateId) !== candidateId) {
                    throw new https_1.HttpsError("failed-precondition", "Avatar approval reservation was lost.");
                }
                tx.update(userRef, {
                    profileImageMode: "avatar",
                    avatar: {
                        status: "approved",
                        approvedAvatarUrl: reservation.approvedAvatarUrl,
                        approvedAvatarStoragePath: reservation.approvedAvatarStoragePath,
                        avatarId: reservation.avatarId,
                        selectedCandidateId: candidateId,
                        sourceJobId: jobId,
                        updatedAt: firestore_1.FieldValue.serverTimestamp(),
                    },
                    "onboarding.avatarUrls": [reservation.approvedAvatarUrl],
                    "onboarding.avatarGenerationJobId": firestore_1.FieldValue.delete(),
                    "onboarding.avatarSourceSelectionVersion": firestore_1.FieldValue.delete(),
                    "onboarding.sourcePhotoUploadStatus": firestore_1.FieldValue.delete(),
                    "onboarding.photoUrls": writeLegacyOnboardingPhotoUrls()
                        ? [reservation.approvedAvatarUrl]
                        : firestore_1.FieldValue.delete(),
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                });
                tx.set(jobRef, {
                    status: "approved",
                    selectedCandidateId: candidateId,
                    approvedAt: firestore_1.FieldValue.serverTimestamp(),
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
                tx.set(candidateRef, {
                    status: "approved",
                    approvedAvatarUrl: reservation.approvedAvatarUrl,
                    approvedAvatarStoragePath: reservation.approvedAvatarStoragePath,
                    approvedAt: firestore_1.FieldValue.serverTimestamp(),
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
            });
        }
        catch (error) {
            if (copiedApprovedObject && !finalTransactionReturnedExisting) {
                try {
                    await destinationFile.delete({ ignoreNotFound: true });
                }
                catch (deleteError) {
                    logger.error("Failed to delete orphaned approved avatar after approval failure", {
                        uid: logIdentifier("uid", uid),
                        jobId: logIdentifier("job", jobId),
                        candidateId: logIdentifier("candidate", candidateId),
                        avatarId: logIdentifier("avatar", reservation.avatarId),
                        error: deleteError instanceof Error
                            ? deleteError.message
                            : String(deleteError),
                    });
                }
            }
            if (!isAvatarJobSupersededError(error)) {
                await userRef.set({
                    avatar: {
                        status: "approval_copy_failed",
                        avatarId: reservation.avatarId,
                        selectedCandidateId: candidateId,
                        sourceJobId: jobId,
                        approvedAvatarStoragePath: reservation.approvedAvatarStoragePath,
                        updatedAt: firestore_1.FieldValue.serverTimestamp(),
                    },
                    updatedAt: firestore_1.FieldValue.serverTimestamp(),
                }, { merge: true });
            }
            throw error;
        }
        const existingApprovalAfterCopy = finalExistingApproval;
        if (existingApprovalAfterCopy) {
            return {
                avatarStatus: "approved",
                approvedAvatarUrl: existingApprovalAfterCopy.approvedAvatarUrl,
                avatarId: existingApprovalAfterCopy.avatarId,
                selectedCandidateId: candidateId,
                duplicate: true,
            };
        }
        const siblingSnap = await firestore
            .collection("avatarCandidates")
            .where("jobId", "==", jobId)
            .where("uid", "==", uid)
            .get();
        const batch = firestore.batch();
        for (const sibling of siblingSnap.docs) {
            if (sibling.id === candidateId)
                continue;
            batch.set(sibling.ref, {
                status: "unselected",
                updatedAt: firestore_1.FieldValue.serverTimestamp(),
            }, { merge: true });
        }
        await batch.commit();
        logger.info("Avatar candidate approved", {
            uid: logIdentifier("uid", uid),
            jobId: logIdentifier("job", jobId),
            candidateId: logIdentifier("candidate", candidateId),
            avatarId: logIdentifier("avatar", reservation.avatarId),
        });
        return {
            avatarStatus: "approved",
            approvedAvatarUrl: reservation.approvedAvatarUrl,
            avatarId: reservation.avatarId,
            selectedCandidateId: candidateId,
        };
    });
}
//# sourceMappingURL=avatarApproval.js.map