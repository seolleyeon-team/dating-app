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

import { doc, getDoc, setDoc, Timestamp } from "firebase/firestore";

// ---------------------------------------------------------------------------
// Auth re-architecture (identity-contract §2/§6): the interactive surfaces
// (publicProfiles get, interactions/asks/chat_rooms/bamboo_posts create)
// require a CANONICAL app session — either the new `appSession: true` claim
// minted by completePrimaryStudentEmailAuth, or the legacy `kakaoUserId`
// claim from createFirebaseCustomToken. A temporary email-link session
// (verified Yonsei email, pre-exchange) carries neither and must be denied.
// ---------------------------------------------------------------------------

const ME = "app_user_1000";
const OTHER = "app_user_2000";
const MY_EMAIL = "me@yonsei.ac.kr";

function seedSocialGraph() {
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
    await setDoc(doc(db, "publicProfiles", OTHER), {
      uid: OTHER,
      kakaoUserId: OTHER,
      nickname: "상대",
      profileImageUrl: "https://cdn.example/a.png",
      status: "active",
      isWithdrawn: false,
      profileVisible: true,
      isStudentVerified: true,
      schemaVersion: 1,
    });
  });
}

/** The five gated writes/reads, parameterized by the acting session. */
function gatedOps(db, suffix) {
  return {
    getPublicProfile: () => getDoc(doc(db, "publicProfiles", OTHER)),
    createInteraction: () =>
      setDoc(doc(db, "interactions", `like_${suffix}`), {
        fromUserId: ME,
        toUserId: OTHER,
        action: "like",
        source: "daily_recs",
        createdAt: Timestamp.now(),
      }),
    createAsk: () =>
      setDoc(doc(db, "asks", `ask_${suffix}`), {
        fromUserId: ME,
        toUserId: OTHER,
        text: "안녕하세요, 궁금한 게 있어요",
        status: "sent",
      }),
    createChatRoom: () =>
      setDoc(doc(db, "chat_rooms", `dm_${suffix}`), {
        roomId: `dm_${suffix}`,
        participantIds: [ME, OTHER],
        lastMessage: "",
      }),
    createBambooPost: () =>
      setDoc(doc(db, "bamboo_posts", `post_${suffix}`), {
        postId: `post_${suffix}`,
        authorId: ME,
        content: "대나무숲 첫 글",
        category: "일상",
        tags: [],
        likeCount: 0,
        commentCount: 0,
        score7d: 0,
        isDeleted: false,
      }),
  };
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// Temporary email-link session (pre-exchange) — denied on all five surfaces
// ---------------------------------------------------------------------------

test("an email-link session cannot use any canonical-session surface", async () => {
  await seedSocialGraph();
  // Same uid as the app user, but only email claims — this models the window
  // between Firebase email-link sign-in and the custom-token exchange.
  const db = await emailLinkSession(ME, MY_EMAIL);
  const ops = gatedOps(db, "emaillink");

  await assertFails(ops.getPublicProfile());
  await assertFails(ops.createInteraction());
  await assertFails(ops.createAsk());
  await assertFails(ops.createChatRoom());
  await assertFails(ops.createBambooPost());
});

test("an unauthenticated client cannot use any canonical-session surface", async () => {
  await seedSocialGraph();
  const db = await anon();
  const ops = gatedOps(db, "anon");

  await assertFails(ops.getPublicProfile());
  await assertFails(ops.createInteraction());
  await assertFails(ops.createAsk());
  await assertFails(ops.createChatRoom());
  await assertFails(ops.createBambooPost());
});

// ---------------------------------------------------------------------------
// Legacy Kakao custom-token session (kakaoUserId claim) — still allowed
// ---------------------------------------------------------------------------

test("a legacy kakao session keeps every canonical-session surface", async () => {
  await seedSocialGraph();
  const db = await kakaoSession(ME);
  const ops = gatedOps(db, "kakao");

  await assertSucceeds(ops.getPublicProfile());
  await assertSucceeds(ops.createInteraction());
  await assertSucceeds(ops.createAsk());
  // 1:1 방 생성은 unlockDirectChat callable(하트 차감) 전용 — canonical
  // 세션이어도 클라이언트 직접 생성은 거부된다.
  await assertFails(ops.createChatRoom());
  await assertSucceeds(ops.createBambooPost());
});

// ---------------------------------------------------------------------------
// New canonical session (appSession claim, no kakaoUserId) — allowed
// ---------------------------------------------------------------------------

test("a canonical appSession token can use every canonical-session surface", async () => {
  await seedSocialGraph();
  const db = await appSession(ME);
  const ops = gatedOps(db, "appsession");

  await assertSucceeds(ops.getPublicProfile());
  await assertSucceeds(ops.createInteraction());
  await assertSucceeds(ops.createAsk());
  // 1:1 방 생성은 unlockDirectChat callable(하트 차감) 전용 — canonical
  // 세션이어도 클라이언트 직접 생성은 거부된다.
  await assertFails(ops.createChatRoom());
  await assertSucceeds(ops.createBambooPost());
});

// ---------------------------------------------------------------------------
// Server-owned identity indexes — denied to everyone, including "owners"
// ---------------------------------------------------------------------------

const EMAIL_HASH = "a".repeat(64);
const KAKAO_IDENTITY_HASH = "b".repeat(64);

function identityIndexOps(db) {
  return [
    () => getDoc(doc(db, "studentEmailBindings", EMAIL_HASH)),
    () =>
      setDoc(doc(db, "studentEmailBindings", EMAIL_HASH), {
        appUserId: ME,
        emailHash: EMAIL_HASH,
        createdAt: Timestamp.now(),
        updatedAt: Timestamp.now(),
      }),
    () => getDoc(doc(db, "kakaoIdentities", KAKAO_IDENTITY_HASH)),
    () =>
      setDoc(doc(db, "kakaoIdentities", KAKAO_IDENTITY_HASH), {
        appUserId: ME,
        kakaoUserId: ME,
        linkedAt: Timestamp.now(),
        status: "active",
      }),
  ];
}

test("identity indexes deny anon, email-link, kakao and appSession clients", async () => {
  await withClearedDb(async (db) => {
    // Seed "own" docs so the read denials are exercised against real data.
    await setDoc(doc(db, "studentEmailBindings", EMAIL_HASH), {
      appUserId: ME,
      emailHash: EMAIL_HASH,
    });
    await setDoc(doc(db, "kakaoIdentities", KAKAO_IDENTITY_HASH), {
      appUserId: ME,
      kakaoUserId: ME,
      status: "active",
    });
  });

  for (const db of [
    await anon(),
    await emailLinkSession(ME, MY_EMAIL),
    await kakaoSession(ME),
    await appSession(ME),
  ]) {
    for (const op of identityIndexOps(db)) {
      await assertFails(op());
    }
  }
});

// ---------------------------------------------------------------------------
// Regression — the temporary email-link session must KEEP its users-doc
// verification writes (legacy web completion page, firestore.rules
// users create Branch A / update Branch 1) until force-update.
// ---------------------------------------------------------------------------

test("regression: an email-link session still verifies a brand-new users doc", async () => {
  await withClearedDb();
  const db = await emailLinkSession("emaillink_fresh", "fresh@yonsei.ac.kr");

  await assertSucceeds(
    setDoc(doc(db, "users", "app_user_fresh_5000"), {
      kakaoUserId: "app_user_fresh_5000",
      isStudentVerified: true,
      studentEmail: "fresh@yonsei.ac.kr",
      verifiedAt: Timestamp.now(),
    })
  );
});
