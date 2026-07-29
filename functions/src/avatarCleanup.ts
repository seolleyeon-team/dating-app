import { createHash } from "crypto";
import { getAuth } from "firebase-admin/auth";
import { FieldPath, FieldValue, type Firestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";
import {
  HttpsError,
  onCall,
  type CallableOptions,
  type CallableRequest,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import {
  emptySocialCounts,
  emptySocialDocs,
  loadAccountDeletionSocialDocs,
  planAccountDeletionSocialOperations,
  applySocialCleanupOperation,
  socialCountsFromDocs,
  type AccountDeletionSocialDocs,
  type SocialCleanupOperation,
} from "./accountDeletionSocialCleanup";

const DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos";
const DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp";
const DEFAULT_APPROVED_AVATAR_BUCKET = "seolleyeon-approved-avatars";
const DEFAULT_CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-chat-profile-photos";
const CLEANUP_REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$/;
const ALLOWED_REASONS = new Set(["consent_withdrawal", "account_deletion"]);
const ACTIVE_JOB_STATUSES = new Set([
  "queued",
  "running",
  "qa_pending",
  "preview_ready",
  "needs_review",
  "no_previewable",
  "no_previewable_candidates",
  "retryable_failed",
  "pending",
  "generating",
]);

export const CLEANUP_AVATAR_MEDIA_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 120,
  memory: "512MiB",
  invoker: "public",
  enforceAppCheck: true,
};

export type AvatarCleanupReason = "consent_withdrawal" | "account_deletion";

export type AvatarCleanupCounts = {
  storageObjectsDeleted: number;
  candidatesSanitized: number;
  jobsCancelled: number;
  privateMediaSanitized: number;
  usersSanitized: number;
  clipEmbeddingsDeleted: number;
  cleanupRequestsUpdated: number;
  publicUsersDeleted: number;
  authUsersDeleted: number;
  skippedUnsafeRefs: number;
  userPrivateDeleted: number;
  phoneHashIndexDeleted: number;
  deviceTokensDeleted: number;
  notificationsDeleted: number;
  contactBlockedHashesDeleted: number;
  contactBlockedHashIndexOwnersDeleted: number;
  blockTargetsDeleted: number;
  reverseBlockTargetsDeleted: number;
  interactionsDeleted: number;
  asksDeleted: number;
  friendshipsDeleted: number;
  friendEdgesDeleted: number;
  matchesEnded: number;
  chatRoomsClosed: number;
  recEventsDeleted: number;
  bambooPostsSoftDeleted: number;
  friendInvitesScrubbed: number;
  eventTeamMembershipsRemoved: number;
};

export type AccountDeletionDocs = {
  phoneHash: string | null;
  deviceTokenIds: string[];
  notificationIds: string[];
  contactBlockedHashIds: string[];
  blockTargetIds: string[];
  reverseBlockViewerUids: string[];
  social: AccountDeletionSocialDocs;
};

export type AvatarCleanupResponse = {
  status: "completed";
  counts: AvatarCleanupCounts;
};

type ResolvedCleanupUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
};

type ResolveCleanupUser = (
  auth: CallableRequest<unknown>["auth"],
) => Promise<ResolvedCleanupUser>;

type GcsRef = {
  bucket: string;
  path: string;
};

type CleanupDocs = {
  userData: Record<string, unknown>;
  privateMediaData: Record<string, unknown>;
  candidateDocs: Array<{ id: string; data: Record<string, unknown> }>;
  jobDocs: Array<{ id: string; data: Record<string, unknown> }>;
  existingRequest?: Record<string, unknown> | null;
  accountDeletionDocs: AccountDeletionDocs;
};

export type CleanupOperation =
  | { kind: "markPending"; requestId: string; reason: AvatarCleanupReason }
  | { kind: "deleteStorage"; ref: GcsRef }
  | { kind: "sanitizeCandidate"; id: string; reason: AvatarCleanupReason }
  | { kind: "cancelJob"; id: string; reason: AvatarCleanupReason }
  | { kind: "sanitizePrivateMedia"; reason: AvatarCleanupReason }
  | { kind: "deleteClipEmbedding" }
  | { kind: "sanitizeUser"; reason: AvatarCleanupReason }
  | { kind: "writeAudit"; reason: AvatarCleanupReason; counts: AvatarCleanupCounts }
  | { kind: "markCompleted"; requestId: string; response: AvatarCleanupResponse }
  | { kind: "deletePublicUser" }
  | { kind: "deleteAuthUser" }
  | { kind: "deleteUserPrivate" }
  | { kind: "deletePhoneHashIndex"; phoneHash: string }
  | { kind: "deleteDeviceToken"; tokenId: string }
  | { kind: "deleteNotification"; notificationId: string }
  | { kind: "deleteContactBlockedHash"; phoneHash: string }
  | { kind: "deleteContactBlockedHashIndexOwner"; phoneHash: string }
  | { kind: "deleteBlockTarget"; targetUid: string }
  | { kind: "deleteReverseBlockTarget"; viewerUid: string }
  | SocialCleanupOperation;

export type CleanupExecutor = {
  load(uid: string, requestId: string): Promise<CleanupDocs>;
  apply(operation: CleanupOperation): Promise<void>;
};

function envValue(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

function sourcePhotoBucket(): string {
  return envValue("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET);
}

function avatarTempBucket(): string {
  return envValue("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET);
}

function approvedAvatarBucket(): string {
  return envValue("APPROVED_AVATAR_BUCKET", DEFAULT_APPROVED_AVATAR_BUCKET);
}

function chatProfilePhotoBucket(): string {
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

function parseGcsUri(value: string): GcsRef | null {
  const match = value.match(/^(?:gs|gcs):\/\/([^/]+)\/(.+)$/);
  if (!match) return null;
  const bucket = match[1].trim();
  const path = match[2].trim();
  if (!bucket || !path || path.startsWith("/") || path.includes("..")) {
    return null;
  }
  return { bucket, path };
}

function gcsRefFromFields(
  value: unknown,
  bucketField = "storageBucket",
  pathField = "storagePath",
): GcsRef | null {
  const data = readMap(value);
  const gcsUri = asString(data.gcsUri);
  if (gcsUri) return parseGcsUri(gcsUri);
  const bucket = asString(data[bucketField]);
  const path = asString(data[pathField]);
  if (!bucket || !path || path.startsWith("/") || path.includes("..")) {
    return null;
  }
  return { bucket, path };
}

export function isUidBoundCleanupRef(ref: GcsRef, uid: string): boolean {
  const safeUid = requirePathSegment(uid, "uid");
  const allowed: Array<{ bucket: string; prefix: string }> = [
    { bucket: sourcePhotoBucket(), prefix: `users/${safeUid}/source/` },
    { bucket: avatarTempBucket(), prefix: `users/${safeUid}/candidates/` },
    { bucket: avatarTempBucket(), prefix: `users/${safeUid}/jobs/` },
    { bucket: approvedAvatarBucket(), prefix: `users/${safeUid}/avatar/` },
    { bucket: chatProfilePhotoBucket(), prefix: `users/${safeUid}/chat-profile/` },
  ];
  return allowed.some(
    (item) => ref.bucket === item.bucket && ref.path.startsWith(item.prefix),
  );
}

function emptyCounts(): AvatarCleanupCounts {
  return {
    storageObjectsDeleted: 0,
    candidatesSanitized: 0,
    jobsCancelled: 0,
    privateMediaSanitized: 0,
    usersSanitized: 0,
    clipEmbeddingsDeleted: 0,
    cleanupRequestsUpdated: 0,
    publicUsersDeleted: 0,
    authUsersDeleted: 0,
    skippedUnsafeRefs: 0,
    userPrivateDeleted: 0,
    phoneHashIndexDeleted: 0,
    deviceTokensDeleted: 0,
    notificationsDeleted: 0,
    contactBlockedHashesDeleted: 0,
    contactBlockedHashIndexOwnersDeleted: 0,
    blockTargetsDeleted: 0,
    reverseBlockTargetsDeleted: 0,
    ...emptySocialCounts(),
  };
}

const BLOCKS_TARGET_PATH = /^blocks\/([^/]+)\/targets\/([^/]+)$/;

export function isBlocksTargetRefPath(path: string, targetUid: string): boolean {
  const match = path.match(BLOCKS_TARGET_PATH);
  return match !== null && match[2] === targetUid;
}

export function accountDeletionDocsFromParts(
  parts: Partial<AccountDeletionDocs> = {},
): AccountDeletionDocs {
  return {
    phoneHash: parts.phoneHash ?? null,
    deviceTokenIds: parts.deviceTokenIds ?? [],
    notificationIds: parts.notificationIds ?? [],
    contactBlockedHashIds: parts.contactBlockedHashIds ?? [],
    blockTargetIds: parts.blockTargetIds ?? [],
    reverseBlockViewerUids: parts.reverseBlockViewerUids ?? [],
    social: parts.social ?? emptySocialDocs(),
  };
}

export function planAccountDeletionPiiOperations(params: {
  uid: string;
  docs: AccountDeletionDocs;
}): CleanupOperation[] {
  const uid = requirePathSegment(params.uid, "uid");
  const docs = params.docs;
  const operations: CleanupOperation[] = [];

  for (const tokenId of docs.deviceTokenIds) {
    operations.push({ kind: "deleteDeviceToken", tokenId });
  }
  for (const notificationId of docs.notificationIds) {
    operations.push({ kind: "deleteNotification", notificationId });
  }
  for (const phoneHash of docs.contactBlockedHashIds) {
    operations.push({ kind: "deleteContactBlockedHash", phoneHash });
    operations.push({
      kind: "deleteContactBlockedHashIndexOwner",
      phoneHash,
    });
  }
  if (docs.phoneHash) {
    operations.push({ kind: "deletePhoneHashIndex", phoneHash: docs.phoneHash });
  }
  operations.push({ kind: "deleteUserPrivate" });
  for (const targetUid of docs.blockTargetIds) {
    operations.push({ kind: "deleteBlockTarget", targetUid });
  }
  for (const viewerUid of docs.reverseBlockViewerUids) {
    if (viewerUid === uid) continue;
    operations.push({ kind: "deleteReverseBlockTarget", viewerUid });
  }
  operations.push(
    ...planAccountDeletionSocialOperations({ uid, docs: docs.social }),
  );

  return operations;
}

function applyAccountDeletionCounts(
  counts: AvatarCleanupCounts,
  uid: string,
  docs: AccountDeletionDocs,
): void {
  counts.userPrivateDeleted = 1;
  counts.phoneHashIndexDeleted = docs.phoneHash ? 1 : 0;
  counts.deviceTokensDeleted = docs.deviceTokenIds.length;
  counts.notificationsDeleted = docs.notificationIds.length;
  counts.contactBlockedHashesDeleted = docs.contactBlockedHashIds.length;
  counts.contactBlockedHashIndexOwnersDeleted = docs.contactBlockedHashIds.length;
  counts.blockTargetsDeleted = docs.blockTargetIds.length;
  counts.reverseBlockTargetsDeleted = docs.reverseBlockViewerUids.filter(
    (viewerUid) => viewerUid !== uid,
  ).length;
  Object.assign(counts, socialCountsFromDocs(docs.social));
}

function requestDocId(uid: string, clientRequestId: string): string {
  return createHash("sha256")
    .update(`${uid}:${clientRequestId}:avatar_cleanup_v1`)
    .digest("hex")
    .slice(0, 32);
}

function uidHash(uid: string): string {
  return createHash("sha256").update(uid).digest("hex").slice(0, 16);
}

function safeErrorLogFields(error: unknown): {
  errorType: string;
  errorCode?: string | number;
} {
  const errorCode = isRecord(error) ? error.code : undefined;
  return {
    errorType:
      error instanceof HttpsError
        ? "HttpsError"
        : error instanceof Error
          ? "Error"
          : typeof error,
    ...(typeof errorCode === "string" || typeof errorCode === "number"
      ? { errorCode }
      : {}),
  };
}

export function requireAvatarCleanupRequest(value: unknown): {
  clientRequestId: string;
  reason: AvatarCleanupReason;
} {
  const data = readMap(value);
  const clientRequestId = asString(data.clientRequestId);
  const reason = asString(data.reason);
  if (!CLEANUP_REQUEST_ID.test(clientRequestId)) {
    throw new HttpsError("invalid-argument", "avatar_cleanup_request_invalid");
  }
  if (!ALLOWED_REASONS.has(reason)) {
    throw new HttpsError("invalid-argument", "avatar_cleanup_reason_invalid");
  }
  return {
    clientRequestId,
    reason: reason as AvatarCleanupReason,
  };
}

function uniqueUidBoundRefs(
  uid: string,
  refs: Array<GcsRef | null>,
): { refs: GcsRef[]; skippedUnsafeRefs: number } {
  const seen = new Set<string>();
  const safeRefs: GcsRef[] = [];
  let skippedUnsafeRefs = 0;
  for (const ref of refs) {
    if (!ref) continue;
    if (!isUidBoundCleanupRef(ref, uid)) {
      skippedUnsafeRefs += 1;
      continue;
    }
    const key = `${ref.bucket}/${ref.path}`;
    if (!seen.has(key)) {
      seen.add(key);
      safeRefs.push(ref);
    }
  }
  return { refs: safeRefs, skippedUnsafeRefs };
}

function collectCleanupRefs(uid: string, docs: CleanupDocs): {
  refs: GcsRef[];
  skippedUnsafeRefs: number;
} {
  const refs: Array<GcsRef | null> = [];
  const sourcePhotos = Array.isArray(docs.privateMediaData.sourcePhotos)
    ? docs.privateMediaData.sourcePhotos
    : [];
  for (const entry of sourcePhotos) {
    refs.push(gcsRefFromFields(entry));
  }
  refs.push(gcsRefFromFields(docs.privateMediaData.chatRealPhoto));

  const avatar = readMap(docs.userData.avatar);
  const approvedAvatarStoragePath = asString(avatar.approvedAvatarStoragePath);
  if (approvedAvatarStoragePath) {
    refs.push(parseGcsUri(approvedAvatarStoragePath));
  }

  for (const candidate of docs.candidateDocs) {
    const imageRef = asString(candidate.data.imageRef);
    if (imageRef) refs.push(parseGcsUri(imageRef));
  }
  return uniqueUidBoundRefs(uid, refs);
}

export function planAvatarCleanup(params: {
  uid: string;
  requestId: string;
  reason: AvatarCleanupReason;
  docs: CleanupDocs;
}): { duplicate: boolean; response?: AvatarCleanupResponse; operations: CleanupOperation[] } {
  const existingStatus = asString(params.docs.existingRequest?.status);
  const existingReason = asString(params.docs.existingRequest?.reason);
  if (existingReason && existingReason !== params.reason) {
    throw new HttpsError("already-exists", "avatar_cleanup_request_conflict");
  }
  if (existingStatus === "completed") {
    const existingResponse = readMap(params.docs.existingRequest?.response);
    return {
      duplicate: true,
      response: {
        status: "completed",
        counts: { ...emptyCounts(), ...readMap(existingResponse.counts) },
      },
      operations: [],
    };
  }

  const counts = emptyCounts();
  const { refs, skippedUnsafeRefs } = collectCleanupRefs(params.uid, params.docs);
  counts.skippedUnsafeRefs = skippedUnsafeRefs;
  counts.storageObjectsDeleted = refs.length;
  counts.candidatesSanitized = params.docs.candidateDocs.length;
  counts.jobsCancelled = params.docs.jobDocs.filter((job) =>
    ACTIVE_JOB_STATUSES.has(asString(job.data.status).toLowerCase()),
  ).length;
  counts.privateMediaSanitized = 1;
  counts.usersSanitized = 1;
  counts.clipEmbeddingsDeleted = 1;
  counts.cleanupRequestsUpdated = 1;
  if (params.reason === "account_deletion") {
    counts.publicUsersDeleted = 1;
    counts.authUsersDeleted = 1;
    applyAccountDeletionCounts(counts, params.uid, params.docs.accountDeletionDocs);
  }

  const accountDeletionPiiOperations =
    params.reason === "account_deletion"
      ? planAccountDeletionPiiOperations({
          uid: params.uid,
          docs: params.docs.accountDeletionDocs,
        })
      : [];

  const response: AvatarCleanupResponse = {
    status: "completed",
    counts,
  };
  return {
    duplicate: false,
    response,
    operations: [
      { kind: "markPending", requestId: params.requestId, reason: params.reason },
      ...params.docs.jobDocs
        .filter((job) => ACTIVE_JOB_STATUSES.has(asString(job.data.status).toLowerCase()))
        .map((job): CleanupOperation => ({
          kind: "cancelJob",
          id: job.id,
          reason: params.reason,
        })),
      ...refs.map((ref): CleanupOperation => ({ kind: "deleteStorage", ref })),
      ...params.docs.candidateDocs.map((candidate): CleanupOperation => ({
        kind: "sanitizeCandidate",
        id: candidate.id,
        reason: params.reason,
      })),
      { kind: "sanitizePrivateMedia", reason: params.reason },
      { kind: "deleteClipEmbedding" },
      { kind: "sanitizeUser", reason: params.reason },
      { kind: "writeAudit", reason: params.reason, counts },
      ...accountDeletionPiiOperations,
      ...(params.reason === "account_deletion"
        ? ([{ kind: "deletePublicUser" }, { kind: "deleteAuthUser" }] as CleanupOperation[])
        : []),
      { kind: "markCompleted", requestId: params.requestId, response },
    ],
  };
}

export async function executeAvatarCleanup(params: {
  uid: string;
  clientRequestId: string;
  reason: AvatarCleanupReason;
  executor: CleanupExecutor;
}): Promise<AvatarCleanupResponse> {
  const uid = requirePathSegment(params.uid, "uid");
  const requestId = requestDocId(uid, params.clientRequestId);
  const docs = await params.executor.load(uid, requestId);
  const plan = planAvatarCleanup({
    uid,
    requestId,
    reason: params.reason,
    docs,
  });
  if (plan.duplicate && plan.response) return plan.response;
  for (const operation of plan.operations) {
    await params.executor.apply(operation);
  }
  if (!plan.response) {
    throw new HttpsError("internal", "avatar_cleanup_plan_empty");
  }
  return plan.response;
}

export async function loadAccountDeletionDocs(
  firestore: Firestore,
  uid: string,
): Promise<AccountDeletionDocs> {
  const safeUid = requirePathSegment(uid, "uid");
  const [
    userPrivateSnap,
    deviceTokensSnap,
    notificationsSnap,
    contactBlockedHashesSnap,
    blockTargetsSnap,
    reverseBlockTargetsSnap,
    social,
  ] = await Promise.all([
    firestore.collection("userPrivate").doc(safeUid).get(),
    firestore.collection("users").doc(safeUid).collection("deviceTokens").get(),
    firestore.collection("users").doc(safeUid).collection("notifications").get(),
    firestore
      .collection("users")
      .doc(safeUid)
      .collection("contactBlockedHashes")
      .get(),
    firestore.collection("blocks").doc(safeUid).collection("targets").get(),
    firestore
      .collectionGroup("targets")
      .where(FieldPath.documentId(), "==", safeUid)
      .get(),
    loadAccountDeletionSocialDocs(firestore, safeUid),
  ]);

  const reverseBlockViewerUids = reverseBlockTargetsSnap.docs
    .filter((doc) => isBlocksTargetRefPath(doc.ref.path, safeUid))
    .map((doc) => {
      const match = doc.ref.path.match(BLOCKS_TARGET_PATH);
      return match?.[1] ?? "";
    })
    .filter((viewerUid) => viewerUid.length > 0);

  return accountDeletionDocsFromParts({
    phoneHash: asString(userPrivateSnap.data()?.phoneHash) || null,
    deviceTokenIds: deviceTokensSnap.docs.map((doc) => doc.id),
    notificationIds: notificationsSnap.docs.map((doc) => doc.id),
    contactBlockedHashIds: contactBlockedHashesSnap.docs.map((doc) => doc.id),
    blockTargetIds: blockTargetsSnap.docs.map((doc) => doc.id),
    reverseBlockViewerUids,
    social,
  });
}

function firestoreExecutor(firestore: Firestore, uid: string): CleanupExecutor {
  return {
    async load(loadUid: string, requestId: string): Promise<CleanupDocs> {
      const [userSnap, privateSnap, candidateQuery, jobQuery, requestSnap, accountDeletionDocs] =
        await Promise.all([
          firestore.collection("users").doc(loadUid).get(),
          firestore.collection("userPrivateMedia").doc(loadUid).get(),
          firestore
            .collection("avatarCandidates")
            .where("uid", "==", loadUid)
            .get(),
          firestore.collection("avatarJobs").where("uid", "==", loadUid).get(),
          firestore.collection("avatarMediaCleanupRequests").doc(requestId).get(),
          loadAccountDeletionDocs(firestore, loadUid),
        ]);
      return {
        userData: (userSnap.data() ?? {}) as Record<string, unknown>,
        privateMediaData: (privateSnap.data() ?? {}) as Record<string, unknown>,
        candidateDocs: candidateQuery.docs.map((doc) => ({
          id: doc.id,
          data: (doc.data() ?? {}) as Record<string, unknown>,
        })),
        jobDocs: jobQuery.docs.map((doc) => ({
          id: doc.id,
          data: (doc.data() ?? {}) as Record<string, unknown>,
        })),
        existingRequest: requestSnap.exists
          ? ((requestSnap.data() ?? {}) as Record<string, unknown>)
          : null,
        accountDeletionDocs,
      };
    },
    async apply(operation: CleanupOperation): Promise<void> {
      const now = FieldValue.serverTimestamp();
      switch (operation.kind) {
        case "markPending":
          await firestore
            .collection("avatarMediaCleanupRequests")
            .doc(operation.requestId)
            .set(
              {
                uid,
                uidHash: uidHash(uid),
                reason: operation.reason,
                status: "pending",
                startedAt: now,
                updatedAt: now,
              },
              { merge: true },
            );
          return;
        case "deleteStorage":
          await getStorage()
            .bucket(operation.ref.bucket)
            .file(operation.ref.path)
            .delete({ ignoreNotFound: true });
          return;
        case "sanitizeCandidate":
          await firestore.collection("avatarCandidates").doc(operation.id).set(
            {
              status: "deleted",
              cleanupReason: operation.reason,
              imageRef: FieldValue.delete(),
              previewUrl: FieldValue.delete(),
              approvedAvatarUrl: FieldValue.delete(),
              approvedAvatarStoragePath: FieldValue.delete(),
              qa: {},
              imageDeletedAt: now,
              updatedAt: now,
            },
            { merge: true },
          );
          return;
        case "cancelJob":
          await firestore.collection("avatarJobs").doc(operation.id).set(
            {
              status: "cancelled",
              cleanupReason: operation.reason,
              sourcePhotoRefs: [],
              sourcePhotoIds: [],
              selectedCandidateId: FieldValue.delete(),
              updatedAt: now,
            },
            { merge: true },
          );
          return;
        case "sanitizePrivateMedia":
          await firestore.collection("userPrivateMedia").doc(uid).set(
            {
              sourcePhotos: [],
              currentAvatarSourcePhotoId: FieldValue.delete(),
              currentAvatarJobId: FieldValue.delete(),
              avatarSourceSelectionVersion: FieldValue.delete(),
              photoConsent: {
                avatarGeneration: false,
                clipRecommendation: false,
                profileDisplayOriginalPhoto: false,
                chatPartnerRealPhotoDisclosure: false,
                sourcePhotoRetention: false,
                withdrawnAt: now,
              },
              chatRealPhoto: {
                enabled: false,
                photoId: "",
                sourcePhotoId: "",
                deletedAt: now,
                updatedAt: now,
              },
              clip: {
                embeddingStatus: "deleted",
                sourcePhotoIds: [],
                deletedAt: now,
              },
              cleanupReason: operation.reason,
              updatedAt: now,
            },
            { merge: true },
          );
          return;
        case "deleteClipEmbedding":
          await firestore.collection("clipEmbeddings").doc(uid).delete();
          return;
        case "sanitizeUser":
          await firestore.collection("users").doc(uid).set(
            {
              profileImageMode: "avatar",
              profileImageUrl: FieldValue.delete(),
              photoUrls: FieldValue.delete(),
              avatar: {
                status: "none",
                approvedAvatarUrl: FieldValue.delete(),
                approvedAvatarStoragePath: FieldValue.delete(),
                avatarId: FieldValue.delete(),
                selectedCandidateId: FieldValue.delete(),
                sourceJobId: FieldValue.delete(),
                updatedAt: now,
              },
              onboarding: {
                avatarUrls: [],
                photoUrls: [],
                sourcePhotoUploadStatus: "avatar_media_cleaned",
              },
              cleanupReason: operation.reason,
              updatedAt: now,
            },
            { merge: true },
          );
          return;
        case "writeAudit":
          await firestore
            .collection("avatarMediaCleanupAudit")
            .doc(
              createHash("sha256")
                .update(`${uid}:${Date.now()}`)
                .digest("hex")
                .slice(0, 24),
            )
            .set({
              uidHash: uidHash(uid),
              reason: operation.reason,
              status: "completed",
              counts: operation.counts,
            });
          return;
        case "deletePublicUser":
          await firestore.collection("users").doc(uid).delete();
          return;
        case "deleteAuthUser":
          await getAuth().deleteUser(uid);
          return;
        case "deleteUserPrivate":
          await firestore.collection("userPrivate").doc(uid).delete();
          return;
        case "deletePhoneHashIndex": {
          const phoneHash = requirePathSegment(operation.phoneHash, "phoneHash");
          const indexRef = firestore.collection("phoneHashIndex").doc(phoneHash);
          const indexSnap = await indexRef.get();
          if (indexSnap.exists && asString(indexSnap.data()?.userId) === uid) {
            await indexRef.delete();
          }
          return;
        }
        case "deleteDeviceToken": {
          const tokenId = requirePathSegment(operation.tokenId, "tokenId");
          await firestore
            .collection("users")
            .doc(uid)
            .collection("deviceTokens")
            .doc(tokenId)
            .delete();
          return;
        }
        case "deleteNotification": {
          const notificationId = requirePathSegment(
            operation.notificationId,
            "notificationId",
          );
          await firestore
            .collection("users")
            .doc(uid)
            .collection("notifications")
            .doc(notificationId)
            .delete();
          return;
        }
        case "deleteContactBlockedHash": {
          const phoneHash = requirePathSegment(operation.phoneHash, "phoneHash");
          await firestore
            .collection("users")
            .doc(uid)
            .collection("contactBlockedHashes")
            .doc(phoneHash)
            .delete();
          return;
        }
        case "deleteContactBlockedHashIndexOwner": {
          const phoneHash = requirePathSegment(operation.phoneHash, "phoneHash");
          await firestore
            .collection("contactBlockedHashIndex")
            .doc(phoneHash)
            .collection("owners")
            .doc(uid)
            .delete();
          return;
        }
        case "deleteBlockTarget": {
          const targetUid = requirePathSegment(operation.targetUid, "targetUid");
          await firestore
            .collection("blocks")
            .doc(uid)
            .collection("targets")
            .doc(targetUid)
            .delete();
          return;
        }
        case "deleteReverseBlockTarget": {
          const viewerUid = requirePathSegment(operation.viewerUid, "viewerUid");
          if (viewerUid === uid) return;
          await firestore
            .collection("blocks")
            .doc(viewerUid)
            .collection("targets")
            .doc(uid)
            .delete();
          return;
        }
        case "deleteInteraction":
        case "deleteAsk":
        case "deleteFriendship":
        case "deleteFriendEdge":
        case "endMatch":
        case "closeChatRoom":
        case "deleteRecEvent":
        case "deleteRecEventsParent":
        case "softDeleteBambooPost":
        case "scrubFriendInvite":
        case "removeEventTeamMember":
          await applySocialCleanupOperation(firestore, uid, operation);
          return;
        case "markCompleted":
          await firestore
            .collection("avatarMediaCleanupRequests")
            .doc(operation.requestId)
            .set(
              {
                status: "completed",
                response: operation.response,
                completedAt: now,
                updatedAt: now,
              },
              { merge: true },
            );
          return;
      }
    },
  };
}

export function createCleanupAvatarMediaFunction(
  firestore: Firestore,
  resolveUser: ResolveCleanupUser,
) {
  return onCall(
    CLEANUP_AVATAR_MEDIA_CALLABLE_OPTIONS,
    async (request) => {
      const user = await resolveUser(request.auth);
      const uid = requirePathSegment(user.userId, "uid");
      const { clientRequestId, reason } = requireAvatarCleanupRequest(
        request.data,
      );
      try {
        return await executeAvatarCleanup({
          uid,
          clientRequestId,
          reason,
          executor: firestoreExecutor(firestore, uid),
        });
      } catch (error) {
        logger.error("Avatar media cleanup failed", {
          uidHash: uidHash(uid),
          reason,
          status: "failed",
          ...safeErrorLogFields(error),
        });
        if (error instanceof HttpsError) throw error;
        throw new HttpsError("internal", "avatar_cleanup_failed");
      }
    },
  );
}
