import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  buildExactReplayReport,
  exactReplaySelectionSha256,
  parseAvatarExactReplayArgs,
  runAvatarExactReplay,
  type AvatarExactReplayRow,
} from "./avatarExactReplay";
import { safeExactReplayErrorCode } from "./avatarExactReplayCli";

const sourceBucket = "seolleyeon-final-private-source-photos";

type Db = Map<string, Record<string, unknown>>;
type RowIdentity = {
  uid: string;
  uidHash: string;
  jobId: string;
  jobIdHash: string;
  photoId: string;
  photoIdHash: string;
  sourcePath: string;
  sourcePathHash: string;
};

function sha(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function identity(index: number): RowIdentity {
  const uid = `uid-secret-${index}`;
  const jobId = `job-secret-${index}`;
  const photoId = `photo-secret-${index}`;
  const sourcePath = `users/${uid}/source/photo-${index}.jpg`;
  return {
    uid,
    uidHash: sha(uid),
    jobId,
    jobIdHash: sha(jobId),
    photoId,
    photoIdHash: sha(photoId),
    sourcePath,
    sourcePathHash: sha(sourcePath),
  };
}

function row(index: number, overrides: Partial<AvatarExactReplayRow> = {}): AvatarExactReplayRow {
  const item = identity(index);
  return {
    rowIndex: index,
    uid: item.uid,
    expectedUidHash: item.uidHash,
    expectedJobIdHash: item.jobIdHash,
    expectedSourcePhotoIdHash: item.photoIdHash,
    expectedSourcePathHash: item.sourcePathHash,
    priorStatus: "no_previewable_candidates",
    priorReportRow: {
      rowIndex: index,
      uidHash: item.uidHash,
      jobIdHash: item.jobIdHash,
      sourcePhotoIdHash: item.photoIdHash,
      sourcePathHash: item.sourcePathHash,
      status: "no_previewable_candidates",
      validationEligible: true,
    },
    consentReportSha256: `consent-${index}`,
    validationReportSha256: `validation-${index}`,
    ...overrides,
  };
}

function rows(overrides: Partial<AvatarExactReplayRow> = {}): AvatarExactReplayRow[] {
  return Array.from({ length: 7 }, (_, index) => row(index + 1, overrides));
}

function key(collection: string, id: string): string {
  return `${collection}/${id}`;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function mergeData(existing: Record<string, unknown>, next: Record<string, unknown>): Record<string, unknown> {
  const merged = { ...existing };
  for (const [field, value] of Object.entries(next)) {
    if (value && typeof value === "object" && "_methodName" in value && value._methodName === "FieldValue.delete") {
      delete merged[field];
    } else {
      merged[field] = clone(value);
    }
  }
  return merged;
}
class FakeFirestore {
  constructor(readonly db: Db) {}

  collection(name: string) {
    return {
      doc: (id: string) => ({
        get: async () => ({
          exists: this.db.has(key(name, id)),
          data: () => clone(this.db.get(key(name, id)) ?? {}),
        }),
        set: async (data: Record<string, unknown>, options?: { merge?: boolean }) => {
          const path = key(name, id);
          this.db.set(
            path,
            options?.merge ? mergeData(this.db.get(path) ?? {}, data) : clone(data),
          );
        },
        update: async (data: Record<string, unknown>) => {
          const path = key(name, id);
          this.db.set(path, mergeData(this.db.get(path) ?? {}, data));
        },
      }),
      where: (field: string, operator: string, value: unknown) => ({
        get: async () => ({
          docs: Array.from(this.db.entries())
            .filter(([path]) => path.startsWith(`${name}/`))
            .filter(([, data]) => operator === "==" && data[field] === value)
            .map(([path, data]) => ({
              id: path.slice(name.length + 1),
              data: () => clone(data),
              ref: this.collection(name).doc(path.slice(name.length + 1)),
            })),
        }),
      }),
    };
  }

  async runTransaction<T>(fn: (tx: {
    get(ref: { get(): Promise<{ exists: boolean; data(): Record<string, unknown> | undefined }> }): Promise<{ exists: boolean; data(): Record<string, unknown> | undefined }>;
    set(ref: { set(data: Record<string, unknown>, options?: { merge?: boolean }): Promise<unknown> }, data: Record<string, unknown>, options?: { merge?: boolean }): void;
  }) => Promise<T>): Promise<T> {
    return fn({
      get: async (ref) => ref.get(),
      set: (ref, data, options) => {
        void ref.set(data, options);
      },
    });
  }
}

function dbFixture(overrides: {
  user?: (item: RowIdentity) => Record<string, unknown>;
  privateMedia?: (item: RowIdentity) => Record<string, unknown>;
  job?: (item: RowIdentity) => Record<string, unknown>;
} = {}): Db {
  const db: Db = new Map();
  for (let index = 1; index <= 7; index += 1) {
    const item = identity(index);
    db.set(key("users", item.uid), {
      disabled: false,
      emailVerified: true,
      isStudentVerified: true,
      avatar: { status: "none" },
      ...(overrides.user?.(item) ?? {}),
    });
    db.set(key("userPrivateMedia", item.uid), {
      currentAvatarJobId: item.jobId,
      currentAvatarSourcePhotoId: item.photoId,
      avatarSourceSelectionVersion: 2,
      photoConsent: { purposes: { sourcePhotoRetention: false, clipRecommendation: false } },
      sourcePhotos: [{
        photoId: item.photoId,
        status: "active",
        avatarGenerationState: "current",
        storageBucket: sourceBucket,
        storagePath: item.sourcePath,
      }],
      ...(overrides.privateMedia?.(item) ?? {}),
    });
    db.set(key("avatarJobs", item.jobId), {
      uid: item.uid,
      status: "no_previewable_candidates",
      retryable: false,
      sourcePhotoIds: [item.photoId],
      avatarSourceSelectionVersion: 2,
      sourcePhotoRefs: [`gs://${sourceBucket}/${item.sourcePath}`],
      ...(overrides.job?.(item) ?? {}),
    });
  }
  return db;
}

function addCandidateDocs(
  db: Db,
  perRow = 8,
  overrides: (item: RowIdentity, candidateIndex: number, id: string) => Record<string, unknown> = () => ({}),
): void {
  for (let rowIndex = 1; rowIndex <= 7; rowIndex += 1) {
    const item = identity(rowIndex);
    for (let candidateIndex = 1; candidateIndex <= perRow; candidateIndex += 1) {
      const id = `candidate-${rowIndex}-${candidateIndex}`;
      db.set(key("avatarCandidates", id), {
        uid: item.uid,
        jobId: item.jobId,
        candidateId: id,
        approved: false,
        imageRef: `gs://seolleyeon-final-avatar-temp/users/${item.uid}/jobs/${item.jobId}/candidates/${id}.png`,
        ...overrides(item, candidateIndex, id),
      });
    }
  }
}
function storageFixture(missingPath = "") {
  const deleted: string[] = [];
  return {
    deleted,
    objectExists: async (bucket: string, path: string) =>
      (bucket === sourceBucket || bucket === "seolleyeon-final-avatar-temp") &&
      path.startsWith("users/uid-secret-") &&
      path !== missingPath && !deleted.includes(`${bucket}/${path}`),
    deleteObject: async (bucket: string, path: string) => {
      deleted.push(`${bucket}/${path}`);
    },
  };
}

test("hard-stops unless project, flag, count, mapping hash, and row pairs are exact", async () => {
  const selectedRows = rows();
  const mappingSha256 = exactReplaySelectionSha256(selectedRows);
  assert.throws(
    () => parseAvatarExactReplayArgs([
      "--project=seolleyeon-dev",
      "--operator-authorized-exact-replay",
      `--expected-mapping-sha256=${mappingSha256}`,
      "--mapping-json=[]",
    ]),
    /ERR_EXACT_REPLAY_PROJECT/,
  );
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture()),
      storage: storageFixture(),
      selectedRows: selectedRows.slice(0, 6),
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows.slice(0, 6)),
    }),
    /ERR_EXACT_REPLAY_ROW_COUNT/,
  );
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture()),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: sha("wrong"),
    }),
    /ERR_EXACT_REPLAY_SELECTED_DIGEST/,
  );
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture()),
      storage: storageFixture(),
      selectedRows: [row(1), row(1, { rowIndex: 2 }), ...rows().slice(2)],
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256([row(1), row(1, { rowIndex: 2 }), ...rows().slice(2)]),
    }),
    /ERR_EXACT_REPLAY_DUPLICATE_PAIR/,
  );
});

test("CLI parser keeps raw mapping and selected replay digests separate", () => {
  const parsed = parseAvatarExactReplayArgs([
    "--project=seolleyeon-final",
    "--operator-authorized-exact-replay",
    "--expected-raw-mapping-sha256=raw-digest",
    "--expected-selected-replay-sha256=selected-digest",
  ]);

  assert.equal(parsed.expectedRawMappingSha256, "raw-digest");
  assert.equal(parsed.expectedSelectedReplaySha256, "selected-digest");
});
test("CLI error sanitizer suppresses external messages", () => {
  assert.equal(
    safeExactReplayErrorCode(new Error("C:/private/source/path failed")),
    "ERR_EXACT_REPLAY_FAILED",
  );
  assert.equal(
    safeExactReplayErrorCode(new Error("ERR_EXACT_REPLAY_PRIVATE_INPUT_FILES")),
    "ERR_EXACT_REPLAY_PRIVATE_INPUT_FILES",
  );
});
test("hard-stops when the operator selected replay digest does not match selected rows", async () => {
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture()),
      storage: storageFixture(),
      selectedRows: rows(),
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: sha("wrong-selection"),
    }),
    /ERR_EXACT_REPLAY_SELECTED_DIGEST/,
  );
});
test("dry-run report is sanitized and validates all seven matched rows", async () => {
  const selectedRows = rows();
  const report = await runAvatarExactReplay({
    firestore: new FakeFirestore(dbFixture()),
    storage: storageFixture(),
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
  });
  const serialized = JSON.stringify(report);
  assert.equal(report.dryRun, true);
  assert.equal(report.counts.selected, 7);
  assert.equal(report.counts.passed, 7);
  assert.equal(report.allRowsPassed, true);
  assert.equal("uidHash" in report.rows[0], false);
  assert.equal(report.rows[0].status, "eligible");
  for (const item of Array.from({ length: 7 }, (_, index) => identity(index + 1))) {
    assert.equal(serialized.includes(item.uid), false);
    assert.equal(serialized.includes(item.jobId), false);
    assert.equal(serialized.includes(item.photoId), false);
    assert.equal(serialized.includes(item.sourcePath), false);
  }
});

test("dry-run accepts real prior truncated hashes without source path hash", async () => {
  const selectedRows = rows().map((item, index) => {
    const exact = identity(index + 1);
    return {
      ...item,
      expectedUidHash: `uid:${sha(exact.uid).slice(0, 12)}`,
      expectedJobIdHash: sha(exact.jobId).slice(0, 12),
      expectedSourcePhotoIdHash: sha(exact.photoId).slice(0, 12),
      expectedSourcePathHash: "",
      priorReportRow: {
        ...item.priorReportRow,
        uidHash: `uid:${sha(exact.uid).slice(0, 12)}`,
        jobIdHash: sha(exact.jobId).slice(0, 12),
        sourcePhotoIdHash: sha(exact.photoId).slice(0, 12),
        sourcePathHash: "",
      },
    };
  });

  const report = await runAvatarExactReplay({
    firestore: new FakeFirestore(dbFixture()),
    storage: storageFixture(),
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
  });

  assert.equal(report.counts.passed, 7);
  assert.equal(report.rows[0].status, "eligible");
});
test("dry-run aggregates candidate temp object counts and apply deletes only proven candidates", async () => {
  const selectedRows = rows();
  const db = dbFixture();
  addCandidateDocs(db);
  const storage = storageFixture();

  const dryRun = await runAvatarExactReplay({
    firestore: new FakeFirestore(db),
    storage,
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
  });

  assert.equal(dryRun.counts.candidateObjectsMatched, 56);
  assert.equal(dryRun.counts.candidateObjectsDeleted, 0);
  assert.equal(JSON.stringify(dryRun).includes("candidate-1-1"), false);

  const applied = await runAvatarExactReplay({
    firestore: new FakeFirestore(db),
    storage,
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    apply: true,
    privateRollbackSnapshotPath: "C:/tmp/private.json",
    writePrivateRollbackSnapshot: async () => undefined,
    executeRetention: async ({ uid }: { uid: string; jobId: string }) => {
      const privatePath = key("userPrivateMedia", uid);
      const privateData = db.get(privatePath) ?? {};
      db.set(privatePath, {
        ...privateData,
        sourcePhotos: [{ photoId: privateData.currentAvatarSourcePhotoId, status: "source_deleted", sourceDeleted: true }],
      });
      return "claimed";
    },
  });

  assert.equal(applied.counts.candidateObjectsMatched, 56);
  assert.equal(applied.counts.candidateObjectsDeleted, 56);
  assert.equal(storage.deleted.length, 56);
  assert.equal(typeof db.get(key("avatarCandidates", "candidate-1-1"))?.imageRef, "object");
});
test("apply hard-stops unless exactly fifty-six candidates are proven and none are retained", async () => {
  const selectedRows = rows();
  const dbWith55 = dbFixture();
  addCandidateDocs(dbWith55, 7);
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbWith55),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
      privateRollbackSnapshotPath: "C:/tmp/private.json",
      writePrivateRollbackSnapshot: async () => undefined,
      executeRetention: async () => "claimed",
    }),
    /ERR_EXACT_REPLAY_CANDIDATE_COUNT/,
  );

  const dbWith0 = dbFixture();
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbWith0),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
      privateRollbackSnapshotPath: "C:/tmp/private.json",
      writePrivateRollbackSnapshot: async () => undefined,
      executeRetention: async () => "claimed",
    }),
    /ERR_EXACT_REPLAY_CANDIDATE_COUNT/,
  );

  const unrelatedDb = dbFixture();
  addCandidateDocs(unrelatedDb, 8, (item, candidateIndex, id) => (
    candidateIndex === 1
      ? { imageRef: `gs://seolleyeon-final-avatar-temp/users/${item.uid}/jobs/other-job/candidates/${id}.png` }
      : {}
  ));
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(unrelatedDb),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
      privateRollbackSnapshotPath: "C:/tmp/private.json",
      writePrivateRollbackSnapshot: async () => undefined,
      executeRetention: async () => "claimed",
    }),
    /ERR_EXACT_REPLAY_CANDIDATE_SAFE_RETAINED/,
  );
});
test("apply requires all seven rows and a private rollback snapshot path", async () => {
  const selectedRows = rows();
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture({ user: () => ({ isStudentVerified: false }) })),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
      privateRollbackSnapshotPath: "C:/tmp/private.json",
    }),
    /ERR_EXACT_REPLAY_STUDENT_VERIFICATION/,
  );
  const missingSnapshotDb = dbFixture();
  addCandidateDocs(missingSnapshotDb);
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(missingSnapshotDb),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
    }),
    /ERR_EXACT_REPLAY_PRIVATE_SNAPSHOT/
  );
});

test("validation vetoes CAS mismatch and approval protected state", async () => {
  const selectedRows = rows();
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture({
        privateMedia: () => ({ currentAvatarJobId: "changed" }),
      })),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    }),
    /ERR_EXACT_REPLAY_JOB_HASH/,
  );
  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FakeFirestore(dbFixture({
        user: () => ({ avatar: { status: "approved" } }),
      })),
      storage: storageFixture(),
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    }),
    /ERR_EXACT_REPLAY_APPROVED_AVATAR/,
  );
});

test("apply resumes CAS repair after retention redacted source and previous transaction failed", async () => {
  const selectedRows = rows();
  const db = dbFixture({
    user: (item) => ({ avatar: { status: "queued", jobId: item.jobId } }),
  });
  addCandidateDocs(db);
  const storage = storageFixture();
  let failTransaction = true;
  class FailingOnceFirestore extends FakeFirestore {
    override async runTransaction<T>(fn: Parameters<FakeFirestore["runTransaction"]>[0]): Promise<T> {
      if (failTransaction) {
        failTransaction = false;
        throw new Error("transaction failed after retention");
      }
      return super.runTransaction(fn) as Promise<T>;
    }
  }
  let retentionCalls = 0;
  const executeRetention = async ({ uid }: { uid: string; jobId: string }): Promise<"claimed" | "skipped"> => {
    retentionCalls += 1;
    const privatePath = key("userPrivateMedia", uid);
    const privateData = db.get(privatePath) ?? {};
    db.set(privatePath, {
      ...privateData,
      sourcePhotos: [{ photoId: privateData.currentAvatarSourcePhotoId, status: "source_deleted", sourceDeleted: true }],
    });
    return "claimed";
  };

  await assert.rejects(
    () => runAvatarExactReplay({
      firestore: new FailingOnceFirestore(db),
      storage,
      selectedRows,
      projectId: "seolleyeon-final",
      operatorAuthorizedExactReplay: true,
      expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
      apply: true,
      privateRollbackSnapshotPath: "C:/tmp/private.json",
      writePrivateRollbackSnapshot: async () => undefined,
      executeRetention,
    }),
    /transaction failed after retention/,
  );

  const resumed = await runAvatarExactReplay({
    firestore: new FailingOnceFirestore(db),
    storage,
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    apply: true,
    privateRollbackSnapshotPath: "C:/tmp/private.json",
    writePrivateRollbackSnapshot: async () => undefined,
    executeRetention: async ({ uid }: { uid: string; jobId: string }) => {
      assert.notEqual(uid, identity(1).uid);
      retentionCalls += 1;
      const privatePath = key("userPrivateMedia", uid);
      const privateData = db.get(privatePath) ?? {};
      db.set(privatePath, {
        ...privateData,
        sourcePhotos: [{ photoId: privateData.currentAvatarSourcePhotoId, status: "source_deleted", sourceDeleted: true }],
      });
      return "claimed";
    },
  });

  assert.equal(retentionCalls, 7);
  assert.equal(resumed.counts.applied, 7);
  assert.equal((db.get(key("users", identity(1).uid))?.avatar as Record<string, unknown>).status, "none");
});
test("apply normalizes old jobs, invokes retention sequentially, CAS-clears stale queued state, and is idempotent", async () => {
  const selectedRows = rows();
  const db = dbFixture({
    user: (item) => ({ avatar: { status: "queued", jobId: item.jobId } }),
  });
  addCandidateDocs(db);
  const calls: string[] = [];
  const executeRetention = async (
    { uid, jobId }: { uid: string; jobId: string },
  ): Promise<"claimed" | "skipped"> => {
    calls.push(`${uid}:${jobId}`);
    const privatePath = key("userPrivateMedia", uid);
    const privateData = db.get(privatePath) ?? {};
    db.set(privatePath, {
      ...privateData,      sourcePhotos: [{ photoId: privateData.currentAvatarSourcePhotoId, status: "source_deleted", sourceDeleted: true }],
    });
    return "claimed";
  };

  const first = await runAvatarExactReplay({
    firestore: new FakeFirestore(db),
    storage: storageFixture(),
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    apply: true,
    privateRollbackSnapshotPath: "C:/tmp/private.json",
    writePrivateRollbackSnapshot: async () => undefined,
    executeRetention,
  });
  const second = await runAvatarExactReplay({
    firestore: new FakeFirestore(db),
    storage: storageFixture(),
    selectedRows,
    projectId: "seolleyeon-final",
    operatorAuthorizedExactReplay: true,
    expectedSelectedReplaySha256: exactReplaySelectionSha256(selectedRows),
    apply: true,
    privateRollbackSnapshotPath: "C:/tmp/private.json",
    writePrivateRollbackSnapshot: async () => undefined,
    executeRetention: async () => {
      throw new Error("must not rerun retention after redaction");
    },
  });

  assert.equal(first.counts.applied, 7);
  assert.deepEqual(calls, Array.from({ length: 7 }, (_, index) => {
    const item = identity(index + 1);
    return `${item.uid}:${item.jobId}`;
  }));
  for (let index = 1; index <= 7; index += 1) {
    const item = identity(index);
    assert.equal(db.get(key("avatarJobs", item.jobId))?.status, "terminal_failed");
    assert.equal((db.get(key("users", item.uid))?.avatar as Record<string, unknown>).status, "none");
  }
  assert.equal(second.counts.idempotent, 7);
  assert.equal(second.counts.applied, 0);
});

test("buildExactReplayReport emits only safe row fields", () => {
  assert.deepEqual(Object.keys(buildExactReplayReport({
    dryRun: true,
    counts: { selected: 1, passed: 1, failed: 0, applied: 0, idempotent: 0, safeRetained: 0, candidateObjectsMatched: 0, candidateObjectsDeleted: 0 },
    allRowsPassed: true,
    rows: [{ rowIndex: 1, status: "eligible" }],
  }).rows[0]), ["rowIndex", "status"]);
});