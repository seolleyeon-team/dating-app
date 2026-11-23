import assert from "node:assert/strict";
import test from "node:test";
import { Timestamp } from "firebase-admin/firestore";

import {
  avatarSourceRetentionStateId,
  recoverAvatarSourceRetentionDeletions,
  RECOVERY_CHECKPOINT_COLLECTION,
  RECOVERY_CHECKPOINT_ID,
} from "./avatarSourceRetention";
import { FakeFirestore, type Db, type Doc } from "./testing/fakeFirestore";

/**
 * AUD-09 — the recovery scan must reach every DUE state document.
 *
 * Before: `where(status in …).limit(25)` with no cursor read the same 25
 * documents on every run. State documents that are not due yet (a deferred
 * source waits out the recovery grace) or that re-plan to "skip" every run
 * stay retry-eligible, so 25 of them sorting first starved a source whose
 * deletion deadline had passed (the retention contract, not data loss).
 *
 * These fixtures drive the real claim -> revalidate -> delete -> mark path
 * through the in-memory Firestore, like avatarSourceRetentionRecovery.test.ts.
 */

const BUCKET = "seolleyeon-final-private-source-photos";
const STATES = "avatarSourceRetentionStates";
const CONSENT = { avatarGeneration: true, clipRecommendation: false, sourcePhotoRetention: false };

type Kind = "due" | "deferred_future" | "skip_forever";

function addUser(db: Db, uid: string, kind: Kind): string {
  const job = `job_${uid}`;
  const photo = `photo_${uid}`;
  const path = `users/${uid}/source/${photo}.jpg`;
  db.set(`avatarJobs/${job}`, {
    uid,
    status: "terminal_failed",
    failureClass: "content_terminal",
    sourcePhotoIds: [photo],
    sourcePhotoRefs: [`gs://${BUCKET}/${path}`],
    avatarSourceSelectionVersion: 1,
    consentPurposes: CONSENT,
  });
  db.set(`userPrivateMedia/${uid}`, {
    // skip_forever: the user moved on to another generation, so this state
    // re-plans to "not_current_job" on every run and is never mutated.
    currentAvatarJobId: kind === "skip_forever" ? `job_other_${uid}` : job,
    currentAvatarSourcePhotoId: photo,
    avatarSourceSelectionVersion: 1,
    photoConsent: { purposes: CONSENT },
    sourcePhotos: [
      {
        photoId: photo,
        status: "active",
        avatarGenerationState: "current",
        gcsUri: `gs://${BUCKET}/${path}`,
        storageBucket: BUCKET,
        storagePath: path,
      },
    ],
  });
  db.set(`users/${uid}`, { avatar: { status: "terminal_failed" } });
  const stateId = avatarSourceRetentionStateId(uid, photo);
  const state: Doc = {
    uid,
    jobId: job,
    photoId: photo,
    sourceSelectionVersion: 1,
    attempts: 1,
    trigger: "avatar_job",
    status: kind === "deferred_future" ? "deferred" : "stale",
  };
  if (kind === "deferred_future") {
    state.nextRetryAt = Timestamp.fromMillis(Date.now() + 48 * 60 * 60 * 1000);
  }
  db.set(`${STATES}/${stateId}`, state);
  return stateId;
}

function deleter(deleted: string[]) {
  return async (ref: { bucket: string; path: string }) => {
    deleted.push(`gs://${ref.bucket}/${ref.path}`);
  };
}

/** Builds `blockers` state docs that all sort before one due state doc. */
function fixture(blockers: number, blockerKind: Kind) {
  const db: Db = new Map();
  const candidates: Array<{ uid: string; stateId: string }> = [];
  for (let i = 0; i < blockers + 1; i += 1) {
    const uid = `uid_scan_${String(i).padStart(3, "0")}`;
    candidates.push({ uid, stateId: avatarSourceRetentionStateId(uid, `photo_${uid}`) });
  }
  // The due document gets the id that sorts LAST, i.e. behind every blocker.
  candidates.sort((a, b) => (a.stateId < b.stateId ? -1 : 1));
  const due = candidates[candidates.length - 1];
  for (const candidate of candidates) {
    addUser(db, candidate.uid, candidate === due ? "due" : blockerKind);
  }
  return { db, fs: new FakeFirestore(db), due, blockers: candidates.slice(0, -1) };
}

test("AUD-09 old shape: the fixed 25-document window never contains the due document", async () => {
  const { fs, due } = fixture(30, "deferred_future");
  // The query recoverAvatarSourceRetentionDeletions issued before the fix.
  const window = await fs
    .collection(STATES)
    .where("status", "in", ["deleting", "retryable_failed", "stale", "deferred"])
    .orderBy("__name__")
    .limit(25)
    .get();
  assert.equal(window.size, 25);
  assert.ok(
    !window.docs.some((doc) => doc.id === due.stateId),
    "BUG: the due source sits behind 25 not-yet-due documents and is never read"
  );
});

test("not-due documents no longer use up the work cap: the due source behind 30 of them is deleted in one run", async () => {
  const { db, fs, due } = fixture(30, "deferred_future");
  const deleted: string[] = [];
  const summary = await recoverAvatarSourceRetentionDeletions({
    firestore: fs as never,
    deleteObject: deleter(deleted),
    scanPageSize: 10,
  });
  assert.deepEqual(summary, { scanned: 31, due: 1, claimed: 1, skipped: 0 });
  assert.deepEqual(deleted, [`gs://${BUCKET}/users/${due.uid}/source/photo_${due.uid}.jpg`]);
  assert.equal(db.get(`${STATES}/${due.stateId}`)?.status, "deleted");
  // A finished pass leaves no checkpoint behind.
  assert.equal(db.get(`${RECOVERY_CHECKPOINT_COLLECTION}/${RECOVERY_CHECKPOINT_ID}`), undefined);
});

test("permanently skipped documents cannot starve a due one: the scan resumes behind them, and never writes to them", async () => {
  const { db, fs, due, blockers } = fixture(60, "skip_forever");
  const before = new Map(blockers.map((b) => [b.stateId, JSON.stringify(db.get(`${STATES}/${b.stateId}`))]));
  const deleted: string[] = [];
  const runOnce = () =>
    recoverAvatarSourceRetentionDeletions({ firestore: fs as never, deleteObject: deleter(deleted), scanPageSize: 20 });

  const first = await runOnce();
  assert.deepEqual(first, { scanned: 25, due: 25, claimed: 0, skipped: 25 }, "the work cap still bounds a run");
  assert.deepEqual(deleted, []);
  assert.equal(
    db.get(`${RECOVERY_CHECKPOINT_COLLECTION}/${RECOVERY_CHECKPOINT_ID}`)?.cursor,
    blockers[24].stateId,
    "a run stopped by its cap stores where it stopped"
  );

  const second = await runOnce();
  assert.equal(second.skipped, 25);
  assert.deepEqual(deleted, []);

  const third = await runOnce();
  assert.equal(third.claimed, 1, "the third run reaches the due source behind 60 skipped documents");
  assert.deepEqual(deleted, [`gs://${BUCKET}/users/${due.uid}/source/photo_${due.uid}.jpg`]);
  assert.equal(db.get(`${STATES}/${due.stateId}`)?.status, "deleted");

  for (const blocker of blockers) {
    assert.equal(
      JSON.stringify(db.get(`${STATES}/${blocker.stateId}`)),
      before.get(blocker.stateId),
      "a skipped state document is never mutated"
    );
  }

  // The pass keeps rotating: later runs revisit the skipped documents without
  // deleting anything again, and a completed pass clears the checkpoint.
  let cleared = false;
  for (let i = 0; i < 6 && !cleared; i += 1) {
    await runOnce();
    cleared = db.get(`${RECOVERY_CHECKPOINT_COLLECTION}/${RECOVERY_CHECKPOINT_ID}`)?.cursor === null;
  }
  assert.equal(deleted.length, 1, "exactly one deletion in total");
});

test("a run stopped by its time budget resumes; nothing is deleted twice", async () => {
  const db: Db = new Map();
  const ids: string[] = [];
  for (let i = 0; i < 12; i += 1) ids.push(addUser(db, `uid_budget_${i}`, "due"));
  const fs = new FakeFirestore(db);
  const deleted: string[] = [];
  let clock = 0;
  const first = await recoverAvatarSourceRetentionDeletions({
    firestore: fs as never,
    deleteObject: async (ref) => {
      deleted.push(ref.path);
      if (deleted.length === 5) clock = 10_000;
    },
    timeBudgetMs: 1000,
    nowMs: () => clock,
  });
  assert.equal(first.claimed, 5);
  const second = await recoverAvatarSourceRetentionDeletions({
    firestore: fs as never,
    deleteObject: async (ref) => {
      deleted.push(ref.path);
    },
  });
  assert.equal(second.claimed, 7);
  assert.equal(new Set(deleted).size, 12);
  assert.equal(deleted.length, 12);
  for (const id of ids) assert.equal(db.get(`${STATES}/${id}`)?.status, "deleted");
});
