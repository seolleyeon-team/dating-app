/**
 * NEW-24 — the account-state policy on the real handlers and the real
 * Firestore engine: active allowed; suspended / banned / withdrawn / inactive
 * refused; the state is read per call (an ID token issued before a
 * suspension stops working at once); verification-recovery, account-deletion,
 * operator and Play-review paths behave as declared in
 * callableAccountStatePolicy.ts.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-auth \
 *     "node --test functions/<outDir>/accountStateGate.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import {
  getCommunityModerationAccess,
  getPlayReviewFeed,
  recordTermsAcceptance,
  sendStudentVerificationEmail,
  spendHearts,
  syncContactBlocks,
  syncKakaoTalkFriendBlocks,
  unlockDirectChat,
  updateProfileVisibility,
} from "./index";
import { resolveAccountDeletionOwner } from "./accountDeletionAuthorization";
import { createLinkKakaoFriendIdentityFunction, kakaoIdentityHash } from "./kakaoIdentityLink";
import { PLAY_REVIEWER_UID, resolvePlayReviewUser } from "./playReviewAccess";

type Runnable = { run: (request: unknown) => Promise<unknown> };
type Auth = { uid: string; token: Record<string, unknown> };
const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

const RESTRICTED: Record<string, Record<string, unknown>> = {
  // exactly what decideCommunityReport / lockAccountForDeletion write
  suspended: { status: "suspended", loginDisabled: true, isActive: false, moderationActionType: "indefinite_suspension" },
  banned: { status: "banned", loginDisabled: true, isActive: false, moderationActionType: "permanent_ban" },
  withdrawn: { status: "deleting", isWithdrawn: true, loginDisabled: true, canRejoin: false, profileVisible: false },
  inactive: { isActive: false },
};

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid,
    isStudentVerified: true,
    studentEmail: `${uid}@yonsei.ac.kr`,
    nickname: uid,
    ...extra,
  });
}

function call(fn: unknown, auth: Auth | null, data: Record<string, unknown> = {}) {
  return (fn as Runnable).run({ data, auth, rawRequest: {} }) as Promise<Record<string, unknown>>;
}

async function outcome(promise: Promise<unknown>): Promise<{ code: string; detail: unknown; message: string }> {
  try {
    await promise;
  } catch (error) {
    const e = error as { code?: string; details?: { detail?: unknown }; message?: string };
    return { code: String(e.code), detail: e.details?.detail ?? null, message: String(e.message) };
  }
  return { code: "ok", detail: null, message: "" };
}

const session = (uid: string, claims: Record<string, unknown> = {}): Auth => ({ uid, token: claims });
const TERMS = {
  version: "2026-05-16",
  acceptedDocumentIds: ["termsOfService", "privacyPolicy", "kakaoNamePhone", "ageOver20"],
};

test("G1 shared resolver: active passes, every restricted state is refused with its own detail", async () => {
  const active = fresh("active");
  await seedUser(active, { status: "active", isActive: true, loginDisabled: false });
  // spendHearts is retired: reaching its own refusal proves the resolver let the caller through.
  const passed = await outcome(call(spendHearts, session(active)));
  assert.equal(passed.code, "failed-precondition");
  assert.equal(passed.detail, null);

  for (const [state, fields] of Object.entries(RESTRICTED)) {
    const uid = fresh(state);
    await seedUser(uid, fields);
    const refused = await outcome(call(spendHearts, session(uid)));
    assert.deepEqual([refused.code, refused.detail], ["permission-denied", `account_${state}`], state);
    assert.match(refused.message, /이용이 정지된 계정이에요/);
  }
});

test("G2 a token issued before the suspension is refused on the very next call, and works again after restore", async () => {
  const uid = fresh("stale");
  await seedUser(uid);
  const auth = session(uid); // the same, still-valid ID token throughout
  assert.equal((await call(updateProfileVisibility, auth, { visible: false })).visible, false);

  await db.collection("users").doc(uid).set(RESTRICTED.suspended, { merge: true });
  const refused = await outcome(call(updateProfileVisibility, auth, { visible: true }));
  assert.deepEqual([refused.code, refused.detail], ["permission-denied", "account_suspended"]);
  assert.equal((await db.collection("users").doc(uid).get()).get("profileVisible"), false, "nothing written while suspended");

  // restoreCommunityAccount
  await db.collection("users").doc(uid).set({ status: "active", loginDisabled: false, isActive: true }, { merge: true });
  assert.equal((await call(updateProfileVisibility, auth, { visible: true })).visible, true);
});

test("G3 re-consent: an unverified active account may record terms, a restricted one may not", async () => {
  const unverified = fresh("unverified");
  await seedUser(unverified, { isStudentVerified: false, studentEmail: null });
  assert.equal((await call(recordTermsAcceptance, session(unverified), TERMS)).recorded, true);

  for (const [state, fields] of Object.entries(RESTRICTED)) {
    const uid = fresh(`terms_${state}`);
    await seedUser(uid, fields);
    const refused = await outcome(call(recordTermsAcceptance, session(uid), TERMS));
    assert.deepEqual([refused.code, refused.detail], ["permission-denied", `account_${state}`], state);
    assert.equal((await db.collection("users").doc(uid).get()).get("termsAcceptance"), undefined);
  }
});

test("G4 contact sync: needs the caller's own active account document", async () => {
  const active = fresh("contacts");
  await seedUser(active, { isStudentVerified: false });
  const done = await outcome(call(syncContactBlocks, session(active), { contactHashes: [] }));
  assert.equal(done.code, "ok");

  const noDocument = await outcome(call(syncContactBlocks, session(fresh("email_link_only")), { contactHashes: [] }));
  assert.equal(noDocument.code, "failed-precondition");

  const hash = "a".repeat(64);
  for (const [state, fields] of Object.entries(RESTRICTED)) {
    const uid = fresh(`contacts_${state}`);
    await seedUser(uid, fields);
    const refused = await outcome(call(syncContactBlocks, session(uid), { contactHashes: [hash] }));
    assert.deepEqual([refused.code, refused.detail], ["permission-denied", `account_${state}`], state);
    assert.equal((await db.collection("users").doc(uid).collection("contactBlockedHashes").get()).size, 0);
  }
});

test("G5 legacy verification mail: unverified active account reaches the mail step, restricted account does not", async () => {
  const data = { email: "someone@yonsei.ac.kr", requestId: "request_id_0123456789" };
  const unverified = fresh("legacy");
  await seedUser(unverified, { isStudentVerified: false, studentEmail: null });
  const reached = await outcome(call(sendStudentVerificationEmail, session(unverified), data));
  // No mail sender is configured under test: the refusal comes from AFTER the gate.
  assert.equal(reached.code, "failed-precondition");
  assert.equal(reached.detail, null);

  const suspended = fresh("legacy_suspended");
  await seedUser(suspended, { isStudentVerified: false, studentEmail: null, ...RESTRICTED.suspended });
  const refused = await outcome(call(sendStudentVerificationEmail, session(suspended), data));
  assert.deepEqual([refused.code, refused.detail], ["permission-denied", "account_suspended"]);
});

test("G6 legacy Kakao friend sync (real callable, mocked Kakao): wrong-app token and restricted account are refused", async () => {
  const realFetch = globalThis.fetch;
  const previousAppId = process.env.KAKAO_APP_ID;
  process.env.KAKAO_APP_ID = "1234567";
  let tokenAppId = 1234567;
  let memberId = "";
  const urls: string[] = [];
  globalThis.fetch = (async (input: unknown) => {
    const url = String(input);
    urls.push(url);
    const body = url.endsWith("/v1/user/access_token_info")
      ? { id: Number(memberId), app_id: tokenAppId, expires_in: 100 }
      : url.endsWith("/v2/user/me")
        ? { id: Number(memberId) }
        : null;
    if (!body) throw new Error("unexpected outbound request");
    return { ok: true, status: 200, json: async () => body };
  }) as unknown as typeof fetch;
  try {
    // legacy invariant: Firebase uid == Kakao member number
    memberId = String(4_000_000_000 + Math.floor(Math.random() * 1_000_000));
    await seedUser(memberId);
    tokenAppId = 7654321;
    const foreign = await outcome(call(syncKakaoTalkFriendBlocks, session(memberId), { kakaoAccessToken: "t" }));
    assert.equal(foreign.code, "unauthenticated", "a token of another Kakao app must not authenticate");
    assert.equal((await db.collection("users").doc(memberId).get()).get("kakaoFriendReconcileStatus"), undefined);

    tokenAppId = 1234567;
    await db.collection("users").doc(memberId).set(RESTRICTED.banned, { merge: true });
    urls.length = 0;
    const refused = await outcome(call(syncKakaoTalkFriendBlocks, session(memberId), { kakaoAccessToken: "t" }));
    assert.deepEqual([refused.code, refused.detail], ["permission-denied", "account_banned"]);
    assert.equal(urls.some((u) => u.includes("/talk/friends")), false, "no friend list is fetched for a banned account");
    assert.equal((await db.collection("users").doc(memberId).get()).get("kakaoFriendReconcileStatus"), undefined);
  } finally {
    globalThis.fetch = realFetch;
    if (previousAppId === undefined) delete process.env.KAKAO_APP_ID;
    else process.env.KAKAO_APP_ID = previousAppId;
  }
});

test("G7 Kakao identity link: active links, restricted is refused and no mapping is written", async () => {
  const kakaoId = (uid: string) => `kakao_of_${uid}`;
  const link = createLinkKakaoFriendIdentityFunction({
    db,
    verifyKakaoAccessToken: async (accessToken) => ({ userId: accessToken }),
  });
  const active = fresh("link");
  await seedUser(active, { kakaoUserId: null });
  assert.deepEqual(await call(link, session(active), { kakaoAccessToken: kakaoId(active) }), { linked: true, alreadyLinked: false });

  for (const [state, fields] of Object.entries(RESTRICTED)) {
    const uid = fresh(`link_${state}`);
    await seedUser(uid, { kakaoUserId: null, ...fields });
    const refused = await outcome(call(link, session(uid), { kakaoAccessToken: kakaoId(uid) }));
    assert.deepEqual([refused.code, refused.detail], ["permission-denied", `account_${state}`], state);
    assert.equal((await db.collection("kakaoIdentities").doc(kakaoIdentityHash(kakaoId(uid))).get()).exists, false);
  }
});

test("G8 Play review: isolated session, no cross-partition access, and the same state policy", async () => {
  const reviewerRef = db.collection("users").doc(PLAY_REVIEWER_UID);
  const reviewerDoc = {
    accountType: "google_play_review",
    dataPartition: "play_review",
    reviewAccess: true,
    reviewProfileReady: true,
    nickname: "reviewer",
  };
  const reviewClaims = { playReviewer: true, dataPartition: "play_review", appSession: true };
  const reviewer = session(PLAY_REVIEWER_UID, reviewClaims);
  await reviewerRef.set(reviewerDoc);
  try {
    assert.equal((await resolvePlayReviewUser(db, reviewer)).userId, PLAY_REVIEWER_UID);

    // A production account cannot enter the review plane, with or without forged claims.
    const production = fresh("prod");
    await seedUser(production, { adultVerified: true, realNameVerified: true });
    assert.equal((await outcome(call(getPlayReviewFeed, session(production)))).code, "permission-denied");
    assert.equal((await outcome(call(getPlayReviewFeed, session(production, reviewClaims)))).code, "permission-denied");

    // The review session is not an app account for callables that did not opt in …
    assert.equal((await outcome(call(spendHearts, reviewer))).code, "failed-precondition");
    // … and on one that did, it cannot reach a production account.
    const cross = await outcome(call(unlockDirectChat, reviewer, { partnerId: production }));
    assert.equal(cross.code, "permission-denied");
    assert.match(cross.message, /partitions do not match/);
    // Nor can a production account open a chat with the review account.
    const reverse = await outcome(call(unlockDirectChat, session(production), { partnerId: PLAY_REVIEWER_UID }));
    assert.equal(reverse.code, "permission-denied");
    assert.equal((await db.collection("chat_rooms").where("participantIds", "array-contains", production).get()).size, 0);

    // A moderation decision on the review account takes effect like on any other.
    await reviewerRef.set(RESTRICTED.suspended, { merge: true });
    const suspended = await outcome(resolvePlayReviewUser(db, reviewer));
    assert.deepEqual([suspended.code, suspended.detail], ["permission-denied", "account_suspended"]);
    assert.equal((await outcome(call(getPlayReviewFeed, reviewer))).code, "permission-denied");
  } finally {
    await reviewerRef.delete();
  }
});

test("G9 operator authority is the operations claim plus admin/{uid}, independent of an app account", async () => {
  const operatorUid = fresh("operator");
  await db.collection("admin").doc(operatorUid).set({ active: true });
  const operator = session(operatorUid, { operations: true });
  assert.deepEqual(await call(getCommunityModerationAccess, operator), { allowed: true, operatorId: operatorUid });

  // An ordinary active account is not an operator; neither is a claim without the admin record.
  const user = fresh("user");
  await seedUser(user);
  assert.equal((await outcome(call(getCommunityModerationAccess, session(user)))).code, "permission-denied");
  assert.equal((await outcome(call(getCommunityModerationAccess, session(user, { operations: true })))).code, "permission-denied");
  await db.collection("admin").doc(operatorUid).set({ active: false });
  assert.equal((await outcome(call(getCommunityModerationAccess, operator))).code, "permission-denied");
});

test("G10 account deletion stays available in every state (owner-lifecycle exemption preserved)", async () => {
  for (const [state, fields] of Object.entries(RESTRICTED)) {
    const uid = fresh(`delete_${state}`);
    await seedUser(uid, fields);
    const owner = await resolveAccountDeletionOwner(db, session(uid) as never);
    assert.deepEqual(owner, { uid, usersDocExists: true, isStudentVerified: true }, state);
  }
  const noDocument = fresh("delete_no_doc");
  assert.deepEqual(await resolveAccountDeletionOwner(db, session(noDocument) as never), {
    uid: noDocument,
    usersDocExists: false,
    isStudentVerified: false,
  });
});
