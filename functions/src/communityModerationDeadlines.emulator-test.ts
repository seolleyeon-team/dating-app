/**
 * AUD-14 — moderation deadline alerts on the real Firestore engine.
 *
 * S1 and S2 go through the scheduled handler itself and fail on the previous
 * source (newest-150 scan, `unread` reset on every run).
 *
 * The sweep reads the whole `reports` collection, so this file must not share
 * an emulator run with another suite that writes reports:
 *   npx firebase-tools emulators:exec --only firestore --project demo-mod \
 *     "node --test functions/<outDir>/communityModerationDeadlines.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getApps, initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
if (getApps().length === 0) initializeApp();

import {
  MODERATION_DEADLINE_SCHEDULE_OPTIONS,
  createCommunityModerationDeadlineSchedule,
  moderationAlertId,
  runCommunityModerationDeadlineSweep,
} from "./communityModeration";

const db = getFirestore();
const HOUR = 3600_000;
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

async function wipe() {
  await db.recursiveDelete(db.collection("reports"));
  await db.recursiveDelete(db.collection("moderation_alerts"));
}

type Seed = Record<string, unknown> & { id?: string };
function bamboo(createdAtMs: number, extra: Seed = {}): Seed {
  return {
    reporterId: "rep", reportedId: "author", reason: "spam", source: "bamboo_post",
    contentType: "bamboo_post", contentId: "p1", status: "pending", reportKind: "community",
    dataPartition: "production", createdAt: Timestamp.fromMillis(createdAtMs),
    deadlineAt: Timestamp.fromMillis(createdAtMs + 24 * HOUR), ...extra,
  };
}
function account(createdAtMs: number, extra: Seed = {}): Seed {
  return {
    reporterId: "rep", reportedId: "other", reason: "spam", source: "profile", status: "pending",
    reportKind: "profile", contentSnapshot: null, dataPartition: "production",
    createdAt: Timestamp.fromMillis(createdAtMs), deadlineAt: Timestamp.fromMillis(createdAtMs + 24 * HOUR), ...extra,
  };
}
async function seed(prefix: string, docs: Seed[]): Promise<string[]> {
  const ids: string[] = [];
  for (let i = 0; i < docs.length; i += 400) {
    const batch = db.batch();
    for (const doc of docs.slice(i, i + 400)) {
      const { id, ...data } = doc;
      const ref = db.collection("reports").doc(id ?? fresh(prefix));
      ids.push(ref.id);
      batch.set(ref, data);
    }
    await batch.commit();
  }
  return ids;
}
const alertDocs = async () => (await db.collection("moderation_alerts").get()).docs;
const alertsOf = async (reportId: string) => (await alertDocs()).filter((d) => d.get("reportId") === reportId);
const runSchedule = () =>
  (createCommunityModerationDeadlineSchedule(db) as unknown as { run: (event: unknown) => Promise<void> }).run({});

test("the schedule has an explicit timeout and memory (the 60 s default bounded an unpaged scan)", () => {
  assert.equal(MODERATION_DEADLINE_SCHEDULE_OPTIONS.schedule, "every 15 minutes");
  assert.equal(MODERATION_DEADLINE_SCHEDULE_OPTIONS.timeZone, "Asia/Seoul");
  assert.equal(MODERATION_DEADLINE_SCHEDULE_OPTIONS.timeoutSeconds, 300);
  assert.equal(MODERATION_DEADLINE_SCHEDULE_OPTIONS.memory, "256MiB");
});

test("S1 [schedule] open Bamboo reports behind more than 150 newer reports still get their deadline alert", async () => {
  await wipe();
  const now = Date.now();
  const due = await seed("due", [
    bamboo(now - 21 * HOUR),
    bamboo(now - 23.5 * HOUR, { source: "bamboo_comment", status: "reviewing" }),
    bamboo(now - 30 * HOUR),
    // legacy: written before deadlineAt existed
    { reporterId: "rep", reportedId: "author", reason: "old", source: "bamboo_post", status: "pending", createdAt: Timestamp.fromMillis(now - 72 * HOUR) },
  ]);
  await seed("noise", Array.from({ length: 160 }, (_, i) => account(now - 60_000 - i)));
  await seed("noise", Array.from({ length: 40 }, (_, i) => bamboo(now - 2 * HOUR - i)));
  await runSchedule();
  const levels = new Map<string, string[]>();
  for (const doc of await alertDocs()) {
    levels.set(doc.get("reportId"), [...(levels.get(doc.get("reportId")) ?? []), doc.get("level")]);
  }
  assert.deepEqual(due.map((id) => levels.get(id)), [["20h"], ["23h"], ["overdue"], ["overdue"]]);
  assert.equal(levels.size, 4, "nothing else is alerted");
  const legacy = (await alertsOf(due[3]))[0];
  assert.ok(legacy.get("deadlineAt") instanceof Timestamp, "a legacy report's alert carries the derived deadline");
  assert.equal((legacy.get("deadlineAt") as Timestamp).toMillis(), now - 48 * HOUR);
});

test("S2 [schedule] a second run creates nothing and keeps the operator's read state", async () => {
  await wipe();
  const now = Date.now();
  await seed("read", [bamboo(now - 21 * HOUR), bamboo(now - 23.5 * HOUR), bamboo(now - 30 * HOUR), bamboo(now - 80 * HOUR, { status: "reviewing" })]);
  await runSchedule();
  const before = await alertDocs();
  assert.equal(before.length, 4);
  for (const doc of before) await doc.ref.update({ unread: false, acknowledgedBy: "op_1" });
  const createdAt = new Map(before.map((d) => [d.id, (d.get("createdAt") as Timestamp).toMillis()]));
  await runSchedule();
  await runSchedule();
  const after = await alertDocs();
  assert.equal(after.length, 4, "repeated runs create nothing new");
  for (const doc of after) {
    assert.equal(doc.get("unread"), false, `${doc.id} read state reset`);
    assert.equal(doc.get("acknowledgedBy"), "op_1");
    assert.equal((doc.get("createdAt") as Timestamp).toMillis(), createdAt.get(doc.id), "createdAt not rewritten");
  }
});

test("S3 just before / just after each threshold; one alert per level; hourly overdue reminder", async () => {
  await wipe();
  const t0 = Date.UTC(2026, 10, 20, 3, 0, 0);
  const [id] = await seed("edge", [bamboo(t0)]);
  const at = async (offsetMs: number) => {
    const stats = await runCommunityModerationDeadlineSweep(db, { nowMs: t0 + offsetMs });
    return { stats, ids: (await alertsOf(id)).map((d) => d.id).sort() };
  };
  assert.deepEqual((await at(19 * HOUR)).ids, []);
  const justBefore20 = await at(20 * HOUR - 1);
  assert.deepEqual(justBefore20.ids, []);
  assert.equal(justBefore20.stats.scanned, 0, "a report that cannot be due is not even read");
  assert.deepEqual((await at(20 * HOUR)).ids, [`${id}_20h_once`]);
  assert.deepEqual((await at(22 * HOUR)).ids, [`${id}_20h_once`]);
  assert.deepEqual((await at(23 * HOUR - 1)).ids, [`${id}_20h_once`]);
  assert.deepEqual((await at(23 * HOUR)).ids, [`${id}_20h_once`, `${id}_23h_once`]);
  const justBeforeDeadline = await at(24 * HOUR - 1);
  assert.deepEqual(justBeforeDeadline.ids, [`${id}_20h_once`, `${id}_23h_once`]);
  assert.equal(justBeforeDeadline.stats.created, 0);
  const overdueId = moderationAlertId(id, "overdue", t0 + 24 * HOUR);
  const atDeadline = await at(24 * HOUR);
  assert.deepEqual(atDeadline.ids, [`${id}_20h_once`, `${id}_23h_once`, overdueId].sort());
  assert.equal(atDeadline.stats.created, 1);
  // the same hour again (the 15-minute cadence): nothing new
  for (const minutes of [15, 30, 45]) {
    const again = await at(24 * HOUR + minutes * 60_000);
    assert.equal(again.stats.created, 0);
    assert.equal(again.stats.existing, 1);
    assert.equal(again.ids.length, 3);
  }
  // next clock hour while still open: one reminder (unchanged 2026-09-17 behaviour)
  const nextHour = await at(25 * HOUR);
  assert.equal(nextHour.stats.created, 1);
  assert.equal(nextHour.ids.length, 4);
  // once the report is closed nothing more is created
  await db.collection("reports").doc(id).update({ status: "actioned" });
  const closed = await at(30 * HOUR);
  assert.equal(closed.stats.created, 0);
  assert.equal(closed.stats.scanned, 0);
  assert.equal(closed.ids.length, 4);
});

test("S4 processed reports, account reports and malformed legacy documents are never alerted", async () => {
  await wipe();
  const now = Date.now();
  const old = now - 40 * HOUR;
  const ids = await seed("skip", [
    bamboo(old, { status: "actioned" }),
    bamboo(old, { status: "dismissed" }),
    account(old),
    account(old, { status: "reviewing" }),
    bamboo(old, { status: "test_only" }),
    { ...bamboo(old), status: undefined as unknown as string },
    // no createdAt and no deadlineAt: cannot be due, must not throw
    { reporterId: "rep", reportedId: "author", reason: "x", source: "bamboo_post", status: "pending" },
  ].map((doc) => Object.fromEntries(Object.entries(doc).filter(([, v]) => v !== undefined))));
  const [open, reviewing, playReview] = await seed("alert", [
    bamboo(old),
    bamboo(old, { status: "reviewing" }),
    bamboo(old, { dataPartition: "play_review", reviewFixture: true }),
  ]);
  const stats = await runCommunityModerationDeadlineSweep(db, { nowMs: now });
  assert.equal(stats.created, 3);
  assert.equal(stats.scanned, 3, "only open Bamboo reports are read");
  for (const id of ids) assert.equal((await alertsOf(id)).length, 0, id);
  assert.equal((await alertsOf(open))[0].get("level"), "overdue");
  assert.equal((await alertsOf(reviewing))[0].get("level"), "overdue");
  assert.equal((await alertsOf(open))[0].get("dataPartition"), "production");
  assert.equal((await alertsOf(playReview))[0].get("dataPartition"), "play_review", "the alert stays in its partition");
  assert.equal((await alertsOf(open))[0].get("unread"), true);
});

test("S5 1,050 due reports among 1,850: every one alerted exactly once, pages bounded", async () => {
  await wipe();
  const now = Date.now();
  const due = await seed("many", Array.from({ length: 1050 }, (_, i) =>
    bamboo(now - 21 * HOUR - i * 1000, i % 3 === 0 ? { source: "bamboo_comment" } : i % 5 === 0 ? { status: "reviewing" } : {})));
  await seed("young", Array.from({ length: 300 }, (_, i) => bamboo(now - HOUR - i)));
  await seed("closed", Array.from({ length: 300 }, (_, i) => bamboo(now - 50 * HOUR - i, { status: i % 2 ? "actioned" : "dismissed" })));
  await seed("acct", Array.from({ length: 200 }, (_, i) => account(now - 50 * HOUR - i)));
  const started = Date.now();
  const first = await runCommunityModerationDeadlineSweep(db, { nowMs: now });
  const firstMs = Date.now() - started;
  assert.equal(first.scanned, 1050, "reads are bounded by the due open Bamboo reports, not by the collection");
  assert.equal(first.due, 1050);
  assert.equal(first.created, 1050);
  assert.equal(first.existing, 0);
  assert.equal(first.truncated, false);
  const alerts = await alertDocs();
  assert.equal(alerts.length, 1050);
  assert.deepEqual([...new Set(alerts.map((d) => d.get("reportId")))].sort(), [...due].sort());
  const startedAgain = Date.now();
  const second = await runCommunityModerationDeadlineSweep(db, { nowMs: now });
  const secondMs = Date.now() - startedAgain;
  assert.equal(second.created, 0);
  assert.equal(second.existing, 1050);
  assert.equal((await alertDocs()).length, 1050);
  console.log(`[AUD-14 S5] 1850 reports / 1050 due: run 1 = ${first.scanned} report reads + ${first.due} alert reads, ` +
    `${first.created} writes, ${first.pages} pages, ${firstMs} ms; run 2 = ${second.scanned} + ${second.due} reads, ` +
    `${second.created} writes, ${secondMs} ms`);
});

test("S6 two overlapping runs: no duplicate, no error, no reset", async () => {
  await wipe();
  const now = Date.now();
  await seed("conc", Array.from({ length: 450 }, (_, i) => bamboo(now - 26 * HOUR - i * 1000)));
  const [a, b, c] = await Promise.all([
    runCommunityModerationDeadlineSweep(db, { nowMs: now, pageSize: 50 }),
    runCommunityModerationDeadlineSweep(db, { nowMs: now, pageSize: 70 }),
    runCommunityModerationDeadlineSweep(db, { nowMs: now, pageSize: 200 }),
  ]);
  const alerts = await alertDocs();
  assert.equal(alerts.length, 450);
  assert.equal(new Set(alerts.map((d) => d.get("reportId"))).size, 450);
  assert.equal(a.created + b.created + c.created, 450, "each alert was created by exactly one run");
  assert.equal(a.due, 450);
  assert.equal(b.due, 450);
});

test("S7 old unprocessed legacy reports (no deadlineAt) are alerted with a derived deadline", async () => {
  await wipe();
  const now = Date.now();
  const created = now - 5 * 24 * HOUR;
  const [legacy] = await seed("legacy", [
    { reporterId: "rep", reportedId: "author", reason: "old", source: "bamboo_comment", status: "pending", createdAt: Timestamp.fromMillis(created) },
  ]);
  const stats = await runCommunityModerationDeadlineSweep(db, { nowMs: now });
  assert.equal(stats.created, 1);
  const [alert] = await alertsOf(legacy);
  assert.equal(alert.get("level"), "overdue");
  assert.equal((alert.get("deadlineAt") as Timestamp).toMillis(), created + 24 * HOUR);
  assert.equal(alert.get("dataPartition"), "production");
});

test("S8 while the composite index is missing the sweep falls back to a status scan with the same result", async () => {
  await wipe();
  const now = Date.now();
  const due = await seed("fb", Array.from({ length: 230 }, (_, i) => bamboo(now - 25 * HOUR - i * 1000)));
  await seed("fbskip", [...Array.from({ length: 30 }, (_, i) => account(now - 25 * HOUR - i)), bamboo(now - HOUR), bamboo(now - 30 * HOUR, { status: "dismissed" })]);
  // What production answers until reports(source,status,createdAt) is built.
  const withoutIndex = new Proxy(db, {
    get(target, prop) {
      if (prop !== "collection") {
        const value = Reflect.get(target, prop);
        return typeof value === "function" ? value.bind(target) : value;
      }
      return (name: string) => {
        const collection = target.collection(name);
        if (name !== "reports") return collection;
        return new Proxy(collection, {
          get(inner, key) {
            if (key === "where") {
              return (field: string, ...rest: unknown[]) => {
                if (field === "source") throw Object.assign(new Error("9 FAILED_PRECONDITION: The query requires an index."), { code: 9 });
                return (inner.where as (...args: unknown[]) => unknown)(field, ...rest);
              };
            }
            const value = Reflect.get(inner, key);
            return typeof value === "function" ? value.bind(inner) : value;
          },
        });
      };
    },
  }) as Firestore;
  const stats = await runCommunityModerationDeadlineSweep(withoutIndex, { nowMs: now, pageSize: 100 });
  assert.equal(stats.usedFallback, true);
  assert.equal(stats.created, 230);
  const alerts = await alertDocs();
  assert.deepEqual([...new Set(alerts.map((d) => d.get("reportId")))].sort(), [...due].sort());
  // and the indexed path agrees: nothing left to create
  const indexed = await runCommunityModerationDeadlineSweep(db, { nowMs: now });
  assert.equal(indexed.usedFallback, false);
  assert.equal(indexed.created, 0);
  assert.equal(indexed.existing, 230);
});
