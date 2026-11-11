/**
 * NEW-20 — reportAndBlockUser production contract on the real Firestore engine,
 * through the real index export (resolveReviewCapableAppUser →
 * resolveAuthedAppUser).
 *
 * Pins the behaviour recovered from the live revision reportandblockuser-00009-dak
 * (server 24 h review deadline, report kind, one operations queue for review
 * fixtures, the suspended-account gate in resolveAuthedAppUser) and the P0-3
 * protections that the live revision lacked (no Bamboo authorship oracle, no
 * content snapshot, no lookup before a content reference is refused).
 *
 * Run (repo root, JDK 21):
 *   ./functions/node_modules/.bin/tsc -p functions --outDir functions/.p113-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-new20 \
 *     "node --test functions/.p113-lib/reportAndBlock.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { reportAndBlockUser } from "./index";
import { accountReportId } from "./reportAndBlock";

type Runnable = { run: (request: unknown) => Promise<unknown> };
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

function report(uid: string, data: Record<string, unknown>) {
  return (reportAndBlockUser as unknown as Runnable).run({ data, auth: { uid, token: {} }, rawRequest: {} }) as Promise<Record<string, unknown>>;
}

async function failure(promise: Promise<unknown>): Promise<{ code: string; message: string }> {
  try {
    await promise;
  } catch (error) {
    return { code: String((error as { code?: string }).code), message: String((error as Error).message) };
  }
  return { code: "ok", message: "" };
}

const reportsBy = async (uid: string) => (await db.collection("reports").where("reporterId", "==", uid).get()).docs;
const blocksOf = async (uid: string) => (await db.collection("blocks").doc(uid).collection("targets").get()).docs;

test("N1 an account report: recovered production schema + both blocks in one commit", async () => {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a);
  await seedUser(b);
  const before = Date.now();
  const result = await report(a, { reportedUserId: b, reason: "harassment", details: "abusive", source: "chat" });
  assert.equal(result.blockedBothDirections, true);
  const docs = await reportsBy(a);
  assert.equal(docs.length, 1);
  const r = docs[0].data();
  assert.equal(docs[0].id, accountReportId(a, b));
  assert.equal(r.reportedId, b);
  assert.equal(r.status, "pending");
  assert.equal(r.reportKind, "profile");
  assert.equal(r.contentSnapshot, null);
  assert.equal(r.source, "chat");
  assert.equal(r.dataPartition, "production");
  const deadline = (r.deadlineAt as Timestamp).toMillis();
  assert.ok(deadline >= before + 24 * 3600_000 - 5000 && deadline <= Date.now() + 24 * 3600_000 + 5000, "server-derived 24 h deadline");
  assert.ok(r.createdAt instanceof Timestamp);
  const forward = (await blocksOf(a)).map((d) => d.data());
  const reverse = (await blocksOf(b)).map((d) => d.data());
  assert.deepEqual(forward.map((x) => [x.toUserId, x.source, x.reason]), [[b, "report", "user_report"]]);
  assert.deepEqual(reverse.map((x) => [x.toUserId, x.source, x.reason]), [[a, "report_mutual", "user_report"]]);
});

test("N2 repeated / concurrent reports while one is open: one report, blocks idempotent", async () => {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a);
  await seedUser(b);
  const runs = await Promise.allSettled(Array.from({ length: 5 }, () => report(a, { reportedUserId: b, reason: "spam" })));
  assert.ok(runs.some((r) => r.status === "fulfilled"));
  const ids = new Set(runs.filter((r): r is PromiseFulfilledResult<Record<string, unknown>> => r.status === "fulfilled").map((r) => r.value.reportId));
  assert.equal(ids.size, 1);
  assert.equal((await reportsBy(a)).length, 1);
  assert.equal((await blocksOf(a)).length, 1);
  assert.equal((await blocksOf(b)).length, 1);
});

test("N3 after moderation closed the report, a new report is a new record (history kept)", async () => {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a);
  await seedUser(b);
  await report(a, { reportedUserId: b, reason: "spam" });
  await db.collection("reports").doc(accountReportId(a, b)).update({ status: "dismissed" });
  const second = await report(a, { reportedUserId: b, reason: "spam again" });
  assert.notEqual(second.reportId, accountReportId(a, b));
  const docs = await reportsBy(a);
  assert.equal(docs.length, 2);
  assert.deepEqual(docs.map((d) => d.get("status")).sort(), ["dismissed", "pending"]);
});

test("N4 self-report and a missing account are refused with nothing written", async () => {
  const a = fresh("a");
  await seedUser(a);
  assert.equal((await failure(report(a, { reportedUserId: a, reason: "x" }))).code, "invalid-argument");
  assert.equal((await failure(report(a, { reportedUserId: fresh("ghost"), reason: "x" }))).code, "not-found");
  assert.equal((await reportsBy(a)).length, 0);
  assert.equal((await blocksOf(a)).length, 0);
});

test("N5 [oracle] any content reference is refused before any lookup — same answer whether the account exists", async () => {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a);
  await seedUser(b);
  for (const extra of [
    { contentType: "photo", contentId: "x1" },
    { contentType: "BAMBOO_POST", contentId: "x1" },
    { contentType: " Bamboo_comment", contentId: "c1" },
    { contentId: "x1" },
    { parentContentId: "p1" },
  ]) {
    const existing = await failure(report(a, { reportedUserId: b, reason: "x", ...extra }));
    const missing = await failure(report(a, { reportedUserId: fresh("ghost"), reason: "x", ...extra }));
    assert.equal(existing.code, "invalid-argument", JSON.stringify(extra));
    assert.deepEqual(existing, missing, "the response does not depend on the reported account");
  }
  assert.equal((await reportsBy(a)).length, 0);
  assert.equal((await blocksOf(a)).length, 0);
});

test("N6 [P0-3] Bamboo reports through this callable: identical refusal for every author guess, nothing written", async () => {
  const author = fresh("author"), reporter = fresh("rep"), other = fresh("other");
  for (const uid of [author, reporter, other]) await seedUser(uid);
  const postId = fresh("post");
  await db.collection("bamboo_posts").doc(postId).set({ content: "anon", isDeleted: false });
  await db.collection("bamboo_post_authors").doc(postId).set({ ownerUid: author, postId });
  const answers = [];
  for (const guess of [author, other, "nobody_at_all"]) {
    for (const shape of [
      { source: "bamboo_post", contentType: "bamboo_post", contentId: postId },
      { source: "bamboo_comment", contentType: "bamboo_comment", contentId: "c1", parentContentId: postId },
      { source: "bamboo_post" },
    ]) {
      answers.push(await failure(report(reporter, { reportedUserId: guess, reason: "spam", ...shape })));
    }
  }
  assert.ok(answers.every((x) => x.code === "failed-precondition"));
  assert.equal(new Set(answers.map((x) => x.message)).size, 1, "no answer differs by guess");
  assert.equal((await reportsBy(reporter)).length, 0);
  assert.equal((await blocksOf(reporter)).length, 0);
  assert.equal((await blocksOf(author)).length, 0, "no reverse block would tell the author who reported");
});

test("N7 the source is a bounded screen token", async () => {
  const a = fresh("a"), b = fresh("b");
  await seedUser(a);
  await seedUser(b);
  for (const source of ["x".repeat(65), "has space", "Upper", "<script>", ""]) {
    assert.equal((await failure(report(a, { reportedUserId: b, reason: "x", source }))).code, "invalid-argument", source);
  }
  const ok = await report(a, { reportedUserId: b, reason: "x", source: "profile_specific_detail_screen" });
  assert.ok(ok.reportId);
});

test("N8 cross-partition reports are refused; review fixtures share the operations queue in their own partition", async () => {
  const prod = fresh("prod"), review = fresh("rev"), review2 = fresh("rev2");
  await seedUser(prod);
  await seedUser(review, { dataPartition: "play_review" });
  await seedUser(review2, { dataPartition: "play_review" });
  assert.equal((await failure(report(prod, { reportedUserId: review, reason: "x" }))).code, "permission-denied");
  assert.equal((await reportsBy(prod)).length, 0);
  // Review-partition reports use the same operations queue (status pending,
  // as the live revision and reportBambooContent do), isolated by partition.
  await report(review, { reportedUserId: review2, reason: "x" });
  const docs = await reportsBy(review);
  assert.equal(docs.length, 1);
  assert.equal(docs[0].get("status"), "pending");
  assert.equal(docs[0].get("dataPartition"), "play_review");
  assert.equal(docs[0].get("reviewFixture"), true);
  assert.equal((await blocksOf(review))[0].get("dataPartition"), "play_review");
});

test("N9 [recovered] a suspended or banned account cannot report (stale ID token after moderation)", async () => {
  const b = fresh("b");
  await seedUser(b);
  for (const state of [{ loginDisabled: true }, { isActive: false }, { status: "suspended" }, { status: "banned" }, { status: "WITHDRAWN" }]) {
    const a = fresh("a");
    await seedUser(a, state);
    const result = await failure(report(a, { reportedUserId: b, reason: "x" }));
    assert.equal(result.code, "permission-denied", JSON.stringify(state));
    assert.match(result.message, /이용이 정지된 계정이에요/);
    assert.equal((await reportsBy(a)).length, 0);
    assert.equal((await blocksOf(a)).length, 0);
  }
  // an active account with an unrelated status is unaffected
  const ok = fresh("ok");
  await seedUser(ok, { status: "active" });
  assert.ok((await report(ok, { reportedUserId: b, reason: "x" })).reportId);
});
