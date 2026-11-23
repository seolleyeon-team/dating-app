/**
 * B-12 — promise decisions must not trust the device clock.
 *
 *  - The meeting time is validated against the SERVER time of the write
 *    (the form only compares it with the device clock).
 *  - The "arrival stamp deadline passed" cancellation is validated against
 *    the server time (the client decides it with DateTime.now()).
 *  - A confirmed promise's time / place cannot be moved by one party while it
 *    stays confirmed; it must be re-requested and accepted again.
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

import {
  deleteField,
  doc,
  getDoc,
  serverTimestamp,
  setDoc,
  Timestamp,
  updateDoc,
  writeBatch,
} from "firebase/firestore";

const A = "kakao_a";
const B = "kakao_b";
const C = "kakao_c";
const ROOM = "room_promise_time";
const PROMISE = "promise_1";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const at = (offsetMs) => new Date(Date.now() + offsetMs);

/** 23:59:30 KST and 00:00:30 KST of a day `days` ahead (KST = UTC+9, no DST). */
function kstMidnightPair(days) {
  const kstNow = new Date(Date.now() + 9 * HOUR);
  const nextKstMidnightUtcMs =
    Date.UTC(kstNow.getUTCFullYear(), kstNow.getUTCMonth(), kstNow.getUTCDate() + days) - 9 * HOUR;
  return [new Date(nextKstMidnightUtcMs - 30_000), new Date(nextKstMidnightUtcMs + 30_000)];
}

function promiseDoc(overrides = {}) {
  return {
    promiseId: PROMISE,
    messageId: "msg_1",
    requestedBy: A,
    requestedTo: B,
    dateTime: at(2 * DAY),
    place: "신촌",
    placeCategory: "cafe",
    status: "requested",
    createdAt: at(-DAY),
    updatedAt: at(-DAY),
    isEdited: false,
    editedAt: null,
    acceptedAt: null,
    ...overrides,
  };
}

/** chat_service.dart createPromise (promise document). */
function clientCreate(id, dateTime, overrides = {}) {
  return {
    promiseId: id,
    messageId: `msg_${id}`,
    requestedBy: A,
    requestedTo: B,
    dateTime,
    place: "신촌",
    placeCategory: "cafe",
    status: "requested",
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
    isEdited: false,
    editedAt: null,
    acceptedAt: null,
    ...overrides,
  };
}

async function seed(db, promiseOverrides = {}) {
  await Promise.all([A, B, C].map((uid) => seedActiveUser(db, uid)));
  await setDoc(doc(db, "chat_rooms", ROOM), { roomId: ROOM, participantIds: [A, B, C], lastMessage: "hi" });
  await setDoc(doc(db, "chat_rooms", ROOM, "promises", PROMISE), promiseDoc(promiseOverrides));
}

const promiseRef = (db, id = PROMISE) => doc(db, "chat_rooms", ROOM, "promises", id);

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// Meeting time vs server time
// ---------------------------------------------------------------------------

test("B-12 create: a meeting time in the server's future is accepted", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  await assertSucceeds(setDoc(promiseRef(a, "p_future"), clientCreate("p_future", at(11 * MINUTE))));
  await assertSucceeds(setDoc(promiseRef(a, "p_far"), clientCreate("p_far", at(30 * DAY))));
});

test("B-12 create: device clock in the past — a meeting time that is already over on the server is refused", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  // A phone that is 3 hours slow accepts "in 10 minutes" (device time).
  await assertFails(setDoc(promiseRef(a, "p_past"), clientCreate("p_past", at(-3 * HOUR + 10 * MINUTE))));
  await assertFails(setDoc(promiseRef(a, "p_just_past"), clientCreate("p_just_past", at(-MINUTE))));
  await assertFails(setDoc(promiseRef(a, "p_epoch"), clientCreate("p_epoch", new Date(0))));
});

test("B-12 create: the meeting time must be a timestamp (no numbers, strings or maps)", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  await assertFails(setDoc(promiseRef(a, "p_num"), clientCreate("p_num", Date.now() + DAY)));
  await assertFails(setDoc(promiseRef(a, "p_str"), clientCreate("p_str", at(DAY).toISOString())));
  await assertFails(setDoc(promiseRef(a, "p_map"), clientCreate("p_map", { seconds: 9_999_999_999 })));
  await assertFails(setDoc(promiseRef(a, "p_null"), clientCreate("p_null", null)));
});

test("B-12 create: timezone change — the same instant is accepted whatever zone the device formats it in", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  const instant = Date.now() + 5 * HOUR;
  // A Timestamp is an absolute instant: a device in KST (+09:00) and one in
  // Los Angeles (-08:00) that mean the same moment send the same value.
  const fromKst = Timestamp.fromDate(new Date(new Date(instant + 9 * HOUR).toISOString().replace("Z", "+09:00")));
  const fromLa = Timestamp.fromDate(new Date(new Date(instant - 8 * HOUR).toISOString().replace("Z", "-08:00")));
  assert.equal(fromKst.toMillis(), fromLa.toMillis());
  await assertSucceeds(setDoc(promiseRef(a, "p_kst"), clientCreate("p_kst", fromKst)));
  await assertSucceeds(setDoc(promiseRef(a, "p_la"), clientCreate("p_la", fromLa)));
  // A wall-clock time that is only "future" in the wrong zone is refused:
  // 1 hour ago, mislabelled as if it were 9 hours later.
  await assertFails(setDoc(promiseRef(a, "p_wrong_zone"), clientCreate("p_wrong_zone", Timestamp.fromMillis(Date.now() - HOUR))));
});

test("B-12 create: KST midnight boundary — both sides of 00:00 KST are ordinary future instants", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  const [before, after] = kstMidnightPair(2);
  await assertSucceeds(setDoc(promiseRef(a, "p_2359"), clientCreate("p_2359", before)));
  await assertSucceeds(setDoc(promiseRef(a, "p_0000"), clientCreate("p_0000", after)));
});

test("B-12 edit: changing the time to the server's past is refused, to the future is accepted", async () => {
  await withClearedDb(seed);
  const a = await kakaoSession(A);
  // chat_service.dart updatePromise by the proposer (status stays requested).
  const edit = (dateTime) => ({
    requestedBy: A,
    requestedTo: B,
    dateTime,
    place: "홍대",
    placeCategory: "cafe",
    status: "requested",
    acceptedAt: null,
    updatedAt: serverTimestamp(),
    isEdited: true,
    editedAt: serverTimestamp(),
  });
  await assertFails(updateDoc(promiseRef(a), edit(at(-HOUR))));
  await assertFails(updateDoc(promiseRef(a), edit(Date.now() + DAY)));
  await assertSucceeds(updateDoc(promiseRef(a), edit(at(3 * DAY))));
});

test("B-12 edit: a place-only edit of a promise whose time already passed is still accepted", async () => {
  const past = at(-20 * MINUTE);
  await withClearedDb((db) => seed(db, { dateTime: past }));
  const a = await kakaoSession(A);
  await assertSucceeds(updateDoc(promiseRef(a), {
    requestedBy: A,
    requestedTo: B,
    dateTime: Timestamp.fromDate(past),
    place: "홍대",
    placeCategory: "cafe",
    status: "requested",
    acceptedAt: null,
    updatedAt: serverTimestamp(),
    isEdited: true,
    editedAt: serverTimestamp(),
  }));
});

test("B-12 edit: the recipient's re-request (swap) to a future time is accepted, to a past time refused", async () => {
  await withClearedDb(seed);
  const b = await kakaoSession(B);
  const swap = (dateTime) => ({
    requestedBy: B,
    requestedTo: A,
    dateTime,
    place: "홍대",
    placeCategory: "cafe",
    status: "requested",
    acceptedAt: null,
    updatedAt: serverTimestamp(),
    isEdited: true,
    editedAt: serverTimestamp(),
  });
  await assertFails(updateDoc(promiseRef(b), swap(at(-5 * MINUTE))));
  await assertSucceeds(updateDoc(promiseRef(b), swap(at(4 * DAY))));
});

// ---------------------------------------------------------------------------
// A confirmed schedule cannot be moved by one party
// ---------------------------------------------------------------------------

test("B-12 confirmed: one party cannot move the time or the place while the promise stays confirmed", async () => {
  await withClearedDb((db) => seed(db, { status: "confirmed", acceptedAt: at(-HOUR) }));
  const a = await kakaoSession(A);
  const b = await kakaoSession(B);
  // To their advantage: push it a month out, or pull it to "right now".
  await assertFails(updateDoc(promiseRef(a), { dateTime: at(30 * DAY), updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(promiseRef(b), { dateTime: at(MINUTE), updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(promiseRef(a), { dateTime: at(-HOUR), updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(promiseRef(a), { place: "강남", updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(promiseRef(a), { placeLat: 37.5, placeLng: 127.0, updatedAt: serverTimestamp() }));
  await assertFails(updateDoc(promiseRef(a), { dateTime: deleteField(), updatedAt: serverTimestamp() }));
  const snap = await assertSucceeds(getDoc(promiseRef(a)));
  assert.equal(snap.data().status, "confirmed");
  assert.equal(snap.data().place, "신촌");
});

test("B-12 confirmed: the real edit flow (re-request, which the other side must accept again) still works", async () => {
  await withClearedDb((db) => seed(db, { status: "confirmed", acceptedAt: at(-HOUR) }));
  const a = await kakaoSession(A);
  const b = await kakaoSession(B);
  await assertSucceeds(updateDoc(promiseRef(a), {
    requestedBy: A,
    requestedTo: B,
    dateTime: at(5 * DAY),
    place: "홍대",
    placeCategory: "cafe",
    status: "requested",
    acceptedAt: null,
    updatedAt: serverTimestamp(),
    isEdited: true,
    editedAt: serverTimestamp(),
  }));
  // chat_service.dart acceptPromise
  await assertSucceeds(updateDoc(promiseRef(b), {
    status: "confirmed",
    acceptedAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  }));
});

test("B-12 accept: accepting does not need (and cannot smuggle) a time change", async () => {
  await withClearedDb(seed);
  const b = await kakaoSession(B);
  await assertFails(updateDoc(promiseRef(b), {
    status: "confirmed",
    dateTime: at(-HOUR),
    acceptedAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  }));
  // Not even to a future time or another place: the proposer never agreed.
  await assertFails(updateDoc(promiseRef(b), {
    status: "confirmed",
    dateTime: at(9 * DAY),
    acceptedAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  }));
  await assertFails(updateDoc(promiseRef(b), {
    status: "confirmed",
    place: "강남",
    acceptedAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  }));
  await assertSucceeds(updateDoc(promiseRef(b), {
    status: "confirmed",
    acceptedAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  }));
});

// ---------------------------------------------------------------------------
// Cancellation
// ---------------------------------------------------------------------------

/** chat_service.dart cancelExpiredIncompleteSafetyStamp (promise write). */
const timeoutCancel = () => ({
  status: "cancelled",
  cancelledAt: serverTimestamp(),
  cancelledReason: "safety_stamp_timeout",
  updatedAt: serverTimestamp(),
});

test("B-12 timeout cancel: device clock in the future — the deadline is checked against server time", async () => {
  // Meeting is tomorrow; a phone whose clock is two days ahead believes the
  // arrival-stamp deadline passed and tries to auto-cancel.
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(DAY), acceptedAt: at(-HOUR) }));
  const a = await kakaoSession(A);
  const b = await kakaoSession(B);
  await assertFails(updateDoc(promiseRef(a), timeoutCancel()));
  await assertFails(updateDoc(promiseRef(b), timeoutCancel()));
  // Same refusal inside the stamp window (meeting started 30 minutes ago).
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(-30 * MINUTE), acceptedAt: at(-DAY) }));
  await assertFails(updateDoc(promiseRef(await kakaoSession(A)), timeoutCancel()));
  // And just before the deadline (59 minutes after the meeting time).
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(-59 * MINUTE), acceptedAt: at(-DAY) }));
  await assertFails(updateDoc(promiseRef(await kakaoSession(A)), timeoutCancel()));
});

test("B-12 timeout cancel: safety stamp expiry — after promise time + 1 hour either party may cancel, a bystander may not", async () => {
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(-61 * MINUTE), acceptedAt: at(-DAY) }));
  const c = await kakaoSession(C);
  await assertFails(updateDoc(promiseRef(c), timeoutCancel()));
  const b = await kakaoSession(B);
  await assertSucceeds(updateDoc(promiseRef(b), timeoutCancel()));
  const snap = await assertSucceeds(getDoc(promiseRef(b)));
  assert.equal(snap.data().cancelledReason, "safety_stamp_timeout");
});

test("B-12 timeout cancel: the timeout label cannot be used on a pending promise or with a non-timestamp time", async () => {
  await withClearedDb((db) => seed(db, { status: "requested", dateTime: at(-2 * HOUR) }));
  await assertFails(updateDoc(promiseRef(await kakaoSession(A)), timeoutCancel()));
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: Date.now() - 2 * HOUR, acceptedAt: at(-DAY) }));
  await assertFails(updateDoc(promiseRef(await kakaoSession(A)), timeoutCancel()));
});

test("B-12 cancel: an ordinary cancellation by either party works at any time, whatever the device clock says", async () => {
  // chat_service.dart cancelPromise writes no reason.
  const cancel = () => ({ status: "cancelled", updatedAt: serverTimestamp() });
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(DAY), acceptedAt: at(-HOUR) }));
  await assertSucceeds(updateDoc(promiseRef(await kakaoSession(A)), cancel()));
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(-30 * MINUTE), acceptedAt: at(-DAY) }));
  await assertSucceeds(updateDoc(promiseRef(await kakaoSession(B)), cancel()));
  await withClearedDb(seed);
  await assertSucceeds(updateDoc(promiseRef(await kakaoSession(A)), cancel()));
  // A bystander still cannot.
  await withClearedDb((db) => seed(db, { status: "confirmed", dateTime: at(DAY), acceptedAt: at(-HOUR) }));
  await assertFails(updateDoc(promiseRef(await kakaoSession(C)), cancel()));
});

test("B-12 cancel: the client's timeout transaction (promise + room mirror) is atomic — refused early, accepted late", async () => {
  const run = async (db) => {
    const batch = writeBatch(db);
    batch.update(promiseRef(db), timeoutCancel());
    batch.set(doc(db, "chat_rooms", ROOM), {
      activePromise: deleteField(),
      lastMessage: "약속이 취소되었어요",
      lastMessageAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    }, { merge: true });
    return batch.commit();
  };
  const active = { promiseId: PROMISE, status: "confirmed", place: "신촌" };
  await withClearedDb(async (db) => {
    await seed(db, { status: "confirmed", dateTime: at(DAY), acceptedAt: at(-HOUR) });
    await setDoc(doc(db, "chat_rooms", ROOM), { activePromise: active }, { merge: true });
  });
  const early = await kakaoSession(A);
  await assertFails(run(early));
  const room = await assertSucceeds(getDoc(doc(early, "chat_rooms", ROOM)));
  assert.equal(room.data().activePromise.promiseId, PROMISE);

  await withClearedDb(async (db) => {
    await seed(db, { status: "confirmed", dateTime: at(-2 * HOUR), acceptedAt: at(-DAY) });
    await setDoc(doc(db, "chat_rooms", ROOM), { activePromise: active }, { merge: true });
  });
  await assertSucceeds(run(await kakaoSession(A)));
});
