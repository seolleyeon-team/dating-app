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
  applySocialCleanupOperation,
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
    bambooPostMappingIds: [],
    bambooCommentMappingIds: [],
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

test("SEC-04 소유권 매핑도 삭제 대상에 들어간다", () => {
  // 매핑을 남기면 계정을 지운 뒤에도 uid -> 작성글 연결이 그대로 남는다.
  const operations = planAccountDeletionSocialOperations({
    uid: "alice",
    docs: docs({
      bambooPostIds: ["p1"],
      bambooComments: [{ postId: "p1", commentId: "c1" }],
      bambooPostMappingIds: ["p1"],
      bambooCommentMappingIds: ["p1__c1"],
    }),
  });

  const mappingOps = operations.filter(
    (op) => op.kind === "deleteBambooOwnershipMapping"
  );
  assert.deepEqual(mappingOps, [
    {
      kind: "deleteBambooOwnershipMapping",
      collection: "bamboo_post_authors",
      id: "p1",
    },
    {
      kind: "deleteBambooOwnershipMapping",
      collection: "bamboo_comment_authors",
      id: "p1__c1",
    },
  ]);

  // 내용 정리가 먼저다. 매핑을 먼저 지우고 중간에 실패하면 어떤 글이 이
  // 사용자 것이었는지 다시 찾을 방법이 없다.
  const firstMapping = operations.findIndex(
    (op) => op.kind === "deleteBambooOwnershipMapping"
  );
  const lastContent = operations.reduce(
    (acc, op, i) =>
      op.kind === "softDeleteBambooPost" ||
      op.kind === "softDeleteBambooComment"
        ? i
        : acc,
    -1
  );
  assert.ok(lastContent >= 0);
  assert.ok(firstMapping > lastContent);
});

test("SEC-04 매핑이 없는 레거시 계정은 매핑 삭제를 계획하지 않는다", () => {
  const operations = planAccountDeletionSocialOperations({
    uid: "alice",
    docs: docs({
      bambooPostIds: ["p1"],
      bambooComments: [{ postId: "p1", commentId: "c1" }],
    }),
  });
  assert.equal(
    operations.some((op) => op.kind === "deleteBambooOwnershipMapping"),
    false
  );
});

test("SEC-04 매핑 삭제 건수는 글/댓글 매핑을 합산한다", () => {
  const counts = socialCountsFromDocs(
    docs({
      bambooPostMappingIds: ["p1", "p2"],
      bambooCommentMappingIds: ["p1__c1"],
    })
  );
  assert.equal(counts.bambooOwnershipMappingsDeleted, 3);
});

// -----------------------------------------------------------------------------
// deleteFriendEdge keeps the survivor's users.friendsCount in step with the
// canonical users/{uid}/friends edges (minimal in-memory Firestore double).
// -----------------------------------------------------------------------------

class EdgeFakeFirestore {
  readonly store = new Map<string, Record<string, unknown>>();

  seed(path: string, data: Record<string, unknown>): void {
    this.store.set(path, { ...data });
  }

  private ref(path: string): FakeRef {
    return new FakeRef(this, path);
  }

  collection(name: string): { doc(id: string): FakeRef } {
    return { doc: (id: string) => this.ref(`${name}/${id}`) };
  }

  async runTransaction<T>(
    fn: (tx: {
      get(ref: FakeRef): Promise<FakeSnap>;
      delete(ref: FakeRef): void;
      set(ref: FakeRef, data: Record<string, unknown>, opts?: unknown): void;
    }) => Promise<T>
  ): Promise<T> {
    const writes: Array<() => void> = [];
    const result = await fn({
      get: async (ref) => new FakeSnap(this.store.get(ref.path)),
      delete: (ref) => writes.push(() => this.store.delete(ref.path)),
      set: (ref, data) =>
        writes.push(() =>
          this.store.set(ref.path, { ...(this.store.get(ref.path) ?? {}), ...data })
        ),
    });
    for (const write of writes) write();
    return result;
  }
}

class FakeRef {
  constructor(private readonly db: EdgeFakeFirestore, readonly path: string) {}
  collection(name: string): { doc(id: string): FakeRef } {
    return { doc: (id: string) => new FakeRef(this.db, `${this.path}/${name}/${id}`) };
  }
}

class FakeSnap {
  constructor(private readonly data_: Record<string, unknown> | undefined) {}
  get exists(): boolean {
    return this.data_ !== undefined;
  }
  get(field: string): unknown {
    return this.data_?.[field];
  }
  data(): Record<string, unknown> | undefined {
    return this.data_;
  }
}

function friendGraph(): EdgeFakeFirestore {
  const db = new EdgeFakeFirestore();
  db.seed("users/alice", { friendsCount: 2 });
  db.seed("users/bob", { friendsCount: 1 });
  db.seed("users/alice/friends/bob", { friendUserId: "bob" });
  db.seed("users/bob/friends/alice", { friendUserId: "alice" });
  db.seed("users/alice/friends/carol", { friendUserId: "carol" });
  return db;
}

async function deleteEdge(db: EdgeFakeFirestore, uid: string, otherUid: string) {
  await applySocialCleanupOperation(
    db as unknown as Parameters<typeof applySocialCleanupOperation>[0],
    uid,
    { kind: "deleteFriendEdge", otherUid }
  );
}

test("deleteFriendEdge removes both edges and decrements the survivor's friendsCount once", async () => {
  const db = friendGraph();
  await deleteEdge(db, "bob", "alice");

  assert.equal(db.store.has("users/bob/friends/alice"), false);
  assert.equal(db.store.has("users/alice/friends/bob"), false);
  assert.equal(db.store.get("users/alice")?.friendsCount, 1);
  // The deleted account's own counter is irrelevant (the doc is purged) and
  // the unrelated edge alice→carol is untouched.
  assert.equal(db.store.has("users/alice/friends/carol"), true);
});

test("deleteFriendEdge is idempotent: a retry never decrements twice or below zero", async () => {
  const db = friendGraph();
  await deleteEdge(db, "bob", "alice");
  await deleteEdge(db, "bob", "alice");
  assert.equal(db.store.get("users/alice")?.friendsCount, 1);

  db.seed("users/dave", { friendsCount: 0 });
  db.seed("users/dave/friends/bob", { friendUserId: "bob" });
  await deleteEdge(db, "bob", "dave");
  assert.equal(db.store.get("users/dave")?.friendsCount, 0);
});

test("deleteFriendEdge tolerates a survivor without a friendsCount field", async () => {
  const db = friendGraph();
  db.seed("users/erin", {});
  db.seed("users/erin/friends/bob", { friendUserId: "bob" });
  await deleteEdge(db, "bob", "erin");
  assert.equal(db.store.has("users/erin/friends/bob"), false);
  assert.equal(db.store.get("users/erin")?.friendsCount, 0);
});
