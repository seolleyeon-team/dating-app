export const QUALITY_SELECTOR_MODE = "quality_selector_v1" as const;
export const LEGACY_FIRST_PHOTO_MODE = "legacy_first_photo" as const;
export const AVATAR_SOURCE_SELECTOR_VERSION =
  "avatar_source_quality_selector_v1" as const;

export type AvatarSourceSelectionMode =
  | typeof QUALITY_SELECTOR_MODE
  | typeof LEGACY_FIRST_PHOTO_MODE;

export type AvatarSourceCandidate = {
  photoId: string;
  gcsUri: string;
  objectGeneration: string;
  stableOrder: number;
};

type ServerEnvironment = Readonly<Record<string, string | undefined>>;

export function shouldDispatchPendingSourceSetJob(
  job: Readonly<Record<string, unknown>>,
): boolean {
  const status = String(job.status ?? "").trim();
  const queueStatus = String(job.queueStatus ?? "").trim();
  const errorCode = String(job.errorCode ?? "").trim();
  if (
    status === "retryable_failed" &&
    errorCode === "avatar_queue_dispatch_failed"
  ) {
    return true;
  }
  return status === "queued" && !queueStatus;
}

export function resolveServerSourceSelectionMode(
  environment: ServerEnvironment,
): AvatarSourceSelectionMode {
  const configured = environment.AVATAR_SOURCE_SELECTION_MODE?.trim();
  if (!configured || configured === QUALITY_SELECTOR_MODE) {
    return QUALITY_SELECTOR_MODE;
  }
  if (configured === LEGACY_FIRST_PHOTO_MODE) {
    return LEGACY_FIRST_PHOTO_MODE;
  }
  throw new Error(
    "AVATAR_SOURCE_SELECTION_MODE must be quality_selector_v1 or legacy_first_photo",
  );
}

export function buildPendingAvatarSourceJob(params: {
  uid: string;
  jobId: string;
  clientRequestId: string;
  selectionVersion: number;
  candidates: readonly AvatarSourceCandidate[];
  avatarPresentationGender: string;
  sourceSelectionMode?: AvatarSourceSelectionMode;
}): Record<string, unknown> {
  if (params.candidates.length < 2 || params.candidates.length > 6) {
    throw new Error("Avatar source selection requires between 2 and 6 candidates.");
  }

  const sourceSelectionMode =
    params.sourceSelectionMode ?? resolveServerSourceSelectionMode(process.env);
  return {
    schemaVersion: "avatar_job_v1",
    uid: params.uid,
    jobId: params.jobId,
    uploadClientRequestId: params.clientRequestId,
    sourceSelectionVersion: params.selectionVersion,
    sourceSelectionMode,
    sourcePhotoIds: params.candidates.map((candidate) => candidate.photoId),
    sourcePhotoRefs: params.candidates.map((candidate) => candidate.gcsUri),
    sourcePhotoObjectGenerations: params.candidates.map(
      (candidate) => candidate.objectGeneration,
    ),
    sourceSelectionCandidates: params.candidates.map((candidate) => ({
      photoId: candidate.photoId,
      gcsUri: candidate.gcsUri,
      objectGeneration: candidate.objectGeneration,
      stableOrder: candidate.stableOrder,
    })),
    sourceSelection: {
      status: "pending",
      selectorVersion: AVATAR_SOURCE_SELECTOR_VERSION,
      evaluatedCount: 0,
    },
    avatarPresentationGender: params.avatarPresentationGender,
    candidateCount: 2,
    status: "queued",
    progress: 0,
  };
}
