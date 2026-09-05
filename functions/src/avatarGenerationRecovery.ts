/**
 * needs_review / terminal 실패에서 사용자가 빠져나오는 유일한 안전 경로.
 *
 * 제품 결정(2026-09-05):
 *   같은 logical generation 을 다시 시도하지 않는다.
 *   사용자가 명시적으로 "사진을 바꾸고 다시 만들기"를 선택하면
 *   현재 generation 을 종료하고 source lock 을 풀어 새 generation 을 연다.
 *
 * provider post-send unknown 은 이 경로에서 완전히 제외된다. 이미 과금된
 * 생성이 존재할 수 있으므로 재조정이 끝나기 전에는 새 generation 도 막는다.
 *
 * 순수 함수다. Firestore 를 읽거나 쓰지 않는다.
 */

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

import {
  rejectAvatarRetryRequestWithImageBytes,
  type ResolvedAvatarUploadUser,
} from "./avatarMedia";

type RecordData = Record<string, unknown>;

function readMap(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordData)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

/** 사용자가 스스로 시작할 수 있는 총 generation 횟수 상한. */
export const MAX_USER_GENERATION_ATTEMPTS = 3;

/** 새 generation 으로 교체 가능한 종료 상태. */
const REPLACEABLE_STATUSES = new Set([
  "needs_review",
  "terminal_failed",
  "retryable_failed",
  "no_previewable",
  "no_previewable_candidates",
  "failed",
  "cancelled",
]);

/** 아직 워커/승인이 붙들고 있는 상태. 교체 금지. */
const IN_PROGRESS_STATUSES = new Set([
  "queued",
  "running",
  "generating",
  "provider_inflight",
  "generated",
  "persisted",
  "qa_pending",
  "preview_ready",
  "approval_copying",
]);

const PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES = new Set([
  "azure_unknown_post_send_outcome",
]);

export type NewGenerationRecoveryDecision =
  | { allowed: false; reasonCode: string }
  | {
      allowed: true;
      releasesSourceLock: true;
      jobUpdate: RecordData;
      privateMediaClearFields: readonly string[];
      userAvatarStatus: string;
    };

export function planNewGenerationRecovery(params: {
  currentJobData: unknown;
  userAvatar: unknown;
  generationAttemptCount: number;
}): NewGenerationRecoveryDecision {
  const job = readMap(params.currentJobData);
  const avatar = readMap(params.userAvatar);
  const status = asString(job.status) || asString(avatar.status);
  const errorCode = asString(job.errorCode);
  const claimState = asString(readMap(job.generationClaim).state);

  if (status === "approved" || asString(avatar.status) === "approved") {
    return { allowed: false, reasonCode: "avatar_already_approved" };
  }

  // provider 결과 미확인은 그 어떤 새 생성보다 우선해서 막는다.
  if (
    PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES.has(errorCode) ||
    claimState === "active"
  ) {
    return { allowed: false, reasonCode: "avatar_provider_outcome_unknown" };
  }

  if (IN_PROGRESS_STATUSES.has(status)) {
    return { allowed: false, reasonCode: "avatar_generation_in_progress" };
  }

  if (!REPLACEABLE_STATUSES.has(status)) {
    return { allowed: false, reasonCode: "avatar_generation_not_replaceable" };
  }

  if (params.generationAttemptCount >= MAX_USER_GENERATION_ATTEMPTS) {
    return { allowed: false, reasonCode: "avatar_generation_limit_reached" };
  }

  return {
    allowed: true,
    releasesSourceLock: true,
    jobUpdate: {
      status: "cancelled",
      errorCode: "avatar_generation_replaced_by_user",
      retryable: false,
    },
    // 이 필드들을 지워야 새 source set 이 admission 을 통과할 수 있다.
    privateMediaClearFields: [
      "currentAvatarSourcePhotoId",
      "currentAvatarJobId",
    ],
    userAvatarStatus: "none",
  };
}

// ---------------------------------------------------------------------------
// Callable boundary
// ---------------------------------------------------------------------------

export const REPLACE_AVATAR_GENERATION_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 60,
  memory: "512MiB",
  invoker: "public",
  enforceAppCheck: true,
};

type ResolveUploadUser = (
  auth: CallableRequest<unknown>["auth"],
) => Promise<ResolvedAvatarUploadUser>;

const SAFE_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

function requireSegment(value: unknown, field: string): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!SAFE_SEGMENT.test(normalized)) {
    throw new HttpsError("invalid-argument", `${field} is invalid.`);
  }
  return normalized;
}

export type ReplaceAvatarGenerationResult = {
  replaced: boolean;
  duplicate: boolean;
  previousJobId: string | null;
  generationAttemptCount: number;
};

/// Ends the current logical generation and releases the source lock so the
/// user can pick new photos and start a NEW generation (new source selection,
/// new job id). This is NOT a retry of the same generation.
///
/// Refused for provider-ambiguous outcomes, active generations and approved
/// avatars — see planNewGenerationRecovery. Idempotent per clientRequestId.
export async function replaceAvatarGenerationCore(params: {
  firestore: Firestore;
  uid: string;
  clientRequestId: string;
}): Promise<ReplaceAvatarGenerationResult> {
  const { firestore, uid } = params;
  const clientRequestId = requireSegment(params.clientRequestId, "clientRequestId");
  const userRef = firestore.collection("users").doc(uid);
  const privateRef = firestore.collection("userPrivateMedia").doc(uid);

  return firestore.runTransaction(async (tx) => {
    const [userSnap, privateSnap] = await Promise.all([
      tx.get(userRef),
      tx.get(privateRef),
    ]);
    if (!userSnap.exists) {
      throw new HttpsError("failed-precondition", "User profile was not found.");
    }
    const userData = readMap(userSnap.data());
    const privateData = readMap(privateSnap.data());
    const userAvatar = readMap(userData.avatar);
    const currentJobId = asString(privateData.currentAvatarJobId);

    let jobData: RecordData = {};
    let jobRef: ReturnType<Firestore["collection"]> extends infer C
      ? C extends { doc(id: string): infer D }
        ? D
        : never
      : never;
    jobRef = firestore.collection("avatarJobs").doc(currentJobId || "__none__");
    if (currentJobId) {
      const jobSnap = await tx.get(jobRef);
      jobData = jobSnap.exists ? readMap(jobSnap.data()) : {};
      if (jobSnap.exists && asString(jobData.uid) && asString(jobData.uid) !== uid) {
        throw new HttpsError("failed-precondition", "avatar_job_not_current");
      }
    }

    const previousReplacements = Math.max(
      0,
      Math.floor(Number(userAvatar.generationReplacementCount ?? 0) || 0),
    );

    // Idempotent replay: the same request already released this generation.
    if (
      currentJobId === "" &&
      asString(userAvatar.replacedByClientRequestId) === clientRequestId
    ) {
      // The counter was already advanced by the original request.
      return {
        replaced: true,
        duplicate: true,
        previousJobId: asString(userAvatar.replacedJobId) || null,
        generationAttemptCount: previousReplacements,
      };
    }

    const decision = planNewGenerationRecovery({
      currentJobData: currentJobId ? jobData : { status: asString(userAvatar.status) },
      userAvatar,
      generationAttemptCount: previousReplacements + 1,
    });
    if (!decision.allowed) {
      const code =
        decision.reasonCode === "avatar_generation_limit_reached"
          ? "resource-exhausted"
          : "failed-precondition";
      throw new HttpsError(code, decision.reasonCode);
    }

    if (currentJobId) {
      tx.set(
        jobRef,
        {
          ...decision.jobUpdate,
          replacedByClientRequestId: clientRequestId,
          replacedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true },
      );
    }

    // Release every source that belonged to the replaced generation so the
    // contract reader sees no dangling "current" entry.
    const sourcePhotos = Array.isArray(privateData.sourcePhotos)
      ? privateData.sourcePhotos.filter(
          (entry): entry is RecordData => entry !== null && typeof entry === "object",
        )
      : [];
    const releasedSources = sourcePhotos.map((entry) => {
      const state = asString(entry.avatarGenerationState);
      if (state === "current" || state === "selection_candidate") {
        return { ...entry, avatarGenerationState: "replaced" };
      }
      return entry;
    });
    tx.set(
      privateRef,
      {
        ...Object.fromEntries(
          decision.privateMediaClearFields.map((field) => [field, FieldValue.delete()]),
        ),
        avatarSourceSelection: FieldValue.delete(),
        sourcePhotos: releasedSources,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
    tx.set(
      userRef,
      {
        "avatar.status": decision.userAvatarStatus,
        "avatar.errorCode": FieldValue.delete(),
        "avatar.reasonCode": FieldValue.delete(),
        "avatar.sourceJobId": FieldValue.delete(),
        "avatar.jobId": FieldValue.delete(),
        "avatar.sourcePhotoId": FieldValue.delete(),
        "avatar.generationReplacementCount": previousReplacements + 1,
        "avatar.replacedByClientRequestId": clientRequestId,
        "avatar.replacedJobId": currentJobId || FieldValue.delete(),
        "avatar.updatedAt": FieldValue.serverTimestamp(),
        "onboarding.avatarGenerationJobId": FieldValue.delete(),
        "onboarding.sourcePhotoUploadStatus": "avatar_generation_replaced",
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );

    return {
      replaced: true,
      duplicate: false,
      previousJobId: currentJobId || null,
      generationAttemptCount: previousReplacements + 1,
    };
  });
}

export function createReplaceAvatarGenerationFunction(
  firestore: Firestore,
  resolveUploadUser: ResolveUploadUser,
) {
  return onCall(REPLACE_AVATAR_GENERATION_CALLABLE_OPTIONS, async (request) => {
    const user = await resolveUploadUser(request.auth);
    const uid = requireSegment(user.userId, "uid");
    const data = readMap(request.data);
    // This endpoint never accepts image bytes or source refs.
    rejectAvatarRetryRequestWithImageBytes(data);
    return replaceAvatarGenerationCore({
      firestore,
      uid,
      clientRequestId: asString(data.clientRequestId),
    });
  });
}
