/**
 * NEW-25 — moderation console contract on the real Firestore engine (the
 * callables are built from the same factory index.ts uses; Auth is a recorder).
 *
 * Writes and wipes `reports`: do not share an emulator run with another suite.
 *   npx firebase-tools emulators:exec --only firestore --project demo-mod \
 *     "node --test functions/<outDir>/communityModeration.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getApps, initializeApp } from "firebase-admin/app";
import type { Auth } from "firebase-admin/auth";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
if (getApps().length === 0) initializeApp();

import { createCommunityModerationCallables } from "./communityModeration";

const db = getFirestore();
const HOUR = 3600_000;
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

type AuthCall = { op: string; uid: string; disabled?: boolean };
const authCalls: AuthCall[] = [];
let failNextDisable = 0;
const auth = {
  async updateUser(uid: string, properties: { disabled?: boolean }) {
    if (properties.disabled === true && failNextDisable > 0) {
      failNextDisable -= 1;
      throw new Error("auth backend unavailable");
    }
    authCalls.push({ op: "updateUser", uid, disabled: properties.disabled });
    return {};
  },
  async revokeRefreshTokens(uid: string) {
    authCalls.push({ op: "revoke", uid });
  },
} as unknown as Auth;

const callables = createCommunityModerationCallables({ firestore: db, auth });
type Name = keyof typeof callables;
type Result = Record<string, unknown>;
function call(name: Name, authContext: unknown, data: Record<string, unknown> = {}) {
  return (callables[name] as unknown as { run: (request: unknown) => Promise<Result> })
    .run({ data, auth: authContext, rawRequest: {} });
}
const asOperator = (uid: string) => ({ uid, token: { operations: true } });
const asUser = (uid: string) => ({ uid, token: {} });

async function failure(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (error) {
    const e = error as { code?: string; message?: string; details?: { detail?: string } };
    return { code: String(e.code), message: String(e.message), detail: e.details?.detail ?? null };
  }
  return { code: "ok", message: "", detail: null };
}

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({ nickname: uid, status: "active", isActive: true, ...extra });
}
async function seedOperator(extra: Record<string, unknown> = {}, adminExtra: Record<string, unknown> = {}) {
  const uid = fresh("op");
  await seedUser(uid, { accountType: "operations", ...extra });
  await db.collection("admin").doc(uid).set({ accountType: "operations", active: true, ...adminExtra });
  return uid;
}
async function seedReport(extra: Record<string, unknown> = {}) {
  const id = fresh("bamboo");
  const created = Date.now() - HOUR;
  await db.collection("reports").doc(id).set({
    reporterId: "reporter_x", reportedId: null, reason: "spam", details: null, source: "bamboo_post",
    contentType: "bamboo_post", contentId: "post_x", parentContentId: null, status: "pending",
    reportKind: "community", contentSnapshot: { title: "t", body: "b" }, dataPartition: "production",
    reviewFixture: false, createdAt: Timestamp.fromMillis(created), deadlineAt: Timestamp.fromMillis(created + 24 * HOUR),
    ...extra,
  });
  return id;
}
const reportDoc = async (id: string) => (await db.collection("reports").doc(id).get()).data() ?? {};
const userDoc = async (id: string) => (await db.collection("users").doc(id).get()).data() ?? {};
const auditOf = async (field: string, value: string) =>
  (await db.collection("moderation_audit_logs").where(field, "==", value).get()).docs.map((d) => d.data());

/** A mapped Bamboo post of `author` plus an open report on it (P0-3 layout). */
async function seedReportedPost(partition: "production" | "play_review" = "production") {
  const author = fresh("author");
  await seedUser(author, partition === "play_review" ? { dataPartition: "play_review" } : {});
  const review = partition === "play_review";
  const postId = fresh("post");
  const posts = review ? "playReviewBambooPosts" : "bamboo_posts";
  const owners = review ? "playReviewBambooPostAuthors" : "bamboo_post_authors";
  await db.collection(posts).doc(postId).set({ content: "anonymous words", isDeleted: false });
  await db.collection(owners).doc(postId).set({ ownerUid: author, postId });
  const reportId = await seedReport({ reportedId: author, contentId: postId, dataPartition: partition, reviewFixture: review });
  return { author, postId, posts, reportId };
}

const EVERY_CALL: Array<[Name, Record<string, unknown>]> = [
  ["getCommunityModerationAccess", {}],
  ["listCommunityModerationReports", { scope: "all" }],
  ["setCommunityReportReviewing", { reportId: "r1" }],
  ["decideCommunityReport", { reportId: "r1", decision: "dismiss", reason: "x" }],
  ["restoreCommunityAccount", { userId: "u1", reason: "x" }],
];

test("M1 an active operator is allowed", async () => {
  const op = await seedOperator();
  assert.deepEqual(await call("getCommunityModerationAccess", asOperator(op)), { allowed: true, operatorId: op });
  // an operator account without a users document (not an app account) is also accepted
  const bare = fresh("op");
  await db.collection("admin").doc(bare).set({ active: true });
  assert.equal((await call("getCommunityModerationAccess", asOperator(bare))).allowed, true);
});

test("M2 no operator power is reachable by an ordinary user, by a claim alone or by an admin record alone", async () => {
  const user = fresh("user");
  await seedUser(user);
  const claimOnly = fresh("claim");
  await seedUser(claimOnly);
  const recordOnly = fresh("record");
  await seedUser(recordOnly);
  await db.collection("admin").doc(recordOnly).set({ active: true });
  const inactive = await seedOperator({}, { active: false });
  const reportId = await seedReport();
  const target = fresh("target");
  await seedUser(target, { status: "suspended", loginDisabled: true, isActive: false });
  for (const [name, data] of EVERY_CALL) {
    const payload = { ...data, ...(data.reportId ? { reportId } : {}), ...(data.userId ? { userId: target } : {}) };
    assert.equal((await failure(call(name, null, payload))).code, "unauthenticated", `${name} anonymous`);
    assert.equal((await failure(call(name, asUser(user), payload))).code, "permission-denied", `${name} ordinary user`);
    assert.equal((await failure(call(name, asOperator(claimOnly), payload))).code, "permission-denied", `${name} claim without admin record`);
    assert.equal((await failure(call(name, asUser(recordOnly), payload))).code, "permission-denied", `${name} admin record without claim`);
    assert.equal((await failure(call(name, asOperator(inactive), payload))).code, "permission-denied", `${name} deactivated operator`);
  }
  assert.equal((await reportDoc(reportId)).status, "pending", "nothing was changed");
  assert.equal((await userDoc(target)).status, "suspended");
});

test("M3 a suspended, banned or withdrawn operator is refused on every callable", async () => {
  const reportId = await seedReport();
  for (const [state, detail] of [
    [{ status: "suspended", loginDisabled: true, isActive: false }, "account_suspended"],
    [{ status: "banned" }, "account_banned"],
    [{ status: "withdrawn" }, "account_withdrawn"],
    [{ status: "deleting" }, "account_withdrawn"],
    [{ isSuspended: true }, "account_suspended"],
  ] as Array<[Record<string, unknown>, string]>) {
    const op = await seedOperator(state);
    for (const [name, data] of EVERY_CALL) {
      const result = await failure(call(name, asOperator(op), { ...data, ...(data.reportId ? { reportId } : {}) }));
      assert.equal(result.code, "permission-denied", `${name} ${detail}`);
      assert.equal(result.detail, detail, `${name} ${detail}`);
    }
  }
  assert.equal((await reportDoc(reportId)).status, "pending");
});

test("M4 list: open Bamboo queue only, complete behind unrelated reports, isolated by partition scope", async () => {
  await db.recursiveDelete(db.collection("reports"));
  const op = await seedOperator();
  const now = Date.now();
  const author = fresh("author");
  await seedUser(author, { nickname: "nick" });
  const oldOpen = await seedReport({ reportedId: author, createdAt: Timestamp.fromMillis(now - 50 * HOUR), deadlineAt: Timestamp.fromMillis(now - 26 * HOUR) });
  const reviewing = await seedReport({ source: "bamboo_comment", status: "reviewing", createdAt: Timestamp.fromMillis(now - 40 * HOUR), deadlineAt: Timestamp.fromMillis(now - 16 * HOUR) });
  const review = await seedReport({ dataPartition: "play_review", reviewFixture: true, createdAt: Timestamp.fromMillis(now - 45 * HOUR), deadlineAt: Timestamp.fromMillis(now - 21 * HOUR) });
  // Account reports are never closed through the console: 160 with earlier
  // deadlines and 160 newer ones used to fill both unfiltered reads.
  for (const [offset, count] of [[90 * HOUR, 160], [0, 160]] as Array<[number, number]>) {
    for (let i = 0; i < count; i += 400) {
      const batch = db.batch();
      for (let j = i; j < Math.min(count, i + 400); j++) {
        const created = now - offset - j * 1000;
        batch.set(db.collection("reports").doc(fresh("acct")), {
          reporterId: "a", reportedId: "b", reason: "x", source: "profile", status: "pending", reportKind: "profile",
          contentSnapshot: null, dataPartition: "production",
          createdAt: Timestamp.fromMillis(created), deadlineAt: Timestamp.fromMillis(created + 24 * HOUR),
        });
      }
      await batch.commit();
    }
  }
  const all = await call("listCommunityModerationReports", asOperator(op), { scope: "all" });
  const rows = all.reports as Array<Record<string, unknown>>;
  assert.deepEqual(rows.map((r) => r.reportId), [oldOpen, review, reviewing], "deadline order, every open Bamboo report, nothing else");
  assert.ok(typeof all.serverNow === "number");
  const first = rows[0];
  assert.equal(first.status, "pending");
  assert.equal(first.dataPartition, "production");
  assert.equal(first.deadlineAt, now - 26 * HOUR);
  assert.deepEqual(first.contentSnapshot, { title: "t", body: "b" });
  assert.equal((first.account as Record<string, unknown>).nickname, "nick");
  assert.equal(rows[2].account, null, "a report without a proven owner has no account summary");
  const production = (await call("listCommunityModerationReports", asOperator(op), { scope: "production" })).reports as Array<Record<string, unknown>>;
  assert.deepEqual(production.map((r) => r.reportId), [oldOpen, reviewing]);
  const playReview = (await call("listCommunityModerationReports", asOperator(op), { scope: "play_review" })).reports as Array<Record<string, unknown>>;
  assert.deepEqual(playReview.map((r) => r.reportId), [review]);
  assert.equal(playReview[0].reviewFixture, true);
});

test("M5 state transitions: reviewing, dismissal, and no way back from a decision", async () => {
  const op = await seedOperator();
  const id = await seedReport();
  assert.deepEqual(await call("setCommunityReportReviewing", asOperator(op), { reportId: id }), { ok: true });
  let doc = await reportDoc(id);
  assert.equal(doc.status, "reviewing");
  assert.equal(doc.reviewingBy, op);
  assert.ok(doc.reviewingAt instanceof Timestamp);
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: id, decision: "dismiss", reason: "" }))).code, "invalid-argument");
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: id, decision: "delete_everything", reason: "x" }))).code, "invalid-argument");
  assert.deepEqual(await call("decideCommunityReport", asOperator(op), { reportId: id, decision: "dismiss", reason: "not a violation" }), { ok: true, decision: "dismiss" });
  doc = await reportDoc(id);
  assert.equal(doc.status, "dismissed");
  assert.equal(doc.dismissedBy, op);
  assert.equal(doc.dismissalReason, "not a violation");
  assert.equal((await failure(call("setCommunityReportReviewing", asOperator(op), { reportId: id }))).code, "failed-precondition");
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: id, decision: "dismiss", reason: "again" }))).code, "failed-precondition");
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: id, decision: "suspend", reason: "again" }))).code, "failed-precondition");
  assert.equal((await reportDoc(id)).status, "dismissed");
  assert.equal((await reportDoc(id)).dismissalReason, "not a violation");
  // account reports and unknown ids are not part of this console
  const accountReport = fresh("account");
  await db.collection("reports").doc(accountReport).set({ reporterId: "a", reportedId: "b", source: "profile", status: "pending" });
  assert.equal((await failure(call("setCommunityReportReviewing", asOperator(op), { reportId: accountReport }))).code, "not-found");
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: accountReport, decision: "dismiss", reason: "x" }))).code, "failed-precondition");
  assert.equal((await failure(call("setCommunityReportReviewing", asOperator(op), { reportId: fresh("missing") }))).code, "not-found");
  assert.equal((await failure(call("setCommunityReportReviewing", asOperator(op), { reportId: "a/b" }))).code, "invalid-argument");
  assert.equal((await reportDoc(accountReport)).status, "pending");
});

test("M6 a decision racing the reviewing transition is never overwritten", async () => {
  const op = await seedOperator();
  const other = await seedOperator();
  for (let round = 0; round < 12; round++) {
    const id = await seedReport();
    const results = await Promise.allSettled([
      call("decideCommunityReport", asOperator(op), { reportId: id, decision: "dismiss", reason: "r" }),
      call("setCommunityReportReviewing", asOperator(other), { reportId: id }),
      call("setCommunityReportReviewing", asOperator(other), { reportId: id }),
      call("decideCommunityReport", asOperator(other), { reportId: id, decision: "dismiss", reason: "second" }),
    ]);
    assert.equal((await reportDoc(id)).status, "dismissed", `round ${round}`);
    const decided = [results[0], results[3]].filter((r) => r.status === "fulfilled").length;
    assert.equal(decided, 1, `round ${round}: exactly one decision is recorded`);
  }
});

test("M7 sanction + restore: account state, sign-in block, audit records; hidden content keeps no author (P0-3)", async () => {
  const op = await seedOperator();
  const { author, postId, posts, reportId } = await seedReportedPost();
  authCalls.length = 0;
  const decided = await call("decideCommunityReport", asOperator(op), { reportId, decision: "suspend", reason: "abuse" });
  assert.equal(decided.ok, true);
  assert.equal(decided.hiddenPosts, 1);
  let account = await userDoc(author);
  assert.equal(account.status, "suspended");
  assert.equal(account.loginDisabled, true);
  assert.equal(account.moderationActionType, "indefinite_suspension");
  const report = await reportDoc(reportId);
  assert.equal(report.status, "actioned");
  assert.ok(report.authEnforcedAt instanceof Timestamp);
  assert.deepEqual(authCalls, [{ op: "updateUser", uid: author, disabled: true }, { op: "revoke", uid: author }]);
  const post = (await db.collection(posts).doc(postId).get()).data() ?? {};
  assert.equal(post.moderationHidden, true);
  for (const key of Object.keys(post)) {
    assert.ok(!/author|owner|reported/i.test(key), `public post field ${key}`);
    assert.notEqual(post[key], author, `public post field ${key} carries the author`);
  }
  assert.equal((await auditOf("reportId", reportId)).length, 1);

  // restore
  assert.equal((await failure(call("restoreCommunityAccount", asOperator(op), { userId: author, reason: " " }))).code, "invalid-argument");
  assert.equal((await failure(call("restoreCommunityAccount", asOperator(op), { userId: fresh("ghost"), reason: "x" }))).code, "not-found");
  authCalls.length = 0;
  assert.deepEqual(await call("restoreCommunityAccount", asOperator(op), { userId: author, reason: "appeal accepted" }), { ok: true });
  account = await userDoc(author);
  assert.equal(account.status, "active");
  assert.equal(account.loginDisabled, false);
  assert.equal(account.isActive, true);
  assert.equal(account.moderationRestoredBy, op);
  assert.equal(account.moderationRestoreReason, "appeal accepted");
  assert.deepEqual(authCalls, [{ op: "updateUser", uid: author, disabled: false }]);
  const lifted = await auditOf("userId", author);
  assert.equal(lifted.length, 1);
  assert.equal(lifted[0].type, "suspension_lifted");
  assert.equal(lifted[0].actorId, op);
  assert.equal(lifted[0].reason, "appeal accepted");
  assert.equal(lifted[0].dataPartition, "production");
  // a restored account's old report cannot be used to disable it again
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId, decision: "suspend", reason: "again" }))).code, "failed-precondition");
});

test("M8 restore refuses a permanent ban and a withdrawn account, writing nothing", async () => {
  const op = await seedOperator();
  for (const [state, expected] of [
    [{ status: "banned", loginDisabled: true, isActive: false }, "banned"],
    [{ status: "withdrawn", isActive: false }, "withdrawn"],
    [{ status: "deleted" }, "deleted"],
    [{ status: "deleting" }, "deleting"],
  ] as Array<[Record<string, unknown>, string]>) {
    const uid = fresh("target");
    await seedUser(uid, state);
    authCalls.length = 0;
    assert.equal((await failure(call("restoreCommunityAccount", asOperator(op), { userId: uid, reason: "x" }))).code, "failed-precondition", expected);
    assert.equal((await userDoc(uid)).status, expected);
    assert.equal((await auditOf("userId", uid)).length, 0);
    assert.deepEqual(authCalls, []);
  }
});

test("M9 a failed sign-in block can be repeated; nothing else about a closed report can", async () => {
  const op = await seedOperator();
  const { author, reportId } = await seedReportedPost();
  authCalls.length = 0;
  failNextDisable = 1;
  const failed = await failure(call("decideCommunityReport", asOperator(op), { reportId, decision: "ban", reason: "severe" }));
  assert.equal(failed.code, "unavailable");
  assert.equal((await reportDoc(reportId)).status, "actioned", "the sanction is stored");
  assert.equal((await reportDoc(reportId)).authEnforcedAt, undefined);
  assert.equal((await userDoc(author)).status, "banned");
  assert.deepEqual(authCalls, [], "Auth is still enabled: this is the gap");
  // a different decision is not a retry
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId, decision: "suspend", reason: "severe" }))).code, "failed-precondition");
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId, decision: "dismiss", reason: "severe" }))).code, "failed-precondition");
  assert.deepEqual(authCalls, []);
  const retried = await call("decideCommunityReport", asOperator(op), { reportId, decision: "ban", reason: "severe" });
  assert.deepEqual(retried, { ok: true, decision: "ban", signInBlockRetried: true });
  assert.deepEqual(authCalls, [{ op: "updateUser", uid: author, disabled: true }, { op: "revoke", uid: author }]);
  assert.ok((await reportDoc(reportId)).authEnforcedAt instanceof Timestamp);
  assert.equal((await auditOf("reportId", reportId)).length, 1, "the sanction was recorded once");
  authCalls.length = 0;
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId, decision: "ban", reason: "severe" }))).code, "failed-precondition");
  assert.deepEqual(authCalls, []);
});

test("M10 partitions: a report can only sanction an account of its own partition", async () => {
  const op = await seedOperator();
  const review = await seedReportedPost("play_review");
  const mismatched = await seedReport({ reportedId: review.author, dataPartition: "production" });
  authCalls.length = 0;
  assert.equal((await failure(call("decideCommunityReport", asOperator(op), { reportId: mismatched, decision: "suspend", reason: "x" }))).code, "failed-precondition");
  assert.equal((await userDoc(review.author)).status, "active");
  assert.deepEqual(authCalls, []);
  const ok = await call("decideCommunityReport", asOperator(op), { reportId: review.reportId, decision: "suspend", reason: "fixture" });
  assert.equal(ok.hiddenPosts, 1);
  assert.equal((await db.collection(review.posts).doc(review.postId).get()).get("moderationHidden"), true);
  assert.equal((await auditOf("reportId", review.reportId))[0].dataPartition, "play_review");
  await call("restoreCommunityAccount", asOperator(op), { userId: review.author, reason: "fixture reset" });
  assert.equal((await auditOf("userId", review.author))[0].dataPartition, "play_review");
});
