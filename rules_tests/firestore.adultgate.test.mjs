/**
 * P1-7 — adult verification is enforced by the rules, not only by the Flutter
 * route guard: an account whose users document lacks the server-written
 * adultVerified/realNameVerified pair cannot like, ask or write into chat,
 * and cannot forge the flags itself. The review partition is exempt.
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

import { Timestamp, doc, setDoc, updateDoc } from "firebase/firestore";

const VERIFIED = "kakao_verified";
const UNVERIFIED = "kakao_unverified";
const HALF = "kakao_half";
const PEER = "kakao_peer";
const ROOM = "dm_unverified_peer";
const ROOM_OK = "dm_verified_peer";

async function seed(db) {
  await seedActiveUser(db, VERIFIED);
  await seedActiveUser(db, PEER);
  await seedActiveUser(db, UNVERIFIED, { adultVerified: false, realNameVerified: false, isStudentVerified: true });
  await seedActiveUser(db, HALF, { adultVerified: true, realNameVerified: false });
  for (const [id, a] of [[ROOM, UNVERIFIED], [ROOM_OK, VERIFIED]]) {
    await setDoc(doc(db, "chat_rooms", id), {
      roomId: id, type: "one_to_one", status: "active", participantIds: [a, PEER],
      participantInfo: { [a]: { nickname: "A", avatarUrl: "" }, [PEER]: { nickname: "P", avatarUrl: "" } },
      lastMessage: "hi",
    });
    await setDoc(doc(db, "chat_rooms", id, "promises", "p1"), {
      promiseId: "p1", messageId: "m1", requestedBy: PEER, requestedTo: a, status: "requested",
      dateTime: new Date(), place: "신촌", placeCategory: "cafe",
    });
  }
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

function like(from, to) {
  return { fromUserId: from, toUserId: to, action: "like", source: "test", createdAt: new Date() };
}

test("an unverified (or half-verified) account cannot create a like or an ask; a verified one can", async () => {
  await withClearedDb(seed);
  const un = await kakaoSession(UNVERIFIED);
  const half = await kakaoSession(HALF);
  const ok = await kakaoSession(VERIFIED);
  await assertFails(setDoc(doc(un, "interactions", "i1"), like(UNVERIFIED, PEER)));
  await assertFails(setDoc(doc(half, "interactions", "i2"), like(HALF, PEER)));
  await assertSucceeds(setDoc(doc(ok, "interactions", "i3"), like(VERIFIED, PEER)));
  const ask = (from) => ({ fromUserId: from, toUserId: PEER, text: "질문", status: "sent", createdAt: new Date(), updatedAt: new Date(), readAt: null, sourceScreen: "profile" });
  await assertFails(setDoc(doc(un, "asks", "a1"), ask(UNVERIFIED)));
  await assertSucceeds(setDoc(doc(ok, "asks", "a2"), ask(VERIFIED)));
});

test("an unverified account cannot write into chat (room metadata, promise card, promise accept); a verified one can", async () => {
  await withClearedDb(seed);
  const un = await kakaoSession(UNVERIFIED);
  const ok = await kakaoSession(VERIFIED);
  await assertFails(updateDoc(doc(un, "chat_rooms", ROOM), { lastMessage: "x", updatedAt: new Date() }));
  await assertSucceeds(updateDoc(doc(ok, "chat_rooms", ROOM_OK), { lastMessage: "x", updatedAt: new Date() }));
  const card = (sender) => ({
    senderId: sender, text: "약속 요청", type: "promise_request", promiseId: "p9",
    dateTime: Timestamp.now(), place: "홍대", placeCategory: "bar", status: "requested",
    isEdited: false, editedAt: null, createdAt: new Date(), updatedAt: new Date(),
  });
  await assertFails(setDoc(doc(un, "chat_rooms", ROOM, "messages", "m9"), card(UNVERIFIED)));
  await assertSucceeds(setDoc(doc(ok, "chat_rooms", ROOM_OK, "messages", "m9"), card(VERIFIED)));
  await assertFails(updateDoc(doc(un, "chat_rooms", ROOM, "promises", "p1"), { status: "confirmed", acceptedAt: new Date(), updatedAt: new Date() }));
  await assertSucceeds(updateDoc(doc(ok, "chat_rooms", ROOM_OK, "promises", "p1"), { status: "confirmed", acceptedAt: new Date(), updatedAt: new Date() }));
});

test("a client cannot grant itself adult verification through any users write branch", async () => {
  await withClearedDb(seed);
  const un = await kakaoSession(UNVERIFIED);
  await assertFails(updateDoc(doc(un, "users", UNVERIFIED), { adultVerified: true, realNameVerified: true }));
  await assertFails(updateDoc(doc(un, "users", UNVERIFIED), { adultVerified: true, realNameVerified: true, nickname: "x", updatedAt: new Date() }));
  await assertFails(setDoc(doc(un, "users", UNVERIFIED), { adultVerified: true, realNameVerified: true }, { merge: true }));
  // The P0-2 own-read-state write is not a dating write and stays available.
  await assertSucceeds(updateDoc(doc(un, "chat_rooms", ROOM), {
    [`unreadCounts.${UNVERIFIED}`]: 0,
    [`lastReadAt.${UNVERIFIED}`]: (await import("firebase/firestore")).serverTimestamp(),
  }));
});

test("the review partition is exempt: the fixed reviewer session likes without adult flags", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", "play-reviewer-v1"), { kakaoUserId: "play-reviewer-v1", isActive: true, status: "active", dataPartition: "play_review" });
    await setDoc(doc(db, "users", "play-fixture-b-01"), { isActive: true, status: "active", dataPartition: "play_review", loginDisabled: true });
  });
  const env = await getTestEnv();
  const reviewer = env
    .authenticatedContext("play-reviewer-v1", { appSession: true, playReviewer: true, dataPartition: "play_review" })
    .firestore();
  await assertSucceeds(setDoc(doc(reviewer, "interactions", "r1"), {
    fromUserId: "play-reviewer-v1", toUserId: "play-fixture-b-01", action: "like", source: "review",
    createdAt: new Date(), dataPartition: "play_review",
  }));
});
