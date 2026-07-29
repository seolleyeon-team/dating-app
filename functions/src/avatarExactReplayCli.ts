import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { initializeApp, applicationDefault } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";

import {  parseAvatarExactReplayArgs,
  runAvatarExactReplay,
  type AvatarExactReplayRow,
  type ExactReplayFirestore,
  type ExactReplayStorage,
} from "./avatarExactReplay";
import { executeAvatarSourceRetention } from "./avatarSourceRetention";

const SOURCE_BUCKET = "seolleyeon-final-private-source-photos";

type RecordData = Record<string, unknown>;

type Assignment = { uid: string; path: string };

function firebaseStorage(): ExactReplayStorage {
  return {
    objectExists: async (bucket: string, path: string) => {
      const [exists] = await getStorage().bucket(bucket).file(path).exists();
      return exists;
    },
    deleteObject: async (bucket: string, path: string) => {
      await getStorage().bucket(bucket).file(path).delete({ ignoreNotFound: true });
    },
  };
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function sha256Bytes(value: Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function priorUidHash(uid: string): string {
  return `uid:${sha256Text(uid).slice(0, 12)}`;
}

function asRecord(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
}

function asList(value: unknown): RecordData[] {
  return Array.isArray(value) ? value.filter((item): item is RecordData => (
    item !== null && typeof item === "object" && !Array.isArray(item)
  )) : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function parseAssignmentLines(raw: string): Assignment[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return { uid: line.slice(0, separator).trim(), path: line.slice(separator + 1).trim() };
    })
    .filter((entry) => entry.uid.length > 0 && entry.path.length > 0);
}

async function readJsonFile(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf8"));
}

function rowsFrom(value: unknown, key: string): RecordData[] {
  const data = asRecord(value);
  const nested = asList(data[key]);
  return nested.length > 0 ? nested : asList(value);
}

function latestStatus(job: RecordData): string {
  const explicit = asString(job.status);
  if (explicit) return explicit;
  const history = asList(job.statusHistory);
  return asString(history[history.length - 1]?.status);
}

export async function rawFileSha256(path: string): Promise<string> {
  return sha256Bytes(await readFile(path));
}

export async function loadExactReplayRowsFromPrivateFiles(params: {
  mappingFile: string;
  consentReportFile: string;
  validationReportFile: string;
  priorReportFile: string;
}): Promise<AvatarExactReplayRow[]> {
  const [mappingRaw, consentRaw, validation, prior] = await Promise.all([
    readFile(params.mappingFile, "utf8"),
    readFile(params.consentReportFile, "utf8"),
    readJsonFile(params.validationReportFile),
    readJsonFile(params.priorReportFile),
  ]);
  const mappingRows = parseAssignmentLines(mappingRaw);
  const consentRows = parseAssignmentLines(consentRaw);
  if (mappingRows.length !== 10 || consentRows.length !== 10) throw new Error("ERR_EXACT_REPLAY_PRIVATE_INPUT_COUNT");
  if (JSON.stringify(mappingRows) !== JSON.stringify(consentRows)) {
    throw new Error("ERR_EXACT_REPLAY_CONSENT_MAPPING_MISMATCH");
  }

  const validationRows = rowsFrom(validation, "rows");
  const priorJobs = rowsFrom(prior, "jobs");
  const eligibleValidation = validationRows.filter((row) => (
    row.eligibleForUpload === true && asList(row.blockers).length === 0
  ));
  const selected: AvatarExactReplayRow[] = [];
  for (const job of priorJobs) {
    const uidHash = asString(job.uidHash);
    const photoFile = asString(job.photoFile);
    const mapping = mappingRows.find((entry) => priorUidHash(entry.uid) === uidHash && entry.path.endsWith(photoFile));
    const validationRow = eligibleValidation.find((row) => (
      asString(row.uidHash) === uidHash && asString(row.photoFile) === photoFile
    ));
    if (!mapping || !validationRow) continue;
    const localDigest = sha256Bytes(await readFile(mapping.path));
    const priorPrefix = asString(job.imageSha256Prefix);
    if (priorPrefix && !localDigest.startsWith(priorPrefix)) throw new Error("ERR_EXACT_REPLAY_LOCAL_PHOTO_DIGEST");
    const upload = asRecord(job.upload);
    selected.push({
      rowIndex: selected.length + 1,
      uid: mapping.uid,
      expectedUidHash: uidHash,
      expectedJobIdHash: asString(upload.jobIdHash) || asString(job.jobIdHash),
      expectedSourcePhotoIdHash: asString(upload.photoIdHash) || asString(job.photoIdHash),
      expectedSourcePathHash: "",
      priorStatus: latestStatus(job),
      priorReportRow: {
        rowIndex: selected.length + 1,
        uidHash,
        jobIdHash: asString(upload.jobIdHash) || asString(job.jobIdHash),
        sourcePhotoIdHash: asString(upload.photoIdHash) || asString(job.photoIdHash),
        sourcePathHash: "",
        status: latestStatus(job),
        validationEligible: true,
      },
      consentReportSha256: "private-file",
      validationReportSha256: "private-file",
    });
  }
  if (selected.length !== 7) throw new Error("ERR_EXACT_REPLAY_SELECTED_COUNT");
  return selected;
}

export function safeExactReplayErrorCode(error: unknown): string {
  return error instanceof Error && /^ERR_EXACT_REPLAY_[A-Z0-9_]+$/.test(error.message)
    ? error.message
    : "ERR_EXACT_REPLAY_FAILED";
}

export async function main(args = process.argv.slice(2)): Promise<void> {
  const parsed = parseAvatarExactReplayArgs(args);
  if (!parsed.mappingFile || !parsed.consentReportFile || !parsed.validationReportFile || !parsed.priorReportFile) {
    throw new Error("ERR_EXACT_REPLAY_PRIVATE_INPUT_FILES");
  }
  if (await rawFileSha256(parsed.mappingFile) !== parsed.expectedRawMappingSha256) {
    throw new Error("ERR_EXACT_REPLAY_RAW_MAPPING_DIGEST");
  }
  process.env.SOURCE_PHOTO_BUCKET = SOURCE_BUCKET;
  const selectedRows = await loadExactReplayRowsFromPrivateFiles({
    mappingFile: parsed.mappingFile,
    consentReportFile: parsed.consentReportFile,
    validationReportFile: parsed.validationReportFile,
    priorReportFile: parsed.priorReportFile,
  });
  initializeApp({ credential: applicationDefault(), projectId: parsed.projectId });
  const report = await runAvatarExactReplay({
    firestore: getFirestore() as unknown as ExactReplayFirestore,
    storage: firebaseStorage(),
    selectedRows,
    projectId: parsed.projectId,
    operatorAuthorizedExactReplay: parsed.operatorAuthorizedExactReplay,
    expectedSelectedReplaySha256: parsed.expectedSelectedReplaySha256,
    apply: parsed.apply,
    privateRollbackSnapshotPath: parsed.privateRollbackSnapshotPath,
    writePrivateRollbackSnapshot: async (path, snapshot) => {
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, JSON.stringify(snapshot, null, 2), { encoding: "utf8", flag: "wx" });
    },
    executeRetention: async ({ firestore, uid, jobId, trigger }) => executeAvatarSourceRetention({
      firestore: firestore as unknown as Parameters<typeof executeAvatarSourceRetention>[0]["firestore"],
      uid,
      jobId,
      trigger,
    }),
  });
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

if (require.main === module) {
  main().catch((error: unknown) => {
    const message = safeExactReplayErrorCode(error);
    process.stderr.write(`${JSON.stringify({ error: message })}\\n`);
    process.exitCode = 1;
  });
}