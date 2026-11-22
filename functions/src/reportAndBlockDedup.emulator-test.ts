/**
 * REPORT-DEDUP — one open account report per (reporter, reported) pair, on the
 * real Firestore engine through the real index export.
 *
 * Before the fix only the first (deterministic) report was checked: once it was
 * closed, every later call created another random-id report, so D5–D8 and D10
 * fail on the previous source.
 *
 * Run (repo root, JDK 21):
 *   npx firebase-tools emulators:exec --only firestore --project demo-mod \
 *     "node --test functions/<outDir>/reportAndBlockDedup.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { reportAndBlockUser } from "./index";
import { PAIR_LATEST_REPORT_FIELD, accountReportId } from "./reportAndBlock";

type Runnable = { run: (request: unknown) => Promise<unknown> };
type Result = Record<string, unknown>;
const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid,
    isStudentVerified: true,
    studentEmail: `${uid}@yonsei.ac.kr`,
    nickname: uid,
    isActive: true,
    ...extra,
  });
}

async function pair(extra: Record<string, unknown> = {}) {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a, extra);
  await seedUser(b, extra);
  return { a, b };
}

function report(uid: string, data: Record<string, unknown>) {
  return (reportAndBlockUser as unknown as Runnable).run({ data, auth: { uid, token: {} }, rawRequest: {} }) as Promise<Result>;
}

async function failure(promise: Promise<unknown>): Promise<{ code: string; message: string }> {
  try {
    await promise;
  } catch (error) {
    return { code: String((error as { code?: string }).code), message: String((error as Error).message) };
  }
  return { code: "ok", message: "" };
}

const pairReports = async (a: string, b: string) =>
  (await db.collection("reports").where("reporterId", "==", a).get()).docs.filter((d) => d.get("reportedId") === b);
const openOf = async (a: string, b: string) =>
  (await pairReports(a, b)).filter((d) => ["pending", "reviewing"].includes(String(d.get("status"))));
const close = (id: string, status = "dismissed") => db.collection("reports").doc(id).update({ status });
const fulfilled = (runs: PromiseSettledResult<Result>[]) =>
  runs.filter((r): r is PromiseFulfilledResult<Result> => r.status === "fulfilled").map((r) => r.value);

test("D1 first report: one pending report under the pair's deterministic id", async () => {
  const { a, b } = await pair();
  const first = await report(a, { reportedUserId: b, reason: "spam" });
  assert.equal(first.reportId, accountReportId(a, b));
  assert.equal(first.duplicate, undefined);
  assert.equal((await pairReports(a, b)).length, 1);
  assert.equal((await openOf(a, b)).length, 1);
});

test("D2 the same report retried returns the open report and writes no second one", async () => {
  const { a, b } = await pair();
  const first = await report(a, { reportedUserId: b, reason: "spam" });
  for (let i = 0; i < 3; i++) {
    const retry = await report(a, { reportedUserId: b, reason: "spam" });
    assert.equal(retry.reportId, first.reportId);
    assert.equal(retry.duplicate, true);
  }
  assert.equal((await pairReports(a, b)).length, 1);
});

test("D3 concurrent first reports: exactly one report", async () => {
  const { a, b } = await pair();
  const runs = await Promise.allSettled(Array.from({ length: 8 }, () => report(a, { reportedUserId: b, reason: "spam" })));
  const ok = fulfilled(runs);
  assert.ok(ok.length >= 1);
  assert.equal(new Set(ok.map((r) => r.reportId)).size, 1);
  assert.equal(ok.filter((r) => r.duplicate !== true).length, 1, "exactly one call created the report");
  assert.equal((await pairReports(a, b)).length, 1);
});

test("D4 after the report is resolved a new report is allowed: one new record, history kept", async () => {
  const { a, b } = await pair();
  const first = await report(a, { reportedUserId: b, reason: "spam" });
  await close(String(first.reportId), "actioned");
  const second = await report(a, { reportedUserId: b, reason: "again" });
  assert.notEqual(second.reportId, first.reportId);
  assert.equal(second.duplicate, undefined);
  const docs = await pairReports(a, b);
  assert.deepEqual(docs.map((d) => d.get("status")).sort(), ["actioned", "pending"]);
  const anchor = await db.collection("reports").doc(accountReportId(a, b)).get();
  assert.equal(anchor.get("status"), "actioned", "the resolved report keeps its outcome");
  assert.equal(anchor.get("reason"), "spam");
  assert.equal(anchor.get(PAIR_LATEST_REPORT_FIELD), second.reportId);
});

test("D5 re-report while the SECOND report is open is deduplicated", async () => {
  const { a, b } = await pair();
  const first = await report(a, { reportedUserId: b, reason: "spam" });
  await close(String(first.reportId));
  const second = await report(a, { reportedUserId: b, reason: "again" });
  const third = await report(a, { reportedUserId: b, reason: "and again" });
  assert.equal(third.reportId, second.reportId);
  assert.equal(third.duplicate, true);
  assert.equal((await pairReports(a, b)).length, 2);
  assert.equal((await openOf(a, b)).length, 1);
  // the second report under review is still the open one
  await db.collection("reports").doc(String(second.reportId)).update({ status: "reviewing" });
  const fourth = await report(a, { reportedUserId: b, reason: "still" });
  assert.equal(fourth.reportId, second.reportId);
  assert.equal((await pairReports(a, b)).length, 2);
});

test("D6 third / fourth duplicates sent concurrently after a resolution: exactly one new report", async () => {
  const { a, b } = await pair();
  const first = await report(a, { reportedUserId: b, reason: "spam" });
  await close(String(first.reportId));
  const runs = await Promise.allSettled(Array.from({ length: 8 }, (_, i) => report(a, { reportedUserId: b, reason: `r${i}` })));
  const ok = fulfilled(runs);
  assert.ok(ok.length >= 1);
  assert.equal(new Set(ok.map((r) => r.reportId)).size, 1);
  assert.equal(ok.filter((r) => r.duplicate !== true).length, 1);
  assert.equal((await pairReports(a, b)).length, 2);
  assert.equal((await openOf(a, b)).length, 1);
});

test("D7 each resolution allows exactly one more report (third, fourth), never two open", async () => {
  const { a, b } = await pair();
  const ids: string[] = [];
  for (let round = 0; round < 4; round++) {
    const created = await report(a, { reportedUserId: b, reason: `round ${round}` });
    assert.equal(created.duplicate, undefined, `round ${round} creates`);
    assert.ok(!ids.includes(String(created.reportId)));
    ids.push(String(created.reportId));
    const dup = await report(a, { reportedUserId: b, reason: `round ${round} dup` });
    assert.equal(dup.reportId, created.reportId);
    assert.equal(dup.duplicate, true);
    assert.equal((await openOf(a, b)).length, 1);
    await close(String(created.reportId), round % 2 ? "actioned" : "dismissed");
  }
  const docs = await pairReports(a, b);
  assert.equal(docs.length, 4, "every historical report is preserved");
  assert.equal((await openOf(a, b)).length, 0);
});

test("D8 a moderation status change racing a report never leaves two open reports", async () => {
  for (let round = 0; round < 6; round++) {
    const { a, b } = await pair();
    const first = await report(a, { reportedUserId: b, reason: "spam" });
    await close(String(first.reportId));
    const second = await report(a, { reportedUserId: b, reason: "second" });
    const [, ...runs] = await Promise.allSettled([
      close(String(second.reportId), "actioned"),
      report(a, { reportedUserId: b, reason: "race 1" }),
      report(a, { reportedUserId: b, reason: "race 2" }),
      report(a, { reportedUserId: b, reason: "race 3" }),
    ]);
    const ok = fulfilled(runs as PromiseSettledResult<Result>[]);
    const open = await openOf(a, b);
    const all = await pairReports(a, b);
    assert.ok(open.length <= 1, `round ${round}: ${open.length} open reports`);
    assert.ok(all.length === 2 || all.length === 3, `round ${round}: ${all.length} reports`);
    // every answer names a report of this pair; a created report is unique
    assert.ok(ok.filter((r) => r.duplicate !== true).length <= 1);
    for (const r of ok) assert.ok(all.some((d) => d.id === r.reportId));
    assert.equal((await db.collection("reports").doc(String(second.reportId)).get()).get("status"), "actioned");
  }
});

test("D9 partitions are isolated: review fixtures and production pairs never share a tracker", async () => {
  const prod = await pair();
  const review = await pair({ dataPartition: "play_review" });
  const p1 = await report(prod.a, { reportedUserId: prod.b, reason: "x" });
  const r1 = await report(review.a, { reportedUserId: review.b, reason: "x" });
  assert.notEqual(p1.reportId, r1.reportId);
  assert.equal((await db.collection("reports").doc(String(r1.reportId)).get()).get("dataPartition"), "play_review");
  assert.equal((await db.collection("reports").doc(String(p1.reportId)).get()).get("dataPartition"), "production");
  // cross-partition calls are refused and neither create nor dedupe anything
  assert.equal((await failure(report(prod.a, { reportedUserId: review.b, reason: "x" }))).code, "permission-denied");
  assert.equal((await failure(report(review.a, { reportedUserId: prod.b, reason: "x" }))).code, "permission-denied");
  assert.equal((await pairReports(prod.a, review.b)).length, 0);
  assert.equal((await pairReports(review.a, prod.b)).length, 0);
  // closing the review report does not open a slot for the production pair
  await close(String(r1.reportId));
  const p2 = await report(prod.a, { reportedUserId: prod.b, reason: "y" });
  assert.equal(p2.reportId, p1.reportId);
  assert.equal(p2.duplicate, true);
  const r2 = await report(review.a, { reportedUserId: review.b, reason: "y" });
  assert.notEqual(r2.reportId, r1.reportId);
  assert.equal((await db.collection("reports").doc(String(r2.reportId)).get()).get("reviewFixture"), true);
});

test("D10 legacy reports without the tracker are honoured (random ids, no pointer)", async () => {
  // (a) an open report written before deterministic ids existed
  const one = await pair();
  const legacyOpen = await db.collection("reports").add({
    reporterId: one.a, reportedId: one.b, reason: "old", source: "profile", status: "pending",
  });
  const again = await report(one.a, { reportedUserId: one.b, reason: "new" });
  assert.equal(again.reportId, legacyOpen.id);
  assert.equal(again.duplicate, true);
  assert.equal((await pairReports(one.a, one.b)).length, 1);

  // (b) the previous source's leftovers: closed first report, two later open ones, no pointer
  const two = await pair();
  const first = await report(two.a, { reportedUserId: two.b, reason: "spam" });
  await close(String(first.reportId));
  const base = { reporterId: two.a, reportedId: two.b, reason: "dup", source: "profile", status: "pending", reportKind: "profile", contentSnapshot: null };
  const left1 = await db.collection("reports").add(base);
  const left2 = await db.collection("reports").add(base);
  const answer = await report(two.a, { reportedUserId: two.b, reason: "now" });
  assert.equal(answer.duplicate, true);
  assert.ok([left1.id, left2.id].includes(String(answer.reportId)));
  assert.equal((await pairReports(two.a, two.b)).length, 3, "no fourth report");
  // still deduplicated while either leftover is open
  await close(String(answer.reportId));
  const other = await report(two.a, { reportedUserId: two.b, reason: "now 2" });
  assert.equal(other.duplicate, true);
  assert.ok([left1.id, left2.id].includes(String(other.reportId)));
  assert.notEqual(other.reportId, answer.reportId);
  assert.equal((await pairReports(two.a, two.b)).length, 3);
});

test("D11 [NEW-20] an open Bamboo report never deduplicates an account report (no authorship oracle)", async () => {
  const author = fresh("author"), other = fresh("other"), reporter = fresh("rep");
  for (const uid of [author, other, reporter]) await seedUser(uid);
  // What reportBambooContent stores: reportedId is the anonymous author.
  await db.collection("reports").doc(fresh("bamboo")).set({
    reporterId: reporter, reportedId: author, reason: "spam", source: "bamboo_post",
    contentType: "bamboo_post", contentId: "post_1", status: "pending", reportKind: "community",
    contentSnapshot: { title: "t" },
  });
  // A legacy-shaped Bamboo report (pre-P0-3 writer) with no reportKind.
  await db.collection("reports").add({
    reporterId: reporter, reportedId: author, reason: "spam", source: "bamboo_comment",
    contentType: "bamboo_comment", contentId: "c_1", parentContentId: "post_1", status: "reviewing",
  });
  const aboutAuthor = await report(reporter, { reportedUserId: author, reason: "profile abuse" });
  const aboutOther = await report(reporter, { reportedUserId: other, reason: "profile abuse" });
  // identical shape: a new report each, never `duplicate`
  assert.deepEqual(Object.keys(aboutAuthor).sort(), Object.keys(aboutOther).sort());
  assert.equal(aboutAuthor.duplicate, undefined);
  assert.equal(aboutOther.duplicate, undefined);
  assert.equal(aboutAuthor.reportId, accountReportId(reporter, author));
  assert.equal(aboutOther.reportId, accountReportId(reporter, other));
  // Bamboo-shaped calls stay refused identically whatever account reports exist
  const answers = [];
  for (const guess of [author, other, "nobody_at_all"]) {
    answers.push(await failure(report(reporter, { reportedUserId: guess, reason: "x", source: "bamboo_post", contentType: "bamboo_post", contentId: "post_1" })));
  }
  assert.ok(answers.every((x) => x.code === "failed-precondition"));
  assert.equal(new Set(answers.map((x) => x.message)).size, 1);
});
