import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  anon,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
} from "firebase/firestore";

// Friend graph = friendInvites/{id} + friendships/{pairId} +
// users/{uid}/friends/{friendUid} + users.friendsCount. All of it is written
// only by the acceptFriendInvite callable (Admin SDK). A client that could
// write any of these could forge friendships, replay invites, or inflate
// its friend count.

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const PAIR_ID = [ALICE, BOB].sort().join("_");
const INVITE_ID = "invite_1";

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

function verifiedUser(uid) {
  return {
    kakaoUserId: uid,
    studentEmail: `${uid}@yonsei.ac.kr`,
    isStudentVerified: true,
    friendsCount: 1,
    onboarding: { nickname: uid },
  };
}

async function seedGraph(db) {
  await setDoc(doc(db, "users", ALICE), verifiedUser(ALICE));
  await setDoc(doc(db, "users", BOB), verifiedUser(BOB));
  await setDoc(doc(db, "friendInvites", INVITE_ID), {
    inviterUserId: ALICE,
    tokenHash: "f".repeat(64),
    status: "pending",
  });
  await setDoc(doc(db, "friendships", PAIR_ID), {
    pairId: PAIR_ID,
    userIds: [ALICE, BOB].sort(),
    status: "active",
  });
  await setDoc(doc(db, "users", ALICE, "friends", BOB), {
    friendUserId: BOB,
    pairId: PAIR_ID,
  });
  await setDoc(doc(db, "users", BOB, "friends", ALICE), {
    friendUserId: ALICE,
    pairId: PAIR_ID,
  });
}

test("SEC: client cannot create, read, update, or consume friendInvites", async () => {
  await withClearedDb(seedGraph);
  const db = await kakaoSession(BOB);

  await assertFails(getDoc(doc(db, "friendInvites", INVITE_ID)));
  await assertFails(getDocs(collection(db, "friendInvites")));
  await assertFails(
    setDoc(doc(db, "friendInvites", "forged"), {
      inviterUserId: ALICE,
      tokenHash: "0".repeat(64),
      status: "pending",
    }),
  );
  await assertFails(
    updateDoc(doc(db, "friendInvites", INVITE_ID), {
      status: "accepted",
      acceptedByUserId: BOB,
    }),
  );
  await assertFails(deleteDoc(doc(db, "friendInvites", INVITE_ID)));
});

test("SEC: client cannot forge or delete a canonical friendship", async () => {
  await withClearedDb(seedGraph);
  const db = await kakaoSession(BOB);
  const forgedPair = [BOB, "kakao_carol"].sort().join("_");

  await assertFails(
    setDoc(doc(db, "friendships", forgedPair), {
      pairId: forgedPair,
      userIds: [BOB, "kakao_carol"].sort(),
      status: "active",
    }),
  );
  await assertFails(updateDoc(doc(db, "friendships", PAIR_ID), { status: "removed" }));
  await assertFails(deleteDoc(doc(db, "friendships", PAIR_ID)));
  await assertFails(getDoc(doc(db, "friendships", PAIR_ID)));
});

test("SEC: client cannot add itself to anyone's friend list (either edge)", async () => {
  await withClearedDb(seedGraph);
  const db = await kakaoSession(BOB);

  await assertFails(
    setDoc(doc(db, "users", BOB, "friends", "kakao_carol"), {
      friendUserId: "kakao_carol",
      pairId: "x",
    }),
  );
  await assertFails(
    setDoc(doc(db, "users", "kakao_carol", "friends", BOB), {
      friendUserId: BOB,
      pairId: "x",
    }),
  );
  await assertFails(deleteDoc(doc(db, "users", BOB, "friends", ALICE)));
  await assertFails(deleteDoc(doc(db, "users", ALICE, "friends", BOB)));
});

test("SEC: client cannot inflate its own friendsCount", async () => {
  await withClearedDb(seedGraph);
  const db = await kakaoSession(BOB);

  await assertFails(updateDoc(doc(db, "users", BOB), { friendsCount: 999 }));
  await assertFails(
    updateDoc(doc(db, "users", BOB), { friendsCount: 2, updatedAt: new Date() }),
  );
});

test("SEC: client cannot forge team membership or team invitations (share-link redemption is server-only)", async () => {
  await withClearedDb(async (db) => {
    await seedGraph(db);
    await setDoc(doc(db, "eventTeamSetups", "team_1"), {
      leaderUserId: ALICE,
      acceptedUserIds: [ALICE],
      pendingInviteeIds: [BOB],
      memberCount: 1,
    });
    await setDoc(doc(db, "eventTeamInvites", "inv_1"), {
      teamSetupId: "team_1",
      inviterUserId: ALICE,
      inviteeUserId: BOB,
      status: "pending",
    });
  });
  const db = await kakaoSession(BOB);

  // The invitee may read but never flip the authoritative status field.
  await assertSucceeds(getDoc(doc(db, "eventTeamInvites", "inv_1")));
  await assertFails(updateDoc(doc(db, "eventTeamInvites", "inv_1"), { status: "accepted" }));
  await assertFails(deleteDoc(doc(db, "eventTeamInvites", "inv_1")));

  await assertFails(
    updateDoc(doc(db, "eventTeamSetups", "team_1"), {
      acceptedUserIds: [ALICE, BOB],
      memberCount: 2,
    }),
  );
  await assertFails(
    updateDoc(doc(db, "eventTeamSetups", "team_1"), { pendingInviteeIds: [BOB] }),
  );
  await assertFails(
    setDoc(doc(db, "eventTeamInvites", "forged"), {
      teamSetupId: "team_1",
      inviterUserId: ALICE,
      inviteeUserId: BOB,
      status: "pending",
    }),
  );
});

test("legit: owner can read its own friend list; others and anon cannot", async () => {
  await withClearedDb(seedGraph);

  const bob = await kakaoSession(BOB);
  const own = await assertSucceeds(getDocs(collection(bob, "users", BOB, "friends")));
  assert.equal(own.size, 1);
  assert.equal(own.docs[0].id, ALICE);
  await assertSucceeds(getDoc(doc(bob, "users", BOB, "friends", ALICE)));

  await assertFails(getDocs(collection(bob, "users", ALICE, "friends")));
  await assertFails(getDoc(doc(bob, "users", ALICE, "friends", BOB)));

  const stranger = await anon();
  await assertFails(getDocs(collection(stranger, "users", BOB, "friends")));
});
