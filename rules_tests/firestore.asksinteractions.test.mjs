/**
 * P1-10 — asks and interactions carry no client-controlled identity, obey a
 * strict schema, and are refused between blocked users.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  seedActiveUser,
  withClearedDb,
} from "./helpers.mjs";

import { doc, serverTimestamp, setDoc } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const MALLORY = "kakao_mallory";

async function seed(db) {
  await seedActiveUser(db, ALICE);
  await seedActiveUser(db, BOB);
  await seedActiveUser(db, MALLORY);
  // Bob blocked Mallory (server-written, both directions as reportAndBlockUser does).
  await setDoc(doc(db, "blocks", BOB, "targets", MALLORY), { createdAt: new Date() });
  await setDoc(doc(db, "blocks", MALLORY, "targets", BOB), { createdAt: new Date() });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

function ask(from, to, extra = {}) {
  return {
    fromUserId: from,
    toUserId: to,
    text: "안녕하세요, 질문이 있어요",
    status: "sent",
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
    readAt: null,
    sourceScreen: "profile_specific_detail_screen",
    ...extra,
  };
}

function like(from, to, extra = {}) {
  return { fromUserId: from, toUserId: to, action: "like", source: "profile_specific_detail_screen", createdAt: serverTimestamp(), ...extra };
}

test("a legitimate ask (question only) is accepted", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(setDoc(doc(alice, "asks", "a1"), ask(ALICE, BOB)));
  await assertSucceeds(setDoc(doc(alice, "asks", "a2"), { fromUserId: ALICE, toUserId: BOB, text: "짧게", status: "sent" }));
});

test("a sender cannot attach a profile snapshot (fake nickname, external image) or any extra field", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(setDoc(doc(alice, "asks", "a1"), ask(ALICE, BOB, {
    fromUserProfileSnapshot: { uid: ALICE, nickname: "운영팀", profileImageUrl: "https://attacker.example/track.png", universityName: "연세대" },
  })));
  await assertFails(setDoc(doc(alice, "asks", "a2"), ask(ALICE, BOB, {
    toUserProfileSnapshot: { uid: BOB, nickname: "x" },
  })));
  await assertFails(setDoc(doc(alice, "asks", "a3"), ask(ALICE, BOB, { imageUrl: "https://attacker.example/a.png" })));
  await assertFails(setDoc(doc(alice, "asks", "a4"), ask(ALICE, BOB, { senderNickname: "운영팀" })));
});

test("ask schema: oversized text, wrong status, pre-read, bogus timestamps, spoofed sender and self-ask are refused", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(setDoc(doc(alice, "asks", "a1"), ask(ALICE, BOB, { text: "x".repeat(501) })));
  await assertFails(setDoc(doc(alice, "asks", "a2"), ask(ALICE, BOB, { text: "" })));
  await assertFails(setDoc(doc(alice, "asks", "a3"), ask(ALICE, BOB, { status: "read" })));
  await assertFails(setDoc(doc(alice, "asks", "a4"), ask(ALICE, BOB, { readAt: new Date() })));
  await assertFails(setDoc(doc(alice, "asks", "a5"), ask(ALICE, BOB, { createdAt: new Date(2020, 1, 1) })));
  await assertFails(setDoc(doc(alice, "asks", "a6"), ask(BOB, ALICE)));
  await assertFails(setDoc(doc(alice, "asks", "a7"), ask(ALICE, ALICE)));
  await assertFails(setDoc(doc(alice, "asks", "a8"), ask(ALICE, BOB, { sourceScreen: "s".repeat(65) })));
});

test("blocks: neither side of a block can ask or like the other", async () => {
  await withClearedDb(seed);
  const mallory = await kakaoSession(MALLORY);
  const bob = await kakaoSession(BOB);
  await assertFails(setDoc(doc(mallory, "asks", "m1"), ask(MALLORY, BOB)));
  await assertFails(setDoc(doc(bob, "asks", "b1"), ask(BOB, MALLORY)));
  await assertFails(setDoc(doc(mallory, "interactions", "mi1"), like(MALLORY, BOB)));
  await assertFails(setDoc(doc(bob, "interactions", "bi1"), like(BOB, MALLORY)));
  // Unrelated pair unaffected.
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(setDoc(doc(alice, "interactions", "ai1"), like(ALICE, BOB)));
});

test("interaction schema: action allowlist, source bound, metadata shape, spoofed sender, self-target", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  for (const action of ["like", "super_like", "nope", "view"]) {
    await assertSucceeds(setDoc(doc(alice, "interactions", `ok_${action}`), like(ALICE, BOB, { action })));
  }
  await assertSucceeds(setDoc(doc(alice, "interactions", "ok_message"), like(ALICE, BOB, {
    action: "message", source: "chat", metadata: { messagePreview: "안녕" },
  })));
  await assertSucceeds(setDoc(doc(alice, "interactions", "ok_null_meta"), like(ALICE, BOB, { metadata: null })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_action"), like(ALICE, BOB, { action: "block" })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_action2"), like(ALICE, BOB, { action: "match" })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_source"), like(ALICE, BOB, { source: "" })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_meta_key"), like(ALICE, BOB, { metadata: { nickname: "운영팀" } })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_meta_len"), like(ALICE, BOB, { action: "message", metadata: { messagePreview: "x".repeat(201) } })));
  await assertFails(setDoc(doc(alice, "interactions", "bad_meta_type"), like(ALICE, BOB, { metadata: "string" })));
  await assertFails(setDoc(doc(alice, "interactions", "spoof"), like(BOB, ALICE)));
  await assertFails(setDoc(doc(alice, "interactions", "self"), like(ALICE, ALICE)));
  await assertFails(setDoc(doc(alice, "interactions", "old_time"), like(ALICE, BOB, { createdAt: new Date(2020, 1, 1) })));
  await assertFails(setDoc(doc(alice, "interactions", "extra"), like(ALICE, BOB, { nickname: "x" })));
});

test("the deterministic client id for one-shot decisions is accepted, and a second write to it is refused (create-only)", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  const id = `${ALICE}_${BOB}_like`;
  await assertSucceeds(setDoc(doc(alice, "interactions", id), like(ALICE, BOB)));
  await assertFails(setDoc(doc(alice, "interactions", id), like(ALICE, BOB)));
  await assertFails(setDoc(doc(alice, "interactions", id), like(ALICE, BOB), { merge: true }));
});
