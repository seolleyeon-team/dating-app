import assert from "node:assert/strict";
import test from "node:test";

import {
  DELETED_USER_DISPLAY_NAME,
  buildFriendPairId,
  planAccountDeletionSocialOperations,
  socialCountsFromDocs,
  type AccountDeletionSocialDocs,
} from "./accountDeletionSocialCleanup";

function docs(
  overrides: Partial<AccountDeletionSocialDocs> = {}
): AccountDeletionSocialDocs {
  return {
    interactionIds: [],
    askIds: [],
    friendshipIds: [],
    friendOtherUids: [],
    matchIds: [],
    chatRoomIds: [],
    recEventIds: [],
    bambooPostIds: [],
    friendInviteIds: [],
    eventTeamSetupIds: [],
    ...overrides,
  };
}

test("friend pair id matches index.ts sorting without prefix", () => {
  assert.equal(buildFriendPairId("bob", "alice"), "alice_bob");
  assert.equal(buildFriendPairId("alice", "bob"), "alice_bob");
});

test("plan deletes owned edges and deactivates shared 1:1", () => {
  const operations = planAccountDeletionSocialOperations({
    uid: "alice",
    docs: docs({
      interactionIds: ["i1"],
      askIds: ["a1"],
      friendshipIds: ["alice_bob"],
      friendOtherUids: ["bob"],
      matchIds: ["m1"],
      chatRoomIds: ["dm_alice_bob"],
      recEventIds: ["e1", "e2"],
      bambooPostIds: ["p1"],
      friendInviteIds: ["inv1"],
      eventTeamSetupIds: ["team1"],
    }),
  });

  const kinds = operations.map((op) => op.kind);
  assert.ok(kinds.includes("deleteInteraction"));
  assert.ok(kinds.includes("deleteAsk"));
  assert.ok(kinds.includes("deleteFriendship"));
  assert.ok(kinds.includes("deleteFriendEdge"));
  assert.ok(kinds.includes("endMatch"));
  assert.ok(kinds.includes("closeChatRoom"));
  assert.ok(kinds.includes("deleteRecEvent"));
  assert.ok(kinds.includes("deleteRecEventsParent"));
  assert.ok(kinds.includes("softDeleteBambooPost"));
  assert.ok(kinds.includes("scrubFriendInvite"));
  assert.ok(kinds.includes("removeEventTeamMember"));
  assert.equal(DELETED_USER_DISPLAY_NAME, "탈퇴한 사용자");
});

test("recEvents parent delete is only planned when events exist", () => {
  const empty = planAccountDeletionSocialOperations({
    uid: "alice",
    docs: docs(),
  });
  assert.equal(
    empty.some((op) => op.kind === "deleteRecEventsParent"),
    false
  );
});

test("social counts mirror planned docs", () => {
  const counts = socialCountsFromDocs(
    docs({
      interactionIds: ["i1", "i2"],
      friendOtherUids: ["bob"],
      matchIds: ["m1"],
    })
  );
  assert.equal(counts.interactionsDeleted, 2);
  assert.equal(counts.friendEdgesDeleted, 2);
  assert.equal(counts.matchesEnded, 1);
});
