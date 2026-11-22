/**
 * AUD-12 — scan driver for autoCompleteExpiredGoodbyeSafetyStamps.
 *
 * The schedule used to read EVERY promise whose meet-up stamp was older than
 * 24 h — including every promise completed months ago — in one unpaginated
 * collection-group query, then run one transaction per document, one at a
 * time, inside the default 60 s timeout. The read set only ever grew.
 *
 * `meetupCompletedAt` is written by the server only (safetyStamp.ts, a
 * serverTimestamp at the confirmed -> in_progress transition; rules deny it to
 * clients), so it is monotonic in wall-clock time and a promise becomes due
 * exactly once, 24 h later. That makes a watermark sound: once every promise
 * with `meetupCompletedAt <= W` has been evaluated while already due, nothing
 * at or below W can become due again. Each run therefore reads only
 * `[watermark, cutoff]`, in pages, with bounded parallelism and a time/work
 * budget, and stores how far it got.
 *
 * Index: the query is a range + orderBy on the single field
 * `meetupCompletedAt` of collection group `promises`, served by the existing
 * collection-group field override in firestore.indexes.json. No composite
 * index (and no `status` filter, which would need one) is used.
 */
import {
  Timestamp,
  type Firestore,
  type Query,
  type QueryDocumentSnapshot,
} from "firebase-admin/firestore";

import { runWithConcurrency } from "./shared/boundedConcurrency";

export const SCHEDULER_CHECKPOINT_COLLECTION = "schedulerCheckpoints";
export const GOODBYE_SWEEP_CHECKPOINT_ID = "autoCompleteExpiredGoodbyeSafetyStamps";

/** "completed": the promise was auto-completed now. "skipped": nothing to do. */
export type GoodbyeSweepOutcome = "completed" | "skipped";

export type GoodbyeSweepSummary = {
  scanned: number;
  completed: number;
  skipped: number;
  failed: number;
  pages: number;
  /** true when the run reached the cutoff (no due promise left unread). */
  exhausted: boolean;
  /** Failures older than the hold window that the watermark moved past. */
  abandonedFailures: number;
  watermarkMs: number | null;
  durationMs: number;
};

export type GoodbyeSweepOptions = {
  firestore: Firestore;
  /** Promises with meetupCompletedAt <= cutoff are due. */
  cutoff: Date;
  /**
   * Handles one due promise. Must be idempotent (it runs again for the
   * watermark boundary document and after a failure). Throwing marks the
   * promise failed: the watermark is held at it so the next run retries.
   */
  processPromise: (doc: QueryDocumentSnapshot) => Promise<GoodbyeSweepOutcome>;
  onFailure?: (doc: QueryDocumentSnapshot, error: unknown) => void;
  pageSize?: number;
  concurrency?: number;
  /** Upper bound of promises read per run; the next run continues. */
  maxDocs?: number;
  timeBudgetMs?: number;
  /** How long a failing promise may pin the watermark before it is passed. */
  failureHoldMs?: number;
  nowMs?: () => number;
};

const DEFAULT_PAGE_SIZE = 200;
const DEFAULT_CONCURRENCY = 8;
const DEFAULT_MAX_DOCS = 5000;
const DEFAULT_TIME_BUDGET_MS = 120_000;
const DEFAULT_FAILURE_HOLD_MS = 7 * 24 * 60 * 60 * 1000;

function compareTimestamps(a: Timestamp, b: Timestamp): number {
  if (a.seconds !== b.seconds) return a.seconds < b.seconds ? -1 : 1;
  if (a.nanoseconds !== b.nanoseconds) return a.nanoseconds < b.nanoseconds ? -1 : 1;
  return 0;
}

function earlier(a: Timestamp, b: Timestamp): Timestamp {
  return compareTimestamps(a, b) <= 0 ? a : b;
}

function checkpointRef(firestore: Firestore) {
  return firestore
    .collection(SCHEDULER_CHECKPOINT_COLLECTION)
    .doc(GOODBYE_SWEEP_CHECKPOINT_ID);
}

export async function readGoodbyeSweepWatermark(
  firestore: Firestore
): Promise<Timestamp | null> {
  const snap = await checkpointRef(firestore).get();
  const value = snap.get("watermark");
  return value instanceof Timestamp ? value : null;
}

/**
 * Moves the watermark forward only. Two overlapping runs each make a claim
 * that is valid on its own (everything at or below it was evaluated while
 * due), so the larger claim is safe to keep.
 */
async function advanceWatermark(
  firestore: Firestore,
  watermark: Timestamp,
  summary: Record<string, unknown>
): Promise<void> {
  const ref = checkpointRef(firestore);
  await firestore.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const current = snap.get("watermark");
    const next =
      current instanceof Timestamp && compareTimestamps(current, watermark) > 0
        ? current
        : watermark;
    tx.set(
      ref,
      { watermark: next, lastRun: summary, updatedAt: Timestamp.now() },
      { merge: true }
    );
  });
}

export async function sweepExpiredGoodbyePromises(
  options: GoodbyeSweepOptions
): Promise<GoodbyeSweepSummary> {
  const { firestore } = options;
  const nowMs = options.nowMs ?? (() => Date.now());
  const startedAt = nowMs();
  const pageSize = Math.max(1, options.pageSize ?? DEFAULT_PAGE_SIZE);
  const concurrency = Math.max(1, options.concurrency ?? DEFAULT_CONCURRENCY);
  const maxDocs = Math.max(1, options.maxDocs ?? DEFAULT_MAX_DOCS);
  const timeBudgetMs = options.timeBudgetMs ?? DEFAULT_TIME_BUDGET_MS;
  const failureHoldMs = options.failureHoldMs ?? DEFAULT_FAILURE_HOLD_MS;
  const cutoff = Timestamp.fromDate(options.cutoff);
  const outOfTime = () => nowMs() - startedAt >= timeBudgetMs;

  const lowerBound = await readGoodbyeSweepWatermark(firestore);

  const summary: GoodbyeSweepSummary = {
    scanned: 0,
    completed: 0,
    skipped: 0,
    failed: 0,
    pages: 0,
    exhausted: false,
    abandonedFailures: 0,
    watermarkMs: lowerBound ? lowerBound.toMillis() : null,
    durationMs: 0,
  };

  const failedAt: Timestamp[] = [];
  let cursor: QueryDocumentSnapshot | null = null;
  // Highest meetupCompletedAt such that every promise at or below it was
  // handed to processPromise in this run.
  let processedThrough: Timestamp | null = null;

  for (;;) {
    let query: Query = firestore
      .collectionGroup("promises")
      .where("meetupCompletedAt", "<=", cutoff);
    // Inclusive: promises sharing the boundary timestamp are read again
    // rather than risk skipping one (processPromise is idempotent).
    if (lowerBound) query = query.where("meetupCompletedAt", ">=", lowerBound);
    query = query.orderBy("meetupCompletedAt", "asc").limit(pageSize);
    if (cursor) query = query.startAfter(cursor);

    const page = await query.get();
    if (page.empty) {
      summary.exhausted = true;
      break;
    }
    summary.pages += 1;

    let interrupted = false;
    const started = await runWithConcurrency(
      page.docs,
      concurrency,
      async (doc) => {
        try {
          const outcome = await options.processPromise(doc);
          if (outcome === "completed") summary.completed += 1;
          else summary.skipped += 1;
        } catch (error) {
          summary.failed += 1;
          const at = doc.get("meetupCompletedAt");
          if (at instanceof Timestamp) failedAt.push(at);
          options.onFailure?.(doc, error);
        }
      },
      () => {
        if (outOfTime()) interrupted = true;
        return interrupted;
      }
    );
    summary.scanned += started;

    // runWithConcurrency starts items in order, so the first `started`
    // documents of the page are exactly the ones that were handled.
    if (started > 0) {
      const lastHandled = page.docs[started - 1].get("meetupCompletedAt");
      if (lastHandled instanceof Timestamp) processedThrough = lastHandled;
    }
    if (interrupted || started < page.size) break;

    cursor = page.docs[page.docs.length - 1];
    if (page.size < pageSize) {
      summary.exhausted = true;
      break;
    }
    if (summary.scanned >= maxDocs || outOfTime()) break;
  }

  // A run that read up to the cutoff has evaluated everything due so far.
  let nextWatermark: Timestamp | null = summary.exhausted ? cutoff : processedThrough;
  if (nextWatermark) {
    // A failed promise pins the watermark so the next run retries it — but
    // not forever: a permanently failing document would otherwise make the
    // scanned range grow without bound again.
    const holdFloorMs = cutoff.toMillis() - failureHoldMs;
    for (const at of failedAt) {
      if (at.toMillis() < holdFloorMs) {
        summary.abandonedFailures += 1;
        continue;
      }
      nextWatermark = earlier(nextWatermark, at);
    }
    summary.watermarkMs = nextWatermark.toMillis();
  }
  summary.durationMs = nowMs() - startedAt;

  if (nextWatermark) {
    await advanceWatermark(firestore, nextWatermark, {
      scanned: summary.scanned,
      completed: summary.completed,
      skipped: summary.skipped,
      failed: summary.failed,
      exhausted: summary.exhausted,
      durationMs: summary.durationMs,
    });
  }
  return summary;
}
