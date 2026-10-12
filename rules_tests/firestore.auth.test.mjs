import { createHash } from "node:crypto";
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

/**
 * A legacy student-verification token exactly as sendStudentVerificationEmail
 * writes it (Admin SDK): the Kakao session's uid plus the mailbox it asked for.
 */
async function seedLegacyEmailLinkToken(db, tokenId, { email, kakaoUserId, expiresAt }) {
  await setDoc(doc(db, "emailLinkTokens", tokenId), {
    email,
    kakaoUserId,
    createdAt: Timestamp.now(),
    expiresAt: expiresAt ?? Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
  });
}

/**
 * The server-owned studentEmailBindings doc exactly as sendStudentVerificationEmail
 * reserves it at issuance (P0-1 uniqueness): id = sha256(normalized email).
 */
function studentEmailBindingId(email) {
  return createHash("sha256").update(email.trim().toLowerCase(), "utf8").digest("hex");
}

async function seedStudentEmailBinding(db, email, appUserId, overrides = {}) {
  await setDoc(doc(db, "studentEmailBindings", studentEmailBindingId(email)), {
    appUserId,
    emailHash: studentEmailBindingId(email),
    status: "pending",
    expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    createdAt: Timestamp.now(),
    updatedAt: Timestamp.now(),
    ...overrides,
  });
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

test("SEC-P0-01: even the owning app session cannot create emailLinkTokens", async () => {
  await seedVictim();
  const db = await kakaoSession(VICTIM);

  await assertFails(
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

// F8 (terms-gate-contract §0/§8): users CREATE is server-owned. An email-link
// session may only stamp verification onto a document the server already
// created — creating one would be a second account-creation path that never
// touches completePrimaryStudentEmailAuth (and therefore never records terms).
test("F8: an email-link session cannot create a brand-new users doc", async () => {
  await withClearedDb();
  const db = await emailLinkSession("emaillink_new", "newbie@yonsei.ac.kr");

  await assertFails(
    setDoc(doc(db, "users", "kakao_newbie_4000"), {
      kakaoUserId: "kakao_newbie_4000",
      isStudentVerified: true,
      studentEmail: "newbie@yonsei.ac.kr",
      verifiedAt: Timestamp.now(),
    })
  );
});

test("legit: an email-link session can verify a server-created users doc with its own email", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", "kakao_newbie_4000"), {
      kakaoUserId: "kakao_newbie_4000",
      nickname: "새 사용자",
    });
    // sendStudentVerificationEmail (Admin SDK) issues this for the Kakao
    // session that owns users/kakao_newbie_4000.
    await seedLegacyEmailLinkToken(db, "newbie-token-id", {
      email: "newbie@yonsei.ac.kr",
      kakaoUserId: "kakao_newbie_4000",
    });
    await seedStudentEmailBinding(db, "newbie@yonsei.ac.kr", "kakao_newbie_4000");
  });
  const db = await emailLinkSession("emaillink_new", "newbie@yonsei.ac.kr");

  await assertSucceeds(
    updateDoc(doc(db, "users", "kakao_newbie_4000"), {
      isStudentVerified: true,
      studentEmail: "newbie@yonsei.ac.kr",
      studentEmailLinkToken: "newbie-token-id",
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
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled(async (ctx) => {
    await seedLegacyEmailLinkToken(ctx.firestore(), "victim-rerun-token", {
      email: VICTIM_EMAIL,
      kakaoUserId: VICTIM,
    });
    await seedStudentEmailBinding(ctx.firestore(), VICTIM_EMAIL, VICTIM, {
      status: "confirmed",
    });
  });
  const db = await emailLinkSession("emaillink_victim", VICTIM_EMAIL);

  await assertSucceeds(
    updateDoc(doc(db, "users", VICTIM), {
      isStudentVerified: true,
      studentEmail: VICTIM_EMAIL,
      studentEmailLinkToken: "victim-rerun-token",
      verifiedAt: Timestamp.now(),
    })
  );
});

// ---------------------------------------------------------------------------
// P0-1 (2026-10 production audit) — cross-account student verification
// ---------------------------------------------------------------------------
// The email-link update branch proved the caller owns a Yonsei mailbox but
// never tied the caller to the TARGET document. One mailbox could therefore
// stamp isStudentVerified/studentEmail onto any users doc whose studentEmail
// was still empty, and isUserDocOwner() then treated that mailbox as the
// document owner. The binding is now the server-issued emailLinkTokens doc:
// sendStudentVerificationEmail writes {email, kakaoUserId: <caller uid>} with
// the Admin SDK, so only the account that requested the mail can be verified.

const UNBOUND_B = "kakao_unbound_b_5000";
const UNBOUND_C = "kakao_unbound_c_5001";

async function seedUnboundShells(extraSeed) {
  return withClearedDb(async (db) => {
    for (const uid of [ATTACKER, UNBOUND_B, UNBOUND_C]) {
      await setDoc(doc(db, "users", uid), { kakaoUserId: uid, nickname: "shell" });
    }
    if (extraSeed) await extraSeed(db);
  });
}

function verificationWrite(email, token) {
  return {
    isStudentVerified: true,
    studentEmail: email,
    verifiedAt: Timestamp.now(),
    ...(token === undefined ? {} : { studentEmailLinkToken: token }),
  };
}

test("P0-1: a verified mailbox cannot student-verify another account's unbound users doc", async () => {
  await seedUnboundShells();
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL))
  );
});

test("P0-1: the hosted-page write shape (set+merge with kakaoUserId) is denied without a token", async () => {
  await seedUnboundShells();
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    setDoc(
      doc(db, "users", UNBOUND_B),
      { kakaoUserId: UNBOUND_B, ...verificationWrite(ATTACKER_EMAIL) },
      { merge: true }
    )
  );
});

test("P0-1: one mailbox cannot be stamped onto a second and third account", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "attacker-own-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: ATTACKER,
    });
    await seedStudentEmailBinding(db, ATTACKER_EMAIL, ATTACKER);
  });
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  // The attacker's own, genuinely issued token only names the attacker.
  await assertSucceeds(
    updateDoc(
      doc(db, "users", ATTACKER),
      verificationWrite(ATTACKER_EMAIL, "attacker-own-token")
    )
  );
  for (const target of [UNBOUND_B, UNBOUND_C]) {
    await assertFails(
      updateDoc(doc(db, "users", target), verificationWrite(ATTACKER_EMAIL))
    );
    await assertFails(
      updateDoc(
        doc(db, "users", target),
        verificationWrite(ATTACKER_EMAIL, "attacker-own-token")
      )
    );
  }
});

test("P0-1: a token issued for a different mailbox does not authorize the caller", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: "owner-b@yonsei.ac.kr",
      kakaoUserId: UNBOUND_B,
    });
  });
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, "b-token"))
  );
});

test("P0-1: expired, missing, malformed and primary-auth tokens do not authorize the write", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "expired-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
      expiresAt: Timestamp.fromMillis(Date.now() - 60 * 1000),
    });
    // completePrimaryStudentEmailAuth tokens carry no kakaoUserId.
    await setDoc(doc(db, "emailLinkTokens", "primary-token"), {
      email: ATTACKER_EMAIL,
      purpose: "primary_auth",
      createdAt: Timestamp.now(),
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 60 * 1000),
    });
    await setDoc(doc(db, "emailLinkTokens", "no-expiry-token"), {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
      createdAt: Timestamp.now(),
    });
  });
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  for (const token of [
    "expired-token",
    "primary-token",
    "no-expiry-token",
    "does-not-exist",
    "bad/../token",
    "",
  ]) {
    await assertFails(
      updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, token))
    );
  }
  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, 12345))
  );
});

test("P0-1: an unverified email claim cannot use a valid token", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
    });
  });
  const env = await getTestEnv();
  const db = env
    .authenticatedContext("emaillink_unverified", {
      email: ATTACKER_EMAIL,
      email_verified: false,
    })
    .firestore();

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, "b-token"))
  );
});

test("P0-1: partial verification writes are denied (boolean only / email only)", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
    });
  });
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), { isStudentVerified: true })
  );
  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), { studentEmail: ATTACKER_EMAIL })
  );
  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), {
      studentEmail: ATTACKER_EMAIL,
      studentEmailLinkToken: "b-token",
    })
  );
});

test("P0-1: a valid token cannot be used to rewrite the kakaoUserId identity field", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
    });
  });
  const db = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), {
      ...verificationWrite(ATTACKER_EMAIL, "b-token"),
      kakaoUserId: "emaillink_attacker",
    })
  );
});

test("P0-1: a Kakao session cannot verify itself or another account, with or without a token", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "attacker-own-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: ATTACKER,
    });
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
    });
  });
  const db = await kakaoSession(ATTACKER);

  await assertFails(
    updateDoc(
      doc(db, "users", ATTACKER),
      verificationWrite(ATTACKER_EMAIL, "attacker-own-token")
    )
  );
  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, "b-token"))
  );
});

test("P0-1: unauthenticated clients cannot use a valid token", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: ATTACKER_EMAIL,
      kakaoUserId: UNBOUND_B,
    });
  });
  const db = await anon();

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(ATTACKER_EMAIL, "b-token"))
  );
});

test("P0-1: an unrelated account cannot touch a verified user's student email fields", async () => {
  await seedVictim();
  const kakaoDb = await kakaoSession(ATTACKER);
  const mailDb = await emailLinkSession("emaillink_attacker", ATTACKER_EMAIL);

  for (const db of [kakaoDb, mailDb]) {
    await assertFails(
      updateDoc(doc(db, "users", VICTIM), { studentEmail: ATTACKER_EMAIL })
    );
    await assertFails(
      updateDoc(doc(db, "users", VICTIM), { isStudentVerified: false })
    );
    await assertFails(
      updateDoc(doc(db, "users", VICTIM), { studentEmail: deleteField() })
    );
  }
});

// P0-1 uniqueness (hosted path): the token proves WHICH account asked, but
// two accounts can each hold a token for the same mailbox. The server decides
// uniqueness atomically when it reserves studentEmailBindings/{sha256(email)}
// at issuance; the hosted write is honoured only for the account that
// reservation names. Rules cannot decide uniqueness across documents — they
// only verify the server-made decision.

test("P0-1 uniqueness: two accounts each holding a valid token — only the account the binding names may verify", async () => {
  const email = "shared@yonsei.ac.kr";
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "shared-token-b", { email, kakaoUserId: UNBOUND_B });
    await seedLegacyEmailLinkToken(db, "shared-token-c", { email, kakaoUserId: UNBOUND_C });
    await seedStudentEmailBinding(db, email, UNBOUND_B);
  });
  const db = await emailLinkSession("emaillink_shared", email);

  await assertSucceeds(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(email, "shared-token-b"))
  );
  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_C), verificationWrite(email, "shared-token-c"))
  );
});

test("P0-1 uniqueness: a valid token without a server reservation does not verify", async () => {
  const email = "unreserved@yonsei.ac.kr";
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "unreserved-token", { email, kakaoUserId: UNBOUND_B });
  });
  const db = await emailLinkSession("emaillink_unreserved", email);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(email, "unreserved-token"))
  );
});

test("P0-1 uniqueness: a binding confirmed for another account blocks the hosted write even with a valid token", async () => {
  const email = "taken@yonsei.ac.kr";
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "taken-token", { email, kakaoUserId: UNBOUND_B });
    await seedStudentEmailBinding(db, email, UNBOUND_C, { status: "confirmed" });
  });
  const db = await emailLinkSession("emaillink_taken", email);

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(email, "taken-token"))
  );
});

test("P0-1 uniqueness: the binding is matched on the normalized mailbox, so a case-variant session cannot dodge it", async () => {
  const email = "mixedcase@yonsei.ac.kr";
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "mixed-token", { email, kakaoUserId: UNBOUND_B });
    await seedStudentEmailBinding(db, email, UNBOUND_C, { status: "confirmed" });
  });
  const db = await emailLinkSession("emaillink_mixed", "MixedCase@Yonsei.ac.kr");

  await assertFails(
    updateDoc(doc(db, "users", UNBOUND_B), verificationWrite(email, "mixed-token"))
  );
});

test("legit: the hosted-page write shape succeeds with the server-issued token", async () => {
  await seedUnboundShells(async (db) => {
    await seedLegacyEmailLinkToken(db, "b-token", {
      email: "owner-b@yonsei.ac.kr",
      kakaoUserId: UNBOUND_B,
    });
    await seedStudentEmailBinding(db, "owner-b@yonsei.ac.kr", UNBOUND_B);
  });
  // Firebase keeps the mailbox as typed; the server stores it lowercased.
  const db = await emailLinkSession("emaillink_owner_b", "Owner-B@yonsei.ac.kr");

  await assertSucceeds(
    setDoc(
      doc(db, "users", UNBOUND_B),
      {
        kakaoUserId: UNBOUND_B,
        isStudentVerified: true,
        studentEmail: "owner-b@yonsei.ac.kr",
        studentEmailLinkToken: "b-token",
        verifiedAt: Timestamp.now(),
      },
      { merge: true }
    )
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
