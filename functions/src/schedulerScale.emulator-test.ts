/**
 * AUD-12 / AUD-25 — scheduler scan shapes at scale (emulator only, never
 * production). Measured quantity: Firestore DOCUMENTS READ by each scan shape
 * (query result sizes) and transactions/writes started, plus wall clock as a
 * sanity bound.
 *
 *  A. Goodbye auto-complete sweep: the old shape reads every promise ever
 *     stamped on every run; the watermark sweep reads the backlog once and
 *     afterwards only what became due. Interruption, failure retry and
 *     overlapping runs neither skip nor double-process a promise.
 *  B. Email-link token purge: the old fixed 500-document window deletes
 *     nothing once kept tokens fill it; the paged walk reaches every token
 *     and resumes after an interrupted run.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-sched \
 *     "node --test functions/.audit-lib-sched/schedulerScale.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import {
  getFirestore,
  Timestamp,
  type QueryDocumentSnapshot,
} from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-sched" });

import {
  purgeExpiredEmailLinkTokens,
  selectEmailLinkTokenIdsToPurge,
  EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID,
} from "./emailLinkTokenPurge";
import {
  GOODBYE_SWEEP_CHECKPOINT_ID,
  readGoodbyeSweepWatermark,
  SCHEDULER_CHECKPOINT_COLLECTION,
  sweepExpiredGoodbyePromises,
  type GoodbyeSweepOutcome,
} from "./goodbyeAutoCompleteSweep";

const db = getFirestore();
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

async function clearCollectionGroup(name: string) {
  for (;;) {
    const snap = await db.collectionGroup(name).limit(400).get();
    if (snap.empty) return;
    const batch = db.batch();
    snap.docs.forEach((doc) => batch.delete(doc.ref));
    await batch.commit();
  }
}

async function resetGoodbyeFixture() {
  await clearCollectionGroup("promises");
  await db.collection(SCHEDULER_CHECKPOINT_COLLECTION).doc(GOODBYE_SWEEP_CHECKPOINT_ID).delete();
}

/** Seeds promises; `ageMs` is how long ago the meet-up stamp completed. */
async function seedPromises(
  prefix: string,
  rows: Array<{ status: string; ageMs: number }>,
  baseMs: number
): Promise<string[]> {
  const paths: string[] = [];
  let batch = db.batch();
  let ops = 0;
  for (let i = 0; i < rows.length; i += 1) {
    const ref = db
      .collection("chat_rooms")
      .doc(`${prefix}_room${i % 50}`)
      .collection("promises")
      .doc(`${prefix}_p${String(i).padStart(5, "0")}`);
    batch.set(ref, {
      promiseId: ref.id,
      status: rows[i].status,
      // Distinct, increasing-with-age timestamps (1 ms apart inside a bucket).
      meetupCompletedAt: Timestamp.fromMillis(baseMs - rows[i].ageMs - i),
    });
    paths.push(ref.path);
    ops += 1;
    if (ops === 400) {
      await batch.commit();
      batch = db.batch();
      ops = 0;
    }
  }
  if (ops > 0) await batch.commit();
  return paths;
}

/** The processing the schedule performs, reduced to its state transition. */
function completingProcessor(counters: { transactions: number; writes: number }) {
  return async (doc: QueryDocumentSnapshot): Promise<GoodbyeSweepOutcome> => {
    if (doc.get("status") !== "in_progress") return "skipped";
    counters.transactions += 1;
    const outcome = await db.runTransaction(async (tx) => {
      const fresh = await tx.get(doc.ref);
      if (fresh.get("status") !== "in_progress") return "skipped" as const;
      tx.update(doc.ref, { status: "completed", completionMode: "auto_without_goodbye_stamp" });
      return "completed" as const;
    });
    // Counted after commit: a transaction body may run more than once.
    if (outcome === "completed") counters.writes += 1;
    return outcome;
  };
}

async function statusCounts(prefix: string) {
  const snap = await db.collectionGroup("promises").get();
  const counts: Record<string, number> = {};
  for (const doc of snap.docs) {
    if (!doc.id.startsWith(prefix)) continue;
    const status = String(doc.get("status"));
    counts[status] = (counts[status] ?? 0) + 1;
  }
  return counts;
}

test("A1 goodbye sweep: old shape re-reads all history every run; the watermark sweep reads it once", async () => {
  await resetGoodbyeFixture();
  const now = Date.now();
  const cutoff = new Date(now - DAY);
  const prefix = `a1_${now.toString(36)}`;
  // 2,000 promises: 1,600 finished long ago, 300 due and still in progress,
  // 100 stamped less than 24 h ago (not due).
  const rows = [
    ...Array.from({ length: 1600 }, () => ({ status: "completed", ageMs: 30 * DAY })),
    ...Array.from({ length: 300 }, () => ({ status: "in_progress", ageMs: 2 * DAY })),
    ...Array.from({ length: 100 }, () => ({ status: "in_progress", ageMs: 2 * HOUR })),
  ];
  await seedPromises(prefix, rows, now);

  // OLD SHAPE (index.ts before AUD-12): one unpaginated read of everything
  // with meetupCompletedAt <= cutoff, then one transaction per document.
  const oldStarted = Date.now();
  const oldSnap = await db
    .collectionGroup("promises")
    .where("meetupCompletedAt", "<=", Timestamp.fromDate(cutoff))
    .get();
  const oldReadMs = Date.now() - oldStarted;
  assert.equal(oldSnap.size, 1900, "old shape reads every promise older than 24 h");

  const counters = { transactions: 0, writes: 0 };
  const first = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff,
    processPromise: completingProcessor(counters),
  });
  assert.equal(first.scanned, 1900, "the first run has no watermark and reads the backlog once");
  assert.equal(first.completed, 300);
  assert.equal(first.failed, 0);
  assert.equal(first.exhausted, true);
  assert.equal(counters.transactions, 300, "no transaction for promises that are not in_progress");
  assert.deepEqual(await statusCounts(prefix), { completed: 1900, in_progress: 100 });
  assert.equal((await readGoodbyeSweepWatermark(db))?.toMillis(), cutoff.getTime());

  // 15 minutes later nothing new is due: the old shape reads 1,900 documents
  // again (and ran 1,900 transactions); the sweep reads nothing.
  const laterCutoff = new Date(cutoff.getTime() + 15 * 60 * 1000);
  const oldAgain = await db
    .collectionGroup("promises")
    .where("meetupCompletedAt", "<=", Timestamp.fromDate(laterCutoff))
    .get();
  assert.equal(oldAgain.size, 1900);
  const second = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff: laterCutoff,
    processPromise: completingProcessor(counters),
  });
  assert.equal(second.scanned, 0, "steady state: nothing behind the watermark is read again");
  assert.equal(second.exhausted, true);
  assert.equal(counters.transactions, 300);

  // A day later the 100 recent promises are due: exactly those are read.
  const nextDay = new Date(now + 2 * HOUR);
  const third = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff: nextDay,
    processPromise: completingProcessor(counters),
  });
  assert.equal(third.scanned, 100);
  assert.equal(third.completed, 100);
  assert.deepEqual(await statusCounts(prefix), { completed: 2000 });

  console.log(
    `[AUD-12 goodbye] old shape: ${oldSnap.size} docs read + ${oldSnap.size} transactions per run ` +
      `(read ${oldReadMs}ms) | sweep run1: ${first.scanned} read, ${first.completed} completed, ` +
      `${first.pages} pages, ${first.durationMs}ms | run2: ${second.scanned} read, ${second.durationMs}ms | ` +
      `run3: ${third.scanned} read, ${third.durationMs}ms`
  );
  assert.ok(first.durationMs < 60_000, `first sweep took ${first.durationMs}ms`);
});

test("A2 goodbye sweep: a run cut short by its work cap resumes without skipping a due promise", async () => {
  await resetGoodbyeFixture();
  const now = Date.now();
  const cutoff = new Date(now - DAY);
  const prefix = `a2_${now.toString(36)}`;
  await seedPromises(
    prefix,
    Array.from({ length: 650 }, () => ({ status: "in_progress", ageMs: 3 * DAY })),
    now
  );
  const counters = { transactions: 0, writes: 0 };
  let runs = 0;
  let completed = 0;
  for (;;) {
    runs += 1;
    const summary = await sweepExpiredGoodbyePromises({
      firestore: db,
      cutoff,
      pageSize: 100,
      maxDocs: 200,
      processPromise: completingProcessor(counters),
    });
    completed += summary.completed;
    assert.ok(summary.scanned <= 200 + 100, "a run stops at its work cap (page granularity)");
    if (summary.exhausted) break;
    assert.ok(runs < 12, "the sweep must make progress every run");
  }
  assert.equal(completed, 650, "every due promise completed exactly once across runs");
  assert.equal(counters.writes, 650);
  assert.ok(runs >= 3, `needed ${runs} runs`);
  assert.deepEqual(await statusCounts(prefix), { completed: 650 });
});

test("A3 goodbye sweep: a run stopped by its time budget stores how far it got and the next run continues", async () => {
  await resetGoodbyeFixture();
  const now = Date.now();
  const cutoff = new Date(now - DAY);
  const prefix = `a3_${now.toString(36)}`;
  await seedPromises(
    prefix,
    Array.from({ length: 240 }, () => ({ status: "in_progress", ageMs: 3 * DAY })),
    now
  );
  const counters = { transactions: 0, writes: 0 };
  // The clock jumps past the budget after 90 promises were started.
  let fakeNow = 0;
  let startedCount = 0;
  const base = completingProcessor(counters);
  const interrupted = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff,
    pageSize: 60,
    concurrency: 4,
    timeBudgetMs: 1000,
    nowMs: () => fakeNow,
    processPromise: async (doc) => {
      startedCount += 1;
      if (startedCount >= 90) fakeNow = 5000;
      return base(doc);
    },
  });
  assert.equal(interrupted.exhausted, false);
  assert.ok(interrupted.scanned >= 90 && interrupted.scanned < 240, `scanned ${interrupted.scanned}`);
  assert.equal(interrupted.completed, interrupted.scanned, "everything that started was finished");

  const resumed = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff,
    processPromise: completingProcessor(counters),
  });
  assert.equal(resumed.exhausted, true);
  assert.equal(interrupted.completed + resumed.completed, 240, "no promise skipped, none completed twice");
  assert.equal(counters.writes, 240);
  assert.deepEqual(await statusCounts(prefix), { completed: 240 });
});

test("A4 goodbye sweep: a failed promise holds the watermark and is retried; an overlapping run cannot double-complete", async () => {
  await resetGoodbyeFixture();
  const now = Date.now();
  const cutoff = new Date(now - DAY);
  const prefix = `a4_${now.toString(36)}`;
  const paths = await seedPromises(
    prefix,
    Array.from({ length: 120 }, () => ({ status: "in_progress", ageMs: 3 * DAY })),
    now
  );
  // seedPromises makes later rows older, so this one sits mid-range.
  const poisoned = paths[60];
  const counters = { transactions: 0, writes: 0 };
  const base = completingProcessor(counters);
  const failures: string[] = [];
  const failing = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff,
    processPromise: async (doc) => {
      if (doc.ref.path === poisoned) throw new Error("transient failure");
      return base(doc);
    },
    onFailure: (doc) => failures.push(doc.ref.path),
  });
  assert.equal(failing.failed, 1);
  assert.deepEqual(failures, [poisoned]);
  assert.equal(failing.completed, 119);
  const held = await readGoodbyeSweepWatermark(db);
  const poisonedAt = (await db.doc(poisoned).get()).get("meetupCompletedAt") as Timestamp;
  assert.equal(held?.toMillis(), poisonedAt.toMillis(), "the watermark stops at the failed promise");
  assert.ok(held !== null && held.toMillis() < cutoff.getTime());

  // Two overlapping runs retry it: exactly one completes it.
  const [left, right] = await Promise.all([
    sweepExpiredGoodbyePromises({ firestore: db, cutoff, processPromise: completingProcessor(counters) }),
    sweepExpiredGoodbyePromises({ firestore: db, cutoff, processPromise: completingProcessor(counters) }),
  ]);
  assert.equal(left.completed + right.completed, 1, "the retried promise is completed once");
  assert.equal(left.failed + right.failed, 0);
  assert.equal(counters.writes, 120);
  assert.deepEqual(await statusCounts(prefix), { completed: 120 });
  assert.equal((await readGoodbyeSweepWatermark(db))?.toMillis(), cutoff.getTime());

  // A failure older than the hold window does not pin the watermark forever.
  await resetGoodbyeFixture();
  await seedPromises(`${prefix}_old`, [{ status: "in_progress", ageMs: 30 * DAY }], now);
  const abandoned = await sweepExpiredGoodbyePromises({
    firestore: db,
    cutoff,
    processPromise: async () => {
      throw new Error("permanent failure");
    },
  });
  assert.equal(abandoned.failed, 1);
  assert.equal(abandoned.abandonedFailures, 1);
  assert.equal((await readGoodbyeSweepWatermark(db))?.toMillis(), cutoff.getTime());
  // Leave no watermark behind for other suites sharing this emulator.
  await resetGoodbyeFixture();
});

// ---------------------------------------------------------------------------
// B. emailLinkTokens purge
// ---------------------------------------------------------------------------

async function resetTokenFixture() {
  for (;;) {
    const snap = await db.collection("emailLinkTokens").limit(400).get();
    if (snap.empty) break;
    const batch = db.batch();
    snap.docs.forEach((doc) => batch.delete(doc.ref));
    await batch.commit();
  }
  await db.collection(SCHEDULER_CHECKPOINT_COLLECTION).doc(EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID).delete();
}

async function seedTokens(now: Date) {
  const past = Timestamp.fromMillis(now.getTime() - DAY);
  const future = Timestamp.fromMillis(now.getTime() + DAY);
  let batch = db.batch();
  let ops = 0;
  const put = async (id: string, data: Record<string, unknown>) => {
    batch.set(db.collection("emailLinkTokens").doc(id), data);
    ops += 1;
    if (ops === 400) {
      await batch.commit();
      batch = db.batch();
      ops = 0;
    }
  };
  // 600 tokens that are kept on purpose sort first: mailbox-proven ones are
  // never purged, unexpired ones not yet.
  for (let i = 0; i < 450; i += 1) {
    await put(`a_kept_${String(i).padStart(4, "0")}`, { expiresAt: past, emailVerifiedUid: `uid_${i}` });
  }
  for (let i = 0; i < 150; i += 1) {
    await put(`b_live_${String(i).padStart(4, "0")}`, { expiresAt: future });
  }
  // 700 expired, unproven tokens sort behind them.
  for (let i = 0; i < 700; i += 1) {
    await put(`z_dead_${String(i).padStart(4, "0")}`, { expiresAt: past });
  }
  if (ops > 0) await batch.commit();
}

test("B1 token purge: the fixed 500-document window deletes nothing; the paged walk deletes every expired token", async () => {
  await resetTokenFixture();
  const now = new Date();
  await seedTokens(now);

  // OLD SHAPE (emailLinkTokenPurge.ts before AUD-25): limit(500), no cursor.
  const oldWindow = await db.collection("emailLinkTokens").limit(500).get();
  const oldCandidates = selectEmailLinkTokenIdsToPurge(
    oldWindow.docs.map((doc) => ({
      id: doc.id,
      expiresAt: doc.data().expiresAt ?? null,
      emailVerifiedUid: doc.data().emailVerifiedUid,
    })),
    now
  );
  assert.equal(oldWindow.size, 500);
  assert.equal(oldCandidates.length, 0, "BUG: 700 expired tokens exist and the old window selects none, every night");

  const started = Date.now();
  const result = await purgeExpiredEmailLinkTokens(db, { now });
  const durationMs = Date.now() - started;
  assert.equal(result.scanned, 1300);
  assert.equal(result.deleted, 700);
  assert.equal(result.skipped, 600);
  assert.equal(result.exhausted, true);
  const left = await db.collection("emailLinkTokens").get();
  assert.equal(left.size, 600);
  assert.ok(left.docs.every((doc) => !doc.id.startsWith("z_dead_")));
  assert.equal(left.docs.filter((doc) => doc.id.startsWith("a_kept_")).length, 450, "proven tokens are kept");
  assert.equal(left.docs.filter((doc) => doc.id.startsWith("b_live_")).length, 150, "unexpired tokens are kept");
  console.log(
    `[AUD-25 token purge] old window: ${oldWindow.size} read, ${oldCandidates.length} deleted | ` +
      `paged: ${result.scanned} read, ${result.deleted} deleted, ${result.pages} pages, ${durationMs}ms`
  );

  // A second run finds nothing to delete and still terminates.
  const again = await purgeExpiredEmailLinkTokens(db, { now });
  assert.equal(again.deleted, 0);
  assert.equal(again.scanned, 600);
  assert.equal(again.exhausted, true);
});

test("B2 token purge: an interrupted run resumes behind the documents it already handled", async () => {
  await resetTokenFixture();
  const now = new Date();
  await seedTokens(now);

  const first = await purgeExpiredEmailLinkTokens(db, { now, limit: 200, maxDocs: 400 });
  assert.equal(first.exhausted, false);
  assert.equal(first.scanned, 400);
  assert.equal(first.deleted, 0, "the first 400 ids are all kept tokens");
  const cursor = (
    await db.collection(SCHEDULER_CHECKPOINT_COLLECTION).doc(EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID).get()
  ).get("cursor");
  assert.equal(cursor, "a_kept_0399");

  let deleted = 0;
  let runs = 1;
  for (;;) {
    runs += 1;
    const next = await purgeExpiredEmailLinkTokens(db, { now, limit: 200, maxDocs: 400 });
    deleted += next.deleted;
    if (next.exhausted) break;
    assert.ok(runs < 10, "the purge must make progress every run");
  }
  assert.equal(deleted, 700, "every expired token behind the kept ones is reached across runs");
  assert.equal((await db.collection("emailLinkTokens").get()).size, 600);
  assert.equal(
    (
      await db.collection(SCHEDULER_CHECKPOINT_COLLECTION).doc(EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID).get()
    ).get("cursor"),
    null,
    "a finished pass starts from the beginning next time"
  );
});
