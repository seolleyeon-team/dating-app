import {
  FieldValue,
  type Firestore,
} from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";

type RecordData = Record<string, unknown>;

type AvatarGenerationStateSyncPlan =
  | { action: "skip"; reason: string }
  | {
      action: "update_user_avatar";
      uid: string;
      jobId: string;
      sourcePhotoId: string;
      avatarStatus: string;
      onboardingStatus: string;
      sourceSelectionVersion: number | null;
      avatarErrorCode: string | null;
      clearAvatarError: boolean;
    };

const PRESERVED_AVATAR_STATUSES = new Set([
  "approved",
  "approval_copying",
  "approval_copy_failed",
]);

const TERMINAL_JOB_STATUSES = new Set([
  "preview_ready",
  "completed",
  "failed",
  "retryable_failed",
  "terminal_failed",
  "no_previewable",
  "no_previewable_candidates",
  "needs_review",
  "cancelled",
  "canceled",
  "superseded",
]);

function isRecord(value: unknown): value is RecordData {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readMap(value: unknown): RecordData {
  return isRecord(value) ? value : {};
}

function readList(value: unknown): RecordData[] {
  return Array.isArray(value) ? value.filter(isRecord).map((entry) => ({ ...entry })) : [];
}

function asString(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function numericValue(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? Math.floor(parsed) : null;
}

function sourcePhotoIds(jobData: RecordData): string[] {
  const ids = Array.isArray(jobData.sourcePhotoIds)
    ? jobData.sourcePhotoIds.map(asString).filter(Boolean)
    : [];
  const legacy = asString(jobData.sourcePhotoId);
  return legacy && !ids.includes(legacy) ? [...ids, legacy] : ids;
}

function currentSourceContract(params: {
  jobData: RecordData;
  privateData: RecordData;
}): { ok: true; sourcePhotoId: string; sourceSelectionVersion: number | null } | { ok: false } {
  const currentJobId = asString(params.privateData.currentAvatarJobId);
  const jobId = asString(params.jobData.jobId);
  if (!currentJobId || currentJobId !== jobId) return { ok: false };

  const currentPhotoId = asString(params.privateData.currentAvatarSourcePhotoId);
  const jobPhotoIds = sourcePhotoIds(params.jobData);
  if (!currentPhotoId || !jobPhotoIds.includes(currentPhotoId)) return { ok: false };

  const sourceEntry = readList(params.privateData.sourcePhotos).find(
    (entry) =>
      asString(entry.photoId) === currentPhotoId &&
      asString(entry.status) === "active" &&
      asString(entry.avatarGenerationState) === "current",
  );
  if (!sourceEntry) return { ok: false };

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
    return { ok: false };
  }
  return {
    ok: true,
    sourcePhotoId: currentPhotoId,
    sourceSelectionVersion: jobSelectionVersion ?? privateSelectionVersion,
  };
}

function publicAvatarContractOk(params: {
  avatar: RecordData;
  jobId: string;
  sourcePhotoId: string;
  sourceSelectionVersion: number | null;
}): boolean {
  const sourceJobId = asString(params.avatar.sourceJobId);
  if (sourceJobId && sourceJobId !== params.jobId) return false;
  const avatarJobId = asString(params.avatar.jobId);
  if (avatarJobId && avatarJobId !== params.jobId) return false;
  const avatarSourcePhotoId = asString(params.avatar.sourcePhotoId);
  if (avatarSourcePhotoId && avatarSourcePhotoId !== params.sourcePhotoId) return false;
  const avatarSelectionVersion = numericValue(params.avatar.sourceSelectionVersion);
  if (
    avatarSelectionVersion !== null &&
    params.sourceSelectionVersion !== null &&
    avatarSelectionVersion !== params.sourceSelectionVersion
  ) {
    return false;
  }
  return true;
}

function mapTerminalJobStatus(jobStatus: string): {
  avatarStatus: string;
  onboardingStatus: string;
  avatarErrorCode: string | null;
  clearAvatarError: boolean;
} | null {
  switch (jobStatus) {
    case "preview_ready":
      return {
        avatarStatus: "preview_ready",
        onboardingStatus: "avatar_generation_preview_ready",
        avatarErrorCode: null,
        clearAvatarError: true,
      };
    case "completed":
      return {
        avatarStatus: "completed",
        onboardingStatus: "avatar_generation_completed",
        avatarErrorCode: null,
        clearAvatarError: true,
      };
    case "no_previewable":
    case "no_previewable_candidates":
      return {
        avatarStatus: "no_previewable_candidates",
        onboardingStatus: "no_previewable_candidates",
        avatarErrorCode: "no_previewable_candidates",
        clearAvatarError: false,
      };
    case "retryable_failed":
      return {
        avatarStatus: "retryable_failed",
        onboardingStatus: "avatar_generation_retryable_failed",
        avatarErrorCode: "avatar_generation_retryable_failed",
        clearAvatarError: false,
      };
    case "failed":
      return {
        avatarStatus: "failed",
        onboardingStatus: "avatar_generation_failed",
        avatarErrorCode: "avatar_generation_failed",
        clearAvatarError: false,
      };
    case "terminal_failed":
      return {
        avatarStatus: "terminal_failed",
        onboardingStatus: "avatar_generation_terminal_failed",
        avatarErrorCode: "avatar_generation_terminal_failed",
        clearAvatarError: false,
      };
    case "needs_review":
      return {
        avatarStatus: "needs_review",
        onboardingStatus: "avatar_generation_needs_review",
        avatarErrorCode: "avatar_generation_needs_review",
        clearAvatarError: false,
      };
    case "cancelled":
    case "canceled":
      return {
        avatarStatus: jobStatus,
        onboardingStatus: `avatar_generation_${jobStatus}`,
        avatarErrorCode: "avatar_generation_cancelled",
        clearAvatarError: false,
      };
    default:
      return null;
  }
}

export function planAvatarGenerationStateSync(params: {
  jobId: string;
  jobData: RecordData;
  privateData: RecordData;
  userData: RecordData;
}): AvatarGenerationStateSyncPlan {
  const uid = asString(params.jobData.uid);
  if (!uid) return { action: "skip", reason: "missing_uid" };
  if (asString(params.jobData.jobId) && asString(params.jobData.jobId) !== params.jobId) {
    return { action: "skip", reason: "job_id_mismatch" };
  }
  const jobData: RecordData = { ...params.jobData, jobId: params.jobId };
  const jobStatus = asString(jobData.status).toLowerCase();
  if (!TERMINAL_JOB_STATUSES.has(jobStatus)) {
    return { action: "skip", reason: "job_not_terminal" };
  }
  if (jobStatus === "superseded") {
    return { action: "skip", reason: "job_superseded" };
  }
  const sourceContract = currentSourceContract({
    jobData,
    privateData: params.privateData,
  });
  if (!sourceContract.ok) {
    return { action: "skip", reason: "stale_or_superseded_job" };
  }

  const avatar = readMap(params.userData.avatar);
  const avatarStatus = asString(avatar.status);
  if (PRESERVED_AVATAR_STATUSES.has(avatarStatus)) {
    return { action: "skip", reason: "avatar_approval_preserved" };
  }
  if (
    !publicAvatarContractOk({
      avatar,
      jobId: params.jobId,
      sourcePhotoId: sourceContract.sourcePhotoId,
      sourceSelectionVersion: sourceContract.sourceSelectionVersion,
    })
  ) {
    return { action: "skip", reason: "public_avatar_contract_mismatch" };
  }

  const mapped = mapTerminalJobStatus(jobStatus);
  if (!mapped) return { action: "skip", reason: "terminal_status_not_public" };
  return {
    action: "update_user_avatar",
    uid,
    jobId: params.jobId,
    sourcePhotoId: sourceContract.sourcePhotoId,
    avatarStatus: mapped.avatarStatus,
    onboardingStatus: mapped.onboardingStatus,
    sourceSelectionVersion: sourceContract.sourceSelectionVersion,
    avatarErrorCode: mapped.avatarErrorCode,
    clearAvatarError: mapped.clearAvatarError,
  };
}

export async function syncAvatarGenerationStateForJob(params: {
  firestore: Firestore;
  jobId: string;
}): Promise<"updated" | "skipped"> {
  const jobRef = params.firestore.collection("avatarJobs").doc(params.jobId);
  return params.firestore.runTransaction(async (tx) => {
    const jobSnap = await tx.get(jobRef);
    if (!jobSnap.exists) return "skipped";
    const jobData = readMap(jobSnap.data());
    const uid = asString(jobData.uid);
    if (!uid) return "skipped";
    const privateRef = params.firestore.collection("userPrivateMedia").doc(uid);
    const userRef = params.firestore.collection("users").doc(uid);
    const [privateSnap, userSnap] = await Promise.all([
      tx.get(privateRef),
      tx.get(userRef),
    ]);
    const plan = planAvatarGenerationStateSync({
      jobId: params.jobId,
      jobData,
      privateData: readMap(privateSnap.data()),
      userData: readMap(userSnap.data()),
    });
    if (plan.action !== "update_user_avatar") return "skipped";

    tx.update(userRef, {
      profileImageMode: "avatar",
      "avatar.status": plan.avatarStatus,
      "avatar.sourceJobId": plan.jobId,
      "avatar.jobId": plan.jobId,
      "avatar.sourcePhotoId": plan.sourcePhotoId,
      "avatar.sourceSelectionVersion": plan.sourceSelectionVersion ?? FieldValue.delete(),
      "avatar.errorCode": plan.avatarErrorCode ?? FieldValue.delete(),
      "avatar.reasonCode": plan.avatarErrorCode ?? FieldValue.delete(),
      "avatar.updatedAt": FieldValue.serverTimestamp(),
      "onboarding.sourcePhotoUploadStatus": plan.onboardingStatus,
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.set(jobRef, {
      publicStateSyncedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    return "updated";
  });
}

export function createAvatarGenerationStateSyncTrigger(firestore: Firestore) {
  return onDocumentWritten("avatarJobs/{jobId}", async (event) => {
    const after = event.data?.after;
    if (!after?.exists) return;
    const result = await syncAvatarGenerationStateForJob({
      firestore,
      jobId: asString(event.params.jobId),
    });
    if (result === "updated") {
      logger.info("Avatar generation terminal state synced", {
        jobId: asString(event.params.jobId),
      });
    }
  });
}
