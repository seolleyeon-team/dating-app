import { createHash, randomBytes } from "crypto";
import { getStorage } from "firebase-admin/storage";
import {
  FieldValue,
  Timestamp,
  type Firestore,
} from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";

const DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos";
const SOURCE_RETENTION_STATE_COLLECTION = "avatarSourceRetentionStates";
const SOURCE_RETENTION_EVENTS_COLLECTION = "avatarSourceRetentionEvents";
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

function isIrreversibleSourceDeletionTerminal(jobData: RecordData): boolean {
  const status = asString(jobData.status).toLowerCase();
  if (["terminal_failed", "cancelled", "canceled"].includes(status)) return true;
  if (status === "failed") return jobData.retryable !== true;
  if (["approved", "completed"].includes(status)) {
    return (
      jobData.sourceDeletionIrreversible === true ||
      jobData.sourceCleanupIrreversible === true
    );
  }
  return false;
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
}): boolean {
  if (!params.afterData || !isIrreversibleSourceDeletionTerminal(params.afterData)) {
    return false;
  }
  if (!params.beforeData) return true;
  return !isIrreversibleSourceDeletionTerminal(params.beforeData);
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
}): AvatarSourceRetentionDecision {
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
  if (!isIrreversibleSourceDeletionTerminal(params.jobData)) {
    return { action: "skip", reason: "avatar_not_irreversible_terminal" };
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
  const now = Timestamp.now();

  return params.firestore.runTransaction(async (tx) => {
    const [privateSnap, jobSnap, clipSnap] = await Promise.all([
      tx.get(privateRef),
      tx.get(jobRef),
      tx.get(clipRef),
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
    });
    if (decision.action !== "claim") return null;

    const stateId = avatarSourceRetentionStateId(params.uid, decision.photoId);
    const stateRef = params.firestore.collection(SOURCE_RETENTION_STATE_COLLECTION).doc(stateId);
    const stateSnap = await tx.get(stateRef);
    const stateData = readMap(stateSnap.data());
    const existingStatus = asString(stateData.status);
    if (existingStatus === "deleted") return null;
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
}): Promise<"claimed" | "skipped"> {
  const claim = await claimPendingSourceDeletion(params);
  if (!claim) return "skipped";
  const valid = await preDeleteRevalidateClaim({ firestore: params.firestore, claim });
  if (!valid) return "skipped";
  try {
    for (const ref of claim.refs) {
      await getStorage().bucket(ref.bucket).file(ref.path).delete({ ignoreNotFound: true });
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

export async function recoverAvatarSourceRetentionDeletions(params: {
  firestore: Firestore;
  limit?: number;
}): Promise<number> {
  const now = Timestamp.now();
  const snap = await params.firestore
    .collection(SOURCE_RETENTION_STATE_COLLECTION)
    .where("status", "in", ["deleting", "retryable_failed", "stale"])
    .limit(params.limit ?? 25)
    .get();
  let claimed = 0;
  for (const doc of snap.docs) {
    const data = readMap(doc.data());
    if (!dueForRetry(data, now)) continue;
    const uid = asString(data.uid);
    const jobId = asString(data.jobId);
    if (!uid || !jobId) continue;
    const result = await executeAvatarSourceRetention({
      firestore: params.firestore,
      uid,
      jobId,
      trigger: "avatar_job",
    });
    if (result === "claimed") claimed += 1;
  }
  return claimed;
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
  return onSchedule("every 15 minutes", async () => {
    const recovered = await recoverAvatarSourceRetentionDeletions({ firestore });
    if (recovered > 0) {
      logger.info("Avatar source retention recovery claimed deletions", { recovered });
    }
  });
}
