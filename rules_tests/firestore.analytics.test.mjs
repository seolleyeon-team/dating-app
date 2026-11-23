/**
 * B-06 — blindMeetingAnalytics / meetingIcebreakerAnalytics.
 *
 * Both collections used to accept UNAUTHENTICATED creates of any size with
 * arbitrary extra fields. A create now needs a canonical app session, the
 * exact shape the client sinks write ({event, params, createdAt}), a server
 * timestamp, allow-listed param keys with bounded scalar values and, when a
 * user hash is present, the hash of the caller's own uid.
 */
import test from "node:test";
import { createHash } from "node:crypto";

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
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  serverTimestamp,
  setDoc,
  updateDoc,
} from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const REVIEWER = "play-reviewer-v1";

const BLIND = "blindMeetingAnalytics";
const ICE = "meetingIcebreakerAnalytics";

/** BlindMeetingAnalytics.hashUserId (blind_meeting_analytics.dart). */
function userHash(uid) {
  return createHash("sha256").update(uid, "utf8").digest("hex").slice(0, 16);
}

/** FirestoreBlindMeetingAnalyticsSink.send. */
function blindEvent(params = {}, extra = {}) {
  return {
    event: "blind_meeting_schedule_submitted",
    params,
    createdAt: serverTimestamp(),
    ...extra,
  };
}

/** FirestoreMeetingIcebreakerAnalyticsSink.send. */
function iceEvent(params = {}, extra = {}) {
  return {
    event: "meeting_roulette_spin_completed",
    params,
    createdAt: serverTimestamp(),
    ...extra,
  };
}

async function reviewerSession() {
  const env = await getTestEnv();
  return env
    .authenticatedContext(REVIEWER, {
      appSession: true,
      playReviewer: true,
      dataPartition: "play_review",
    })
    .firestore();
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("B-06 blind: every event shape the client sink writes is accepted (Kakao and canonical sessions)", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  const bob = await appSession(BOB);
  // No params (card viewed / intro viewed).
  await assertSucceeds(addDoc(collection(alice, BLIND), blindEvent({}, { event: "blind_meeting_card_viewed" })));
  // Every allow-listed key with the value types the screens send.
  await assertSucceeds(addDoc(collection(alice, BLIND), blindEvent({
    meetingId: "meeting_20261121_abc",
    isAlcoholFree: true,
    selectedDateCount: 3,
    availabilityWindowDays: 14,
    crossesMonthBoundary: false,
    relaxationChoice: "expandDates",
    addedDateCount: 2,
    candidateDateCount: 4,
    votedDateCount: 1,
    stage: "waiting",
    selectionCount: 2,
    phase: "meetup",
    urgent: false,
    algorithmVersion: "v2",
    ratingAverage: 4.5,
    userHash: userHash(ALICE),
  })));
  await assertSucceeds(addDoc(collection(bob, BLIND), blindEvent({ meetingId: "", userHash: userHash(BOB) })));
});

test("B-06 icebreaker: every event shape the client sink writes is accepted", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  for (const event of [
    "meeting_icebreaker_prompt_opened",
    "meeting_roulette_shown",
    "meeting_game_result_shown",
    "bomb_timer_exploded",
  ]) {
    await assertSucceeds(addDoc(collection(alice, ICE), iceEvent({}, { event })));
  }
  await assertSucceeds(addDoc(collection(alice, ICE), iceEvent({
    meeting_type: "blindTasteMeeting",
    notification_sequence: 3,
    game_type: "bombPass",
    spin_duration_bucket: "2_4s",
    prompt_stop_reason: "meeting_ended",
    entry_decision: "open_roulette",
    reduce_motion: true,
    alcohol_free_copy: false,
    audio_stage: "explode",
  })));
});

test("B-06: an unauthenticated caller can no longer write analytics", async () => {
  await withClearedDb();
  const nobody = await anon();
  await assertFails(addDoc(collection(nobody, BLIND), blindEvent()));
  await assertFails(addDoc(collection(nobody, ICE), iceEvent()));
});

test("B-06: a pre-exchange email-link session and a Play Review session cannot write production analytics", async () => {
  await withClearedDb();
  const temp = await emailLinkSession("temp_uid", "someone@yonsei.ac.kr");
  await assertFails(addDoc(collection(temp, BLIND), blindEvent()));
  await assertFails(addDoc(collection(temp, ICE), iceEvent()));
  const reviewer = await reviewerSession();
  await assertFails(addDoc(collection(reviewer, BLIND), blindEvent()));
  await assertFails(addDoc(collection(reviewer, ICE), iceEvent()));
});

test("B-06: extra top-level fields, a missing or client-chosen timestamp and a non-map params are refused", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  for (const name of [BLIND, ICE]) {
    const base = name === BLIND ? blindEvent : iceEvent;
    await assertFails(addDoc(collection(alice, name), base({}, { blob: "x".repeat(1000) })));
    await assertFails(addDoc(collection(alice, name), base({}, { uid: ALICE })));
    await assertFails(addDoc(collection(alice, name), base({}, { createdAt: new Date(2020, 0, 1) })));
    await assertFails(addDoc(collection(alice, name), base({}, { createdAt: new Date(Date.now() + 86_400_000) })));
    const { createdAt: _dropped, ...noTimestamp } = base();
    await assertFails(addDoc(collection(alice, name), noTimestamp));
    await assertFails(addDoc(collection(alice, name), base("not-a-map")));
    await assertFails(addDoc(collection(alice, name), base(["a"])));
  }
});

test("B-06: event names are bounded and stay inside their own namespace", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({}, { event: "chat_message_sent" })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({}, { event: "" })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({}, { event: `blind_meeting_${"a".repeat(60)}` })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({}, { event: 7 })));
  await assertFails(addDoc(collection(alice, ICE), iceEvent({}, { event: "blind_meeting_card_viewed" })));
  await assertFails(addDoc(collection(alice, ICE), iceEvent({}, { event: `bomb_timer_${"a".repeat(60)}` })));
});

test("B-06: params are an allow-list — unknown keys, PII keys and the hidden bomb time are refused", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  for (const params of [
    { nickname: "민지" },
    { interests: ["x"] },
    { userId: ALICE },
    { studentEmail: "a@yonsei.ac.kr" },
    { uid: ALICE },
    { note: "free text under a new key" },
    { selectedDates: ["2026-11-22"] },
  ]) {
    await assertFails(addDoc(collection(alice, BLIND), blindEvent(params)));
  }
  for (const params of [
    { userId: ALICE },
    { uid: ALICE },
    { nickname: "민지" },
    { participantIds: [ALICE, BOB] },
    { place: "홍대 카페" },
    { fcmToken: "token" },
    { hiddenSeconds: 7 },
    { bombSeconds: 7 },
    { hiddenDuration: 7 },
    { remainingSeconds: 7 },
  ]) {
    await assertFails(addDoc(collection(alice, ICE), iceEvent(params)));
  }
});

test("B-06: param values are bounded scalars (no oversized strings, maps or lists)", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ stage: "x".repeat(65) })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ meetingId: "x".repeat(129) })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ stage: { nested: "x".repeat(5000) } })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ phase: ["a", "b"] })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ urgent: null })));
  await assertFails(addDoc(collection(alice, ICE), iceEvent({ game_type: "x".repeat(65) })));
  await assertFails(addDoc(collection(alice, ICE), iceEvent({ meeting_type: { nested: true } })));
  await assertFails(addDoc(collection(alice, ICE), iceEvent({ audio_stage: ["a"] })));
});

test("B-06 blind: userHash must be the hash of the caller's own uid", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(addDoc(collection(alice, BLIND), blindEvent({ userHash: userHash(ALICE) })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ userHash: userHash(BOB) })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ userHash: ALICE })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ userHash: userHash(ALICE).toUpperCase() })));
  await assertFails(addDoc(collection(alice, BLIND), blindEvent({ userHash: 12345 })));
});

test("B-06: analytics stay append-only and unreadable for clients", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, BLIND, "e1"), { event: "blind_meeting_card_viewed", params: {}, createdAt: new Date() });
    await setDoc(doc(db, ICE, "e1"), { event: "bomb_timer_opened", params: {}, createdAt: new Date() });
  });
  const alice = await kakaoSession(ALICE);
  for (const name of [BLIND, ICE]) {
    await assertFails(getDoc(doc(alice, name, "e1")));
    await assertFails(getDocs(collection(alice, name)));
    await assertFails(updateDoc(doc(alice, name, "e1"), { event: "bomb_timer_opened" }));
    await assertFails(deleteDoc(doc(alice, name, "e1")));
    // Overwriting an existing id is an update, not a create.
    const payload = name === BLIND
      ? blindEvent({}, { event: "blind_meeting_card_viewed" })
      : iceEvent({}, { event: "bomb_timer_opened" });
    await assertFails(setDoc(doc(alice, name, "e1"), payload));
  }
});
