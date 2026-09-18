import { PubSub } from "@google-cloud/pubsub";
import { CloudTasksClient, protos } from "@google-cloud/tasks";
import { createHash } from "crypto";
import {
  FieldValue,
  type Firestore,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableOptions,
  type CallableRequest,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import {
  canPreviewCandidate,
  isSoftNeedsReviewAvatarCandidate,
} from "./avatarApproval";

const DEFAULT_REGION = "asia-northeast3";
const DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos";
const DEFAULT_CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-final-chat-profile-photos";
const DEFAULT_AVATAR_MODEL_ID = "azure_gpt_image_2";
const CLIP_EMBEDDING_VERSION = "clip-vit-large-patch14_v1";
const CHAT_REAL_PHOTO_CONSENT_VERSION = "chat_real_photo_visibility_v1";
export const AVATAR_SOURCE_CONSENT_VERSION = "photo_consent_v4";
const AVATAR_UPLOAD_REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$/;
export const AVATAR_UPLOAD_SOURCE_PHOTO_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 120,
  memory: "1GiB",
  invoker: "public",
  enforceAppCheck: true,
};

export const CURRENT_AVATAR_GENERATION_STATUS_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 30,
  memory: "256MiB",
  invoker: "public",
  enforceAppCheck: true,
};

export const RETRY_CURRENT_AVATAR_GENERATION_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 60,
  memory: "512MiB",
  invoker: "public",
  enforceAppCheck: true,
};

type UploadAuth = CallableRequest<unknown>["auth"];

export type ResolvedAvatarUploadUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
};

type ResolveUploadUser = (
  auth: UploadAuth,
) => Promise<ResolvedAvatarUploadUser>;

type SourcePhotoEntry = Record<string, unknown> & {
  photoId?: string;
  gcsUri?: string;
  storageBucket?: string;
  storagePath?: string;
  sha256?: string;
  status?: string;
  avatarGenerationState?: string;
};

export type QueueKind = "avatar_generation" | "clip_embedding";

/// Cloud Task/PubSub dispatch only depends on these fields. The legacy
/// single-photo payload and the source-set payload share ONE enqueue contract
/// (queue name, target URL, OIDC, deadline, deterministic task name, retry
/// semantics, redaction) so the two cannot drift apart.
export type QueueDispatchPayload = {
  uid: string;
  jobId?: string;
  sourcePhotoIds: string[];
  sourcePhotoRefs: string[];
  jobType: string;
  schemaVersion: string;
  idempotencyKey: string;
} & Record<string, unknown>;

type ClipJobPayload = {
  uid: string;
  sourcePhotoIds: string[];
  sourcePhotoRefs: string[];
  consentPurposes: AvatarConsentPurposes;
  embeddingVersion: string;
  jobType: "clip_embedding";
  schemaVersion: "clip_job_v1";
  idempotencyKey: string;
};

function envValue(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

function truthyEnv(name: string): boolean {
  return ["1", "true", "yes", "y", "on"].includes(
    process.env[name]?.trim().toLowerCase() ?? "",
  );
}

const AVATAR_UPLOAD_ALLOWLIST_ENV_VARS = [
  "AVATAR_UPLOAD_ALLOWED_UIDS",
  "AVATAR_GENERATION_ALLOWED_UIDS",
  "AVATAR_INTERNAL_SMOKE_ALLOWED_UIDS",
];

export type AvatarUploadAllowlistDecision = {
  enabled: boolean;
  allowed: boolean;
};

function parseAvatarUploadAllowlist(env: NodeJS.ProcessEnv): Set<string> {
  const allowedUids = new Set<string>();
  for (const envName of AVATAR_UPLOAD_ALLOWLIST_ENV_VARS) {
    const rawValue = env[envName];
    if (!rawValue) continue;
    for (const token of rawValue.split(/[\s,;]+/)) {
      const uid = token.trim();
      if (uid) {
        allowedUids.add(uid);
      }
    }
  }
  return allowedUids;
}

export function evaluateAvatarUploadAllowlist(
  uid: string,
  env: NodeJS.ProcessEnv = process.env,
): AvatarUploadAllowlistDecision {
  const allowedUids = parseAvatarUploadAllowlist(env);
  if (allowedUids.size === 0) {
    return { enabled: false, allowed: true };
  }
  return {
    enabled: true,
    allowed: allowedUids.has(uid),
  };
}

function isProductionEnvironment(): boolean {
  const environment = process.env.ENVIRONMENT?.trim().toLowerCase();
  return (
    environment === "production" ||
    environment === "prod" ||
    environment === "production_bridge" ||
    process.env.NODE_ENV === "production"
  );
}

/**
 * 배포된 Firebase/Cloud Run 런타임인가.
 *
 * `ENVIRONMENT` 는 사람이 설정하는 라벨이라 실수로 빠지거나 어긋난다. 실제로
 * 프로덕션 Functions 는 `ENVIRONMENT=staging` 으로 떠 있다. 반면 `K_SERVICE`
 * 와 `FUNCTION_TARGET` 은 플랫폼이 주입하므로 배포 여부를 라벨보다 정확하게
 * 말해 준다. 에뮬레이터는 `FUNCTIONS_EMULATOR` 로 자신을 밝힌다.
 */
export function isDeployedFunctionsRuntime(): boolean {
  if (truthyEnv("FUNCTIONS_EMULATOR")) return false;
  return Boolean(
    process.env.K_SERVICE?.trim() || process.env.FUNCTION_TARGET?.trim(),
  );
}

function isLocalEnvironment(): boolean {
  const environment = process.env.ENVIRONMENT?.trim().toLowerCase();
  return (
    environment === "local" ||
    environment === "development" ||
    environment === "dev"
  );
}

function allowInsecureLocalWorkerInvocation(): boolean {
  return (
    isLocalEnvironment() &&
    (truthyEnv("ALLOW_INSECURE_WORKER_LOCAL") ||
      truthyEnv("AVATAR_WORKER_ALLOW_INSECURE_LOCAL"))
  );
}

export function clipEmbeddingQueueEnabled(): boolean {
  const raw = process.env.CLIP_EMBEDDING_QUEUE_ENABLED?.trim().toLowerCase();
  if (!raw) return true;
  return ["1", "true", "yes", "y", "on"].includes(raw);
}

function sourcePhotoBucket(): string {
  return envValue("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET);
}

export function chatProfilePhotoBucket(): string {
  return envValue(
    "CHAT_PROFILE_PHOTO_BUCKET",
    DEFAULT_CHAT_PROFILE_PHOTO_BUCKET,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readMap(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function safeDecodeUriComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

const PRIVATE_AVATAR_STORAGE_MARKERS = [
  "private-source-photos",
  "avatar-temp",
  "chat-profile-photos",
];

function hasPrivateAvatarStorageMarker(value: string): boolean {
  return PRIVATE_AVATAR_STORAGE_MARKERS.some((marker) => value.includes(marker));
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
export type AvatarConsentPurposes = {
  avatarGeneration: true;
  clipRecommendation: boolean;
  sourcePhotoRetention: boolean;
};

export type AvatarUploadRequestMetadata = {
  clientRequestId: string;
  consentVersion: typeof AVATAR_SOURCE_CONSENT_VERSION;
  consentPurposes: AvatarConsentPurposes;
};

export function requireAvatarConsentPurposes(value: unknown): AvatarConsentPurposes {
  const purposes = isRecord(value) ? value : null;
  if (
    !purposes ||
    purposes.avatarGeneration !== true ||
    typeof purposes.clipRecommendation !== "boolean" ||
    typeof purposes.sourcePhotoRetention !== "boolean"
  ) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_consent_invalid",
    );
  }
  return {
    avatarGeneration: true,
    clipRecommendation: purposes.clipRecommendation,
    sourcePhotoRetention: purposes.sourcePhotoRetention,
  };
}

const DEFAULT_AVATAR_CONSENT_PURPOSES: AvatarConsentPurposes = {
  avatarGeneration: true,
  clipRecommendation: false,
  sourcePhotoRetention: false,
};

function cloneConsentPurposes(
  consentPurposes: AvatarConsentPurposes,
): AvatarConsentPurposes {
  return {
    avatarGeneration: true,
    clipRecommendation: consentPurposes.clipRecommendation,
    sourcePhotoRetention: consentPurposes.sourcePhotoRetention,
  };
}

function safeAvatarMediaErrorCode(
  value: unknown,
): string | number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  const lower = trimmed.toLowerCase();
  if (
    !/^[A-Za-z0-9_.:/-]{1,80}$/.test(trimmed) ||
    lower.startsWith("http://") ||
    lower.startsWith("https://") ||
    lower.startsWith("gs://") ||
    lower.startsWith("gcs://") ||
    lower.includes("token") ||
    lower.includes("signature") ||
    lower.includes("users/") ||
    lower.includes("/source/") ||
    lower.includes("/jobs/") ||
    lower.includes("/candidates/")
  ) {
    return undefined;
  }
  return trimmed;
}

export function safeAvatarMediaErrorLogFields(error: unknown): {
  errorType: string;
  errorCode?: string | number;
} {
  const errorCode = isRecord(error)
    ? safeAvatarMediaErrorCode(error.code)
    : undefined;
  return {
    errorType:
      error instanceof HttpsError
        ? "HttpsError"
        : error instanceof Error
          ? "Error"
          : typeof error,
    ...(errorCode !== undefined ? { errorCode } : {}),
  };
}

function isTerminalAvatarProcessingStatus(value: unknown): boolean {
  return new Set([
    "preview_ready",
    "approved",
    "completed",
    "failed",
    "retryable_failed",
    "terminal_failed",
    "no_previewable",
    "no_previewable_candidates",
    "needs_review",
    "superseded",
    "cancelled",
    "canceled",
  ]).has(asString(value).toLowerCase());
}

function isTerminalClipProcessingStatus(value: unknown): boolean {
  return new Set([
    "not_requested",
    "completed",
    "ready",
    "failed",
    "terminal_failed",
    "skipped",
    "disabled",
  ]).has(asString(value).toLowerCase());
}

export function buildAvatarSourceLifecycleState(params: {
  consentPurposes: AvatarConsentPurposes;
  avatarStatus: unknown;
  clipStatus?: unknown;
}): {
  sourceDeletionEligible: boolean;
  sourceDeletionStatus: "retained_by_consent" | "pending_terminal_processing" | "scheduled";
  waitForClipTerminal: boolean;
} {
  if (params.consentPurposes.sourcePhotoRetention) {
    return {
      sourceDeletionEligible: false,
      sourceDeletionStatus: "retained_by_consent",
      waitForClipTerminal: false,
    };
  }

  const avatarTerminal = isTerminalAvatarProcessingStatus(params.avatarStatus);
  const waitForClipTerminal =
    params.consentPurposes.clipRecommendation &&
    !isTerminalClipProcessingStatus(params.clipStatus ?? "not_requested");
  const eligible = avatarTerminal && !waitForClipTerminal;
  return {
    sourceDeletionEligible: eligible,
    sourceDeletionStatus: eligible ? "scheduled" : "pending_terminal_processing",
    waitForClipTerminal,
  };
}

export function requireAvatarUploadRequestMetadata(
  value: unknown,
): AvatarUploadRequestMetadata {
  const data = readMap(value);
  const clientRequestId = asString(data.clientRequestId);
  if (!AVATAR_UPLOAD_REQUEST_ID.test(clientRequestId)) {
    throw new HttpsError(
      "invalid-argument",
      "avatar_upload_request_invalid",
    );
  }
  const consentVersion = asString(data.consentVersion);
  if (consentVersion !== AVATAR_SOURCE_CONSENT_VERSION) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_consent_invalid",
    );
  }
  const consentPurposes = requireAvatarConsentPurposes(data.consentPurposes);
  return { clientRequestId, consentVersion, consentPurposes };
}

function sha256Hex(bytes: Buffer | string): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export function buildChatProfilePhotoStoragePath(
  uid: string,
  photoId: string,
): string {
  return `users/${requirePathSegment(uid, "uid")}/chat-profile/${requirePathSegment(photoId, "photoId")}.jpg`;
}

function buildGcsUri(bucket: string, storagePath: string): string {
  return `gs://${bucket}/${storagePath}`;
}

function readSourcePhotos(value: unknown): SourcePhotoEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((entry) => ({ ...entry }));
}

export function shouldSupersedeAvatarJobStatus(value: unknown): boolean {
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

export function buildAvatarSourceEntry(params: {
  photoId: string;
  gcsUri: string;
  storagePath: string;
  sizeBytes: number;
  imageSha256: string;
  clientRequestId: string;
  consentVersion: string;
  consentPurposes?: AvatarConsentPurposes;
  uploadedAt: unknown;
  updatedAt: unknown;
}): SourcePhotoEntry {
  return {
    photoId: params.photoId,
    gcsUri: params.gcsUri,
    storageBucket: sourcePhotoBucket(),
    storagePath: params.storagePath,
    contentType: "image/jpeg",
    sizeBytes: params.sizeBytes,
    sha256: params.imageSha256,
    uploadClientRequestId: params.clientRequestId,
    consentVersion: params.consentVersion,
    exifStripped: true,
    encrypted: true,
    status: "active",
    avatarGenerationState: "current",
    consentPurposes: cloneConsentPurposes(
      params.consentPurposes ?? DEFAULT_AVATAR_CONSENT_PURPOSES,
    ),
    purpose: cloneConsentPurposes(
      params.consentPurposes ?? DEFAULT_AVATAR_CONSENT_PURPOSES,
    ),
    lifecycle: buildAvatarSourceLifecycleState({
      consentPurposes: params.consentPurposes ?? DEFAULT_AVATAR_CONSENT_PURPOSES,
      avatarStatus: "queued",
      clipStatus: (params.consentPurposes ?? DEFAULT_AVATAR_CONSENT_PURPOSES)
        .clipRecommendation
        ? "pending"
        : "not_requested",
    }),
    uploadedAt: params.uploadedAt,
    updatedAt: params.updatedAt,
  };
}

function activeSourcePhotoIds(sourcePhotos: SourcePhotoEntry[]): string[] {
  return Array.from(
    new Set(
      sourcePhotos
        .filter((entry) => entry.status === "active")
        .map((entry) => asString(entry.photoId))
        .filter(Boolean),
    ),
  ).sort();
}

export type ChatRealPhotoMetadata = {
  photoId: string;
  enabled: boolean;
  consentVersion: string;
  sourcePhotoId: string;
  storageBucket?: string;
  storagePath?: string;
  gcsUri?: string;
  contentType?: string;
  sizeBytes?: number;
  exifStripped?: boolean;
  updatedAt: unknown;
};

export function buildChatRealPhotoMetadata(params: {
  uid: string;
  photoId: string;
  sizeBytes: number;
  updatedAt: unknown;
}): ChatRealPhotoMetadata {
  const storageBucket = chatProfilePhotoBucket();
  const storagePath = buildChatProfilePhotoStoragePath(
    params.uid,
    params.photoId,
  );
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

export function buildDisabledChatRealPhotoMetadata(
  updatedAt: unknown,
): ChatRealPhotoMetadata {
  return {
    photoId: "",
    enabled: false,
    consentVersion: CHAT_REAL_PHOTO_CONSENT_VERSION,
    sourcePhotoId: "",
    updatedAt,
  };
}

export function buildPrivateMediaPayload(
  sourcePhotos: SourcePhotoEntry[],
  params: {
    chatPartnerRealPhotoDisclosure?: boolean;
    chatRealPhoto?: ChatRealPhotoMetadata;
    currentAvatarSourcePhotoId?: string;
    currentAvatarJobId?: string;
    avatarSourceSelectionVersion?: number;
    consentPurposes?: AvatarConsentPurposes;
  } = {},
) {
  const consentPurposes = params.consentPurposes ?? DEFAULT_AVATAR_CONSENT_PURPOSES;
  const payload: Record<string, any> = {
    sourcePhotos,
    photoConsent: {
      avatarGeneration: true,
      clipRecommendation: consentPurposes.clipRecommendation,
      profileDisplayOriginalPhoto: false,
      chatPartnerRealPhotoDisclosure:
        params.chatPartnerRealPhotoDisclosure === true,
      sourcePhotoRetention: consentPurposes.sourcePhotoRetention,
      consentedAt: FieldValue.serverTimestamp(),
      version: AVATAR_SOURCE_CONSENT_VERSION,
      purposes: cloneConsentPurposes(consentPurposes),
    },
    chatRealPhoto:
      params.chatRealPhoto ??
      buildDisabledChatRealPhotoMetadata(FieldValue.serverTimestamp()),
    clip: {
      embeddingStatus: consentPurposes.clipRecommendation ? "pending" : "not_requested",
      embeddingVersion: CLIP_EMBEDDING_VERSION,
      sourcePhotoIds: activeSourcePhotoIds(sourcePhotos),
      updatedAt: FieldValue.serverTimestamp(),
    },
    updatedAt: FieldValue.serverTimestamp(),
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

export function buildClipPayload(
  uid: string,
  photoId: string,
  gcsUri: string,
): ClipJobPayload;
export function buildClipPayload(
  uid: string,
  photoId: string,
  gcsUri: string,
  consentPurposes: AvatarConsentPurposes,
): ClipJobPayload | null;
export function buildClipPayload(
  uid: string,
  photoId: string,
  gcsUri: string,
  consentPurposes: AvatarConsentPurposes = DEFAULT_AVATAR_CONSENT_PURPOSES,
): ClipJobPayload | null {
  if (!consentPurposes.clipRecommendation) return null;
  return {
    uid,
    sourcePhotoIds: [photoId],
    sourcePhotoRefs: [gcsUri],
    consentPurposes: cloneConsentPurposes(consentPurposes),
    embeddingVersion: CLIP_EMBEDDING_VERSION,
    jobType: "clip_embedding",
    schemaVersion: "clip_job_v1",
    idempotencyKey: `${uid}:${photoId}:clip_embedding_v1`,
  };
}

export function isSafeApprovedAvatarUrl(value: unknown): boolean {
  const url = asString(value);
  if (!url) return false;
  const decodedLower = safeDecodeUriComponent(url).toLowerCase();
  if (
    decodedLower.startsWith("gs://") ||
    decodedLower.startsWith("gcs://") ||
    hasPrivateAvatarStorageMarker(decodedLower) ||
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
    const parsed = new URL(url);
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      !parsed.hostname
    ) {
      return false;
    }
    const host = parsed.hostname.toLowerCase();
    const path = safeDecodeUriComponent(parsed.pathname).toLowerCase();
    const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
      ? host.replace(".storage.googleapis.com", "")
      : "";
    return (
      !hasPrivateAvatarStorageMarker(bucketFromVirtualHost) &&
      !/\/source\//.test(path) &&
      !/\/jobs\//.test(path) &&
      !/\/candidates\//.test(path)
    );
  } catch {
    return false;
  }
}

function hasApprovedAvatarLock(userAvatar: unknown): boolean {
  const avatar = readMap(userAvatar);
  return (
    asString(avatar.status).toLowerCase() === "approved" ||
    asString(avatar.approvedAvatarUrl).length > 0
  );
}

const ACTIVE_AVATAR_WORKFLOW_STATUSES = new Set([
  "queued",
  "generating",
  "running",
  "qa_pending",
  "preview_ready",
  "needs_review",
  "no_previewable",
  "no_previewable_candidates",
  "failed",
  "retryable_failed",
  "terminal_failed",
]);

export function hasActiveAvatarWorkflowState(userAvatar: unknown): boolean {
  return ACTIVE_AVATAR_WORKFLOW_STATUSES.has(
    asString(readMap(userAvatar).status).toLowerCase(),
  );
}

function hasActiveCurrentSourceEntry(privateData: Record<string, unknown>): boolean {
  return readSourcePhotos(privateData.sourcePhotos).some(
    (entry) =>
      entry.status === "active" && entry.avatarGenerationState === "current",
  );
}
export type CurrentAvatarContract = {
  sourceLocked: boolean;
  sourceId: string | null;
  jobId: string | null;
  sourceSelectionVersion: number;
  sourceEntry: SourcePhotoEntry | null;
  /// Two-phase source-set admission: the job pointer exists but the worker
  /// has not chosen (or failed to choose) the best source yet. Legal state.
  sourceSelecting: boolean;
};

const SOURCE_SELECTION_NO_SOURCE_STATES = new Set(["pending", "failed"]);

function isSourceSelectionWithoutSource(
  privateData: Record<string, unknown>,
): boolean {
  const selection = readMap(privateData.avatarSourceSelection);
  return SOURCE_SELECTION_NO_SOURCE_STATES.has(
    asString(selection.status).toLowerCase(),
  );
}

export function readCurrentAvatarContract(
  privateData: unknown,
): CurrentAvatarContract {
  const data = readMap(privateData);
  const sourceId = asString(data.currentAvatarSourcePhotoId);
  const jobId = asString(data.currentAvatarJobId);
  const sourceSelectionVersion = Math.max(
    0,
    Math.floor(Number(data.avatarSourceSelectionVersion ?? 0) || 0),
  );

  if (jobId && !sourceId) {
    // Phase A wrote the job pointer; Phase B has not locked a source. This is
    // only legal while the private doc carries an explicit selection state.
    if (
      !isSourceSelectionWithoutSource(data) ||
      hasActiveCurrentSourceEntry(data)
    ) {
      throw new HttpsError("failed-precondition", "avatar_state_inconsistent");
    }
    return {
      sourceLocked: true,
      sourceId: null,
      jobId,
      sourceSelectionVersion,
      sourceEntry: null,
      sourceSelecting: true,
    };
  }
  if (Boolean(sourceId) !== Boolean(jobId)) {
    throw new HttpsError("failed-precondition", "avatar_state_inconsistent");
  }

  if (!sourceId || !jobId) {
    if (hasActiveCurrentSourceEntry(data)) {
      throw new HttpsError("failed-precondition", "avatar_state_inconsistent");
    }
    return {
      sourceLocked: false,
      sourceId: null,
      jobId: null,
      sourceSelectionVersion,
      sourceEntry: null,
      sourceSelecting: false,
    };
  }

  const sourceEntry =
    readSourcePhotos(data.sourcePhotos).find(
      (entry) =>
        asString(entry.photoId) === sourceId &&
        entry.status === "active" &&
        entry.avatarGenerationState === "current",
    ) ?? null;
  if (!sourceEntry) {
    throw new HttpsError("failed-precondition", "avatar_state_inconsistent");
  }

  return {
    sourceLocked: true,
    sourceId,
    jobId,
    sourceSelectionVersion,
    sourceEntry,
    sourceSelecting: false,
  };
}

function normalizeAvatarPresentationGender(value: unknown): string {
  const raw = asString(value).toLowerCase();
  if (["female", "f", "woman", "\uC5EC\uC131", "\uC5EC\uC790"].includes(raw)) return "female";
  if (["male", "m", "man", "\uB0A8\uC131", "\uB0A8\uC790"].includes(raw)) return "male";
  if (["other", "non_binary", "non-binary", "nonbinary"].includes(raw))
    return "non_binary";
  if (["prefer_not_to_say", "prefer-not-to-say", "unknown", ""].includes(raw)) {
    return raw === "prefer_not_to_say" || raw === "prefer-not-to-say"
      ? "prefer_not_to_say"
      : "unknown";
  }
  return "unknown";
}

export function avatarPresentationGenderFromUserData(
  userData: Record<string, unknown>,
): string {
  const onboarding = readMap(userData.onboarding);
  return normalizeAvatarPresentationGender(onboarding.gender);
}

// 워커가 실제로 기록하는 진행 중 상태들. 공개 상태로는 "running" 으로 접어
// 클라이언트 어휘를 늘리지 않되 terminal_failed 로 오분류되지 않게 한다.
const IN_FLIGHT_WORKER_JOB_STATUSES = new Set([
  "provider_inflight",
  "generated",
  "persisted",
]);

const SAFE_AVATAR_STATUS_VALUES = new Set([
  "queued",
  "running",
  "qa_pending",
  "approval_copying",
  "preview_ready",
  "needs_review",
  "no_previewable",
  "no_previewable_candidates",
  "retryable_failed",
  "terminal_failed",
  "reconciliation_required",
  "source_selecting",
  "approved",
]);

const RETRYABLE_CURRENT_AVATAR_STATUSES = new Set([
  "retryable_failed",
  "no_previewable",
  "no_previewable_candidates",
]);

const SAFE_AVATAR_REASON_CODES = new Set([
  // 사진 문제와 서버 문제를 사용자에게 다르게 말하기 위한 코드.
  "avatar_generation_infrastructure_failed",
  "avatar_source_unavailable",
  // 워커가 이미 기록하는 콘텐츠 사유들. 클라이언트에 그대로 전달해야
  // "다른 사진으로" 라는 안내가 실제 이유와 함께 나간다.
  "avatar_no_eligible_source_photo",
  "avatar_source_no_face",
  "avatar_source_multi_face",
  "avatar_source_face_too_small",
  "avatar_source_face_too_blurry",
  "avatar_source_face_out_of_frame",
  "avatar_source_landmarks_unstable",
  "avatar_source_low_light",
  "avatar_source_compression_damage",
  "avatar_source_analysis_uncertain",
  "avatar_background_text_logo_risky",
  "avatar_generation_paused",
  "avatar_provider_outcome_unknown",
  "avatar_queue_dispatch_failed",
  "avatar_budget_exceeded",
  "avatar_queue_enqueue_failed",
  "avatar_retry_not_allowed",
  "avatar_retry_limit_reached",
  "avatar_state_inconsistent",
  "avatar_worker_cost_guard_paused",
  "cost_kill_switch_enabled",
  "daily_generation_quota_exceeded",
  "monthly_generation_quota_exceeded",
  "budget_exceeded",
  "generation_disabled",
  "gpu_worker_disabled",
  "model_unavailable",
  "no_previewable_candidates",
  "qa_failed",
  "qa_requires_review",
  "requires_more_preview_candidates",
  "retryable_failed",
  "worker_timeout",
]);

const RETRY_IMAGE_BYTE_FIELDS = [
  "imageBase64",
  "base64Image",
  "imageBytesBase64",
  "image",
  "photoId",
  "sourcePhotoId",
  "gcsUri",
  "sourcePhotoRefs",
  "storagePath",
  "storageBucket",
  "jobId",
];

export type CurrentAvatarGenerationStatusResponse = {
  sourceLocked: boolean;
  jobId: string | null;
  sourceSelectionVersion: number;
  status: string;
  candidateAvailability: "none" | "preview_safe";
  retryAllowed: boolean;
  approved: boolean;
  safeReasonCode: string | null;
  /**
   * 같은 사진으로 다시 시도할 원본이 아직 남아 있는가. 원본이 이미 삭제된
   * 작업에 재시도 버튼을 띄우면 사용자는 반드시 실패하는 버튼을 누른다.
   */
  sourceAvailable: boolean;
};

function normalizeCurrentAvatarStatus(value: unknown): string {
  const status = asString(value).toLowerCase();
  if (status === "failed") return "terminal_failed";
  if (status === "no_previewable") return "no_previewable_candidates";
  // 유료 생성이 진행 중인 작업을 최종 실패로 보고하면 안 된다.
  if (IN_FLIGHT_WORKER_JOB_STATUSES.has(status)) return "running";
  return SAFE_AVATAR_STATUS_VALUES.has(status) ? status : "terminal_failed";
}
/// provider 로 요청이 나간 뒤 응답을 잃은 상태. 워커는 이것을 needs_review 로
/// 기록하지만, QA 추가 검토와 의미가 완전히 다르다. 전자는 유료 생성이 이미
/// 존재할 수 있어 재조정이 필요하고, 후자는 후보가 확정된 채 자동 통과만
/// 못한 상태다. 두 상태를 같은 UI 로 합치면 안 된다.
const PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES = new Set([
  "azure_unknown_post_send_outcome",
]);

/// 워커가 남긴 실패 분류. 사진 자체가 부적합해서 끝난 실패와, 서버 인프라가
/// 실패한 것을 같은 최종 실패로 합치면 사용자는 "다른 사진으로 다시" 라는
/// 잘못된 안내를 받는다. 사진을 바꿔도 인프라는 고쳐지지 않는다.
const CONTENT_TERMINAL_FAILURE_CLASSES = new Set([
  "content_terminal",
  "user_terminal",
]);

export function isInfrastructureFailureJob(
  jobData: Record<string, unknown>,
): boolean {
  const status = asString(jobData.status).toLowerCase();
  if (status !== "failed" && status !== "terminal_failed") return false;
  if (jobData.retryable === true) return true;
  const failureClass = asString(jobData.failureClass).toLowerCase();
  if (!failureClass) {
    // 분류가 없는 레거시 실패. 사진 탓으로 단정하지 않는다.
    return true;
  }
  return !CONTENT_TERMINAL_FAILURE_CLASSES.has(failureClass);
}

function normalizeCurrentAvatarStatusFromJob(
  jobData: Record<string, unknown>,
  userAvatar: Record<string, unknown>,
): string {
  if (
    PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES.has(
      asString(jobData.errorCode).toLowerCase(),
    )
  ) {
    return "reconciliation_required";
  }
  const rawStatus = asString(jobData.status ?? userAvatar.status).toLowerCase();
  if (rawStatus === "failed" || rawStatus === "terminal_failed") {
    if (asString(jobData.failureClass).toLowerCase() === "provider_ambiguous") {
      return "reconciliation_required";
    }
    return isInfrastructureFailureJob(jobData)
      ? "retryable_failed"
      : "terminal_failed";
  }
  return normalizeCurrentAvatarStatus(rawStatus);
}

function retryAllowedForStatus(status: string): boolean {
  return RETRYABLE_CURRENT_AVATAR_STATUSES.has(status);
}

function safeAvatarReasonCode(value: unknown): string | null {
  const reason = asString(value).toLowerCase();
  if (!reason || reason.length > 80) return null;
  if (!/^[a-z0-9_:-]+$/.test(reason)) return null;
  if (reason.includes("gs:") || reason.includes("/") || reason.includes("\\")) {
    return null;
  }
  return SAFE_AVATAR_REASON_CODES.has(reason) ? reason : null;
}

function safeReasonCodeFromJob(
  jobData: Record<string, unknown>,
): string | null {
  if (
    PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES.has(
      asString(jobData.errorCode).toLowerCase(),
    )
  ) {
    return "avatar_provider_outcome_unknown";
  }
  if (isInfrastructureFailureJob(jobData)) {
    return "avatar_generation_infrastructure_failed";
  }
  return (
    safeAvatarReasonCode(jobData.errorCode) ??
    safeAvatarReasonCode(jobData.reasonCode) ??
    safeAvatarReasonCode(jobData.lastErrorCode) ??
    safeAvatarReasonCode(readMap(jobData.qa).reasonCode)
  );
}

function positiveInteger(value: unknown): number {
  const parsed = Math.floor(Number(value ?? 0));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function nonNegativeInteger(value: unknown): number | null {
  const parsed = Math.floor(Number(value));
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

export function currentAvatarJobMatchesContract(params: {
  contract: CurrentAvatarContract;
  jobData: unknown;
  uid: string;
}): boolean {
  const job = readMap(params.jobData);
  const sourcePhotoIds = Array.isArray(job.sourcePhotoIds)
    ? job.sourcePhotoIds.map(asString).filter(Boolean)
    : [];
  return (
    Object.keys(job).length > 0 &&
    asString(job.uid).length > 0 &&
    asString(job.uid) === params.uid &&
    asString(job.jobId) === params.contract.jobId &&
    (params.contract.sourceSelecting
      ? sourcePhotoIds.length >= 1
      : sourcePhotoIds.includes(params.contract.sourceId ?? "")) &&
    nonNegativeInteger(job.avatarSourceSelectionVersion) ===
      params.contract.sourceSelectionVersion
  );
}

export function previewCandidateAvailableFromJob(
  jobData: unknown,
): boolean {
  const job = readMap(jobData);
  if (positiveInteger(job.previewReadyCandidateCount) > 0) return true;
  const generationPlan = readMap(job.generationPlan);
  if (positiveInteger(generationPlan.previewCount) > 0) return true;
  const previewRerank = readMap(job.previewRerank);
  return positiveInteger(previewRerank.previewReadyCandidateCount) > 0;
}

export function previewCandidateAvailableFromCandidate(
  candidate: unknown,
): boolean {
  const data = readMap(candidate);
  const qa = readMap(data.qa);
  if (!canPreviewCandidate(data)) return false;
  if (isSoftNeedsReviewAvatarCandidate(data)) return true;
  return (
    asString(data.status).toLowerCase() === "preview_ready" &&
    qa.selectedForPreview === true
  );
}

export function buildCurrentAvatarGenerationStatusResponse(params: {
  privateData: unknown;
  userData: unknown;
  jobData: unknown;
  candidatesAvailable: boolean;
  uid?: string;
}): CurrentAvatarGenerationStatusResponse {
  const userAvatar = readMap(readMap(params.userData).avatar);
  const rawApprovedAvatarUrl = asString(userAvatar.approvedAvatarUrl);
  const approvedAvatarUrl =
    hasApprovedAvatarLock(userAvatar) && isSafeApprovedAvatarUrl(rawApprovedAvatarUrl)
      ? rawApprovedAvatarUrl
      : undefined;
  if (hasApprovedAvatarLock(userAvatar)) {
    return {
      sourceLocked: true,
      jobId: null,
      sourceSelectionVersion: 0,
      status: "approved",
      candidateAvailability: "none",
      retryAllowed: false,
      approved: Boolean(approvedAvatarUrl),
      safeReasonCode: approvedAvatarUrl ? null : "avatar_already_approved",
      sourceAvailable: false,
    };
  }

  let contract: CurrentAvatarContract;
  try {
    contract = readCurrentAvatarContract(params.privateData);
  } catch (error) {
    if (error instanceof HttpsError) {
      return {
        sourceLocked: true,
        jobId: null,
        sourceSelectionVersion: 0,
        status: "terminal_failed",
        candidateAvailability: "none",
        retryAllowed: false,
        approved: false,
        safeReasonCode: "avatar_state_inconsistent",
        sourceAvailable: false,
      };
    }
    throw error;
  }

  if (!contract.sourceLocked) {
    if (hasActiveAvatarWorkflowState(userAvatar)) {
      return {
        sourceLocked: true,
        jobId: null,
        sourceSelectionVersion: contract.sourceSelectionVersion,
        status: "terminal_failed",
        candidateAvailability: "none",
        retryAllowed: false,
        approved: false,
        safeReasonCode: "avatar_state_inconsistent",
        sourceAvailable: false,
      };
    }
    return {
      sourceLocked: false,
      jobId: null,
      sourceSelectionVersion: contract.sourceSelectionVersion,
      status: "queued",
      candidateAvailability: "none",
      retryAllowed: false,
      approved: false,
      safeReasonCode: null,
      sourceAvailable: false,
    };
  }

  const jobData = readMap(params.jobData);
  if (!currentAvatarJobMatchesContract({
    contract,
    jobData,
    uid: params.uid ?? asString(jobData.uid),
  })) {
    return {
      sourceLocked: true,
      jobId: contract.jobId,
      sourceSelectionVersion: contract.sourceSelectionVersion,
      status: "terminal_failed",
      candidateAvailability: "none",
      retryAllowed: false,
      approved: false,
      safeReasonCode: "avatar_state_inconsistent",
      sourceAvailable: false,
    };
  }
  const jobStatus = normalizeCurrentAvatarStatusFromJob(jobData, userAvatar);
  // While the worker is still choosing the source the job is simply "queued"
  // or "running"; expose that phase explicitly so clients keep waiting.
  const status =
    contract.sourceSelecting && (jobStatus === "queued" || jobStatus === "running")
      ? "source_selecting"
      : jobStatus;
  const candidateAvailability =
    (status === "preview_ready" || status === "needs_review") &&
    params.candidatesAvailable
      ? "preview_safe"
      : "none";
  // 소스 선택 단계는 아직 잠글 원본을 고르는 중이므로 "남아 있다"로 본다.
  const sourceAvailable = contract.sourceSelecting || contract.sourceEntry !== null;
  return {
    sourceLocked: true,
    jobId: contract.jobId,
    sourceSelectionVersion: contract.sourceSelectionVersion,
    status,
    candidateAvailability,
    // 서버가 재시도를 허용해도 원본이 없으면 같은 사진 재시도는 불가능하다.
    retryAllowed: retryAllowedForStatus(status) && sourceAvailable,
    approved: false,
    safeReasonCode: !sourceAvailable
      ? "avatar_source_unavailable"
      : safeReasonCodeFromJob(jobData) ??
        (retryAllowedForStatus(status) ? status : null),
    sourceAvailable,
  };
}

export function rejectAvatarRetryRequestWithImageBytes(data: unknown): void {
  const payload = readMap(data);
  for (const field of RETRY_IMAGE_BYTE_FIELDS) {
    if (payload[field] !== undefined) {
      throw new HttpsError("invalid-argument", "avatar_retry_not_allowed");
    }
  }
}

export function throwIfAvatarGenerationDisabled(): void {
  if (
    truthyEnv("AVATAR_DISABLE_NEW_GENERATION") ||
    truthyEnv("AVATAR_GENERATION_DISABLED") ||
    truthyEnv("AVATAR_GENERATION_PAUSED") ||
    truthyEnv("AVATAR_KILL_SWITCH")
  ) {
    throw new HttpsError("failed-precondition", "avatar_generation_paused");
  }
  if (
    truthyEnv("AVATAR_COST_KILL_SWITCH_ENABLED") ||
    truthyEnv("AVATAR_GENERATION_BUDGET_EXHAUSTED")
  ) {
    throw new HttpsError("resource-exhausted", "avatar_budget_exceeded");
  }
}

function avatarRetryLimit(): number {
  const parsed = Number.parseInt(process.env.AVATAR_RETRY_LIMIT ?? "2", 10);
  if (!Number.isFinite(parsed) || parsed < 0) return 2;
  return Math.min(10, parsed);
}

export function isSourceSetAvatarJob(jobData: unknown): boolean {
  return Array.isArray(readMap(jobData).sourceSelectionCandidates);
}

export type SourceSetRetryPlan =
  | { allowed: false; reasonCode: string }
  | {
      allowed: true;
      replay: boolean;
      shouldEnqueue: boolean;
      sourceLocked: boolean;
      selectedPhotoId: string | null;
      payload: QueueDispatchPayload;
      jobUpdate: Record<string, unknown>;
    };

/// Retry for a source-set job re-dispatches the SAME job id.
///
/// - selection failed before any source was locked -> the selector runs again
///   over the full candidate set (no source was chosen, so nothing is rerun).
/// - a source is already locked -> the single locked source is pinned; the
///   selector never runs again.
/// Provider-ambiguous and terminal states are refused by the shared status
/// normalizer, the same authority the status response uses.
export function buildSourceSetRetryPlan(params: {
  uid: string;
  jobId: string;
  currentJobData: unknown;
  clientRequestId: string;
}): SourceSetRetryPlan {
  const job = readMap(params.currentJobData);
  const clientRequestId = requirePathSegment(
    asString(params.clientRequestId) || "retry",
    "clientRequestId",
  );
  const currentRetryCount = Math.max(
    0,
    Math.floor(Number(job.retryCount ?? 0) || 0),
  );
  const selection = readMap(job.sourceSelection);
  const selected = readMap(job.selectedSource);
  const sourceLocked =
    asString(selection.status).toLowerCase() === "selected" &&
    asString(selected.photoId).length > 0;

  const candidates = (
    Array.isArray(job.sourceSelectionCandidates)
      ? job.sourceSelectionCandidates
      : []
  )
    .filter(isRecord)
    .map((candidate) => ({
      photoId: asString(candidate.photoId),
      gcsUri: asString(candidate.gcsUri),
      objectGeneration: asString(candidate.objectGeneration),
    }))
    .filter((candidate) => candidate.photoId && candidate.gcsUri);
  const sources = sourceLocked
    ? [
        {
          photoId: asString(selected.photoId),
          gcsUri: asString(selected.gcsUri),
          objectGeneration: asString(selected.objectGeneration),
        },
      ]
    : candidates;

  const buildPayload = (retryOrdinal: number): QueueDispatchPayload => ({
    jobId: params.jobId,
    uid: params.uid,
    sourcePhotoIds: sources.map((source) => source.photoId),
    sourcePhotoRefs: sources.map((source) => source.gcsUri),
    sourcePhotoObjectGenerations: sources.map(
      (source) => source.objectGeneration,
    ),
    sourceSelectionMode:
      asString(job.sourceSelectionMode) || "quality_selector_v1",
    consentPurposes: requireAvatarConsentPurposes(job.consentPurposes),
    avatarPresentationGender: normalizeAvatarPresentationGender(
      job.avatarPresentationGender,
    ),
    candidateCount: positiveInteger(job.candidateCount) || 2,
    modelId: DEFAULT_AVATAR_MODEL_ID,
    jobType: "avatar_generation",
    schemaVersion: "avatar_job_v1",
    idempotencyKey: `${params.uid}:${params.jobId}:avatar_generation_source_set_retry_v${retryOrdinal}`,
  });

  if (asString(job.retryClientRequestId) === clientRequestId) {
    const queueStatus = asString(job.queueStatus).toLowerCase();
    return {
      allowed: true,
      replay: true,
      shouldEnqueue:
        queueStatus === "enqueue_failed" || queueStatus === "dispatch_failed",
      sourceLocked,
      selectedPhotoId: sourceLocked ? asString(selected.photoId) : null,
      payload: buildPayload(Math.max(1, currentRetryCount)),
      jobUpdate: {},
    };
  }

  const status = normalizeCurrentAvatarStatusFromJob(job, {});
  if (!retryAllowedForStatus(status)) {
    return { allowed: false, reasonCode: "avatar_retry_not_allowed" };
  }
  if (currentRetryCount >= avatarRetryLimit()) {
    return { allowed: false, reasonCode: "avatar_retry_limit_reached" };
  }
  if (sources.length === 0 || (!sourceLocked && sources.length < 2)) {
    return { allowed: false, reasonCode: "avatar_retry_not_allowed" };
  }

  const nextRetryCount = currentRetryCount + 1;
  const jobUpdate: Record<string, unknown> = {
    status: "queued",
    retryCount: nextRetryCount,
    retryClientRequestId: clientRequestId,
    errorCode: FieldValue.delete(),
    errorMessage: FieldValue.delete(),
    retryable: FieldValue.delete(),
    queueStatus: FieldValue.delete(),
    updatedAt: FieldValue.serverTimestamp(),
  };
  if (!sourceLocked) {
    jobUpdate.sourceSelection = {
      status: "pending",
      selectorVersion:
        asString(selection.selectorVersion) ||
        "avatar_source_quality_selector_v1",
      evaluatedCount: 0,
    };
  }
  return {
    allowed: true,
    replay: false,
    shouldEnqueue: true,
    sourceLocked,
    selectedPhotoId: sourceLocked ? asString(selected.photoId) : null,
    payload: buildPayload(nextRetryCount),
    jobUpdate,
  };
}

export function redactQueuePayload(
  payload: QueueDispatchPayload,
): Record<string, unknown> {
  const jobId = asString(payload.jobId);
  return {
    ...payload,
    uid: "<redacted>",
    uidHash: sha256Hex(payload.uid).slice(0, 12),
    ...(jobId
      ? {
          jobId: "<redacted>",
          jobIdHash: sha256Hex(jobId).slice(0, 12),
        }
      : {}),
    ...(Array.isArray(payload.sourcePhotoObjectGenerations)
      ? { sourcePhotoObjectGenerations: "<redacted>" }
      : {}),
    ...(Array.isArray(payload.sourceSelectionCandidates)
      ? { sourceSelectionCandidates: "<redacted>" }
      : {}),
    sourcePhotoIds: payload.sourcePhotoIds.map(
      () => "<source-photo-id-redacted>",
    ),
    sourcePhotoRefs: payload.sourcePhotoRefs.map(
      () => "gs://<private-source-photo-redacted>",
    ),
    idempotencyKey: "<redacted>",
  };
}

export function queueMode(): string {
  const configured = process.env.JOB_QUEUE_MODE?.trim().toLowerCase();
  if (!configured) {
    // 설정이 없을 때의 조용한 dry_run fallback 은 로컬에서만 허용한다. 배포된
    // 런타임에서 이 값이 사라지면 큐에 아무것도 넣지 않고 "넣었다"고 보고하게
    // 되므로, 라벨이 무엇이든 큰 소리로 실패한다.
    if (isDeployedFunctionsRuntime() || isProductionEnvironment()) {
      throw new HttpsError(
        "failed-precondition",
        "JOB_QUEUE_MODE must be explicitly configured in a deployed runtime.",
      );
    }
    return "dry_run";
  }
  if (configured === "dry_run" && isProductionEnvironment()) {
    throw new HttpsError(
      "failed-precondition",
      "JOB_QUEUE_MODE=dry_run is not allowed in production.",
    );
  }
  return configured;
}

function taskQueueName(kind: QueueKind): string {
  const envName =
    kind === "avatar_generation"
      ? "AVATAR_GENERATION_QUEUE_NAME"
      : "CLIP_EMBEDDING_QUEUE_NAME";
  const fallback =
    kind === "avatar_generation" ? "avatar-generation" : "clip-embedding";
  const configured = envValue(envName, fallback);
  if (configured.startsWith("projects/")) return configured;
  const location = envValue("GCP_LOCATION", DEFAULT_REGION);
  const project = envValue(
    "CLOUD_TASKS_PROJECT",
    process.env.GCLOUD_PROJECT ?? process.env.GCP_PROJECT ?? "",
  );
  if (!project) {
    throw new HttpsError(
      "failed-precondition",
      "CLOUD_TASKS_PROJECT is required for Cloud Tasks mode.",
    );
  }
  return `projects/${project}/locations/${location}/queues/${configured}`;
}

function taskTargetUrl(kind: QueueKind): string {
  const envName =
    kind === "avatar_generation"
      ? "AVATAR_GENERATION_TASK_URL"
      : "CLIP_EMBEDDING_TASK_URL";
  const url = process.env[envName]?.trim();
  if (!url) {
    throw new HttpsError(
      "failed-precondition",
      `${envName} is required for Cloud Tasks mode.`,
    );
  }
  return url;
}

function pubsubTopic(kind: QueueKind): string {
  const envName =
    kind === "avatar_generation"
      ? "AVATAR_GENERATION_TOPIC"
      : "CLIP_EMBEDDING_TOPIC";
  return envValue(
    envName,
    kind === "avatar_generation" ? "avatar-generation" : "clip-embedding",
  );
}

export function buildDeterministicCloudTaskName(
  queueName: string,
  kind: QueueKind,
  idempotencyKey: string,
): string {
  const prefix =
    kind === "avatar_generation" ? "avatar-generation" : "clip-embedding";
  return `${queueName}/tasks/${prefix}-${sha256Hex(idempotencyKey).slice(0, 32)}`;
}

export function isCloudTasksAlreadyExistsError(error: unknown): boolean {
  if (!isRecord(error)) return false;
  return (
    error.code === 6 ||
    error.code === "6" ||
    asString(error.message).includes("ALREADY_EXISTS")
  );
}

export function summarizeQueueWriteState(
  queueResults: Record<string, unknown>,
): {
  queueMode: string;
  queueStatus: string;
} {
  const avatar = readMap(queueResults.avatar);
  const clip = readMap(queueResults.clip);
  const avatarStatus = asString(avatar.status);
  const clipStatus = asString(clip.status);
  const queueModeValue =
    asString(avatar.mode) || asString(clip.mode) || queueMode();

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
  if (
    dispatchedStatuses.has(avatarStatus) &&
    (dispatchedStatuses.has(clipStatus) ||
      optionalSkippedStatuses.has(clipStatus))
  ) {
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

export function buildCloudTaskHttpRequest(
  url: string,
  payload: QueueDispatchPayload,
): protos.google.cloud.tasks.v2.IHttpRequest {
  const httpRequest: protos.google.cloud.tasks.v2.IHttpRequest = {
    httpMethod: protos.google.cloud.tasks.v2.HttpMethod.POST,
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
    throw new HttpsError(
      "failed-precondition",
      `TASK_INVOKER_SERVICE_ACCOUNT is required for ${suffix}`,
    );
  }
  httpRequest.oidcToken = {
    serviceAccountEmail,
    audience: process.env.TASK_OIDC_AUDIENCE?.trim() || url,
  };
  return httpRequest;
}

export function cloudTaskDispatchDeadlineSeconds(): number {
  const raw = process.env.AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS?.trim();
  if (!raw) return 900;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return 900;
  return Math.min(1800, Math.max(60, parsed));
}

export async function enqueueQueuePayload(
  kind: QueueKind,
  payload: QueueDispatchPayload,
): Promise<Record<string, unknown>> {
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
    const taskName = buildDeterministicCloudTaskName(
      queueName,
      kind,
      payload.idempotencyKey,
    );
    const client = new CloudTasksClient();
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
    } catch (error) {
      if (isCloudTasksAlreadyExistsError(error)) {
        logger.info(
          "Avatar media Cloud Task already exists; treating as idempotent success",
          {
            kind,
            taskName,
          },
        );
        return { mode, status: "already_exists", queueName, taskName };
      }
      throw error;
    }
  }

  if (mode === "pubsub") {
    const topicName = pubsubTopic(kind);
    const pubsub = new PubSub({
      projectId:
        process.env.CLOUD_TASKS_PROJECT ||
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

  throw new HttpsError(
    "failed-precondition",
    "JOB_QUEUE_MODE must be dry_run, cloud_tasks, or pubsub.",
  );
}

async function currentPreviewCandidateAvailable(
  firestore: Firestore,
  uid: string,
  jobId: string,
  jobData: unknown,
): Promise<boolean> {
  if (previewCandidateAvailableFromJob(jobData)) return true;
  const candidatesSnap = await firestore
    .collection("avatarCandidates")
    .where("jobId", "==", jobId)
    .where("uid", "==", uid)
    .limit(20)
    .get();
  return candidatesSnap.docs.some((doc) =>
    previewCandidateAvailableFromCandidate(doc.data()),
  );
}

export function createGetCurrentAvatarGenerationStatusFunction(
  firestore: Firestore,
  resolveUploadUser: ResolveUploadUser,
) {
  return onCall(
    CURRENT_AVATAR_GENERATION_STATUS_CALLABLE_OPTIONS,
    async (request) => {
      const user = await resolveUploadUser(request.auth);
      const uid = requirePathSegment(user.userId, "uid");
      const userRef = firestore.collection("users").doc(uid);
      const privateRef = firestore.collection("userPrivateMedia").doc(uid);
      const [userSnap, privateSnap] = await Promise.all([
        userRef.get(),
        privateRef.get(),
      ]);
      const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
      const privateData = (privateSnap.data() ?? {}) as Record<string, unknown>;

      let jobData: Record<string, unknown> | null = null;
      let candidatesAvailable = false;
      try {
        const contract = readCurrentAvatarContract(privateData);
        if (contract.jobId) {
          const jobSnap = await firestore
            .collection("avatarJobs")
            .doc(contract.jobId)
            .get();
          jobData = jobSnap.exists
            ? ((jobSnap.data() ?? {}) as Record<string, unknown>)
            : null;
          const jobUid = asString(jobData?.uid);
          if (jobData && jobUid && jobUid !== uid) {
            jobData = null;
          }
          const status = asString(jobData?.status).toLowerCase();
          if (status === "preview_ready" || status === "needs_review") {
            candidatesAvailable = await currentPreviewCandidateAvailable(
              firestore,
              uid,
              contract.jobId,
              jobData,
            );
          }
        }
      } catch (error) {
        if (!(error instanceof HttpsError)) throw error;
      }

      return buildCurrentAvatarGenerationStatusResponse({
        privateData,
        userData,
        jobData,
        candidatesAvailable,
        uid,
      });
    },
  );
}

export function createRetryCurrentAvatarGenerationFunction(
  firestore: Firestore,
  resolveUploadUser: ResolveUploadUser,
) {
  return onCall(
    RETRY_CURRENT_AVATAR_GENERATION_CALLABLE_OPTIONS,
    async (request) => {
      const user = await resolveUploadUser(request.auth);
      const uid = requirePathSegment(user.userId, "uid");
      const data = isRecord(request.data) ? request.data : {};
      rejectAvatarRetryRequestWithImageBytes(data);
      throwIfAvatarGenerationDisabled();
      const clientRequestId = requirePathSegment(
        asString(data.clientRequestId),
        "clientRequestId",
      );

      const userRef = firestore.collection("users").doc(uid);
      const privateRef = firestore.collection("userPrivateMedia").doc(uid);
      const retryResult = await firestore.runTransaction(async (tx) => {
        const [userSnap, privateSnap] = await Promise.all([
          tx.get(userRef),
          tx.get(privateRef),
        ]);
        const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
        if (hasApprovedAvatarLock(userData.avatar)) {
          throw new HttpsError("failed-precondition", "avatar_already_approved");
        }
        const privateData = (privateSnap.data() ?? {}) as Record<string, unknown>;
        const contract = readCurrentAvatarContract(privateData);
        if (!contract.sourceLocked || !contract.jobId) {
          throw new HttpsError("failed-precondition", "avatar_retry_not_allowed");
        }

        const currentJobRef = firestore.collection("avatarJobs").doc(contract.jobId);
        const currentJobSnap = await tx.get(currentJobRef);
        if (!currentJobSnap.exists) {
          throw new HttpsError("failed-precondition", "avatar_retry_not_allowed");
        }
        const currentJobData = (currentJobSnap.data() ?? {}) as Record<string, unknown>;
        if (asString(currentJobData.uid) !== uid) {
          throw new HttpsError("failed-precondition", "avatar_job_not_current");
        }

        if (isSourceSetAvatarJob(currentJobData)) {
          // Canonical source-set job: re-dispatch the same job id. No new job
          // doc, no new source pointer, no selector rerun once a source is locked.
          const plan = buildSourceSetRetryPlan({
            uid,
            jobId: contract.jobId,
            currentJobData,
            clientRequestId,
          });
          if (!plan.allowed) {
            const code =
              plan.reasonCode === "avatar_retry_limit_reached"
                ? "resource-exhausted"
                : "failed-precondition";
            throw new HttpsError(code, plan.reasonCode);
          }
          if (!plan.replay) {
            tx.set(currentJobRef, plan.jobUpdate, { merge: true });
            if (!plan.sourceLocked) {
              tx.set(
                privateRef,
                {
                  avatarSourceSelection: {
                    status: "pending",
                    selectorVersion: "avatar_source_quality_selector_v1",
                    evaluatedCount: 0,
                  },
                  updatedAt: FieldValue.serverTimestamp(),
                },
                { merge: true },
              );
            }
            tx.set(
              userRef,
              {
                avatar: {
                  status: "queued",
                  errorCode: FieldValue.delete(),
                  updatedAt: FieldValue.serverTimestamp(),
                },
                onboarding: {
                  sourcePhotoUploadStatus: plan.sourceLocked
                    ? "avatar_generation_queued"
                    : "avatar_source_selection_pending",
                },
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true },
            );
          }
          const selectionState = plan.sourceLocked ? "selected" : "pending";
          return {
            retryJobId: contract.jobId,
            retryPayload: plan.payload,
            sourceSelectionVersion: contract.sourceSelectionVersion,
            shouldEnqueue: plan.replay ? plan.shouldEnqueue : true,
            jobData: plan.replay
              ? currentJobData
              : { ...currentJobData, ...plan.jobUpdate, status: "queued" },
            responsePrivateData: {
              currentAvatarJobId: contract.jobId,
              avatarSourceSelectionVersion: contract.sourceSelectionVersion,
              avatarSourceSelection: { status: selectionState },
              ...(plan.sourceLocked && plan.selectedPhotoId
                ? {
                    currentAvatarSourcePhotoId: plan.selectedPhotoId,
                    sourcePhotos: [
                      {
                        photoId: plan.selectedPhotoId,
                        status: "active",
                        avatarGenerationState: "current",
                      },
                    ],
                  }
                : {}),
            } as Record<string, unknown>,
          };
        }

        // Legacy single-photo jobs (pre source-set) are read-only: their
        // generation path is retired, so no new legacy lock/job/task may be
        // created. Recovery is replaceAvatarGeneration with a new source set.
        throw new HttpsError(
          "failed-precondition",
          "avatar_legacy_job_retry_retired",
        );
      });

      const retryJobRef = firestore.collection("avatarJobs").doc(retryResult.retryJobId);
      if (retryResult.shouldEnqueue) {
        try {
          const queueResult = await enqueueQueuePayload(
            "avatar_generation",
            retryResult.retryPayload,
          );
          await retryJobRef.set(
            {
              status: "queued",
              errorCode: FieldValue.delete(),
              queueStatus: summarizeQueueWriteState({
                avatar: queueResult,
                clip: { status: "skipped_disabled" },
              }).queueStatus,
              queueMode: readMap(queueResult).mode ?? queueMode(),
              queuedAt: FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          retryResult.jobData = {
            ...readMap(retryResult.jobData),
            status: "queued",
            errorCode: undefined,
            queueStatus: summarizeQueueWriteState({
              avatar: queueResult,
              clip: { status: "skipped_disabled" },
            }).queueStatus,
          };
        } catch (error) {
          logger.error("Avatar retry enqueue failed", {
            uidHash: sha256Hex(uid).slice(0, 12),
            jobIdHash: sha256Hex(retryResult.retryJobId).slice(0, 12),
            ...safeAvatarMediaErrorLogFields(error),
          });
          await retryJobRef.set(
            {
              status: "retryable_failed",
              errorCode: "avatar_queue_enqueue_failed",
              queueStatus: "enqueue_failed",
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          await userRef.set(
            {
              avatar: {
                status: "retryable_failed",
                errorCode: "avatar_queue_enqueue_failed",
                updatedAt: FieldValue.serverTimestamp(),
              },
              onboarding: {
                sourcePhotoUploadStatus: "avatar_queue_enqueue_failed",
              },
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          if (error instanceof HttpsError) throw error;
          throw new HttpsError(
            "internal",
            "Avatar retry could not be queued.",
          );
        }
      }

      return buildCurrentAvatarGenerationStatusResponse({
        privateData: retryResult.responsePrivateData,
        userData: { avatar: { status: asString(readMap(retryResult.jobData).status) || "queued" } },
        jobData: {
          ...readMap(retryResult.jobData),
          uid,
          jobId: retryResult.retryJobId,
        },
        candidatesAvailable: false,
        uid,
      });
    },
  );
}
