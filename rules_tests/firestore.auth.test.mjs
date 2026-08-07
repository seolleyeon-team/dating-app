import test from "node:test";

import {
  anon,
  assertFails,
  assertSucceeds,
  emailLinkSession,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  doc,
  collection,
  deleteField,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
  Timestamp,
} from "firebase/firestore";

const VICTIM = "kakao_victim_1000";
const ATTACKER = "kakao_attacker_2000";
const VICTIM_EMAIL = "victim@yonsei.ac.kr";
const ATTACKER_EMAIL = "attacker@yonsei.ac.kr";

/** A fully onboarded, student-verified user document. */
function verifiedUserDoc(uid, email) {
  return {
    kakaoUserId: uid,
    isStudentVerified: true,
    studentEmail: email,
    nickname: "테스트",
    onboarding: { nickname: "테스트", birthYear: "2003", major: "컴퓨터과학" },
    preferenceVector: [0.1, 0.2, 0.3],
  };
}

async function seedVictim() {
  return withClearedDb(async (db) => {
    await setDoc(doc(db, "users", VICTIM), verifiedUserDoc(VICTIM, VICTIM_EMAIL));
    await setDoc(
      doc(db, "users", ATTACKER),
      verifiedUserDoc(ATTACKER, ATTACKER_EMAIL)
    );
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// SEC-P0-01 — emailLinkTokens forgery leading to account takeover
// ---------------------------------------------------------------------------

test("SEC-P0-01: unauthenticated clients cannot forge an emailLinkTokens doc", async () => {
  await seedVictim();
  const db = await anon();

  // The takeover primitive: plant a token doc that names the victim, then
  // exchange it for a custom token via the callable.
  await assertFails(
    setDoc(doc(db, "emailLinkTokens", "attacker-chosen-id"), {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    })
  );
});

test("SEC-P0-01: a signed-in user cannot create an emailLinkTokens doc for another uid", async () => {
  await seedVictim();
  const db = await kakaoSession(ATTACKER);

  await assertFails(
    setDoc(doc(db, "emailLinkTokens", "attacker-chosen-id-2"), {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    })
  );
});

test("legit: the app creates an emailLinkTokens doc for its own session uid", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertSucceeds(
    setDoc(doc(db, "emailLinkTokens", "own-token-id"), {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    })
  );
});

test("legit: the unauthenticated verification web page can still read the token doc", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "emailLinkTokens", "web-token-id"), {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    });
  });

  const db = await anon();
  await assertSucceeds(getDoc(doc(db, "emailLinkTokens", "web-token-id")));
});

test("SEC-P0-01: clients cannot mark an emailLinkTokens doc as email-verified", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "emailLinkTokens", "mark-token-id"), {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    });
  });

  const attackerDb = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);
  await assertFails(
    updateDoc(doc(attackerDb, "emailLinkTokens", "mark-token-id"), {
      emailVerifiedUid: "emaillink_attacker",
      emailVerifiedAt: Timestamp.now(),
    })
  );

  const ownerDb = await emailLinkSession("emaillink_victim", VICTIM_EMAIL);
  await assertFails(
    updateDoc(doc(ownerDb, "emailLinkTokens", "mark-token-id"), {
      emailVerifiedUid: "emaillink_victim",
      emailVerifiedAt: Timestamp.now(),
    })
  );
});

// ---------------------------------------------------------------------------
// SEC-P0-02 — unauthenticated users-doc creation / student verification forgery
// ---------------------------------------------------------------------------

test("SEC-P0-02: unauthenticated clients cannot create a users doc", async () => {
  await withClearedDb();
  const db = await anon();

  await assertFails(
    setDoc(doc(db, "users", "kakao_squatted_3000"), {
      kakaoUserId: "kakao_squatted_3000",
      nickname: "무단생성",
      createdAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-02: unauthenticated clients cannot self-assert student verification", async () => {
  await withClearedDb();
  const db = await anon();

  await assertFails(
    setDoc(doc(db, "users", "kakao_squatted_3001"), {
      kakaoUserId: "kakao_squatted_3001",
      isStudentVerified: true,
      studentEmail: "forged@yonsei.ac.kr",
      studentVerifiedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-02: a Kakao session cannot self-assert student verification", async () => {
  await withClearedDb();
  const db = await kakaoSession(ATTACKER);

  await assertFails(
    setDoc(doc(db, "users", ATTACKER), {
      kakaoUserId: ATTACKER,
      isStudentVerified: true,
      studentEmail: ATTACKER_EMAIL,
      studentVerifiedAt: Timestamp.now(),
    })
  );
});

test("legit: a Kakao session can create its own unverified shell doc", async () => {
  await withClearedDb();
  const db = await kakaoSession(ATTACKER);

  await assertSucceeds(
    setDoc(doc(db, "users", ATTACKER), {
      kakaoUserId: ATTACKER,
      nickname: "새 사용자",
      createdAt: Timestamp.now(),
      lastLoginAt: Timestamp.now(),
    })
  );
});

test("legit: an email-link session can verify a brand-new users doc with its own email", async () => {
  await withClearedDb();
  const db = await emailLinkSession("emaillink_new", "newbie@yonsei.ac.kr");

  await assertSucceeds(
    setDoc(doc(db, "users", "kakao_newbie_4000"), {
      kakaoUserId: "kakao_newbie_4000",
      isStudentVerified: true,
      studentEmail: "newbie@yonsei.ac.kr",
      verifiedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-02: an email-link session cannot verify a doc with someone else's email", async () => {
  await withClearedDb();
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    setDoc(doc(db, "users", "kakao_newbie_4001"), {
      kakaoUserId: "kakao_newbie_4001",
      isStudentVerified: true,
      studentEmail: VICTIM_EMAIL,
      verifiedAt: Timestamp.now(),
    })
  );
});

// ---------------------------------------------------------------------------
// SEC-P0-03 — studentEmail overwrite leading to profile takeover
// ---------------------------------------------------------------------------

test("SEC-P0-03: a Yonsei-email holder cannot rebind another user's studentEmail", async () => {
  await seedVictim();
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  // Repointing studentEmail at the attacker would make isUserDocOwner() true
  // for the attacker on the victim's document.
  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      isStudentVerified: true,
      studentEmail: ATTACKER_EMAIL,
      verifiedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-03: an email-link session cannot rewrite a verified doc to a third-party email", async () => {
  await seedVictim();
  const db = await emailLinkSession("emaillink_victim", VICTIM_EMAIL);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      isStudentVerified: true,
      studentEmail: "someoneelse@yonsei.ac.kr",
      verifiedAt: Timestamp.now(),
    })
  );
});

test("legit: re-running email verification with the same email stays allowed", async () => {
  await seedVictim();
  const db = await emailLinkSession("emaillink_victim", VICTIM_EMAIL);

  await assertSucceeds(
    updateDoc(doc(db, "users", VICTIM), {
      isStudentVerified: true,
      studentEmail: VICTIM_EMAIL,
      verifiedAt: Timestamp.now(),
    })
  );
});

test("legit: the owning Kakao session can still edit its own onboarding data", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertSucceeds(
    updateDoc(doc(db, "users", VICTIM), {
      onboarding: { nickname: "바뀐닉", birthYear: "2003", major: "전기전자" },
      onboardingUpdatedAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
    })
  );
});

test("cross-user: a signed-in user cannot edit another user's onboarding data", async () => {
  await seedVictim();
  const db = await kakaoSession(ATTACKER);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      onboarding: { nickname: "탈취", birthYear: "2003", major: "전기전자" },
      updatedAt: Timestamp.now(),
    })
  );
});

// ---------------------------------------------------------------------------
// SEC-P0-04 — unauthenticated mass read of the users collection
// ---------------------------------------------------------------------------

test("SEC-P0-04: unauthenticated clients cannot read a user document", async () => {
  await seedVictim();
  const db = await anon();

  await assertFails(getDoc(doc(db, "users", VICTIM)));
});

test("SEC-P0-04: unauthenticated clients cannot list the users collection", async () => {
  await seedVictim();
  const db = await anon();

  await assertFails(getDocs(collection(db, "users")));
});

test("SEC-P0-04b: signed-in clients cannot list the users collection", async () => {
  await seedVictim();
  const db = await kakaoSession(ATTACKER);

  await assertFails(getDocs(collection(db, "users")));
});

test("SEC-P0-USER-DOC-IDOR: signed-in clients cannot read another user's private users doc", async () => {
  await seedVictim();
  const db = await kakaoSession(ATTACKER);

  await assertFails(getDoc(doc(db, "users", VICTIM)));
});

test("legit: a signed-in user can read their own private users doc", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertSucceeds(getDoc(doc(db, "users", VICTIM)));
});

test("legit: a signed-in user can read another user's publicProfiles doc", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", VICTIM), verifiedUserDoc(VICTIM, VICTIM_EMAIL));
    await setDoc(doc(db, "publicProfiles", VICTIM), {
      uid: VICTIM,
      kakaoUserId: VICTIM,
      nickname: "테스트",
      profileImageUrl: "https://cdn.example/a.png",
      status: "active",
      isWithdrawn: false,
      profileVisible: true,
      isStudentVerified: true,
      onboarding: { nickname: "테스트", major: "컴퓨터과학", birthYear: "2003" },
      schemaVersion: 1,
    });
  });
  const db = await kakaoSession(ATTACKER);

  await assertSucceeds(getDoc(doc(db, "publicProfiles", VICTIM)));
});

test("SEC-P0-USER-DOC-IDOR: clients cannot write publicProfiles", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertFails(
    setDoc(doc(db, "publicProfiles", VICTIM), {
      uid: VICTIM,
      nickname: "forged",
      studentEmail: "leak@yonsei.ac.kr",
    })
  );
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot clear loginDisabled", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", VICTIM), {
      ...verifiedUserDoc(VICTIM, VICTIM_EMAIL),
      loginDisabled: true,
    });
  });
  const db = await kakaoSession(VICTIM);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      loginDisabled: false,
      updatedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot forge withdrawal or rejoin fields", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      status: "withdrawn",
      isWithdrawn: true,
      canRejoin: true,
      rejoinRestricted: false,
      scheduledHardDeleteAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot delete or forge verification timestamps", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      studentVerifiedAt: Timestamp.now(),
      verifiedAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot forge role/admin/premium/permission", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  for (const payload of [
    { role: "admin", updatedAt: Timestamp.now() },
    { admin: true, updatedAt: Timestamp.now() },
    { verified: true, updatedAt: Timestamp.now() },
    { schoolVerified: true, updatedAt: Timestamp.now() },
    { premium: true, updatedAt: Timestamp.now() },
    { permission: "all", updatedAt: Timestamp.now() },
  ]) {
    await assertFails(updateDoc(doc(db, "users", VICTIM), payload));
  }
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot clear loginDisabled when absent via add", async () => {
  // changedKeys() would miss this — field is newly added, not "changed".
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      loginDisabled: false,
      updatedAt: Timestamp.now(),
    })
  );
});

test("SEC-P0-PROTECTED-FIELDS: owner cannot null or deleteField protected fields", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", VICTIM), {
      ...verifiedUserDoc(VICTIM, VICTIM_EMAIL),
      loginDisabled: true,
      studentVerifiedAt: Timestamp.now(),
    });
  });
  const db = await kakaoSession(VICTIM);

  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      loginDisabled: null,
      updatedAt: Timestamp.now(),
    })
  );
  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      loginDisabled: deleteField(),
      updatedAt: Timestamp.now(),
    })
  );
  await assertFails(
    updateDoc(doc(db, "users", VICTIM), {
      studentVerifiedAt: deleteField(),
      updatedAt: Timestamp.now(),
    })
  );
});

test("legit: owner can update ordinary profile fields", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertSucceeds(
    updateDoc(doc(db, "users", VICTIM), {
      nickname: "새닉네임",
      updatedAt: Timestamp.now(),
    })
  );
});
