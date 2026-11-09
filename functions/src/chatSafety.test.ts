import assert from "node:assert/strict";
import test from "node:test";

import {
  buildClientMessageDocId,
  evaluateSendAuthorization,
  isRoomSendable,
  parseClientMessageId,
  peerOf,
} from "./chatSafety";

const alice = { userId: "alice", data: { adultVerified: true, realNameVerified: true } };

function room(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { type: "one_to_one", participantIds: ["alice", "bob"], status: "active", ...extra };
}

test("P1-2: lifecycle states — only an active, writable room accepts messages", () => {
  assert.equal(isRoomSendable(room()), true);
  assert.equal(isRoomSendable(room({ status: undefined })), true, "legacy rooms without status stay sendable");
  assert.equal(isRoomSendable(room({ writable: true })), true);
  for (const status of ["closed", "read_only", "archived", "ended", "unknown_state"]) {
    assert.equal(isRoomSendable(room({ status })), false, status);
  }
  assert.equal(isRoomSendable(room({ writable: false })), false, "writable:false refuses even when status is active");
});

test("P1-2: authorisation denials in order — missing room, non-participant, partition, lifecycle, block", () => {
  assert.equal(evaluateSendAuthorization({ room: undefined, roomExists: false, user: alice, blocked: false })?.code, "not-found");
  assert.equal(
    evaluateSendAuthorization({ room: room({ participantIds: ["bob", "carol"] }), roomExists: true, user: alice, blocked: false })?.code,
    "permission-denied",
    "a user removed from participantIds cannot send"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room({ dataPartition: "play_review" }), roomExists: true, user: alice, blocked: false })?.code,
    "permission-denied",
    "a production account cannot write into a review-partition room"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room(), roomExists: true, user: { userId: "alice", data: { dataPartition: "play_review" } }, blocked: false })?.code,
    "permission-denied",
    "a review account cannot write into a production room"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room(), roomExists: true, user: { userId: "alice", data: { isStudentVerified: true } }, blocked: false })?.code,
    "failed-precondition",
    "P1-7: an account without server-side adult verification cannot send"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room({ dataPartition: "play_review" }), roomExists: true, user: { userId: "alice", data: { dataPartition: "play_review" } }, blocked: false }),
    null,
    "the review partition is exempt from the adult gate"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room({ status: "closed" }), roomExists: true, user: alice, blocked: false })?.code,
    "failed-precondition"
  );
  assert.equal(
    evaluateSendAuthorization({ room: room(), roomExists: true, user: alice, blocked: true })?.code,
    "permission-denied"
  );
  assert.equal(evaluateSendAuthorization({ room: room(), roomExists: true, user: alice, blocked: false }), null);
});

test("P1-2: the peer of a two-person room is derived from participantIds, never from a client-mutable type", () => {
  assert.equal(peerOf(room(), "alice"), "bob");
  assert.equal(peerOf(room({ type: "group", roomType: "whatever" }), "alice"), "bob", "a spoofed type does not disable the block check");
  assert.equal(peerOf(room({ participantIds: ["alice", "bob", "carol"] }), "alice"), null, "group rooms have no single peer");
  assert.equal(peerOf(room(), "mallory"), null);
});

test("P1-2: clientMessageId is validated and maps to a sender-scoped deterministic document id", () => {
  assert.equal(parseClientMessageId(undefined), null);
  assert.equal(parseClientMessageId(null), null);
  assert.equal(parseClientMessageId("  7b1a2c3d-4e5f-6071-8293-a4b5c6d7e8f9 "), "7b1a2c3d-4e5f-6071-8293-a4b5c6d7e8f9");
  for (const bad of ["", "short", "has space 123", "x".repeat(65), 42, { id: 1 }]) {
    assert.throws(() => parseClientMessageId(bad), /clientMessageId is invalid/);
  }
  const id = buildClientMessageDocId("dm_a_b", "alice", "k".repeat(16));
  assert.match(id, /^c_[0-9a-f]{40}$/);
  assert.equal(id, buildClientMessageDocId("dm_a_b", "alice", "k".repeat(16)), "stable");
  assert.notEqual(id, buildClientMessageDocId("dm_a_b", "bob", "k".repeat(16)), "sender-scoped: another sender cannot collide");
  assert.notEqual(id, buildClientMessageDocId("dm_a_c", "alice", "k".repeat(16)), "room-scoped");
});
