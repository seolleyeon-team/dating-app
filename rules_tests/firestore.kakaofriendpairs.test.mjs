import test from "node:test";

import {
  anon,
  appSession,
  assertFails,
  assertSucceeds,
  emailLinkSession,
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
  query,
  setDoc,
  Timestamp,
  updateDoc,
  where,
} from "firebase/firestore";

// ---------------------------------------------------------------------------
// Kakao friend one-time snapshot (kakao-friend-pairs-contract §2/§3/§10):
// - kakaoFriendPairs is a server-only social-graph materialization. It must
//   be denied for EVERY client session, including a member of the pair
//   reading their own pair doc (learning "we are Kakao friends" about the
//   other member is exactly the leak the deny-all prevents).
// - users/{uid}.kakaoFriendSnapshot and .kakaoFriendAvoidanceEnabled are
//   server-written only (callables); the owner's own session must not be
//   able to forge them (e.g. faking a "completed" snapshot to skip the
//   one-time snapshot gate).
// - recommendationExclusions keeps its shape: owner-readable targets,
//   never client-writable.
// ---------------------------------------------------------------------------

const ME = "app_user_1000";
const OTHER = "app_user_2000";
const THIRD = "app_user_3000";
const MY_EMAIL = "me@yonsei.ac.kr";

// Same construction as buildRecommendationExclusionPairId: sorted join.
const PAIR_ID = [ME, OTHER].sort().join("_");

function seed() {
  return withClearedDb(async (db) => {
    await setDoc(doc(db, "users", ME), {
      kakaoUserId: ME,
      isStudentVerified: true,
      studentEmail: MY_EMAIL,
      nickname: "나",
    });
    await setDoc(doc(db, "users", OTHER), {
      kakaoUserId: OTHER,
      isStudentVerified: true,
      studentEmail: "other@yonsei.ac.kr",
      nickname: "상대",
    });
    // A pair doc whose memberUids CONTAINS the caller (ME) — reads must
    // still be denied.
    await setDoc(doc(db, "kakaoFriendPairs", PAIR_ID), {
      pairId: PAIR_ID,
      memberUids: [ME, OTHER].sort(),
      source: "kakao_friend_snapshot",
      discoveredByUids: [ME],
      avoidanceEnabledBy: [ME],
      avoidanceActive: true,
      createdAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
      schemaVersion: 1,
    });
    // Materialized exclusion for the regression test below.
    await setDoc(doc(db, "recommendationExclusions", ME, "targets", OTHER), {
      pairId: PAIR_ID,
      userIds: [ME, OTHER].sort(),
      source: "kakao_friend_pair",
      reason: "kakao_friend_avoidance",
      active: true,
      enabledBy: { [ME]: true, [OTHER]: false },
      createdAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
    });
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// kakaoFriendPairs — denied for every session, including own-member docs
// ---------------------------------------------------------------------------

function pairOps(db) {
  const newPairId = [ME, THIRD].sort().join("_");
  return [
    // get: a doc whose memberUids contains the caller's own uid.
    () => getDoc(doc(db, "kakaoFriendPairs", PAIR_ID)),
    // list: whole collection.
    () => getDocs(collection(db, "kakaoFriendPairs")),
    // list: even scoped to "my own pairs".
    () =>
      getDocs(
        query(
          collection(db, "kakaoFriendPairs"),
          where("memberUids", "array-contains", ME)
        )
      ),
    // create.
    () =>
      setDoc(doc(db, "kakaoFriendPairs", newPairId), {
        pairId: newPairId,
        memberUids: [ME, THIRD].sort(),
        source: "kakao_friend_snapshot",
        discoveredByUids: [ME],
        avoidanceEnabledBy: [],
        avoidanceActive: false,
        createdAt: Timestamp.now(),
        updatedAt: Timestamp.now(),
        schemaVersion: 1,
      }),
    // update: e.g. flipping avoidance state on an existing own pair.
    () =>
      updateDoc(doc(db, "kakaoFriendPairs", PAIR_ID), {
        avoidanceEnabledBy: [],
        avoidanceActive: false,
        updatedAt: Timestamp.now(),
      }),
    // delete.
    () => deleteDoc(doc(db, "kakaoFriendPairs", PAIR_ID)),
  ];
}

test("kakaoFriendPairs denies anon, email-link, kakao and appSession clients (incl. own-member docs)", async () => {
  await seed();

  for (const db of [
    await anon(),
    await emailLinkSession(ME, MY_EMAIL),
    await kakaoSession(ME),
    await appSession(ME),
  ]) {
    for (const op of pairOps(db)) {
      await assertFails(op());
    }
  }
});

// ---------------------------------------------------------------------------
// users snapshot/preference fields — not writable by the owner's own session
// ---------------------------------------------------------------------------

test("owner sessions cannot forge kakaoFriendSnapshot or kakaoFriendAvoidanceEnabled on their users doc", async () => {
  await seed();

  for (const db of [await kakaoSession(ME), await appSession(ME)]) {
    // Faking a completed snapshot would skip the one-time snapshot gate.
    await assertFails(
      updateDoc(doc(db, "users", ME), {
        kakaoFriendSnapshot: {
          status: "completed",
          pairCount: 0,
          schemaVersion: 1,
        },
        updatedAt: Timestamp.now(),
      })
    );
    // The avoidance preference is server-written via callable only.
    await assertFails(
      updateDoc(doc(db, "users", ME), {
        kakaoFriendAvoidanceEnabled: true,
        updatedAt: Timestamp.now(),
      })
    );
    // Merge-writes must not slip through either.
    await assertFails(
      setDoc(
        doc(db, "users", ME),
        { kakaoFriendSnapshot: { status: "completed" } },
        { merge: true }
      )
    );
    // Control: the same session CAN still update an allowlisted field, so
    // the denials above are about the fields, not the session.
    await assertSucceeds(
      updateDoc(doc(db, "users", ME), {
        nickname: "새 닉네임",
        updatedAt: Timestamp.now(),
      })
    );
  }
});

// ---------------------------------------------------------------------------
// Regression — recommendationExclusions targets stay owner-readable and
// never client-writable
// ---------------------------------------------------------------------------

test("regression: recommendationExclusions targets are owner-readable, never client-writable", async () => {
  await seed();

  for (const db of [await kakaoSession(ME), await appSession(ME)]) {
    // Owner get/list keep working (the client feed filter depends on this).
    await assertSucceeds(
      getDoc(doc(db, "recommendationExclusions", ME, "targets", OTHER))
    );
    await assertSucceeds(
      getDocs(collection(db, "recommendationExclusions", ME, "targets"))
    );
    // Create is denied even for the owner — writes belong to the callables.
    await assertFails(
      setDoc(doc(db, "recommendationExclusions", ME, "targets", THIRD), {
        pairId: [ME, THIRD].sort().join("_"),
        userIds: [ME, THIRD].sort(),
        source: "kakao_friend_pair",
        reason: "kakao_friend_avoidance",
        active: true,
        enabledBy: { [ME]: true, [THIRD]: false },
        createdAt: Timestamp.now(),
        updatedAt: Timestamp.now(),
      })
    );
    // Update/delete of an existing doc are denied for the owner too.
    await assertFails(
      updateDoc(doc(db, "recommendationExclusions", ME, "targets", OTHER), {
        active: false,
      })
    );
    await assertFails(
      deleteDoc(doc(db, "recommendationExclusions", ME, "targets", OTHER))
    );
  }

  // A non-member cannot read someone else's targets.
  const otherDb = await kakaoSession(OTHER);
  await assertFails(
    getDoc(doc(otherDb, "recommendationExclusions", ME, "targets", OTHER))
  );
});
