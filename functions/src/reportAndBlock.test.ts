import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_REPORT_DETAILS_LENGTH,
  MAX_REPORT_REASON_LENGTH,
  PAIR_LATEST_REPORT_FIELD,
  REPORT_AND_BLOCK_USER_CALLABLE_OPTIONS,
  accountReportId,
  buildReportAndBlockPlan,
  isOpenAccountReportOfPair,
} from "./reportAndBlock";

function plan(overrides: Record<string, unknown> = {}) {
  return buildReportAndBlockPlan({
    reporterUid: "alice",
    reportedUid: "bob",
    reason: "harassment",
    ...overrides,
  });
}

function blockFor(
  result: ReturnType<typeof buildReportAndBlockPlan>,
  ownerUid: string
) {
  return result.blockWrites.find((write) => write.ownerUid === ownerUid);
}

test("report and block callable enforces App Check", () => {
  assert.equal(REPORT_AND_BLOCK_USER_CALLABLE_OPTIONS.enforceAppCheck, true);
});

test("a report blocks in both directions", () => {
  const result = plan();

  assert.equal(result.blockWrites.length, 2);

  const forward = blockFor(result, "alice");
  assert.equal(forward?.targetUid, "bob");
  assert.equal(forward?.data.fromUserId, "alice");
  assert.equal(forward?.data.toUserId, "bob");

  // Without this write the reported user keeps seeing the reporter.
  const reverse = blockFor(result, "bob");
  assert.equal(reverse?.targetUid, "alice");
  assert.equal(reverse?.data.fromUserId, "bob");
  assert.equal(reverse?.data.toUserId, "alice");
});

test("the reverse block is labelled so it can be audited separately", () => {
  const result = plan();

  assert.equal(blockFor(result, "alice")?.data.source, "report");
  assert.equal(blockFor(result, "bob")?.data.source, "report_mutual");
});

test("report payload matches the reports collection contract", () => {
  const result = plan({ details: "sent abusive messages", source: "chat" });

  assert.deepEqual(result.reportData, {
    reporterId: "alice",
    reportedId: "bob",
    reason: "harassment",
    details: "sent abusive messages",
    source: "chat",
    contentType: null,
    contentId: null,
    parentContentId: null,
    status: "pending",
  });
});

test("content reports retain an auditable post or comment reference", () => {
  const result = plan({
    source: "bamboo_comment",
    contentType: "bamboo_comment",
    contentId: "comment_1",
    parentContentId: "post_1",
  });
  assert.equal(result.reportData.contentType, "bamboo_comment");
  assert.equal(result.reportData.contentId, "comment_1");
  assert.equal(result.reportData.parentContentId, "post_1");
});

test("reporter identity comes from the resolved caller, never from the payload", () => {
  const result = buildReportAndBlockPlan({
    reporterUid: "alice",
    reportedUid: "bob",
    reason: "spam",
    // A spoofed reporterId in the request body must not be honoured.
    ...({ reporterId: "mallory" } as Record<string, unknown>),
  });

  assert.equal(result.reportData.reporterId, "alice");
});

test("details default to null and blank details are normalised", () => {
  assert.equal(plan().reportData.details, null);
  assert.equal(plan({ details: "   " }).reportData.details, null);
});

test("source defaults to profile", () => {
  assert.equal(plan().reportData.source, "profile");
});

test("self reports are rejected", () => {
  assert.throws(
    () => plan({ reportedUid: "alice" }),
    /자기 자신은 신고할 수 없어요/
  );
});

test("missing or malformed uids are rejected", () => {
  assert.throws(() => plan({ reportedUid: "" }), /reportedUid is invalid/);
  assert.throws(() => plan({ reportedUid: null }), /reportedUid is invalid/);
  assert.throws(() => plan({ reportedUid: 42 }), /reportedUid is invalid/);
});

test("uids that could escape the document path are rejected", () => {
  assert.throws(() => plan({ reportedUid: "../admin" }), /reportedUid is invalid/);
  assert.throws(() => plan({ reportedUid: "a/b" }), /reportedUid is invalid/);
  assert.throws(
    () => plan({ reportedUid: "x".repeat(129) }),
    /reportedUid is invalid/
  );
});

test("a reason is required", () => {
  assert.throws(() => plan({ reason: "" }), /reason is required/);
  assert.throws(() => plan({ reason: "   " }), /reason is required/);
  assert.throws(() => plan({ reason: undefined }), /reason is required/);
});

test("oversized text is rejected instead of stored", () => {
  assert.throws(
    () => plan({ reason: "x".repeat(MAX_REPORT_REASON_LENGTH + 1) }),
    /reason must be at most/
  );
  assert.throws(
    () => plan({ details: "x".repeat(MAX_REPORT_DETAILS_LENGTH + 1) }),
    /details must be at most/
  );
});

test("text at the length limit is accepted", () => {
  const reason = "x".repeat(MAX_REPORT_REASON_LENGTH);
  assert.equal(plan({ reason }).reportData.reason, reason);
});

test("REPORT-DEDUP: only an open account report of exactly this pair deduplicates", () => {
  const open = { reporterId: "alice", reportedId: "bob", status: "pending", source: "profile", reportKind: "profile", contentSnapshot: null };
  assert.equal(isOpenAccountReportOfPair(open, "alice", "bob"), true);
  assert.equal(isOpenAccountReportOfPair({ ...open, status: "reviewing" }, "alice", "bob"), true);
  // legacy account report: no reportKind / contentSnapshot fields at all
  assert.equal(isOpenAccountReportOfPair({ reporterId: "alice", reportedId: "bob", status: "pending" }, "alice", "bob"), true);
  for (const status of ["dismissed", "actioned", "", undefined, "PENDING", 1]) {
    assert.equal(isOpenAccountReportOfPair({ ...open, status }, "alice", "bob"), false, String(status));
  }
  assert.equal(isOpenAccountReportOfPair(open, "alice", "carol"), false);
  assert.equal(isOpenAccountReportOfPair(open, "bob", "alice"), false);
  assert.equal(isOpenAccountReportOfPair(undefined, "alice", "bob"), false);
});

test("REPORT-DEDUP [NEW-20]: a Bamboo report is never an account report of the pair", () => {
  const base = { reporterId: "alice", reportedId: "bob", status: "pending" };
  for (const bamboo of [
    { source: "bamboo_post", contentType: "bamboo_post", contentId: "p1", reportKind: "community" },
    { source: "bamboo_comment" },
    { contentType: "bamboo_post" },
    { source: "profile", reportKind: "community" },
    { source: "profile", contentId: "p1" },
    { source: "profile", contentSnapshot: { title: "t" } },
  ]) {
    assert.equal(isOpenAccountReportOfPair({ ...base, ...bamboo }, "alice", "bob"), false, JSON.stringify(bamboo));
  }
});

test("REPORT-DEDUP: the pair tracker id is deterministic, direction-sensitive and path-safe", () => {
  assert.equal(accountReportId("alice", "bob"), accountReportId("alice", "bob"));
  assert.notEqual(accountReportId("alice", "bob"), accountReportId("bob", "alice"));
  assert.match(accountReportId("alice", "bob"), /^account_[0-9a-f]{40}$/);
  assert.equal(PAIR_LATEST_REPORT_FIELD, "pairLatestReportId");
});
