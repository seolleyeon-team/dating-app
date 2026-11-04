import assert from "node:assert/strict";
import test from "node:test";

import { Timestamp } from "firebase-admin/firestore";

import {
  chatDigestNotificationId,
  checkRoomUnreadIntegrity,
  digestContributionsForRoom,
  messageCommitTime,
  recipientsToIncrement,
  roomHasUnreadModel,
  timestampAtOrAfter,
  unreadCountFor,
  unreadRecipientsFor,
} from "./chatUnread";
import { legacyMessageIsUnreadFor } from "./chatUnreadLegacyMigration";

const A = "kakao_a";
const B = "kakao_b";
const SIX = ["u1", "u2", "u3", "u4", "u5", "u6"];

// ---------------------------------------------------------------------------
// Behavior contract (C2): who sees a message as unread
// ---------------------------------------------------------------------------

test("1:1 — only the recipient is incremented, never the sender", () => {
  assert.deepEqual(unreadRecipientsFor({ senderId: A, participantIds: [A, B] }), [B]);
  assert.deepEqual(unreadRecipientsFor({ senderId: B, participantIds: [A, B] }), [A]);
});

test("group — every participant except the sender, exactly once each", () => {
  const recipients = unreadRecipientsFor({ senderId: "u3", participantIds: [...SIX, "u3", "u1"] });
  assert.deepEqual(recipients, ["u1", "u2", "u4", "u5", "u6"]);
});

test("system messages count as unread for every participant (legacy client semantics)", () => {
  assert.deepEqual(
    unreadRecipientsFor({ senderId: "system", participantIds: [A, B] }),
    [A, B]
  );
});

test("malformed sender or participants never produce increments", () => {
  assert.deepEqual(unreadRecipientsFor({ senderId: "", participantIds: [A, B] }), []);
  assert.deepEqual(unreadRecipientsFor({ senderId: undefined, participantIds: [A] }), []);
  assert.deepEqual(unreadRecipientsFor({ senderId: A, participantIds: "not-a-list" }), []);
  assert.deepEqual(unreadRecipientsFor({ senderId: A, participantIds: [null, 3, "", A] }), []);
});

test("legacy readBy rule (migration module only): unread iff not mine and readBy lacks me", () => {
  assert.equal(legacyMessageIsUnreadFor({ senderId: A, readBy: [A] }, B), true);
  assert.equal(legacyMessageIsUnreadFor({ senderId: A, readBy: [A, B] }, B), false);
  assert.equal(legacyMessageIsUnreadFor({ senderId: A, readBy: [A] }, A), false);
  assert.equal(legacyMessageIsUnreadFor({ senderId: "system", readBy: [] }, A), true);
  assert.equal(legacyMessageIsUnreadFor({ senderId: "system" }, A), true);
  assert.equal(legacyMessageIsUnreadFor({ readBy: [] }, A), false);
});

// ---------------------------------------------------------------------------
// Room-level state readers
// ---------------------------------------------------------------------------

test("unreadCountFor reads the participant's counter and tolerates legacy rooms", () => {
  assert.equal(unreadCountFor({ unreadCounts: { [A]: 3, [B]: 0 } }, A), 3);
  assert.equal(unreadCountFor({ unreadCounts: { [A]: 3 } }, B), 0);
  assert.equal(unreadCountFor({}, A), 0);
  assert.equal(unreadCountFor(undefined, A), 0);
  assert.equal(unreadCountFor({ unreadCounts: { [A]: -2 } }, A), 0);
  assert.equal(unreadCountFor({ unreadCounts: { [A]: "7" } }, A), 0);
  assert.equal(unreadCountFor({ unreadCounts: "junk" }, A), 0);
});

test("a room carries the model only when the version marker is present", () => {
  assert.equal(roomHasUnreadModel({ unreadModelVersion: 1 }), true);
  assert.equal(roomHasUnreadModel({ unreadCounts: { [A]: 1 } }), false);
  assert.equal(roomHasUnreadModel({}), false);
  assert.equal(roomHasUnreadModel(undefined), false);
});

// ---------------------------------------------------------------------------
// Digest contribution (no message documents involved)
// ---------------------------------------------------------------------------

test("digest rows come only from active production rooms with positive counters", () => {
  const room = {
    status: "active",
    participantIds: [A, B],
    participantInfo: { [A]: { nickname: "에이" }, [B]: { nickname: "비" } },
    unreadCounts: { [A]: 2, [B]: 0 },
  };
  assert.deepEqual(digestContributionsForRoom(room), [
    { uid: A, unreadCount: 2, previewSenderName: "비" },
  ]);
  assert.deepEqual(digestContributionsForRoom({ ...room, status: "closed" }), []);
  assert.deepEqual(digestContributionsForRoom({ ...room, dataPartition: "play_review" }), []);
});

test("group rooms contribute counts without a preview name", () => {
  const room = {
    status: "active",
    participantIds: SIX,
    unreadCounts: Object.fromEntries(SIX.map((u) => [u, 1])),
  };
  const rows = digestContributionsForRoom(room);
  assert.equal(rows.length, 6);
  assert.ok(rows.every((r) => r.previewSenderName === null && r.unreadCount === 1));
});

test("a counter for a uid that is not a participant is ignored by the digest", () => {
  const room = { status: "active", participantIds: [A], unreadCounts: { [A]: 0, stranger: 9 } };
  assert.deepEqual(digestContributionsForRoom(room), []);
});

test("digest notification id is deterministic per day", () => {
  assert.equal(chatDigestNotificationId("2026-10-14"), "chat_digest_2026-10-14");
});

// ---------------------------------------------------------------------------
// Integrity check
// ---------------------------------------------------------------------------

test("integrity: healthy rooms report nothing, broken shapes are named", () => {
  assert.deepEqual(
    checkRoomUnreadIntegrity("r", { participantIds: [A, B], unreadCounts: { [A]: 0, [B]: 4 }, unreadModelVersion: 1 }),
    []
  );
  assert.deepEqual(checkRoomUnreadIntegrity("r", { participantIds: [A, B] }), []);
  const issues = checkRoomUnreadIntegrity("r", {
    participantIds: [A],
    unreadCounts: { [A]: -1, [B]: 2, c: 1.5 },
  });
  assert.deepEqual(
    [...new Set(issues.map((i) => i.issue))].sort(),
    ["count_for_non_participant", "missing_model_version", "negative_count", "non_integer_count"].sort()
  );
  assert.equal(issues.filter((i) => i.issue === "count_for_non_participant").length, 2);
});

test("Timestamp import stays usable for digest ordering fixtures", () => {
  assert.ok(Timestamp.fromMillis(1).toMillis() === 1);
});

// ---------------------------------------------------------------------------
// Read high-water mark: a recipient who marked the room read at or after the
// message's commit time is already covered by their reset (no phantom unread)
// ---------------------------------------------------------------------------

const COMMIT = new Timestamp(1_700_000_000, 500_000_000);
const BEFORE = new Timestamp(1_700_000_000, 499_999_999);
const AFTER = new Timestamp(1_700_000_000, 500_000_001);

test("HWM — no lastReadAt: every recipient is incremented", () => {
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: undefined, messageCommittedAt: COMMIT }),
    { increment: [B], alreadyRead: [] }
  );
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: {}, messageCommittedAt: COMMIT }),
    { increment: [B], alreadyRead: [] }
  );
});

test("HWM — lastReadAt before the commit: incremented; at or after: skipped", () => {
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [B]: BEFORE }, messageCommittedAt: COMMIT }),
    { increment: [B], alreadyRead: [] }
  );
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [B]: COMMIT }, messageCommittedAt: COMMIT }),
    { increment: [], alreadyRead: [B] }
  );
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [B]: AFTER }, messageCommittedAt: COMMIT }),
    { increment: [], alreadyRead: [B] }
  );
});

test("HWM — the sender's own lastReadAt never matters; the sender is never a recipient", () => {
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [A]: AFTER }, messageCommittedAt: COMMIT }),
    { increment: [B], alreadyRead: [] }
  );
});

test("HWM — group room: each member decided independently", () => {
  const lastReadAt = { u1: AFTER, u2: BEFORE, u4: COMMIT, u5: "garbage" };
  assert.deepEqual(
    recipientsToIncrement({ senderId: "u3", participantIds: SIX, lastReadAt, messageCommittedAt: COMMIT }),
    { increment: ["u2", "u5", "u6"], alreadyRead: ["u1", "u4"] }
  );
});

test("HWM — fails toward counting: garbage lastReadAt or unknown commit time increments", () => {
  for (const garbage of ["2026-10-22", 1_700_000_000_000, null, { seconds: 1 }, true]) {
    assert.deepEqual(
      recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [B]: garbage }, messageCommittedAt: COMMIT }),
      { increment: [B], alreadyRead: [] },
      `garbage lastReadAt ${JSON.stringify(garbage)}`
    );
  }
  assert.deepEqual(
    recipientsToIncrement({ senderId: A, participantIds: [A, B], lastReadAt: { [B]: AFTER }, messageCommittedAt: null }),
    { increment: [B], alreadyRead: [] }
  );
});

test("timestampAtOrAfter compares seconds then nanoseconds", () => {
  assert.equal(timestampAtOrAfter(COMMIT, COMMIT), true);
  assert.equal(timestampAtOrAfter(AFTER, COMMIT), true);
  assert.equal(timestampAtOrAfter(BEFORE, COMMIT), false);
  assert.equal(timestampAtOrAfter(new Timestamp(1_700_000_001, 0), COMMIT), true);
  assert.equal(timestampAtOrAfter(new Timestamp(1_699_999_999, 999_999_999), COMMIT), false);
});

test("messageCommitTime prefers the server create time over the createdAt field", () => {
  assert.equal(messageCommitTime({ createTime: COMMIT }, { createdAt: AFTER }), COMMIT);
  assert.equal(messageCommitTime({}, { createdAt: AFTER }), AFTER);
  assert.equal(messageCommitTime({}, { createdAt: "2026-10-22" }), null);
  assert.equal(messageCommitTime({}, {}), null);
});
