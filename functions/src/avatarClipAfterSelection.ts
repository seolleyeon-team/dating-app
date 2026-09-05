/**
 * CLIP recommendation embedding, decoupled from avatar generation admission.
 *
 * Product decision (2026-09-05): clipRecommendation consent is independent of
 * avatar admission. clipRecommendation=false must never reject generation;
 * clipRecommendation=true must run the existing CLIP flow idempotently, and
 * the failure of either concern must not block the other.
 *
 * The source-set admission cannot enqueue CLIP at submit time because the
 * embedding must be computed on the SELECTED source, which the worker chooses
 * later. This trigger fires on the pending -> selected transition of
 * avatarJobs/{jobId}.sourceSelection and enqueues the existing CLIP payload.
 *
 * Trigger graph: watches avatarJobs, writes NOTHING to Firestore. Idempotent
 * via the deterministic Cloud Task name derived from the CLIP idempotencyKey.
 */
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";

import {
  buildClipPayload,
  clipEmbeddingQueueEnabled,
  enqueueQueuePayload,
  requireAvatarConsentPurposes,
  type QueueDispatchPayload,
} from "./avatarMedia";

type RecordData = Record<string, unknown>;

function readMap(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordData)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export type ClipAfterSelectionPlan =
  | { action: "skip"; reason: string }
  | { action: "enqueue"; payload: QueueDispatchPayload };

export function planClipEnqueueAfterSelection(params: {
  beforeData: RecordData | null;
  afterData: RecordData | null;
}): ClipAfterSelectionPlan {
  const after = params.afterData;
  if (!after) return { action: "skip", reason: "job_deleted" };

  const afterSelection = asString(readMap(after.sourceSelection).status).toLowerCase();
  const beforeSelection = asString(
    readMap(params.beforeData?.sourceSelection).status,
  ).toLowerCase();
  if (afterSelection !== "selected") {
    return { action: "skip", reason: "source_not_selected" };
  }
  if (beforeSelection === "selected") {
    // Semantic no-op gate: only the transition into "selected" counts.
    return { action: "skip", reason: "already_selected" };
  }

  let consent;
  try {
    consent = requireAvatarConsentPurposes(after.consentPurposes);
  } catch {
    return { action: "skip", reason: "consent_missing" };
  }
  if (!consent.clipRecommendation) {
    return { action: "skip", reason: "clip_not_consented" };
  }

  const uid = asString(after.uid);
  const selected = readMap(after.selectedSource);
  const photoId = asString(selected.photoId);
  const gcsUri = asString(selected.gcsUri);
  if (!uid || !photoId || !gcsUri.startsWith("gs://")) {
    return { action: "skip", reason: "selected_source_incomplete" };
  }

  const payload = buildClipPayload(uid, photoId, gcsUri, consent);
  if (!payload) return { action: "skip", reason: "clip_not_consented" };
  return { action: "enqueue", payload };
}

export const AVATAR_CLIP_AFTER_SELECTION_TRIGGER_OPTIONS = {
  document: "avatarJobs/{jobId}",
  retry: true,
} as const;

export function createAvatarClipAfterSelectionTrigger(
  enqueue: (
    payload: QueueDispatchPayload,
  ) => Promise<Record<string, unknown>> = (payload) =>
    enqueueQueuePayload("clip_embedding", payload),
) {
  return onDocumentWritten(
    AVATAR_CLIP_AFTER_SELECTION_TRIGGER_OPTIONS,
    async (event) => {
      const after = event.data?.after;
      const before = event.data?.before;
      const plan = planClipEnqueueAfterSelection({
        beforeData: before?.exists ? readMap(before.data()) : null,
        afterData: after?.exists ? readMap(after.data()) : null,
      });
      if (plan.action !== "enqueue") return;
      if (!clipEmbeddingQueueEnabled()) {
        logger.info("CLIP enqueue after selection skipped by configuration", {
          jobId: asString(event.params.jobId),
        });
        return;
      }
      const result = await enqueue(plan.payload);
      logger.info("CLIP embedding enqueued after source selection", {
        jobId: asString(event.params.jobId),
        status: asString(readMap(result).status),
      });
    },
  );
}
