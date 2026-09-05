import { createHash } from "crypto";

import { getStorage } from "firebase-admin/storage";
import {
  FieldValue,
  Firestore,
  Timestamp,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableRequest,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import {
  AVATAR_SOURCE_CONSENT_VERSION,
  AVATAR_UPLOAD_SOURCE_PHOTO_CALLABLE_OPTIONS,
  avatarPresentationGenderFromUserData,
  buildAvatarSourceEntry,
  buildPrivateMediaPayload,
  evaluateAvatarUploadAllowlist,
  hasActiveAvatarWorkflowState,
  isSafeApprovedAvatarUrl,
  requireAvatarUploadRequestMetadata,
  throwIfAvatarGenerationDisabled,
  type AvatarConsentPurposes,
  type ResolvedAvatarUploadUser,
} from "./avatarMedia";
import {
  type AvatarSourceCandidate,
  buildPendingAvatarSourceJob,
  resolveServerSourceSelectionMode,
  shouldDispatchPendingSourceSetJob,
} from "./avatarSourceSelectionAdmission";
import {
  type OnboardingPhotoSourceRef,
  onboardingPhotoPath,
  parseOnboardingPhotoSourceSet,
  validateStoredOnboardingPhoto,
} from "./onboardingPhotoSourceSet";
import {
  enqueueAvatarSourceSetJob,
  type AvatarSourceSetQueuePayload,
} from "./avatarSourceSetQueue";

const PRIVATE_SOURCE_BUCKET =
  "seolleyeon-final-private-source-photos";
const AVATAR_MODEL_ID = "azure_gpt_image_2" as const;
const JOB_SCHEMA_VERSION = "avatar_job_v1" as const;

type ResolveUploadUser = (
  auth: CallableRequest<unknown>["auth"],
) => Promise<ResolvedAvatarUploadUser>;

/// Minimal Storage surface the admission needs. Real deps wrap firebase-admin;
/// tests supply in-memory fakes so the whole admission matrix runs offline.
export type StoredFileLike = {
  getMetadata(): Promise<[Record<string, unknown>]>;
  download(): Promise<[Buffer]>;
  exists(): Promise<[boolean]>;
  save(data: Buffer, options: Record<string, unknown>): Promise<unknown>;
};

export type BucketLike = {
  name: string;
  file(path: string, options?: { generation?: string }): StoredFileLike;
};

export type SourceSetAdmissionDeps = {
  firestore: Firestore;
  onboardingBucket: () => BucketLike;
  privateSourceBucket: () => BucketLike;
  enqueueAvatar: (
    payload: AvatarSourceSetQueuePayload,
  ) => Promise<Record<string, unknown>>;
  env: Readonly<Record<string, string | undefined>>;
};

export type SourceSetAdmissionResult = {
  jobId: string;
  avatarStatus: string;
  message: string;
  duplicate: boolean;
  sourceSelectionVersion: number;
  clipRecommendation: "not_requested" | "deferred_until_source_selected";
};

export function defaultSourceSetAdmissionDeps(
  firestore: Firestore,
): SourceSetAdmissionDeps {
  return {
    firestore,
    onboardingBucket: () => getStorage().bucket() as unknown as BucketLike,
    privateSourceBucket: () =>
      getStorage().bucket(sourceBucketName()) as unknown as BucketLike,
    enqueueAvatar: enqueueAvatarSourceSetJob,
    env: process.env,
  };
}

type PreparedSource = AvatarSourceCandidate & {
  storagePath: string;
  sizeBytes: number;
  imageSha256: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeUid(value: string): string {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new HttpsError("permission-denied", "invalid_authenticated_user");
  }
  return value;
}

function digest(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function isStoragePreconditionFailure(error: unknown): boolean {
  if (!isRecord(error)) return false;
  const code = error.code ?? error.statusCode;
  if (code === 412 || code === "412") return true;
  const message = String(error.message ?? "");
  return message.includes("412") || /precondition/i.test(message);
}

function sourceBucketName(): string {
  return (
    process.env.SOURCE_PHOTO_BUCKET?.trim() ||
    process.env.AVATAR_SOURCE_PHOTO_BUCKET?.trim() ||
    PRIVATE_SOURCE_BUCKET
  );
}

function sourcePhotoId(
  source: OnboardingPhotoSourceRef,
  clientRequestId: string,
): string {
  return `src_${digest(`${clientRequestId}:${source.photoId}`).slice(0, 28)}`;
}

function sourceJobId(uid: string, clientRequestId: string): string {
  return `avatar_job_${digest(`${uid}:${clientRequestId}:source_set_v1`).slice(0, 24)}`;
}

function sourceSelectionVersion(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed + 1 : 1;
}

function hasApprovedAvatar(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const status = String(value.status ?? "").trim().toLowerCase();
  return (
    status === "approved" ||
    status === "approval_copying" ||
    status === "approval_in_progress" ||
    // users/{uid}.avatar stores approvedAvatarUrl; keep the legacy alias too.
    isSafeApprovedAvatarUrl(value.approvedAvatarUrl) ||
    isSafeApprovedAvatarUrl(value.approvedUrl)
  );
}

function sourcePhotos(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((entry) => ({ ...entry }));
}

function replacePreparedSources(
  existing: Record<string, unknown>[],
  prepared: PreparedSource[],
  params: {
    clientRequestId: string;
    consentVersion: typeof AVATAR_SOURCE_CONSENT_VERSION;
    consentPurposes: AvatarConsentPurposes;
  },
): Record<string, unknown>[] {
  const preparedIds = new Set(prepared.map((item) => item.photoId));
  const retained = existing.filter(
    (entry) => !preparedIds.has(String(entry.photoId ?? "")),
  );
  const now = Timestamp.now();
  return [
    ...retained,
    ...prepared.map((item) => ({
      ...buildAvatarSourceEntry({
        photoId: item.photoId,
        gcsUri: item.gcsUri,
        storagePath: item.storagePath,
        sizeBytes: item.sizeBytes,
        imageSha256: item.imageSha256,
        clientRequestId: params.clientRequestId,
        consentVersion: params.consentVersion,
        consentPurposes: params.consentPurposes,
        uploadedAt: now,
        updatedAt: now,
      }),
      objectGeneration: item.objectGeneration,
      avatarGenerationState: "selection_candidate",
    })),
  ];
}

async function prepareVerifiedSource(params: {
  deps: SourceSetAdmissionDeps;
  uid: string;
  clientRequestId: string;
  source: OnboardingPhotoSourceRef;
  stableOrder: number;
}): Promise<PreparedSource> {
  const inputBucket = params.deps.onboardingBucket();
  const inputPath = onboardingPhotoPath(params.uid, params.source.photoId);
  const inputFile = inputBucket.file(inputPath, {
    generation: params.source.objectGeneration,
  });
  let inputMetadata;
  try {
    [inputMetadata] = await inputFile.getMetadata();
    validateStoredOnboardingPhoto(
      params.source,
      inputMetadata,
      params.uid,
    );
  } catch (error) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_onboarding_source_invalid",
      { reason: error instanceof Error ? error.message : "validation_failed" },
    );
  }

  let bytes: Buffer;
  try {
    [bytes] = await inputFile.download();
  } catch {
    throw new HttpsError(
      "failed-precondition",
      "avatar_onboarding_source_generation_mismatch",
    );
  }

  const imageSha256 = digest(bytes);
  const photoId = sourcePhotoId(params.source, params.clientRequestId);
  const storagePath = `users/${params.uid}/source/${photoId}.jpg`;
  const outputBucket = params.deps.privateSourceBucket();
  const outputFile = outputBucket.file(storagePath);
  const [exists] = await outputFile.exists();
  if (!exists) {
    try {
      await outputFile.save(bytes, {
        resumable: false,
        preconditionOpts: { ifGenerationMatch: 0 },
        metadata: {
          contentType: "image/jpeg",
          metadata: {
            ownerUid: params.uid,
            uploadKind: "avatar_source_selection_candidate",
            uploadState: "ready",
            sourceInputMode: "storage_normalized_original_direct",
            sourceRequestId: params.clientRequestId,
            sourceSha256: imageSha256,
          },
        },
      });
    } catch (error) {
      // Two submits of the same request can race here (double tap before the
      // first response). The create-only precondition makes the loser see a
      // 412; that is idempotent success as long as the provenance below
      // matches. Anything else is a real Storage failure.
      if (!isStoragePreconditionFailure(error)) throw error;
    }
  }
  const [outputMetadata] = await outputFile.getMetadata();
  const custom = isRecord(outputMetadata.metadata)
    ? outputMetadata.metadata
    : {};
  if (
    String(custom.ownerUid ?? "") !== params.uid ||
    String(custom.sourceRequestId ?? "") !== params.clientRequestId ||
    String(custom.sourceSha256 ?? "") !== imageSha256
  ) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_private_source_conflict",
    );
  }
  const objectGeneration = String(outputMetadata.generation ?? "").trim();
  if (!/^\d+$/.test(objectGeneration)) {
    throw new HttpsError("internal", "avatar_private_source_generation_missing");
  }
  return {
    photoId,
    gcsUri: `gs://${outputBucket.name}/${storagePath}`,
    objectGeneration,
    stableOrder: params.stableOrder,
    storagePath,
    sizeBytes: bytes.length,
    imageSha256,
  };
}

export function createBeginAvatarGenerationFromOnboardingPhotosFunction(
  firestore: Firestore,
  resolveUploadUser: ResolveUploadUser,
  deps: SourceSetAdmissionDeps = defaultSourceSetAdmissionDeps(firestore),
) {
  return onCall(
    AVATAR_UPLOAD_SOURCE_PHOTO_CALLABLE_OPTIONS,
    async (request) => {
      const user = await resolveUploadUser(request.auth);
      const uid = safeUid(user.userId);
      const data = isRecord(request.data) ? request.data : {};
      return admitAvatarGenerationFromOnboardingPhotos(deps, { uid, data });
    },
  );
}

/// CANONICAL GENERATION ADMISSION (2026-09-05).
///
///   2-6 server-verified onboarding photos -> private normalized copies
///   -> ONE pending source-set job (sourceSelection.status = "pending")
///   -> ONE Cloud Task. The worker (Phase B) selects the best source and
///   locks it transactionally; until then the contract is `source_selecting`.
///
/// CLIP recommendation consent is an independent concern: it never blocks
/// admission. When consented, the CLIP embedding is enqueued only once the
/// selected source is known (see avatarClipAfterSelection), never here.
export async function admitAvatarGenerationFromOnboardingPhotos(
  deps: SourceSetAdmissionDeps,
  params: { uid: string; data: Record<string, unknown> },
): Promise<SourceSetAdmissionResult> {
  const { firestore } = deps;
  const uid = safeUid(params.uid);
  const data = params.data;
  {
      const requestedUid = String(data.uid ?? "").trim();
      if (requestedUid && requestedUid !== uid) {
        throw new HttpsError("permission-denied", "uid does not match authenticated user.");
      }
      const metadata = requireAvatarUploadRequestMetadata(data);
      const clipRecommendation = metadata.consentPurposes.clipRecommendation
        ? "deferred_until_source_selected"
        : "not_requested";
      const allowlist = evaluateAvatarUploadAllowlist(uid);
      if (allowlist.enabled && !allowlist.allowed) {
        throw new HttpsError("permission-denied", "avatar_generation_not_allowed");
      }
      throwIfAvatarGenerationDisabled();

      let requestedSources: OnboardingPhotoSourceRef[];
      try {
        requestedSources = parseOnboardingPhotoSourceSet(data.sourcePhotos);
      } catch {
        throw new HttpsError("invalid-argument", "avatar_source_set_invalid");
      }

      const userRef = firestore.collection("users").doc(uid);
      const privateRef = firestore.collection("userPrivateMedia").doc(uid);
      const [userSnap, privateSnap] = await Promise.all([
        userRef.get(),
        privateRef.get(),
      ]);
      if (!userSnap.exists) {
        throw new HttpsError("failed-precondition", "User profile was not found.");
      }
      const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
      const privateData = (privateSnap.data() ?? {}) as Record<string, unknown>;
      if (hasApprovedAvatar(userData.avatar)) {
        throw new HttpsError("failed-precondition", "avatar_already_approved");
      }

      const currentJobId = String(privateData.currentAvatarJobId ?? "").trim();
      let replayingFailedDispatch = false;
      if (currentJobId) {
        const currentJob = await firestore.collection("avatarJobs").doc(currentJobId).get();
        if (
          currentJob.exists &&
          currentJob.get("uploadClientRequestId") === metadata.clientRequestId
        ) {
          const currentJobData = (currentJob.data() ?? {}) as Record<
            string,
            unknown
          >;
          if (!shouldDispatchPendingSourceSetJob(currentJobData)) {
            return {
              jobId: currentJobId,
              avatarStatus: String(currentJob.get("status") ?? "queued"),
              message: "avatar_generation_queued",
              duplicate: true,
              sourceSelectionVersion: Number(
                currentJob.get("avatarSourceSelectionVersion") ?? 0,
              ),
              clipRecommendation,
            };
          }
          replayingFailedDispatch = true;
        } else {
          throw new HttpsError("failed-precondition", "avatar_source_locked");
        }
      }
      if (
        !replayingFailedDispatch &&
        hasActiveAvatarWorkflowState(userData.avatar)
      ) {
        throw new HttpsError("failed-precondition", "avatar_source_locked");
      }

      const prepared = await Promise.all(
        requestedSources.map((source, stableOrder) =>
          prepareVerifiedSource({
            deps,
            uid,
            clientRequestId: metadata.clientRequestId,
            source,
            stableOrder,
          }),
        ),
      );
      const jobId = sourceJobId(uid, metadata.clientRequestId);
      const jobRef = firestore.collection("avatarJobs").doc(jobId);
      const selectionMode = resolveServerSourceSelectionMode(deps.env);
      const avatarGender = avatarPresentationGenderFromUserData(userData);
      let persistedSelectionVersion = 0;
      let duplicate = false;
      let shouldEnqueue = false;

      await firestore.runTransaction(async (transaction) => {
        const [freshUserSnap, freshPrivateSnap, freshJobSnap] = await Promise.all([
          transaction.get(userRef),
          transaction.get(privateRef),
          transaction.get(jobRef),
        ]);
        const freshUser = (freshUserSnap.data() ?? {}) as Record<string, unknown>;
        const freshPrivate = (freshPrivateSnap.data() ?? {}) as Record<string, unknown>;
        if (!freshUserSnap.exists || hasApprovedAvatar(freshUser.avatar)) {
          throw new HttpsError("failed-precondition", "avatar_source_locked");
        }
        const freshCurrentJobId = String(
          freshPrivate.currentAvatarJobId ?? "",
        ).trim();
        if (freshCurrentJobId) {
          if (
            freshCurrentJobId === jobId &&
            freshJobSnap.exists &&
            freshJobSnap.get("uploadClientRequestId") === metadata.clientRequestId
          ) {
            duplicate = true;
            persistedSelectionVersion = Number(
              freshJobSnap.get("avatarSourceSelectionVersion") ?? 0,
            );
            shouldEnqueue = shouldDispatchPendingSourceSetJob(
              (freshJobSnap.data() ?? {}) as Record<string, unknown>,
            );
            return;
          }
          throw new HttpsError("failed-precondition", "avatar_source_locked");
        }
        if (hasActiveAvatarWorkflowState(freshUser.avatar)) {
          throw new HttpsError("failed-precondition", "avatar_source_locked");
        }

        persistedSelectionVersion = sourceSelectionVersion(
          freshPrivate.avatarSourceSelectionVersion,
        );
        shouldEnqueue = true;
        const pendingJob = buildPendingAvatarSourceJob({
          uid,
          jobId,
          clientRequestId: metadata.clientRequestId,
          selectionVersion: persistedSelectionVersion,
          candidates: prepared,
          avatarPresentationGender: avatarGender,
          sourceSelectionMode: selectionMode,
        });
        const updatedSources = replacePreparedSources(
          sourcePhotos(freshPrivate.sourcePhotos),
          prepared,
          metadata,
        );
        transaction.set(
          privateRef,
          {
            ...buildPrivateMediaPayload(updatedSources, {
              currentAvatarJobId: jobId,
              avatarSourceSelectionVersion: persistedSelectionVersion,
              consentPurposes: metadata.consentPurposes,
              chatPartnerRealPhotoDisclosure:
                data.chatPartnerRealPhotoDisclosure === true,
            }),
            avatarSourceSelection: {
              status: "pending",
              selectorVersion: "avatar_source_quality_selector_v1",
              evaluatedCount: 0,
            },
          },
          { merge: true },
        );
        transaction.set(jobRef, {
          ...pendingJob,
          modelId: AVATAR_MODEL_ID,
          jobType: "avatar_generation",
          schemaVersion: JOB_SCHEMA_VERSION,
          consentVersion: metadata.consentVersion,
          consentPurposes: metadata.consentPurposes,
          avatarSourceSelectionVersion: persistedSelectionVersion,
          chatPartnerRealPhotoDisclosure:
            data.chatPartnerRealPhotoDisclosure === true,
          model: {
            provider: "azure",
            modelId: AVATAR_MODEL_ID,
            version: "gpt-image-2",
          },
          generationBackend: AVATAR_MODEL_ID,
          provenance: {
            provider: "azure",
            generationBackend: AVATAR_MODEL_ID,
            modelFamily: "gpt-image-2",
            promptVersion: "avatar_general_prompt_v1",
            sourceInputMode: "storage_normalized_original_direct",
            uploadNormalization: "onboarding_normalized_jpeg_v1",
            preGenerationTransform: "none",
            legacyTraitExtraction: false,
            legacyReferencePreprocessing: false,
            legacyFlux: false,
          },
          privacyMode: {
            preserveBroadCues: true,
            preserveExactIdentity: false,
            beautification: 0,
            target: "medium_resemblance_not_biometric_copy",
          },
          idempotencyKey: `${uid}:${jobId}:avatar_generation_source_set_v1`,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
        transaction.update(userRef, {
          profileImageMode: "avatar",
          "avatar.status": "queued",
          "avatar.updatedAt": FieldValue.serverTimestamp(),
          "onboarding.avatarGenerationJobId": jobId,
          "onboarding.avatarSourceSelectionVersion": persistedSelectionVersion,
          "onboarding.sourcePhotoUploadStatus": "avatar_source_selection_pending",
          "onboarding.sourcePhotoUploadCount": prepared.length,
          "onboarding.sourcePhotoLastQueuedAt": FieldValue.serverTimestamp(),
          "onboarding.photoUrls": FieldValue.delete(),
          photoUrls: FieldValue.delete(),
          updatedAt: FieldValue.serverTimestamp(),
        });
      });

      if (shouldEnqueue) {
        const queuePayload: AvatarSourceSetQueuePayload = {
          jobId,
          uid,
          sourcePhotoIds: prepared.map((item) => item.photoId),
          sourcePhotoRefs: prepared.map((item) => item.gcsUri),
          sourcePhotoObjectGenerations: prepared.map(
            (item) => item.objectGeneration,
          ),
          sourceSelectionMode: selectionMode,
          consentPurposes: metadata.consentPurposes,
          avatarPresentationGender: avatarGender,
          candidateCount: 2,
          modelId: AVATAR_MODEL_ID,
          jobType: "avatar_generation",
          schemaVersion: JOB_SCHEMA_VERSION,
          idempotencyKey: `${uid}:${jobId}:avatar_generation_source_set_v1`,
        };
        try {
          const queue = await deps.enqueueAvatar(queuePayload);
          await jobRef.set(
            {
              status: "queued",
              queueMode: queue.mode,
              queueStatus: queue.status,
              errorCode: FieldValue.delete(),
              retryable: FieldValue.delete(),
              queueUpdatedAt: FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
        } catch (error) {
          // Typed, client-safe reason. No provider state is touched: the job
          // never left Functions, so generationClaim/providerUsage stay absent.
          logger.error("Avatar source-set enqueue failed", {
            jobIdHash: digest(jobId).slice(0, 12),
            error: error instanceof Error ? error.message : String(error),
          });
          await jobRef.set(
            {
              status: "retryable_failed",
              errorCode: "avatar_queue_dispatch_failed",
              retryable: true,
              queueStatus: "dispatch_failed",
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          await userRef.set(
            {
              "avatar.status": "retryable_failed",
              "avatar.errorCode": "avatar_queue_dispatch_failed",
              "avatar.updatedAt": FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true },
          );
          if (error instanceof HttpsError) throw error;
          throw new HttpsError(
            "internal",
            "avatar_queue_dispatch_failed",
          );
        }
      }

      return {
        jobId,
        avatarStatus: "queued",
        message: "avatar_generation_queued",
        duplicate,
        sourceSelectionVersion: persistedSelectionVersion,
        clipRecommendation,
      };
  }
}
