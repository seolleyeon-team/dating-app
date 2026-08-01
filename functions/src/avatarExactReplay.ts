import { createHash } from "node:crypto";
import { FieldValue } from "firebase-admin/firestore";

import {
  hasAvatarApprovalProtectedState,
  planAvatarSourceRetention,
} from "./avatarSourceRetention";

const REQUIRED_PROJECT_ID = "seolleyeon-final";
const EXACT_ROW_COUNT = 7;
const EXACT_CANDIDATE_COUNT = 56;
const SOURCE_BUCKET = "seolleyeon-final-private-source-photos";
const TEMP_BUCKET = "seolleyeon-final-avatar-temp";
const TERMINAL_REPLAY_STATUSES = new Set(["no_previewable", "no_previewable_candidates"]);

type RecordData = Record<string, unknown>;

type DocumentLike = {
  get(): Promise<{ exists: boolean; data(): RecordData | undefined }>;
  set(data: RecordData, options?: { merge?: boolean }): Promise<unknown>;
  update(data: RecordData): Promise<unknown>;
};

type QueryLike = {
  get(): Promise<{ docs: Array<{ id: string; data(): RecordData | undefined }> }>;
};

type CollectionLike = {
  doc(id: string): DocumentLike;
  where?(field: string, operator: "==", value: unknown): QueryLike;
};

export type ExactReplayTransaction = {
  get(ref: DocumentLike): Promise<{ exists: boolean; data(): RecordData | undefined }>;
  set(ref: DocumentLike, data: RecordData, options?: { merge?: boolean }): void;
};

export type ExactReplayFirestore = {
  collection(name: string): CollectionLike;
  runTransaction<T>(fn: (tx: ExactReplayTransaction) => Promise<T>): Promise<T>;
};

export type ExactReplayStorage = {
  objectExists(bucket: string, path: string): Promise<boolean>;
  deleteObject?(bucket: string, path: string): Promise<void>;
};

export type AvatarExactReplayRow = {
  rowIndex: number;
  uid: string;
  expectedUidHash: string;
  expectedJobIdHash: string;
  expectedSourcePhotoIdHash: string;
  expectedSourcePathHash: string;
  priorStatus: string;
  priorReportRow: RecordData;
  consentReportSha256: string;
  validationReportSha256: string;
};

export type ExactReplayRetentionExecutor = (params: {
  firestore: ExactReplayFirestore;
  uid: string;
  jobId: string;
  trigger: "avatar_job";
}) => Promise<"claimed" | "skipped">;

export type ExactReplayReportRow = {
  rowIndex: number;
  status: string;
};

export type ExactReplayCounts = {
  selected: number;
  passed: number;
  failed: number;
  applied: number;
  idempotent: number;
  safeRetained: number;
  candidateObjectsMatched: number;
  candidateObjectsDeleted: number;
};

export type ExactReplayReport = {
  dryRun: boolean;
  counts: ExactReplayCounts;
  allRowsPassed: boolean;
  rows: ExactReplayReportRow[];
};

export type RunAvatarExactReplayParams = {
  firestore: ExactReplayFirestore;
  storage: ExactReplayStorage;
  selectedRows: AvatarExactReplayRow[];
  projectId: string;
  operatorAuthorizedExactReplay: boolean;
  expectedSelectedReplaySha256: string;
  apply?: boolean;
  privateRollbackSnapshotPath?: string;
  writePrivateRollbackSnapshot?: (path: string, snapshot: unknown) => Promise<void>;
  executeRetention?: ExactReplayRetentionExecutor;
};

type CandidateProof = {
  id: string;
  bucket: string;
  path: string;
  status: "active" | "claimed" | "finalized";
};

type RowValidation = {
  row: AvatarExactReplayRow;
  status: "eligible" | "idempotent";
  uid: string;
  jobId: string;
  photoId: string;
  sourcePath: string;
  userData: RecordData;
  privateData: RecordData;
  jobData: RecordData;
  candidateDocs: CandidateProof[];  candidateSafeRetained: number;
  retentionAlreadyApplied: boolean;
};

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asRecord(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
}

function asList(value: unknown): RecordData[] {
  return Array.isArray(value) ? value.filter((item): item is RecordData => (
    item !== null && typeof item === "object" && !Array.isArray(item)
  )) : [];
}

function consentPurposes(privateData: RecordData): RecordData {
  const photoConsent = asRecord(privateData.photoConsent);
  const purposes = asRecord(photoConsent.purposes);
  return Object.keys(purposes).length > 0 ? purposes : photoConsent;
}

function retentionConsentConflict(privateData: RecordData): boolean {
  const purposes = consentPurposes(privateData);
  return purposes.sourcePhotoRetention === true && purposes.sourcePhotoDeletionRequested !== true;
}

function sourcePathFromEntry(entry: RecordData): string {
  const storagePath = asString(entry.storagePath);
  if (storagePath) return storagePath;
  const gcsUri = asString(entry.gcsUri);
  const prefix = `gs://${SOURCE_BUCKET}/`;
  return gcsUri.startsWith(prefix) ? gcsUri.slice(prefix.length) : "";
}

function parseGcsUri(value: string): { bucket: string; path: string } | null {
  const match = value.match(/^(?:gs|gcs):\/\/([^/]+)\/(.+)$/);
  if (!match) return null;
  return { bucket: match[1], path: match[2] };
}

function rowPairKey(row: AvatarExactReplayRow): string {
  return `${row.expectedUidHash}:${row.expectedJobIdHash}:${row.expectedSourcePhotoIdHash}`;
}

function mappingPayload(rows: AvatarExactReplayRow[]): unknown {
  return rows.map((row) => ({
    rowIndex: row.rowIndex,
    expectedUidHash: row.expectedUidHash,
    expectedJobIdHash: row.expectedJobIdHash,
    expectedSourcePhotoIdHash: row.expectedSourcePhotoIdHash,
    expectedSourcePathHash: row.expectedSourcePathHash,
    priorStatus: row.priorStatus,
    priorReportRow: row.priorReportRow,
    consentReportSha256: row.consentReportSha256,
    validationReportSha256: row.validationReportSha256,
  })).sort((left, right) => left.rowIndex - right.rowIndex);
}

export function exactReplaySelectionSha256(rows: AvatarExactReplayRow[]): string {
  return sha256(JSON.stringify(mappingPayload(rows)));
}

export function buildExactReplayReport(report: ExactReplayReport): ExactReplayReport {
  return {
    dryRun: report.dryRun,
    counts: { ...report.counts },
    allRowsPassed: report.allRowsPassed,
    rows: report.rows.map((row) => ({ rowIndex: row.rowIndex, status: row.status })),
  };
}

export function parseAvatarExactReplayArgs(args: string[]): {
  projectId: string;
  operatorAuthorizedExactReplay: boolean;
  expectedSelectedReplaySha256: string;
  expectedRawMappingSha256: string;
  mappingFile?: string;
  consentReportFile?: string;
  validationReportFile?: string;
  priorReportFile?: string;
  apply: boolean;
  privateRollbackSnapshotPath?: string;
} {
  const values = new Map<string, string>();
  let operatorAuthorizedExactReplay = false;
  let apply = false;
  for (const arg of args) {
    if (arg === "--operator-authorized-exact-replay") {
      operatorAuthorizedExactReplay = true;
      continue;
    }
    if (arg === "--apply") {
      apply = true;
      continue;
    }
    const [name, ...rest] = arg.split("=");
    if (name.startsWith("--")) values.set(name.slice(2), rest.join("="));
  }
  const projectId = values.get("project") ?? "";
  if (projectId !== REQUIRED_PROJECT_ID) throw new Error("ERR_EXACT_REPLAY_PROJECT");
  if (!operatorAuthorizedExactReplay) throw new Error("ERR_EXACT_REPLAY_AUTHORIZATION");
  const expectedSelectedReplaySha256 = values.get("expected-selected-replay-sha256") ?? "";
  if (!expectedSelectedReplaySha256) throw new Error("ERR_EXACT_REPLAY_SELECTED_DIGEST_REQUIRED");
  const expectedRawMappingSha256 = values.get("expected-raw-mapping-sha256") ?? "";
  if (!expectedRawMappingSha256) throw new Error("ERR_EXACT_REPLAY_RAW_MAPPING_DIGEST_REQUIRED");
  return {
    projectId,
    operatorAuthorizedExactReplay,
    expectedSelectedReplaySha256,
    expectedRawMappingSha256,
    mappingFile: values.get("mapping-file"),
    consentReportFile: values.get("consent-report-file"),
    validationReportFile: values.get("validation-report-file"),
    priorReportFile: values.get("prior-report-file"),
    apply,
    privateRollbackSnapshotPath: values.get("private-rollback-snapshot-path"),
  };
}

function assertHardGuards(params: RunAvatarExactReplayParams): void {
  if (process.env.SOURCE_PHOTO_BUCKET && process.env.SOURCE_PHOTO_BUCKET !== SOURCE_BUCKET) {
    throw new Error("ERR_EXACT_REPLAY_SOURCE_BUCKET");
  }
  process.env.SOURCE_PHOTO_BUCKET = SOURCE_BUCKET;
  if (params.projectId !== REQUIRED_PROJECT_ID) throw new Error("ERR_EXACT_REPLAY_PROJECT");
  if (!params.operatorAuthorizedExactReplay) throw new Error("ERR_EXACT_REPLAY_AUTHORIZATION");
  if (params.selectedRows.length !== EXACT_ROW_COUNT) throw new Error("ERR_EXACT_REPLAY_ROW_COUNT");
  if (exactReplaySelectionSha256(params.selectedRows) !== params.expectedSelectedReplaySha256) {
    throw new Error("ERR_EXACT_REPLAY_SELECTED_DIGEST");
  }
  const seen = new Set<string>();
  for (const row of params.selectedRows) {
    if (seen.has(rowPairKey(row))) throw new Error("ERR_EXACT_REPLAY_DUPLICATE_PAIR");
    seen.add(rowPairKey(row));
  }
}

async function getDoc(firestore: ExactReplayFirestore, collection: string, id: string): Promise<RecordData> {
  const snap = await firestore.collection(collection).doc(id).get();
  return snap.exists ? asRecord(snap.data()) : {};
}

function assertPriorReport(row: AvatarExactReplayRow): void {
  const prior = row.priorReportRow;
  if (prior.validationEligible !== true) throw new Error("ERR_EXACT_REPLAY_PRIOR_VALIDATION");
  if (asString(prior.uidHash) !== row.expectedUidHash) throw new Error("ERR_EXACT_REPLAY_PRIOR_UID");
  if (asString(prior.jobIdHash) !== row.expectedJobIdHash) throw new Error("ERR_EXACT_REPLAY_PRIOR_JOB");
  if (asString(prior.sourcePhotoIdHash) !== row.expectedSourcePhotoIdHash) {
    throw new Error("ERR_EXACT_REPLAY_PRIOR_PHOTO");
  }
  if (row.expectedSourcePathHash && asString(prior.sourcePathHash) !== row.expectedSourcePathHash) {
    throw new Error("ERR_EXACT_REPLAY_PRIOR_SOURCE");
  }
  if (asString(prior.status) !== row.priorStatus) throw new Error("ERR_EXACT_REPLAY_PRIOR_STATUS");
}

function hashMatches(value: string, expected: string, prefix?: "uid"): boolean {
  const digest = sha256(value);
  const normalized = prefix ? `${prefix}:${digest.slice(0, 12)}` : digest.slice(0, 12);
  return expected === digest || expected === digest.slice(0, 12) || expected === normalized;
}

function validateCurrentHashes(params: {
  row: AvatarExactReplayRow;
  uid: string;
  jobId: string;
  photoId: string;
  sourcePath: string;
}): void {
  if (!hashMatches(params.uid, params.row.expectedUidHash, "uid")) throw new Error("ERR_EXACT_REPLAY_UID_HASH");
  if (!hashMatches(params.jobId, params.row.expectedJobIdHash)) throw new Error("ERR_EXACT_REPLAY_JOB_HASH");
  if (!hashMatches(params.photoId, params.row.expectedSourcePhotoIdHash)) throw new Error("ERR_EXACT_REPLAY_PHOTO_HASH");
  if (params.row.expectedSourcePathHash && !hashMatches(params.sourcePath, params.row.expectedSourcePathHash)) {
    throw new Error("ERR_EXACT_REPLAY_SOURCE_HASH");
  }
}

function isIdempotent(privateData: RecordData, row: AvatarExactReplayRow): boolean {
  if (asString(privateData.currentAvatarJobId) || asString(privateData.currentAvatarSourcePhotoId)) return false;
  return asList(privateData.sourcePhotos).some((entry) => (
    hashMatches(asString(entry.photoId), row.expectedSourcePhotoIdHash) &&
    asString(entry.status) === "source_deleted" &&
    entry.sourceDeleted === true
  ));
}

async function loadCandidateProofs(params: {
  firestore: ExactReplayFirestore;
  storage: ExactReplayStorage;
  uid: string;
  jobId: string;
}): Promise<{ proofs: CandidateProof[]; safeRetained: number }> {
  const collection = params.firestore.collection("avatarCandidates");
  if (!collection.where) return { proofs: [], safeRetained: 0 };
  const snap = await collection.where("uid", "==", params.uid).get();
  const proofs: CandidateProof[] = [];
  let safeRetained = 0;
  for (const doc of snap.docs) {
    const data = asRecord(doc.data());
    const cleanup = asRecord(data.exactReplayCleanup);
    const parsed = parseGcsUri(asString(data.imageRef));
    const cleanupBucket = asString(cleanup.bucket);
    const cleanupPath = asString(cleanup.path);
    const ref = parsed ?? (cleanupBucket && cleanupPath ? { bucket: cleanupBucket, path: cleanupPath } : null);
    const status: CandidateProof["status"] = parsed
      ? "active"
      : asString(cleanup.status) === "finalized"
        ? "finalized"
        : asString(cleanup.status) === "claimed"
          ? "claimed"
          : "active";
    const exactOwner = asString(data.uid) === params.uid && asString(data.jobId) === params.jobId;
    const exactRef = ref !== null &&
      ref.bucket === TEMP_BUCKET &&
      ref.path.includes(params.uid) &&
      ref.path.includes(params.jobId);
    const objectOk = status === "finalized" ||
      status === "claimed" ||
      (ref !== null && await params.storage.objectExists(ref.bucket, ref.path));
    if (!exactOwner || data.approved === true || !exactRef || !objectOk || !ref) {
      safeRetained += 1;
      continue;
    }
    proofs.push({ id: doc.id, bucket: ref.bucket, path: ref.path, status });
  }
  return { proofs, safeRetained };
}
async function validateRow(params: RunAvatarExactReplayParams, row: AvatarExactReplayRow): Promise<RowValidation> {
  assertPriorReport(row);
  const uid = row.uid;
  if (!hashMatches(uid, row.expectedUidHash, "uid")) throw new Error("ERR_EXACT_REPLAY_UID_HASH");
  const privateData = await getDoc(params.firestore, "userPrivateMedia", uid);
  if (isIdempotent(privateData, row)) {
    return {
      row,
      status: "idempotent",
      uid,
      jobId: "",
      photoId: "",
      sourcePath: "",
      userData: {},
      privateData,
      jobData: {},
      candidateDocs: [],
      candidateSafeRetained: 0,
      retentionAlreadyApplied: true,
    };
  }

  const jobId = asString(privateData.currentAvatarJobId);
  const photoId = asString(privateData.currentAvatarSourcePhotoId);
  const redactedSourceEntry = asList(privateData.sourcePhotos).find((entry) => (
    asString(entry.photoId) === photoId &&
    asString(entry.status) === "source_deleted" &&
    entry.sourceDeleted === true
  ));
  if (
    hashMatches(jobId, row.expectedJobIdHash) &&
    hashMatches(photoId, row.expectedSourcePhotoIdHash) &&
    redactedSourceEntry
  ) {
    const [userData, jobData] = await Promise.all([
      getDoc(params.firestore, "users", uid),
      getDoc(params.firestore, "avatarJobs", jobId),
    ]);
    const accountStatus = asString(userData.accountStatus).toLowerCase();
    if (
      userData.disabled === true ||
      userData.deleted === true ||
      userData.suspended === true ||
      ["deleted", "suspended", "disabled"].includes(accountStatus)
    ) throw new Error("ERR_EXACT_REPLAY_ACCOUNT");
    if (userData.isStudentVerified !== true) throw new Error("ERR_EXACT_REPLAY_STUDENT_VERIFICATION");
    if (hasAvatarApprovalProtectedState(userData)) throw new Error("ERR_EXACT_REPLAY_APPROVED_AVATAR");
    if (retentionConsentConflict(privateData)) throw new Error("ERR_EXACT_REPLAY_RETENTION_CONSENT");
    if (asString(jobData.uid) !== uid) throw new Error("ERR_EXACT_REPLAY_JOB_UID");
    const candidates = await loadCandidateProofs({ firestore: params.firestore, storage: params.storage, uid, jobId });
    return {
      row,
      status: "eligible",
      uid,
      jobId,
      photoId,
      sourcePath: "",
      userData,
      privateData,
      jobData,
      candidateDocs: candidates.proofs,
      candidateSafeRetained: candidates.safeRetained,
      retentionAlreadyApplied: true,
    };
  }
  const sourceEntry = asList(privateData.sourcePhotos).find((entry) => (
    asString(entry.photoId) === photoId &&
    asString(entry.status) === "active" &&
    asString(entry.avatarGenerationState) === "current"
  ));
  const sourcePath = sourceEntry ? sourcePathFromEntry(sourceEntry) : "";
  validateCurrentHashes({ row, uid, jobId, photoId, sourcePath });

  const [userData, jobData] = await Promise.all([
    getDoc(params.firestore, "users", uid),
    getDoc(params.firestore, "avatarJobs", jobId),
  ]);
  const accountStatus = asString(userData.accountStatus).toLowerCase();
  if (
    userData.disabled === true ||
    userData.deleted === true ||
    userData.suspended === true ||
    ["deleted", "suspended", "disabled"].includes(accountStatus)
  ) throw new Error("ERR_EXACT_REPLAY_ACCOUNT");
  if (userData.isStudentVerified !== true) throw new Error("ERR_EXACT_REPLAY_STUDENT_VERIFICATION");
  if (hasAvatarApprovalProtectedState(userData)) throw new Error("ERR_EXACT_REPLAY_APPROVED_AVATAR");
  if (retentionConsentConflict(privateData)) throw new Error("ERR_EXACT_REPLAY_RETENTION_CONSENT");  if (asString(jobData.uid) !== uid) throw new Error("ERR_EXACT_REPLAY_JOB_UID");
  if (asString(jobData.status) !== row.priorStatus || !TERMINAL_REPLAY_STATUSES.has(row.priorStatus)) {
    throw new Error("ERR_EXACT_REPLAY_JOB_STATUS");
  }
  if (asString(sourceEntry?.storageBucket) !== SOURCE_BUCKET || !sourcePath.startsWith(`users/${uid}/source/`)) {
    throw new Error("ERR_EXACT_REPLAY_SOURCE_REF");
  }
  const jobRefs = Array.isArray(jobData.sourcePhotoRefs) ? jobData.sourcePhotoRefs.map(asString).filter(Boolean) : [];
  if (jobRefs.length > 0 && (jobRefs.length !== 1 || jobRefs[0] !== `gs://${SOURCE_BUCKET}/${sourcePath}`)) {
    throw new Error("ERR_EXACT_REPLAY_UNRELATED_SOURCE_REFS");
  }
  if (!await params.storage.objectExists(SOURCE_BUCKET, sourcePath)) throw new Error("ERR_EXACT_REPLAY_SOURCE_MISSING");

  const normalizedJobData = { ...jobData, status: "terminal_failed", retryable: false };
  const decision = planAvatarSourceRetention({ uid, jobId, privateData, jobData: normalizedJobData });
  if (decision.action !== "claim") throw new Error("ERR_EXACT_REPLAY_RETENTION_CONTRACT");
  const candidates = await loadCandidateProofs({
    firestore: params.firestore,
    storage: params.storage,
    uid,
    jobId,
  });
  return {
    row,
    status: "eligible",
    uid,
    jobId,
    photoId,
    sourcePath,
    userData,
    privateData,
    jobData,
    candidateDocs: candidates.proofs,
    candidateSafeRetained: candidates.safeRetained,
    retentionAlreadyApplied: false,
  };
}

function emptyCounts(selected: number): ExactReplayCounts {
  return {
    selected,
    passed: 0,
    failed: 0,
    applied: 0,
    idempotent: 0,
    safeRetained: 0,
    candidateObjectsMatched: 0,
    candidateObjectsDeleted: 0,
  };
}

async function defaultSnapshotWriter(): Promise<void> {
  throw new Error("ERR_EXACT_REPLAY_SNAPSHOT_WRITER");
}

async function defaultRetentionExecutor(): Promise<"claimed" | "skipped"> {
  throw new Error("ERR_EXACT_REPLAY_RETENTION_EXECUTOR");
}

async function applyCandidateCleanup(
  params: RunAvatarExactReplayParams,
  validation: RowValidation,
): Promise<{ deleted: number; safeRetained: number }> {
  if (!params.storage.deleteObject) return { deleted: 0, safeRetained: validation.candidateDocs.length };
  let deleted = 0;
  let safeRetained = 0;
  for (const candidate of validation.candidateDocs) {
    const ref = params.firestore.collection("avatarCandidates").doc(candidate.id);
    const snap = await ref.get();
    const data = asRecord(snap.data());
    const cleanup = asRecord(data.exactReplayCleanup);
    const parsed = parseGcsUri(asString(data.imageRef));
    const cleanupPath = asString(cleanup.path);
    const currentRef = parsed ?? (cleanupPath ? { bucket: asString(cleanup.bucket), path: cleanupPath } : null);
    const exact = snap.exists &&
      asString(data.uid) === validation.uid &&
      asString(data.jobId) === validation.jobId &&
      data.approved !== true &&
      currentRef !== null &&
      currentRef.bucket === candidate.bucket &&
      currentRef.path === candidate.path &&
      currentRef.bucket === TEMP_BUCKET &&
      currentRef.path.includes(validation.uid) &&
      currentRef.path.includes(validation.jobId);
    if (!exact || !currentRef) {
      safeRetained += 1;
      continue;
    }
    if (asString(cleanup.status) !== "finalized") {
      await ref.set({
        exactReplayCleanup: {
          status: "claimed",
          bucket: candidate.bucket,
          path: candidate.path,
        },
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    }
    const exists = await params.storage.objectExists(candidate.bucket, candidate.path);
    if (exists) {
      await params.storage.deleteObject(candidate.bucket, candidate.path);
      deleted += 1;
    }
    await ref.set({
      imageRef: FieldValue.delete(),
      exactReplayCleanup: {
        status: "finalized",
        bucket: candidate.bucket,
        path: candidate.path,
      },
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
  }
  return { deleted, safeRetained };
}
async function applyRow(
  params: RunAvatarExactReplayParams,
  validation: RowValidation,
): Promise<{ candidateObjectsDeleted: number; safeRetained: number }> {
  const candidateResult = await applyCandidateCleanup(params, validation);
  if (candidateResult.safeRetained > 0) return { candidateObjectsDeleted: candidateResult.deleted, safeRetained: candidateResult.safeRetained };

  if (!validation.retentionAlreadyApplied) {
    await params.firestore.collection("avatarJobs").doc(validation.jobId).set({
      status: "terminal_failed",
      retryable: false,
    }, { merge: true });
    const executeRetention = params.executeRetention ?? defaultRetentionExecutor;
    await executeRetention({ firestore: params.firestore, uid: validation.uid, jobId: validation.jobId, trigger: "avatar_job" });
  }

  const afterPrivateData = await getDoc(params.firestore, "userPrivateMedia", validation.uid);
  const redacted = asList(afterPrivateData.sourcePhotos).some((entry) => (
    hashMatches(asString(entry.photoId), validation.row.expectedSourcePhotoIdHash) &&
    asString(entry.status) === "source_deleted" &&
    entry.sourceDeleted === true
  ));
  if (!redacted) throw new Error("ERR_EXACT_REPLAY_RETENTION_VERIFY");

  const privateRef = params.firestore.collection("userPrivateMedia").doc(validation.uid);
  const userRef = params.firestore.collection("users").doc(validation.uid);
  await params.firestore.runTransaction(async (tx) => {
    const [privateSnap, userSnap] = await Promise.all([tx.get(privateRef), tx.get(userRef)]);
    const current = asRecord(privateSnap.data());
    if (
      asString(current.currentAvatarJobId) !== validation.jobId ||
      asString(current.currentAvatarSourcePhotoId) !== validation.photoId
    ) {
      throw new Error("ERR_EXACT_REPLAY_CAS_MISMATCH");
    }
    const userData = asRecord(userSnap.data());
    if (hasAvatarApprovalProtectedState(userData)) throw new Error("ERR_EXACT_REPLAY_APPROVED_AVATAR");
    const avatar = asRecord(userData.avatar);
    const publicJob = asString(avatar.jobId) || asString(avatar.sourceJobId);
    const publicSource = asString(avatar.sourcePhotoId) || asString(avatar.currentAvatarSourcePhotoId);
    const canClearQueued = asString(avatar.status) === "queued" &&
      (!publicJob || publicJob === validation.jobId) &&
      (!publicSource || publicSource === validation.photoId);
    tx.set(privateRef, {
      currentAvatarJobId: FieldValue.delete(),
      currentAvatarSourcePhotoId: FieldValue.delete(),
    }, { merge: true });
    if (canClearQueued) {
      tx.set(userRef, { avatar: { ...avatar, status: "none" } }, { merge: true });
    }
  });

  return {
    candidateObjectsDeleted: candidateResult.deleted,
    safeRetained: candidateResult.safeRetained,
  };
}
export async function runAvatarExactReplay(params: RunAvatarExactReplayParams): Promise<ExactReplayReport> {
  assertHardGuards(params);
  const validations: RowValidation[] = [];
  const reportRows: ExactReplayReportRow[] = [];
  const counts = emptyCounts(params.selectedRows.length);
  for (const row of params.selectedRows) {
    const validation = await validateRow(params, row);
    validations.push(validation);
    reportRows.push({ rowIndex: row.rowIndex, status: validation.status });
    if (validation.status === "idempotent") counts.idempotent += 1;
    else counts.passed += 1;
    counts.candidateObjectsMatched += validation.candidateDocs.length;
    counts.safeRetained += validation.candidateSafeRetained;
  }
  const allRowsPassed = counts.passed + counts.idempotent === EXACT_ROW_COUNT;
  if (params.apply) {
    if (!allRowsPassed) throw new Error("ERR_EXACT_REPLAY_APPLY_PRECONDITION");
    if (counts.passed > 0 && counts.safeRetained !== 0) throw new Error("ERR_EXACT_REPLAY_CANDIDATE_SAFE_RETAINED");
    if (counts.passed > 0 && counts.candidateObjectsMatched !== EXACT_CANDIDATE_COUNT) throw new Error("ERR_EXACT_REPLAY_CANDIDATE_COUNT");
    if (counts.passed > 0 && !params.privateRollbackSnapshotPath) throw new Error("ERR_EXACT_REPLAY_PRIVATE_SNAPSHOT");
    const writeSnapshot = params.writePrivateRollbackSnapshot ?? defaultSnapshotWriter;
    if (counts.passed > 0) {
      await writeSnapshot(params.privateRollbackSnapshotPath ?? "", validations.map((validation) => ({
        uid: validation.uid,
        jobId: validation.jobId,
        userData: validation.userData,
        privateData: validation.privateData,
        jobData: validation.jobData,
      })));
    }
    for (const validation of validations) {
      if (validation.status !== "eligible") continue;
      const result = await applyRow(params, validation);
      counts.applied += 1;
      counts.candidateObjectsDeleted += result.candidateObjectsDeleted;
      counts.safeRetained += result.safeRetained;
    }
  }
  return buildExactReplayReport({ dryRun: params.apply !== true, counts, allRowsPassed, rows: reportRows });
}