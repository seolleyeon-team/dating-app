import { getStorage } from "firebase-admin/storage";
import { createHash, randomUUID } from "crypto";
import {
  FieldValue,
  Timestamp,
  type Firestore,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableRequest,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import sharp from "sharp";

const DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp";
const DEFAULT_APPROVED_AVATAR_BUCKET = "seolleyeon-approved-avatars";
const DEFAULT_PREVIEW_IMAGE_SIZE = 512;

type AvatarApiAuth = CallableRequest<unknown>["auth"];

export type ResolvedAvatarApiUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
};

type ResolveAvatarApiUser = (
  auth: AvatarApiAuth,
) => Promise<ResolvedAvatarApiUser>;

type GcsRef = {
  bucket: string;
  path: string;
};

function envValue(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

function avatarTempBucket(): string {
  return envValue("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET);
}

function approvedAvatarBucket(): string {
  return envValue("APPROVED_AVATAR_BUCKET", DEFAULT_APPROVED_AVATAR_BUCKET);
}

function writeLegacyOnboardingPhotoUrls(): boolean {
  return process.env.WRITE_LEGACY_ONBOARDING_PHOTO_URLS === "true";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function logIdentifier(label: string, value: string): string {
  const digest = createHash("sha256").update(value).digest("hex").slice(0, 12);
  return `${label}:${digest}`;
}

function readMap(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(
    new Set(
      value.map((item) => asString(item)).filter((item) => item.length > 0),
    ),
  );
}

function safeDecodeUriComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isSafePublicApprovedAvatarUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  const decodedLower = safeDecodeUriComponent(trimmed).toLowerCase();
  if (
    decodedLower.startsWith("gs://") ||
    decodedLower.startsWith("gcs://") ||
    /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/.test(
      decodedLower,
    ) ||
    decodedLower.includes("x-goog-") ||
    decodedLower.includes("x-amz-") ||
    decodedLower.includes("googleaccessid") ||
    decodedLower.includes("signature=") ||
    decodedLower.includes("expires=") ||
    decodedLower.includes("awsaccesskeyid") ||
    decodedLower.includes("signedurl") ||
    /\/source\//.test(decodedLower) ||
    /\/jobs\//.test(decodedLower) ||
    /\/candidates\//.test(decodedLower)
  ) {
    return false;
  }

  try {
    const parsed = new URL(trimmed);
    const host = parsed.hostname.toLowerCase();
    const path = safeDecodeUriComponent(parsed.pathname).toLowerCase();
    const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
      ? host.replace(".storage.googleapis.com", "")
      : "";
    if (
      /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/.test(
        bucketFromVirtualHost,
      ) ||
      /\/source\//.test(path) ||
      /\/jobs\//.test(path) ||
      /\/candidates\//.test(path)
    ) {
      return false;
    }
  } catch {
    return false;
  }

  return true;
}

function requirePathSegment(value: string, label: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
    throw new HttpsError(
      "invalid-argument",
      `${label} is not a safe path segment.`,
    );
  }
  return normalized;
}

function getCallableData(
  request: CallableRequest<unknown>,
): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

export function parseGcsUri(source: string, label = "imageRef"): GcsRef {
  const match = source.match(/^(?:gs|gcs):\/\/([^/]+)\/(.+)$/);
  if (!match) {
    throw new HttpsError(
      "invalid-argument",
      `${label} must be a gs:// or gcs:// URI.`,
    );
  }
  const bucket = match[1].trim();
  const path = match[2].trim();
  if (!bucket || !path || path.startsWith("/") || path.includes("..")) {
    throw new HttpsError(
      "invalid-argument",
      `${label} is not a safe GCS object ref.`,
    );
  }
  return { bucket, path };
}

function encodeStoragePath(path: string): string {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function buildApprovedAvatarPath(uid: string, avatarId: string): string {
  return `users/${requirePathSegment(uid, "uid")}/avatar/${requirePathSegment(avatarId, "avatarId")}.png`;
}

export function buildApprovedAvatarStoragePath(
  uid: string,
  avatarId: string,
): string {
  return `gs://${approvedAvatarBucket()}/${buildApprovedAvatarPath(uid, avatarId)}`;
}

function approvedAvatarPublicBaseUrl(): string {
  return process.env.APPROVED_AVATAR_PUBLIC_BASE_URL?.trim() ?? "";
}

export function buildApprovedAvatarPublicUrl(
  bucket: string,
  path: string,
  downloadToken?: string,
): string {
  const configuredBase = approvedAvatarPublicBaseUrl();
  if (configuredBase && configuredBase.length > 0) {
    const base = configuredBase.replace(/\/+$/, "");
    return `${base}/${encodeStoragePath(path)}`;
  }
  if (!downloadToken) {
    throw new HttpsError(
      "internal",
      "Approved avatar download token was not created.",
    );
  }
  return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(
    bucket,
  )}/o/${encodeURIComponent(path)}?alt=media&token=${encodeURIComponent(downloadToken)}`;
}

export function buildAvatarId(candidateId: string): string {
  return `avatar_${requirePathSegment(candidateId, "candidateId").replace(/^cand_/, "")}`;
}

function timestampMillis(value: unknown): number | null {
  if (value instanceof Timestamp) return value.toMillis();
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number" && Number.isFinite(value)) return value;
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

function isExpired(value: unknown, nowMs: number): boolean {
  const expiresAtMs = timestampMillis(value);
  return expiresAtMs != null && expiresAtMs <= nowMs;
}

function assertTempCandidateRef(imageRef: string): GcsRef {
  const parsed = parseGcsUri(imageRef, "candidate imageRef");
  if (parsed.bucket !== avatarTempBucket()) {
    throw new HttpsError(
      "failed-precondition",
      "Candidate image is not in the avatar temp bucket.",
    );
  }
  return parsed;
}

function qaPreviewAllowed(candidate: Record<string, unknown>): boolean {
  const qa = readMap(candidate.qa);
  return qa.previewAllowed === true;
}

export function canPreviewCandidate(
  candidate: Record<string, unknown>,
  nowMs = Date.now(),
): boolean {
  return (
    asString(candidate.status) === "preview_ready" &&
    qaPreviewAllowed(candidate) &&
    !isExpired(candidate.expiresAt, nowMs)
  );
}

type AvatarCurrentJobContractResult =
  | {
      ok: true;
      currentAvatarSourcePhotoId: string;
    }
  | {
      ok: false;
      errorCode: "avatar_job_superseded";
      reason: string;
    };

function sourcePhotoIdsForJob(jobData: Record<string, unknown>): string[] {
  const sourcePhotoIds = normalizeStringList(jobData.sourcePhotoIds);
  const legacySourcePhotoId = asString(jobData.sourcePhotoId);
  return legacySourcePhotoId && !sourcePhotoIds.includes(legacySourcePhotoId)
    ? [...sourcePhotoIds, legacySourcePhotoId]
    : sourcePhotoIds;
}

function currentSourceEntry(
  privateData: Record<string, unknown>,
  currentAvatarSourcePhotoId: string,
): Record<string, unknown> | null {
  const sourcePhotos = Array.isArray(privateData.sourcePhotos)
    ? privateData.sourcePhotos
    : [];
  for (const entry of sourcePhotos) {
    if (
      isRecord(entry) &&
      asString(entry.photoId) === currentAvatarSourcePhotoId
    ) {
      return entry;
    }
  }
  return null;
}

function numericValue(value: unknown): number | null {
  const parsed =
    typeof value === "number" ? value : value == null ? NaN : Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

export function checkCurrentAvatarJobContract(params: {
  jobId: string;
  jobData: Record<string, unknown>;
  privateData: Record<string, unknown>;
}): AvatarCurrentJobContractResult {
  const currentAvatarJobId = asString(params.privateData.currentAvatarJobId);
  if (currentAvatarJobId !== params.jobId) {
    return {
      ok: false,
      errorCode: "avatar_job_superseded",
      reason: "current_job_mismatch",
    };
  }

  const currentAvatarSourcePhotoId = asString(
    params.privateData.currentAvatarSourcePhotoId,
  );
  if (!currentAvatarSourcePhotoId) {
    return {
      ok: false,
      errorCode: "avatar_job_superseded",
      reason: "missing_current_source",
    };
  }

  if (
    !sourcePhotoIdsForJob(params.jobData).includes(currentAvatarSourcePhotoId)
  ) {
    return {
      ok: false,
      errorCode: "avatar_job_superseded",
      reason: "job_source_mismatch",
    };
  }

  const sourceEntry = currentSourceEntry(
    params.privateData,
    currentAvatarSourcePhotoId,
  );
  if (
    !sourceEntry ||
    asString(sourceEntry.status) !== "active" ||
    asString(sourceEntry.avatarGenerationState) !== "current"
  ) {
    return {
      ok: false,
      errorCode: "avatar_job_superseded",
      reason: "source_not_current",
    };
  }

  const privateSelectionVersion = numericValue(
    params.privateData.avatarSourceSelectionVersion,
  );
  const jobSelectionVersion = numericValue(
    params.jobData.avatarSourceSelectionVersion,
  );
  if (
    privateSelectionVersion !== null &&
    jobSelectionVersion !== null &&
    privateSelectionVersion !== jobSelectionVersion
  ) {
    return {
      ok: false,
      errorCode: "avatar_job_superseded",
      reason: "selection_version_mismatch",
    };
  }

  return { ok: true, currentAvatarSourcePhotoId };
}

function assertCurrentAvatarJobContract(
  result: AvatarCurrentJobContractResult,
): asserts result is Extract<AvatarCurrentJobContractResult, { ok: true }> {
  if (result.ok) return;
  throw new HttpsError("failed-precondition", result.errorCode);
}

function isAvatarJobSupersededError(error: unknown): boolean {
  return (
    error instanceof HttpsError &&
    error.code === "failed-precondition" &&
    error.message.includes("avatar_job_superseded")
  );
}

type AvatarApprovalStatePlan =
  | {
      action: "return_existing";
      approvedAvatarUrl: string;
      avatarId: string;
      selectedCandidateId: string;
      sourceJobId?: string;
    }
  | {
      action: "conflict";
      errorCode: "avatar_already_approved";
      selectedCandidateId: string;
    }
  | {
      action: "reserve";
      avatarId: string;
      selectedCandidateId: string;
      approvalDownloadToken?: string;
    };

const APPROVAL_LOCK_STATUSES = new Set([
  "approved",
  "approval_copying",
  "approval_copy_failed",
]);

export function planAvatarApprovalState(
  userData: Record<string, unknown>,
  candidateId: string,
): AvatarApprovalStatePlan {
  const avatar = readMap(userData.avatar);
  const status = asString(avatar.status);
  const selectedCandidateId = asString(avatar.selectedCandidateId);
  const approvedAvatarUrl = asString(avatar.approvedAvatarUrl);
  if (
    status === "approved" &&
    selectedCandidateId === candidateId &&
    isSafePublicApprovedAvatarUrl(approvedAvatarUrl)
  ) {
    return {
      action: "return_existing",
      approvedAvatarUrl,
      avatarId: asString(avatar.avatarId),
      selectedCandidateId: candidateId,
      sourceJobId: asString(avatar.sourceJobId) || undefined,
    };
  }

  if (
    (status === "approved" && selectedCandidateId !== candidateId) ||
    (selectedCandidateId &&
      selectedCandidateId !== candidateId &&
      APPROVAL_LOCK_STATUSES.has(status))
  ) {
    return {
      action: "conflict",
      errorCode: "avatar_already_approved",
      selectedCandidateId,
    };
  }

  return {
    action: "reserve",
    avatarId:
      selectedCandidateId === candidateId && asString(avatar.avatarId)
        ? requirePathSegment(asString(avatar.avatarId), "avatarId")
        : buildAvatarId(candidateId),
    selectedCandidateId: candidateId,
    approvalDownloadToken:
      selectedCandidateId === candidateId &&
      asString(avatar.approvalDownloadToken)
        ? asString(avatar.approvalDownloadToken)
        : undefined,
  };
}

function assertCandidateOwnedByUser(
  candidate: Record<string, unknown>,
  uid: string,
): void {
  if (asString(candidate.uid) !== uid) {
    throw new HttpsError(
      "permission-denied",
      "Avatar candidate does not belong to this user.",
    );
  }
}

function assertJobOwnedByUser(job: Record<string, unknown>, uid: string): void {
  if (asString(job.uid) !== uid) {
    throw new HttpsError(
      "permission-denied",
      "Avatar job does not belong to this user.",
    );
  }
}

function previewImageSize(): number {
  const value = Number(
    process.env.AVATAR_PREVIEW_IMAGE_SIZE ?? DEFAULT_PREVIEW_IMAGE_SIZE,
  );
  return Number.isFinite(value) && value >= 128
    ? Math.min(value, 768)
    : DEFAULT_PREVIEW_IMAGE_SIZE;
}

async function runtimePreviewImagePayload(ref: GcsRef): Promise<{
  previewImageBase64: string;
  previewMimeType: "image/jpeg";
}> {
  const [sourceBytes] = await getStorage()
    .bucket(ref.bucket)
    .file(ref.path)
    .download();
  const size = previewImageSize();
  const previewBytes = await sharp(sourceBytes, {
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

function safeAvatarJobErrorCode(value: unknown): string {
  const raw = asString(value).trim();
  return /^[a-z0-9_]{1,80}$/.test(raw) ? raw : "";
}

export function avatarPreviewResponseStatus(params: {
  jobStatus: string;
  currentContractOk: boolean;
  candidateCount: number;
  previewableCandidateCount: number;
}): string {
  if (
    !params.currentContractOk &&
    !["approved", "failed", "cancelled", "canceled"].includes(params.jobStatus)
  ) {
    return "superseded";
  }
  if (
    params.jobStatus === "preview_ready" &&
    params.candidateCount > 0 &&
    params.previewableCandidateCount === 0
  ) {
    return "no_previewable_candidates";
  }
  return params.jobStatus;
}

export function createGetAvatarJobCandidatesFunction(
  firestore: Firestore,
  resolveUser: ResolveAvatarApiUser,
) {
  return onCall(
    {
      timeoutSeconds: 60,
      memory: "512MiB",
      invoker: "public",
      enforceAppCheck: true,
    },
    async (request) => {
      const user = await resolveUser(request.auth);
      const uid = requirePathSegment(user.userId, "uid");
      const data = getCallableData(request);
      const jobId = requirePathSegment(asString(data.jobId), "jobId");

      const jobSnap = await firestore.collection("avatarJobs").doc(jobId).get();
      if (!jobSnap.exists) {
        throw new HttpsError("not-found", "Avatar job was not found.");
      }
      const jobData = (jobSnap.data() ?? {}) as Record<string, unknown>;
      assertJobOwnedByUser(jobData, uid);
      const jobStatus = asString(jobData.status);
      const privateSnap = await firestore
        .collection("userPrivateMedia")
        .doc(uid)
        .get();
      const currentContract = checkCurrentAvatarJobContract({
        jobId,
        jobData,
        privateData: (privateSnap.data() ?? {}) as Record<string, unknown>,
      });
      const canReturnCandidates =
        jobStatus === "preview_ready" && currentContract.ok;

      const candidateDocs = canReturnCandidates
        ? (
            await firestore
              .collection("avatarCandidates")
              .where("jobId", "==", jobId)
              .where("uid", "==", uid)
              .get()
          ).docs
        : [];

      const nowMs = Date.now();
      const candidates = canReturnCandidates
        ? await Promise.all(
            candidateDocs
              .map((doc) => ({
                id: doc.id,
                data: (doc.data() ?? {}) as Record<string, unknown>,
              }))
              .filter(({ data: candidate }) =>
                canPreviewCandidate(candidate, nowMs),
              )
              .map(async ({ id, data: candidate }) => {
                const candidateId = asString(candidate.candidateId) || id;
                const imageRef = assertTempCandidateRef(
                  asString(candidate.imageRef),
                );
                return {
                  candidateId,
                  ...(await runtimePreviewImagePayload(imageRef)),
                  qaSummary: {
                    status: "pass",
                  },
                };
              }),
          )
        : [];
      const responseStatus = avatarPreviewResponseStatus({
        jobStatus,
        currentContractOk: currentContract.ok,
        candidateCount: candidateDocs.length,
        previewableCandidateCount: candidates.length,
      });
      const errorCode =
        responseStatus === "superseded" && !currentContract.ok
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
    },
  );
}

export function createApproveAvatarCandidateFunction(
  firestore: Firestore,
  resolveUser: ResolveAvatarApiUser,
) {
  return onCall(
    {
      timeoutSeconds: 120,
      memory: "512MiB",
      invoker: "public",
      enforceAppCheck: true,
    },
    async (request) => {
      const user = await resolveUser(request.auth);
      const uid = requirePathSegment(user.userId, "uid");
      const data = getCallableData(request);
      const candidateId = requirePathSegment(
        asString(data.candidateId),
        "candidateId",
      );
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
        throw new HttpsError("not-found", "Avatar candidate was not found.");
      }
      if (!userSnap.exists) {
        throw new HttpsError(
          "failed-precondition",
          "User profile was not found.",
        );
      }

      const candidateData = (candidateSnap.data() ?? {}) as Record<
        string,
        unknown
      >;
      assertCandidateOwnedByUser(candidateData, uid);

      if (!canPreviewCandidate(candidateData)) {
        throw new HttpsError(
          "failed-precondition",
          "Avatar candidate is not approved for user preview.",
        );
      }

      const jobId = requirePathSegment(asString(candidateData.jobId), "jobId");
      const jobRef = firestore.collection("avatarJobs").doc(jobId);
      const jobSnap = await jobRef.get();
      if (!jobSnap.exists) {
        throw new HttpsError(
          "failed-precondition",
          "Avatar job was not found.",
        );
      }
      const jobData = (jobSnap.data() ?? {}) as Record<string, unknown>;
      assertJobOwnedByUser(jobData, uid);
      const privateSnap = await privateRef.get();
      assertCurrentAvatarJobContract(
        checkCurrentAvatarJobContract({
          jobId,
          jobData,
          privateData: (privateSnap.data() ?? {}) as Record<string, unknown>,
        }),
      );

      const sourceImage = assertTempCandidateRef(
        asString(candidateData.imageRef),
      );

      const reservation = await firestore.runTransaction(async (tx) => {
        const [freshCandidate, freshUser, freshJob, freshPrivate] =
          await Promise.all([
            tx.get(candidateRef),
            tx.get(userRef),
            tx.get(jobRef),
            tx.get(privateRef),
          ]);
        if (!freshCandidate.exists || !freshUser.exists || !freshJob.exists) {
          throw new HttpsError(
            "failed-precondition",
            "Avatar approval state changed.",
          );
        }

        const freshCandidateData = (freshCandidate.data() ?? {}) as Record<
          string,
          unknown
        >;
        const freshUserData = (freshUser.data() ?? {}) as Record<
          string,
          unknown
        >;
        const freshJobData = (freshJob.data() ?? {}) as Record<string, unknown>;
        assertCandidateOwnedByUser(freshCandidateData, uid);
        assertJobOwnedByUser(freshJobData, uid);
        assertCurrentAvatarJobContract(
          checkCurrentAvatarJobContract({
            jobId,
            jobData: freshJobData,
            privateData: (freshPrivate.data() ?? {}) as Record<string, unknown>,
          }),
        );

        const plan = planAvatarApprovalState(freshUserData, candidateId);
        if (plan.action === "return_existing") {
          return {
            action: "return_existing" as const,
            approvedAvatarUrl: plan.approvedAvatarUrl,
            avatarId: plan.avatarId,
          };
        }
        if (plan.action === "conflict") {
          throw new HttpsError(
            "failed-precondition",
            "avatar_already_approved: A different avatar candidate has already been approved.",
          );
        }

        if (!canPreviewCandidate(freshCandidateData)) {
          throw new HttpsError(
            "failed-precondition",
            "Avatar candidate is no longer available for approval.",
          );
        }

        const jobStatus = asString(freshJobData.status);
        if (jobStatus !== "preview_ready" && jobStatus !== "approval_copying") {
          throw new HttpsError(
            "failed-precondition",
            "Avatar job is not ready for candidate approval.",
          );
        }

        const avatarId = plan.avatarId;
        const destinationPath = buildApprovedAvatarPath(uid, avatarId);
        const destinationBucket = approvedAvatarBucket();
        const downloadToken = approvedAvatarPublicBaseUrl()
          ? undefined
          : randomUUID();
        const approvedAvatarUrl = buildApprovedAvatarPublicUrl(
          destinationBucket,
          destinationPath,
          downloadToken,
        );
        const approvedAvatarStoragePath = buildApprovedAvatarStoragePath(
          uid,
          avatarId,
        );

        tx.update(userRef, {
          profileImageMode: "avatar",
          "avatar.status": "approval_copying",
          "avatar.approvedAvatarUrl": FieldValue.delete(),
          "avatar.approvedAvatarStoragePath": approvedAvatarStoragePath,
          "avatar.avatarId": avatarId,
          "avatar.selectedCandidateId": candidateId,
          "avatar.sourceJobId": jobId,
          "avatar.updatedAt": FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
        tx.set(
          jobRef,
          {
            status: "approval_copying",
            selectedCandidateId: candidateId,
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true },
        );
        tx.set(
          candidateRef,
          {
            status: "approval_copying",
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true },
        );

        return {
          action: "reserved" as const,
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

      const sourceFile = getStorage()
        .bucket(sourceImage.bucket)
        .file(sourceImage.path);
      const destinationFile = getStorage()
        .bucket(reservation.destinationBucket)
        .file(reservation.destinationPath);
      let copiedApprovedObject = false;
      let finalTransactionReturnedExisting = false;
      let finalExistingApproval: {
        approvedAvatarUrl: string;
        avatarId: string;
      } | null = null;
      const objectMetadata: Record<string, string> = {
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
          const [freshCandidate, freshUser, freshJob, freshPrivate] =
            await Promise.all([
              tx.get(candidateRef),
              tx.get(userRef),
              tx.get(jobRef),
              tx.get(privateRef),
            ]);
          if (!freshCandidate.exists || !freshUser.exists || !freshJob.exists) {
            throw new HttpsError(
              "failed-precondition",
              "Avatar approval state changed.",
            );
          }

          const freshCandidateData = (freshCandidate.data() ?? {}) as Record<
            string,
            unknown
          >;
          const freshUserData = (freshUser.data() ?? {}) as Record<
            string,
            unknown
          >;
          const freshJobData = (freshJob.data() ?? {}) as Record<
            string,
            unknown
          >;
          assertCandidateOwnedByUser(freshCandidateData, uid);
          assertJobOwnedByUser(freshJobData, uid);
          assertCurrentAvatarJobContract(
            checkCurrentAvatarJobContract({
              jobId,
              jobData: freshJobData,
              privateData: (freshPrivate.data() ?? {}) as Record<
                string,
                unknown
              >,
            }),
          );

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
            throw new HttpsError(
              "failed-precondition",
              "avatar_already_approved: A different avatar candidate has already been approved.",
            );
          }

          const currentAvatar = readMap(freshUserData.avatar);
          if (
            asString(currentAvatar.status) !== "approval_copying" ||
            asString(currentAvatar.selectedCandidateId) !== candidateId
          ) {
            throw new HttpsError(
              "failed-precondition",
              "Avatar approval reservation was lost.",
            );
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
              updatedAt: FieldValue.serverTimestamp(),
            },
            "onboarding.avatarUrls": [reservation.approvedAvatarUrl],
            "onboarding.avatarGenerationJobId": FieldValue.delete(),
            "onboarding.avatarSourceSelectionVersion": FieldValue.delete(),
            "onboarding.sourcePhotoUploadStatus": FieldValue.delete(),
            "onboarding.photoUrls": writeLegacyOnboardingPhotoUrls()
              ? [reservation.approvedAvatarUrl]
              : FieldValue.delete(),
            updatedAt: FieldValue.serverTimestamp(),
          });

          tx.set(
            jobRef,
            {
              status: "approved",
              selectedCandidateId: candidateId,
              approvedAt: FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          tx.set(
            candidateRef,
            {
              status: "approved",
              approvedAvatarUrl: reservation.approvedAvatarUrl,
              approvedAvatarStoragePath: reservation.approvedAvatarStoragePath,
              approvedAt: FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
        });
      } catch (error) {
        if (copiedApprovedObject && !finalTransactionReturnedExisting) {
          try {
            await destinationFile.delete({ ignoreNotFound: true });
          } catch (deleteError) {
            logger.error(
              "Failed to delete orphaned approved avatar after approval failure",
              {
                uid: logIdentifier("uid", uid),
                jobId: logIdentifier("job", jobId),
                candidateId: logIdentifier("candidate", candidateId),
                avatarId: logIdentifier("avatar", reservation.avatarId),
                error:
                  deleteError instanceof Error
                    ? deleteError.message
                    : String(deleteError),
              },
            );
          }
        }
        if (!isAvatarJobSupersededError(error)) {
          await userRef.set(
            {
              avatar: {
                status: "approval_copy_failed",
                avatarId: reservation.avatarId,
                selectedCandidateId: candidateId,
                sourceJobId: jobId,
                approvedAvatarStoragePath:
                  reservation.approvedAvatarStoragePath,
                updatedAt: FieldValue.serverTimestamp(),
              },
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
        }
        throw error;
      }

      const existingApprovalAfterCopy = finalExistingApproval as {
        approvedAvatarUrl: string;
        avatarId: string;
      } | null;
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
        if (sibling.id === candidateId) continue;
        batch.set(
          sibling.ref,
          {
            status: "unselected",
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true },
        );
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
    },
  );
}
