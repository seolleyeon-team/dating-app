import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAnonymizedSenderId,
  buildDeletedMessageAnonymizePatch,
  shouldPurgeDeletedAuthorMessage,
} from "./accountDeletionChatLifecycle";
import {
  buildEventTeamCleanupPatch,
  planEventTeamMemberRemoval,
  shouldPurgeEmptyEventTeam,
} from "./accountDeletionEventTeamCleanup";
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
    bambooComments: [],
    friendInviteIds: [],
    eventTeamSetupIds: [],
    eventTeamInviteIds: [],
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
      bambooComments: [{ postId: "p1", commentId: "c1" }],
      friendInviteIds: ["inv1"],
      eventTeamSetupIds: ["team1"],
      eventTeamInviteIds: ["tinv1"],
    }),
  });

  const kinds = operations.map((op) => op.kind);
  assert.ok(kinds.includes("deleteInteraction"));
  assert.ok(kinds.includes("deleteAsk"));
  assert.ok(kinds.includes("deleteFriendship"));
  assert.ok(kinds.includes("deleteFriendEdge"));
  assert.ok(kinds.includes("endMatch"));
  assert.ok(kinds.includes("closeChatRoom"));
  assert.ok(kinds.includes("anonymizeChatMessages"));
  assert.ok(kinds.includes("deleteRecEvent"));
  assert.ok(kinds.includes("deleteRecEventsParent"));
  assert.ok(kinds.includes("softDeleteBambooPost"));
  assert.ok(kinds.includes("softDeleteBambooComment"));
  assert.ok(kinds.includes("scrubFriendInvite"));
  assert.ok(kinds.includes("removeEventTeamMember"));
  assert.ok(kinds.includes("cancelEventTeamInvite"));
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
      eventTeamInviteIds: ["x"],
    })
  );
  assert.equal(counts.interactionsDeleted, 2);
  assert.equal(counts.friendEdgesDeleted, 2);
  assert.equal(counts.matchesEnded, 1);
  assert.equal(counts.eventTeamInvitesCancelled, 1);
});

test("chat anonymize patch replaces sender and clears media keys", () => {
  const patch = buildDeletedMessageAnonymizePatch({ uid: "alice" });
  assert.equal(patch.authorDeleted, true);
  assert.equal(patch.senderId, buildAnonymizedSenderId("alice"));
  assert.equal(patch.senderDisplayName, DELETED_USER_DISPLAY_NAME);
  assert.equal(patch.legalHold, false);
  assert.ok(patch.purgeAfter instanceof Date);
  assert.ok(Object.prototype.hasOwnProperty.call(patch, "imageUrl"));
  assert.ok(Object.prototype.hasOwnProperty.call(patch, "storagePath"));
});

test("deleted message purge respects legal hold and purgeAfter", () => {
  const now = new Date("2026-07-30T00:00:00Z");
  assert.equal(
    shouldPurgeDeletedAuthorMessage({
      authorDeleted: true,
      legalHold: true,
      purgeAfter: new Date("2026-01-01T00:00:00Z"),
      now,
    }),
    false
  );
  assert.equal(
    shouldPurgeDeletedAuthorMessage({
      authorDeleted: true,
      legalHold: false,
      purgeAfter: new Date("2026-01-01T00:00:00Z"),
      now,
    }),
    true
  );
  assert.equal(
    shouldPurgeDeletedAuthorMessage({
      authorDeleted: true,
      legalHold: false,
      purgeAfter: new Date("2026-12-01T00:00:00Z"),
      purgedAt: new Date("2026-07-01T00:00:00Z"),
      now,
    }),
    false
  );
});

test("event team removal transfers leader and marks empty teams purge_pending", () => {
  const withPeers = planEventTeamMemberRemoval({
    uid: "alice",
    teamSetupId: "team1",
    data: {
      leaderUserId: "alice",
      acceptedUserIds: ["alice", "bob", "carol"],
      pendingInviteeIds: ["dave"],
      status: "active",
    },
  });
  assert.equal(withPeers.leaderUserId, "bob");
  assert.deepEqual(withPeers.acceptedUserIds, ["bob", "carol"]);
  assert.deepEqual(withPeers.pendingInviteeIds, ["dave"]);
  assert.equal(withPeers.empty, false);
  assert.equal(withPeers.status, "forming");

  const lastMember = planEventTeamMemberRemoval({
    uid: "alice",
    teamSetupId: "team1",
    data: {
      leaderUserId: "alice",
      acceptedUserIds: ["alice"],
      pendingInviteeIds: [],
      status: "forming",
    },
  });
  assert.equal(lastMember.empty, true);
  assert.equal(lastMember.status, "purge_pending");
  assert.equal(lastMember.leaderUserId, "");
  const patch = buildEventTeamCleanupPatch(lastMember);
  assert.equal(patch.status, "purge_pending");
  assert.equal(patch.lifecycleStatus, "purge_pending");
  assert.ok(patch.purgeAfter instanceof Date);
});

test("empty event team purge gate", () => {
  const now = new Date("2026-07-30T00:00:00Z");
  assert.equal(
    shouldPurgeEmptyEventTeam({
      status: "purge_pending",
      legalHold: false,
      purgeAfter: new Date("2026-06-01T00:00:00Z"),
      now,
    }),
    true
  );
  assert.equal(
    shouldPurgeEmptyEventTeam({
      status: "active",
      purgeAfter: new Date("2026-06-01T00:00:00Z"),
      now,
    }),
    false
  );
});
