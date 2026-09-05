import { HttpsError } from "firebase-functions/v2/https";

import {
  enqueueQueuePayload,
  type QueueDispatchPayload,
} from "./avatarMedia";

/// Source-set generation payload. Beyond the shared dispatch fields it carries
/// the full candidate set and the selection mode the worker must honour.
export type AvatarSourceSetQueuePayload = QueueDispatchPayload & {
  jobId: string;
  sourcePhotoObjectGenerations: string[];
  sourceSelectionMode: "quality_selector_v1" | "legacy_first_photo";
  consentPurposes: {
    avatarGeneration: true;
    clipRecommendation: boolean;
    sourcePhotoRetention: boolean;
  };
  avatarPresentationGender: string;
  candidateCount: 2;
  modelId: "azure_gpt_image_2";
  jobType: "avatar_generation";
  schemaVersion: "avatar_job_v1";
};

/// Structural contract the payload must satisfy before it may be dispatched.
/// Kept pure so the privacy/idempotency rules are unit-testable.
export function assertAvatarSourceSetQueuePayload(
  payload: AvatarSourceSetQueuePayload,
): void {
  const count = payload.sourcePhotoIds.length;
  if (
    count < 1 ||
    count > 6 ||
    payload.sourcePhotoRefs.length !== count ||
    payload.sourcePhotoObjectGenerations.length !== count
  ) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_source_set_payload_invalid",
    );
  }
  if (new Set(payload.sourcePhotoIds).size !== count) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_source_set_payload_invalid",
    );
  }
  if (!payload.idempotencyKey.trim()) {
    throw new HttpsError(
      "failed-precondition",
      "avatar_source_set_payload_invalid",
    );
  }
  for (const generation of payload.sourcePhotoObjectGenerations) {
    if (!/^[1-9][0-9]{0,30}$/.test(generation)) {
      throw new HttpsError(
        "failed-precondition",
        "avatar_source_set_payload_invalid",
      );
    }
  }
}

/// Dispatches through the SAME helper the legacy path uses. Queue name, target
/// URL, OIDC token, dispatch deadline, deterministic task name, ALREADY_EXISTS
/// idempotency, dry_run/pubsub modes and log redaction are therefore identical
/// by construction rather than by copy.
export async function enqueueAvatarSourceSetJob(
  payload: AvatarSourceSetQueuePayload,
): Promise<Record<string, unknown>> {
  assertAvatarSourceSetQueuePayload(payload);
  return enqueueQueuePayload("avatar_generation", payload);
}
