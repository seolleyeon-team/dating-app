import { createHash, randomBytes } from "crypto";
import { getStorage } from "firebase-admin/storage";
import {
  FieldPath,
  FieldValue,
  Timestamp,
  type Firestore,
} from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";

import {
  mapTerminalJobStatus,
  syncAvatarGenerationStateForJob,
} from "./avatarGenerationStateSync";

const DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos";
const SOURCE_RETENTION_STATE_COLLECTION = "avatarSourceRetentionStates";
const SOURCE_RETENTION_EVENTS_COLLECTION = "avatarSourceRetentionEvents";
/** Resume point of the recovery scan (only written when a run stops early). */
export const RECOVERY_CHECKPOINT_COLLECTION = "schedulerCheckpoints";
export const RECOVERY_CHECKPOINT_ID = "recoverAvatarSourceRetention";
const RECOVERY_SCAN_PAGE_SIZE = 100;
const RECOVERY_MAX_SCAN = 2000;
const RECOVERY_TIME_BUDGET_MS = 90_000;
const DEFAULT_LEASE_MS = 10 * 60 * 1000;
const MAX_SOURCE_DELETION_ATTEMPTS = 5;
const RETRY_DELAYS_MS = [
  60 * 1000,
  5 * 60 * 1000,
  15 * 60 * 1000,
  60 * 60 * 1000,
  6 * 60 * 60 * 1000,
];

type RecordData = Record<string, unknown>;

type GcsRef = {
  bucket: string;
  path: string;
};

export type AvatarSourceRetentionClaim = {
  uid: string;
  jobId: string;
  photoId: string;
  sourceSelectionVersion: number | null;
  claimToken: string;
  stateId: string;
  refs: GcsRef[];
};

/** Deletes one retained private object. Injected in tests; production uses Storage. */
export type DeleteRetainedObject = (ref: GcsRef) => Promise<void>;

async function deleteRetainedObjectFromStorage(ref: GcsRef): Promise<void> {
  await getStorage().bucket(ref.bucket).file(ref.path).delete({ ignoreNotFound: true });
}

export type AvatarSourceRetentionRecoverySummary = {
  scanned: number;
  due: number;
  claimed: number;
  skipped: number;
};

export type AvatarSourceRetentionDecision =
  | { action: "skip"; reason: string }
  | {
      action: "claim";
      uid: string;
      jobId: string;
      photoId: string;
      sourceSelectionVersion: number | null;
      refs: GcsRef[];
      waitForClipTerminal: boolean;
    }
  /**
   * 아직 삭제해서는 안 되지만 언젠가는 삭제해야 하는 상태. 상태 문서를 남겨
   * 회수 스케줄러가 기한에 다시 평가하도록 한다.
   */
  | {
      action: "defer";
      uid: string;
      jobId: string;
      photoId: string;
      sourceSelectionVersion: number | null;
      refs: GcsRef[];
      reason: string;
      eligibleAtMs: number;
    };

function envValue(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

function sourcePhotoBucket(): string {
  return envValue("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET);
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function numericValue(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? Math.floor(parsed) : null;
}

function readMap(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordData)
    : {};
}

function readList(value: unknown): RecordData[] {
  return Array.isArray(value) ? value.filter(isRecord).map((item) => ({ ...item })) : [];
}

function isRecord(value: unknown): value is RecordData {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function uidHash(uid: string): string {
  return createHash("sha256").update(uid).digest("hex").slice(0, 16);
}

function shortHash(value: string): string {
  return createHash("sha256").update(value).digest("hex").slice(0, 16);
}

export function avatarSourceRetentionPrivacyFields(params: {
  uid: string;
  jobId: string;
  photoId: string;
}): { uidHash: string; jobIdHash: string; photoIdHash: string } {
  return avatarSourceRetentionLogFields(params);
}
export function avatarSourceRetentionLogFields(params: {
  uid: string;
  jobId: string;
  photoId: string;
}): { uidHash: string; jobIdHash: string; photoIdHash: string } {
  return {
    uidHash: uidHash(params.uid),
    jobIdHash: shortHash(params.jobId),
    photoIdHash: shortHash(params.photoId),
  };
}

function parseGcsUri(value: string): GcsRef | null {
  const match = value.match(/^(?:gs|gcs):\/\/([^/]+)\/(.+)$/);
  if (!match) return null;
  return { bucket: match[1], path: match[2] };
}

function gcsRefFromSource(entry: RecordData): GcsRef | null {
  const direct = asString(entry.gcsUri);
  if (direct) return parseGcsUri(direct);
  const path = asString(entry.storagePath);
  if (!path) return null;
  return {
    bucket: asString(entry.storageBucket) || sourcePhotoBucket(),
    path,
  };
}

function isUidBoundPrivateSourceRef(ref: GcsRef, uid: string): boolean {
  return ref.bucket === sourcePhotoBucket() && ref.path.startsWith(`users/${uid}/source/`);
}

function consentPurposes(privateData: RecordData): RecordData {
  const photoConsent = readMap(privateData.photoConsent);
  const purposes = readMap(photoConsent.purposes);
  return Object.keys(purposes).length > 0 ? purposes : photoConsent;
}

function sourceRetentionConsented(privateData: RecordData): boolean {
  return consentPurposes(privateData).sourcePhotoRetention === true;
}

function clipRecommendationConsented(privateData: RecordData, jobData: RecordData): boolean {
  const privateConsent = consentPurposes(privateData).clipRecommendation;
  if (typeof privateConsent === "boolean") return privateConsent;
  const jobConsent = readMap(jobData.consentPurposes).clipRecommendation;
  return jobConsent === true;
}

/**
 * 원본 삭제는 되돌릴 수 없다. 따라서 "종료임이 명시적으로 증명된" 실패만
 * 즉시 삭제를 허용한다. 인프라 오류나 분류가 없는 레거시 실패는 삭제가
 * 아니라 유예로 떨어진다. 과거에는 `status === "failed"` 이면서 retryable
 * 플래그가 없다는 이유만으로 삭제했고, 그래서 Storage 403 같은 인프라
 * 실패가 사용자의 원본 사진을 영구 삭제했다.
 */
const CONTENT_TERMINAL_FAILURE_CLASSES = new Set([
  "content_terminal",
  "user_terminal",
]);

/**
 * 유예는 무기한이 아니다. 동의하지 않은 원본을 영구 보관하지 않도록
 * 회수 기한이 지나면 삭제로 수렴한다.
 */
const DEFAULT_SOURCE_RECOVERY_GRACE_MS = 72 * 60 * 60 * 1000;
const MAX_SOURCE_RECOVERY_GRACE_MS = 30 * 24 * 60 * 60 * 1000;

/** 공개 상태 수렴 증거를 기다리는 짧은 창. 회수 기한을 넘지 않는다. */
const PUBLIC_STATE_CONVERGENCE_WAIT_MS = 15 * 60 * 1000;

export function sourceRecoveryGraceMs(): number {
  const parsed = Number(process.env.AVATAR_SOURCE_RECOVERY_GRACE_MS);
  return Number.isFinite(parsed) && parsed >= 0
    ? Math.min(Math.floor(parsed), MAX_SOURCE_RECOVERY_GRACE_MS)
    : DEFAULT_SOURCE_RECOVERY_GRACE_MS;
}

function millisValue(value: unknown): number | null {
  if (value instanceof Timestamp) return value.toMillis();
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (isRecord(value)) {
    const seconds = numericValue(value._seconds ?? value.seconds);
    if (seconds !== null) {
      const nanos = numericValue(value._nanoseconds ?? value.nanoseconds) ?? 0;
      return seconds * 1000 + Math.floor(nanos / 1_000_000);
    }
    return null;
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function terminalAtMs(jobData: RecordData, nowMs: number): number {
  return (
    millisValue(jobData.failedAt) ??
    millisValue(jobData.terminalAt) ??
    millisValue(jobData.updatedAt) ??
    nowMs
  );
}

/**
 * 공개 아바타 상태가 이 job 의 종료 상태로 수렴했는가.
 *
 * 증거는 별도 스탬프가 아니라 공개 문서 그 자체다. 스탬프는 "sync 가 돌았다"만
 * 증명하지만 여기서 필요한 것은 "사용자가 보는 상태가 실제로 맞다" 이기 때문이다.
 * 트리거 실행 순서는 보장되지 않으므로 파괴적 동작 전에 이 증거를 요구한다.
 */
export function avatarPublicStateConverged(params: {
  jobData: RecordData;
  userData: RecordData | null | undefined;
  userExists?: boolean;
}): boolean {
  // 공개 문서가 없으면 어긋날 공개 상태도 없다.
  if (params.userExists === false || !params.userData) return true;
  // 승인/승인 진행 상태는 state-sync 가 의도적으로 보존한다. 수렴 대기 아님.
  if (hasAvatarApprovalProtectedState(params.userData)) return true;

  const mapped = mapTerminalJobStatus(
    asString(params.jobData.status).toLowerCase(),
    asString(params.jobData.errorCode).toLowerCase(),
  );
  // 공개 어휘로 옮기지 않는 종료 상태는 기다릴 대상이 없다.
  if (!mapped) return true;

  const avatarStatus = asString(readMap(params.userData.avatar).status).toLowerCase();
  return avatarStatus === mapped.avatarStatus;
}

export type AvatarSourceDeletionDisposition =
  | { kind: "delete_now"; reason: string }
  | { kind: "defer"; reason: string; eligibleAtMs: number }
  | { kind: "preserve"; reason: string };

/**
 * 원본 삭제 처분을 결정한다. 부수효과 없음.
 *
 * 안전 기본값은 삭제가 아니라 보존이다. `delete_now` 는 (1) 명시적 종료
 * 사유이고 (2) 공개 상태가 수렴했거나 회수 기한이 지난 경우에만 나온다.
 */
export function planSourceDeletionDisposition(params: {
  jobData: RecordData;
  userData?: RecordData | null;
  userExists?: boolean;
  nowMs?: number;
}): AvatarSourceDeletionDisposition {
  const jobData = params.jobData;
  const nowMs = params.nowMs ?? Date.now();
  const status = asString(jobData.status).toLowerCase();
  const deadlineMs = terminalAtMs(jobData, nowMs) + sourceRecoveryGraceMs();
  const graceExpired = nowMs >= deadlineMs;

  const gate = (reason: string): AvatarSourceDeletionDisposition => {
    const converged = avatarPublicStateConverged({
      jobData,
      userData: params.userData,
      userExists: params.userExists,
    });
    if (converged || graceExpired) {
      return { kind: "delete_now", reason };
    }
    return {
      kind: "defer",
      reason: "awaiting_public_state_convergence",
      eligibleAtMs: Math.min(deadlineMs, nowMs + PUBLIC_STATE_CONVERGENCE_WAIT_MS),
    };
  };

  if (status === "approved" || status === "completed") {
    const irreversible =
      jobData.sourceDeletionIrreversible === true ||
      jobData.sourceCleanupIrreversible === true;
    return irreversible
      ? gate("approved_irreversible_contract")
      : { kind: "preserve", reason: "approval_without_irreversible_contract" };
  }
  if (status === "cancelled" || status === "canceled") {
    return gate("generation_cancelled");
  }
  if (status !== "failed" && status !== "terminal_failed") {
    return { kind: "preserve", reason: "avatar_not_terminal" };
  }

  const retryable = jobData.retryable === true;
  const failureClass = asString(jobData.failureClass).toLowerCase();
  const provenTerminal = !retryable && CONTENT_TERMINAL_FAILURE_CLASSES.has(failureClass);
  if (!provenTerminal && !graceExpired) {
    return {
      kind: "defer",
      reason: retryable
        ? "retryable_failure_source_preserved"
        : "unproven_terminal_source_preserved",
      eligibleAtMs: deadlineMs,
    };
  }
  return gate(provenTerminal ? "content_terminal_failure" : "source_recovery_grace_expired");
}

/**
 * retention 이 깨어나야 하는 전이인가. "삭제해도 되는가" 와 다르다. 유예도
 * 상태 문서를 남겨야 회수 기한에 스케줄러가 다시 평가하므로 여기서 깨운다.
 */
function isSourceRetentionActionable(jobData: RecordData, nowMs: number): boolean {
  // 트리거 페이로드에는 공개 문서가 없다. 여기서는 "깨울 것인가"만 정하고,
  // 삭제 여부는 트랜잭션 안에서 공개 문서까지 읽고 다시 판정한다.
  return (
    planSourceDeletionDisposition({ jobData, nowMs, userData: null, userExists: false })
      .kind !== "preserve"
  );
}

function isTerminalClipStatus(value: unknown): boolean {
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

function clipDocumentStatus(data: RecordData): string {
  return asString(data.status) || asString(data.embeddingStatus);
}

/**
 * Retention is a one-way operation. A terminal job's timestamp, lease, or
 * source-redaction write must not claim the same deletion again.
 */
export function shouldEvaluateAvatarJobSourceRetentionTransition(params: {
  beforeData: RecordData | null | undefined;
  afterData: RecordData | null | undefined;
  nowMs?: number;
}): boolean {
  const nowMs = params.nowMs ?? Date.now();
  if (!params.afterData || !isSourceRetentionActionable(params.afterData, nowMs)) {
    return false;
  }
  if (!params.beforeData) return true;
  return !isSourceRetentionActionable(params.beforeData, nowMs);
}

/**
 * Clip retention only needs to wake when the clip becomes terminal. The
 * retention worker's own source-ref redaction is otherwise a no-op event.
 */
export function shouldEvaluateClipEmbeddingSourceRetentionTransition(params: {
  beforeData: RecordData | null | undefined;
  afterData: RecordData | null | undefined;
}): boolean {
  if (!params.afterData || !isTerminalClipStatus(clipDocumentStatus(params.afterData))) {
    return false;
  }
  if (!params.beforeData) return true;
  return !isTerminalClipStatus(clipDocumentStatus(params.beforeData));
}

function sourcePhotoIds(jobData: RecordData): string[] {
  const ids = Array.isArray(jobData.sourcePhotoIds)
    ? jobData.sourcePhotoIds.map(asString).filter(Boolean)
    : [];
  const legacy = asString(jobData.sourcePhotoId);
  return legacy && !ids.includes(legacy) ? [...ids, legacy] : ids;
}

function currentSourceEntry(privateData: RecordData, jobData: RecordData): RecordData | null {
  const currentPhotoId = asString(privateData.currentAvatarSourcePhotoId);
  const jobPhotoIds = sourcePhotoIds(jobData);
  const selectedPhotoId = currentPhotoId || jobPhotoIds[0] || "";
  if (!selectedPhotoId || (currentPhotoId && !jobPhotoIds.includes(currentPhotoId))) {
    return null;
  }
  return (
    readList(privateData.sourcePhotos).find(
      (entry) =>
        asString(entry.photoId) === selectedPhotoId &&
        asString(entry.status) === "active" &&
        asString(entry.avatarGenerationState) === "current",
    ) ?? null
  );
}

function currentSourceSelectionVersion(
  privateData: RecordData,
  jobData: RecordData,
): number | null {
  const privateSelectionVersion = numericValue(privateData.avatarSourceSelectionVersion);
  const jobSelectionVersion = numericValue(jobData.avatarSourceSelectionVersion);
  if (
    privateSelectionVersion !== null &&
    jobSelectionVersion !== null &&
    privateSelectionVersion !== jobSelectionVersion
  ) {
    return null;
  }
  return jobSelectionVersion ?? privateSelectionVersion;
}

function currentClipStatus(privateData: RecordData, clipData: RecordData | null): string {
  const clipDocStatus = asString(clipData?.status);
  if (clipDocStatus) return clipDocStatus;
  const privateClip = readMap(privateData.clip);
  return asString(privateClip.embeddingStatus);
}

export function hasAvatarApprovalProtectedState(userData: RecordData): boolean {
  const avatar = readMap(userData.avatar);
  return ["approved", "approval_copying", "approval_copy_failed"].includes(
    asString(avatar.status),
  );
}

export function avatarSourceRetentionStateId(uid: string, photoId: string): string {
  return createHash("sha256")
    .update(`${uid}:${photoId}:source_retention_v1`)
    .digest("hex");
}

function sourceDeletionLeaseMs(): number {
  const parsed = Number(process.env.AVATAR_SOURCE_DELETION_LEASE_MS);
  return Number.isFinite(parsed) && parsed >= 60_000
    ? Math.min(Math.floor(parsed), 60 * 60 * 1000)
    : DEFAULT_LEASE_MS;
}

export function nextSourceDeletionRetryAt(params: {
  attempts: number;
  nowMs: number;
}): Date | null {
  if (params.attempts >= MAX_SOURCE_DELETION_ATTEMPTS) return null;
  const delay = RETRY_DELAYS_MS[
    Math.max(0, Math.min(params.attempts, RETRY_DELAYS_MS.length - 1))
  ];
  return new Date(params.nowMs + delay);
}

export function planAvatarSourceRetention(params: {
  uid: string;
  jobId: string;
  privateData: RecordData;
  jobData: RecordData;
  clipData?: RecordData | null;
  userData?: RecordData | null;
  userExists?: boolean;
  nowMs?: number;
}): AvatarSourceRetentionDecision {
  const nowMs = params.nowMs ?? Date.now();
  if (sourceRetentionConsented(params.privateData)) {
    return { action: "skip", reason: "retained_by_consent" };
  }
  const jobUid = asString(params.jobData.uid);
  if (jobUid !== params.uid) {
    return { action: "skip", reason: "job_uid_mismatch" };
  }
  if (asString(params.privateData.currentAvatarJobId) !== params.jobId) {
    return { action: "skip", reason: "not_current_job" };
  }
  const disposition = planSourceDeletionDisposition({
    jobData: params.jobData,
    userData: params.userData,
    userExists: params.userExists,
    nowMs,
  });
  if (disposition.kind === "preserve") {
    return { action: "skip", reason: disposition.reason };
  }

  const sourceEntry = currentSourceEntry(params.privateData, params.jobData);
  if (!sourceEntry) return { action: "skip", reason: "missing_current_source" };
  const sourceSelectionVersion = currentSourceSelectionVersion(
    params.privateData,
    params.jobData,
  );
  if (sourceSelectionVersion === null) {
    return { action: "skip", reason: "selection_version_mismatch" };
  }

  const waitForClipTerminal =
    clipRecommendationConsented(params.privateData, params.jobData) &&
    !isTerminalClipStatus(currentClipStatus(params.privateData, params.clipData ?? null));
  if (waitForClipTerminal) {
    return { action: "skip", reason: "clip_not_terminal" };
  }

  const ref = gcsRefFromSource(sourceEntry);
  if (!ref || !isUidBoundPrivateSourceRef(ref, params.uid)) {
    return { action: "skip", reason: "missing_uid_bound_source_ref" };
  }

  if (disposition.kind === "defer") {
    return {
      action: "defer",
      uid: params.uid,
      jobId: params.jobId,
      photoId: asString(sourceEntry.photoId),
      sourceSelectionVersion,
      refs: [ref],
      reason: disposition.reason,
      eligibleAtMs: disposition.eligibleAtMs,
    };
  }

  return {
    action: "claim",
    uid: params.uid,
    jobId: params.jobId,
    photoId: asString(sourceEntry.photoId),
    sourceSelectionVersion,
    refs: [ref],
    waitForClipTerminal,
  };
}

export function redactSourcePhotosAfterDeletion(
  sourcePhotos: unknown,
  photoId: string,
): RecordData[] {
  return readList(sourcePhotos).map((entry) => {
    if (asString(entry.photoId) !== photoId) return entry;
    const {
      gcsUri: _gcsUri,
      storageBucket: _storageBucket,
      storagePath: _storagePath,
      sourcePhotoRefs: _sourcePhotoRefs,
      sourceDeletion: _sourceDeletion,
      updatedAt: _updatedAt,
      ...safeEntry
    } = entry;
    return {
      ...safeEntry,
      status: "source_deleted",
      sourceDeleted: true,
    };
  });
}

function sourceRefFieldDeletes(): Record<string, unknown> {
  return {
    gcsUri: FieldValue.delete(),
    storageBucket: FieldValue.delete(),
    storagePath: FieldValue.delete(),
    sourcePhotoRefs: [],
    sourceRefRedactedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
  };
}

function isLeaseClaimable(stateData: RecordData, now: Timestamp): boolean {
  const status = asString(stateData.status);
  if (status === "deleted" || status === "terminal_failed") return false;
  if (status !== "deleting") return true;
  const leaseExpiresAt = stateData.leaseExpiresAt;
  if (leaseExpiresAt instanceof Timestamp) {
    return leaseExpiresAt.toMillis() <= now.toMillis();
  }
  return true;
}

function dueForRetry(stateData: RecordData, now: Timestamp): boolean {
  const status = asString(stateData.status);
  if (status === "deleted" || status === "terminal_failed") return false;
  const nextRetryAt = stateData.nextRetryAt;
  if (nextRetryAt instanceof Timestamp) {
    return nextRetryAt.toMillis() <= now.toMillis();
  }
  return status !== "deleting" || isLeaseClaimable(stateData, now);
}

async function writeRetentionEvent(params: {
  firestore: Firestore;
  stateId: string;
  event: RecordData;
}): Promise<void> {
  await params.firestore
    .collection(SOURCE_RETENTION_EVENTS_COLLECTION)
    .doc()
    .set({
      stateId: params.stateId,
      ...params.event,
      createdAt: FieldValue.serverTimestamp(),
    });
}

async function claimPendingSourceDeletion(params: {
  firestore: Firestore;
  uid: string;
  jobId: string;
  trigger: "avatar_job" | "clip_embedding";
}): Promise<AvatarSourceRetentionClaim | null> {
  const privateRef = params.firestore.collection("userPrivateMedia").doc(params.uid);
  const jobRef = params.firestore.collection("avatarJobs").doc(params.jobId);
  const clipRef = params.firestore.collection("clipEmbeddings").doc(params.uid);
  const userRef = params.firestore.collection("users").doc(params.uid);
  const now = Timestamp.now();

  return params.firestore.runTransaction(async (tx) => {
    const [privateSnap, jobSnap, clipSnap, userSnap] = await Promise.all([
      tx.get(privateRef),
      tx.get(jobRef),
      tx.get(clipRef),
      tx.get(userRef),
    ]);
    const privateData = readMap(privateSnap.data());
    const jobData = readMap(jobSnap.data());
    const clipData = clipSnap.exists ? readMap(clipSnap.data()) : null;
    const decision = planAvatarSourceRetention({
      uid: params.uid,
      jobId: params.jobId,
      privateData,
      jobData,
      clipData,
      userData: userSnap.exists ? readMap(userSnap.data()) : null,
      userExists: userSnap.exists,
      nowMs: now.toMillis(),
    });
    if (decision.action === "skip") return null;

    const stateId = avatarSourceRetentionStateId(params.uid, decision.photoId);
    const stateRef = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION).doc(stateId);
    const stateSnap = await tx.get(stateRef);
    const stateData = readMap(stateSnap.data());
    const existingStatus = asString(stateData.status);
    if (existingStatus === "deleted") return null;

    if (decision.action === "defer") {
      // 삭제하지 않는다. 다만 회수 기한을 상태 문서에 남겨야 스케줄러가
      // 기한에 다시 평가한다. 남기지 않으면 동의 없는 원본이 영구 보관된다.
      if (existingStatus === "deleting") return null;
      tx.set(stateRef, {
        uid: decision.uid,
        jobId: decision.jobId,
        photoId: decision.photoId,
        sourceSelectionVersion: decision.sourceSelectionVersion,
        refs: decision.refs,
        status: "deferred",
        deferredReason: decision.reason,
        nextRetryAt: Timestamp.fromMillis(decision.eligibleAtMs),
        trigger: params.trigger,
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      return null;
    }

    if (!isLeaseClaimable(stateData, now) || !dueForRetry(stateData, now)) return null;

    const attempts = Math.max(0, numericValue(stateData.attempts) ?? 0) + 1;
    if (attempts > MAX_SOURCE_DELETION_ATTEMPTS) {
      tx.set(stateRef, {
        status: "terminal_failed",
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      return null;
    }

    const claimToken = randomBytes(16).toString("hex");
    tx.set(stateRef, {
      uid: params.uid,
      jobId: params.jobId,
      photoId: decision.photoId,
      sourceSelectionVersion: decision.sourceSelectionVersion,
      refs: decision.refs,
      status: "deleting",
      claimToken,
      attempts,
      trigger: params.trigger,
      leaseExpiresAt: Timestamp.fromMillis(now.toMillis() + sourceDeletionLeaseMs()),
      claimedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });

    return {
      uid: decision.uid,
      jobId: decision.jobId,
      photoId: decision.photoId,
      sourceSelectionVersion: decision.sourceSelectionVersion,
      claimToken,
      stateId,
      refs: decision.refs,
    };
  });
}

async function preDeleteRevalidateClaim(params: {
  firestore: Firestore;
  claim: AvatarSourceRetentionClaim;
}): Promise<boolean> {
  const privateRef = params.firestore.collection("userPrivateMedia").doc(params.claim.uid);
  const jobRef = params.firestore.collection("avatarJobs").doc(params.claim.jobId);
  const clipRef = params.firestore.collection("clipEmbeddings").doc(params.claim.uid);
  const userRef = params.firestore.collection("users").doc(params.claim.uid);
  const stateRef = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION).doc(params.claim.stateId);

  return params.firestore.runTransaction(async (tx) => {
    const [privateSnap, jobSnap, clipSnap, userSnap, stateSnap] = await Promise.all([
      tx.get(privateRef),
      tx.get(jobRef),
      tx.get(clipRef),
      tx.get(userRef),
      tx.get(stateRef),
    ]);
    const stateData = readMap(stateSnap.data());
    if (
      asString(stateData.status) === "deleted" ||
      asString(stateData.claimToken) !== params.claim.claimToken
    ) {
      return false;
    }
    const privateData = readMap(privateSnap.data());
    const jobData = readMap(jobSnap.data());
    const decision = planAvatarSourceRetention({
      uid: params.claim.uid,
      jobId: params.claim.jobId,
      privateData,
      jobData,
      clipData: clipSnap.exists ? readMap(clipSnap.data()) : null,
      userData: userSnap.exists ? readMap(userSnap.data()) : null,
      userExists: userSnap.exists,
    });
    if (
      decision.action !== "claim" ||
      decision.photoId !== params.claim.photoId ||
      decision.sourceSelectionVersion !== params.claim.sourceSelectionVersion
    ) {
      tx.set(stateRef, {
        status: "stale",
        staleAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      return false;
    }
    if (hasAvatarApprovalProtectedState(readMap(userSnap.data()))) {
      tx.set(stateRef, {
        status: "stale",
        staleAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      return false;
    }
    tx.set(stateRef, {
      preDeleteValidatedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    return true;
  });
}

async function markSourceDeleted(params: {
  firestore: Firestore;
  claim: AvatarSourceRetentionClaim;
}): Promise<void> {
  const privateRef = params.firestore.collection("userPrivateMedia").doc(params.claim.uid);
  const jobRef = params.firestore.collection("avatarJobs").doc(params.claim.jobId);
  const clipRef = params.firestore.collection("clipEmbeddings").doc(params.claim.uid);
  const stateRef = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION).doc(params.claim.stateId);

  await params.firestore.runTransaction(async (tx) => {
    const [privateSnap, stateSnap] = await Promise.all([
      tx.get(privateRef),
      tx.get(stateRef),
    ]);
    const stateData = readMap(stateSnap.data());
    if (
      asString(stateData.status) === "deleted" ||
      asString(stateData.claimToken) !== params.claim.claimToken
    ) {
      return;
    }
    const privateData = readMap(privateSnap.data());
    tx.set(privateRef, {
      sourcePhotos: redactSourcePhotosAfterDeletion(
        privateData.sourcePhotos,
        params.claim.photoId,
      ),
      clip: {
        ...readMap(privateData.clip),
        sourcePhotoIds: [],
        sourceRefRedacted: true,
      },
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.set(jobRef, sourceRefFieldDeletes(), { merge: true });
    tx.set(clipRef, {
      sourcePhotoRefs: [],
      sourceRefRedactedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.set(stateRef, {
      status: "deleted",
      deletedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
  });

  await writeRetentionEvent({
    firestore: params.firestore,
    stateId: params.claim.stateId,
    event: {
      type: "source_deleted",
      ...avatarSourceRetentionPrivacyFields({
        uid: params.claim.uid,
        jobId: params.claim.jobId,
        photoId: params.claim.photoId,
      }),
    },
  });
}

async function markSourceDeletionRetryableFailure(params: {
  firestore: Firestore;
  claim: AvatarSourceRetentionClaim;
  error: unknown;
}): Promise<void> {
  const privateRef = params.firestore.collection("userPrivateMedia").doc(params.claim.uid);
  const stateRef = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION).doc(params.claim.stateId);
  const message = params.error instanceof Error ? params.error.message : String(params.error);
  await params.firestore.runTransaction(async (tx) => {
    const stateSnap = await tx.get(stateRef);
    const stateData = readMap(stateSnap.data());
    if (asString(stateData.claimToken) !== params.claim.claimToken) return;
    const attempts = Math.max(1, numericValue(stateData.attempts) ?? 1);
    const retryAt = nextSourceDeletionRetryAt({ attempts, nowMs: Date.now() });
    tx.set(stateRef, {
      status: retryAt ? "retryable_failed" : "terminal_failed",
      errorHash: createHash("sha256").update(message).digest("hex").slice(0, 16),
      nextRetryAt: retryAt ? Timestamp.fromDate(retryAt) : FieldValue.delete(),
      failedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.set(privateRef, { updatedAt: FieldValue.serverTimestamp() }, { merge: true });
  });
}

export async function executeAvatarSourceRetention(params: {
  firestore: Firestore;
  uid: string;
  jobId: string;
  trigger: "avatar_job" | "clip_embedding";
  deleteObject?: DeleteRetainedObject;
  convergePublicState?: (jobId: string) => Promise<unknown>;
}): Promise<"claimed" | "skipped"> {
  const deleteObject = params.deleteObject ?? deleteRetainedObjectFromStorage;
  // Firestore 트리거 실행 순서는 보장되지 않는다. retention 이 먼저 깨어났다면
  // 스스로 공개 상태 수렴을 유도한 뒤에만 파괴적 동작으로 넘어간다. 이 호출은
  // 멱등이며, state-sync 가 이미 돌았다면 아무것도 바꾸지 않는다.
  const converge = params.convergePublicState ?? defaultConvergePublicState(params.firestore);
  try {
    await converge(params.jobId);
  } catch (error) {
    logger.warn("Avatar public state convergence failed before source retention", {
      jobIdHash: shortHash(params.jobId),
      errorHash: createHash("sha256")
        .update(error instanceof Error ? error.message : String(error))
        .digest("hex")
        .slice(0, 16),
    });
  }
  const claim = await claimPendingSourceDeletion(params);
  if (!claim) return "skipped";
  const valid = await preDeleteRevalidateClaim({ firestore: params.firestore, claim });
  if (!valid) return "skipped";
  try {
    for (const ref of claim.refs) {
      await deleteObject(ref);
    }
    await markSourceDeleted({ firestore: params.firestore, claim });
    logger.info(
      "Avatar source retention deleted private source object",
      avatarSourceRetentionLogFields(claim),
    );
    return "claimed";
  } catch (error) {
    await markSourceDeletionRetryableFailure({ firestore: params.firestore, claim, error });
    logger.warn("Avatar source retention deletion failed", {
      ...avatarSourceRetentionLogFields(claim),
      errorHash: createHash("sha256")
        .update(error instanceof Error ? error.message : String(error))
        .digest("hex")
        .slice(0, 16),
    });
    return "claimed";
  }
}

/**
 * Recovery loop for pending source deletions. Only state documents already in
 * a retry-eligible status are considered; every candidate is re-planned and
 * re-validated through the same authority as the trigger path, so historical,
 * non-current, approval-protected or already-deleted records are never
 * mutated here. Deleted accounts are out of scope: their private media is the
 * account-deletion purge's responsibility, not this generation-lifecycle loop.
 */
export async function recoverAvatarSourceRetentionDeletions(params: {
  firestore: Firestore;
  /** Max DUE state documents evaluated per run (the destructive work cap). */
  limit?: number;
  deleteObject?: DeleteRetainedObject;
  /** State documents read per query page. */
  scanPageSize?: number;
  /** Max state documents read per run. */
  maxScan?: number;
  timeBudgetMs?: number;
  nowMs?: () => number;
}): Promise<AvatarSourceRetentionRecoverySummary> {
  const now = Timestamp.now();
  const nowMs = params.nowMs ?? (() => Date.now());
  const startedAtMs = nowMs();
  const dueLimit = Math.max(1, params.limit ?? 25);
  const pageSize = Math.max(1, params.scanPageSize ?? RECOVERY_SCAN_PAGE_SIZE);
  const maxScan = Math.max(1, params.maxScan ?? RECOVERY_MAX_SCAN);
  const timeBudgetMs = params.timeBudgetMs ?? RECOVERY_TIME_BUDGET_MS;
  const states = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION);
  const checkpointRef = params.firestore
    .collection(RECOVERY_CHECKPOINT_COLLECTION)
    .doc(RECOVERY_CHECKPOINT_ID);

  // AUD-09: this used to read `limit(25)` with no cursor — the same 25 state
  // documents every run. Documents that are not due yet (a deferred source
  // waits up to the recovery grace) or that re-plan to "skip" every time stay
  // in a retry-eligible status, so once 25 of them sorted first, a source
  // whose deletion deadline had passed was never reached.
  //
  // Now the whole retry-eligible set is walked in document-id pages. Documents
  // that are not due cost one read and no longer use up the work cap. When
  // the cap or the budget stops a run, the id it stopped at is stored and the
  // next run continues behind it (wrapping around), so every due document is
  // reached within a bounded number of runs. Skipped documents are still
  // never written to, and a run that finishes its pass writes nothing.
  const storedCursor = asString((await checkpointRef.get()).get("cursor"));
  const startAfterId = storedCursor.length > 0 ? storedCursor : null;

  const summary: AvatarSourceRetentionRecoverySummary = {
    scanned: 0,
    due: 0,
    claimed: 0,
    skipped: 0,
  };

  let after: string | null = startAfterId;
  // Second leg of a resumed pass: from the first id up to the stored cursor.
  let wrapped = startAfterId === null;
  let stoppedAtId: string | null = null;
  let passComplete = false;

  scan: for (;;) {
    let query = states
      .where("status", "in", ["deleting", "retryable_failed", "stale", "deferred"])
      .orderBy(FieldPath.documentId())
      .limit(pageSize);
    if (after) query = query.startAfter(after);
    const page = await query.get();

    let reachedStart = false;
    for (const doc of page.docs) {
      if (wrapped && startAfterId !== null && doc.id > startAfterId) {
        reachedStart = true;
        break;
      }
      if (
        summary.due >= dueLimit ||
        summary.scanned >= maxScan ||
        nowMs() - startedAtMs >= timeBudgetMs
      ) {
        break scan;
      }
      summary.scanned += 1;
      stoppedAtId = doc.id;
      const data = readMap(doc.data());
      if (!dueForRetry(data, now)) continue;
      const uid = asString(data.uid);
      const jobId = asString(data.jobId);
      if (!uid || !jobId) continue;
      summary.due += 1;
      const result = await executeAvatarSourceRetention({
        firestore: params.firestore,
        uid,
        jobId,
        trigger: "avatar_job",
        deleteObject: params.deleteObject,
      });
      if (result === "claimed") summary.claimed += 1;
      else summary.skipped += 1;
    }

    if (reachedStart || page.docs.length < pageSize) {
      if (!wrapped) {
        wrapped = true;
        after = null;
        continue;
      }
      passComplete = true;
      break;
    }
    after = page.docs[page.docs.length - 1].id;
  }

  if (!passComplete && stoppedAtId !== null) {
    await checkpointRef.set({ cursor: stoppedAtId, updatedAt: FieldValue.serverTimestamp() });
  } else if (passComplete && startAfterId !== null) {
    await checkpointRef.set({ cursor: null, updatedAt: FieldValue.serverTimestamp() });
  }
  return summary;
}

function defaultConvergePublicState(
  firestore: Firestore,
): (jobId: string) => Promise<unknown> {
  return (jobId: string) =>
    syncAvatarGenerationStateForJob({ firestore, jobId });
}

async function currentJobIdForUid(
  firestore: Firestore,
  uid: string,
): Promise<string | null> {
  const snap = await firestore.collection("userPrivateMedia").doc(uid).get();
  const jobId = asString(readMap(snap.data()).currentAvatarJobId);
  return jobId || null;
}

export function createAvatarJobSourceRetentionTrigger(firestore: Firestore) {
  return onDocumentWritten("avatarJobs/{jobId}", async (event) => {
    const after = event.data?.after;
    if (!after?.exists) return;
    const before = event.data?.before;
    if (
      !shouldEvaluateAvatarJobSourceRetentionTransition({
        beforeData: before?.exists ? readMap(before.data()) : null,
        afterData: readMap(after.data()),
      })
    ) {
      return;
    }
    const jobData = readMap(after.data());
    const uid = asString(jobData.uid);
    const jobId = asString(event.params.jobId);
    if (!uid || !jobId) return;
    await executeAvatarSourceRetention({
      firestore,
      uid,
      jobId,
      trigger: "avatar_job",
    });
  });
}

export function createClipEmbeddingSourceRetentionTrigger(firestore: Firestore) {
  return onDocumentWritten("clipEmbeddings/{uid}", async (event) => {
    const before = event.data?.before;
    const after = event.data?.after;
    if (
      !shouldEvaluateClipEmbeddingSourceRetentionTransition({
        beforeData: before?.exists ? readMap(before.data()) : null,
        afterData: after?.exists ? readMap(after.data()) : null,
      })
    ) {
      return;
    }
    const uid = asString(event.params.uid);
    if (!uid) return;
    const jobId = await currentJobIdForUid(firestore, uid);
    if (!jobId) return;
    await executeAvatarSourceRetention({
      firestore,
      uid,
      jobId,
      trigger: "clip_embedding",
    });
  });
}

export function createAvatarSourceRetentionRecoveryTrigger(firestore: Firestore) {
  // AUD-09: explicit timeout (was the default 60 s); the scan stops itself at
  // RECOVERY_TIME_BUDGET_MS and resumes on the next run.
  return onSchedule({ schedule: "every 15 minutes", timeoutSeconds: 180 }, async () => {
    const startedAt = Date.now();
    const summary = await recoverAvatarSourceRetentionDeletions({ firestore });
    // Always log the run shape (counts only, no identifiers) so an operator can
    // verify the first controlled run against its dry run.
    logger.info("Avatar source retention recovery run", {
      ...summary,
      durationMs: Date.now() - startedAt,
    });
  });
}
