/**
 * P1-2 — chat authorisation: room metadata is server-owned, client message
 * creation is limited to the exact promise card shapes, and closed rooms
 * accept nothing from clients.
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

import { Timestamp, deleteField, doc, getDoc, setDoc, updateDoc } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const CAROL = "kakao_carol";
const MALLORY = "kakao_mallory";
const ROOM = "dm_alice_bob";
const CLOSED_ROOM = "dm_alice_bob_closed";
const GROUP_ROOM = "season_group_room";
const PROMISE = "promise_alice_bob";

async function seed(db) {
  await seedActiveUser(db, ALICE);
  await seedActiveUser(db, BOB);
  await seedActiveUser(db, CAROL);
  await seedActiveUser(db, MALLORY);
  await setDoc(doc(db, "chat_rooms", ROOM), {
    roomId: ROOM,
    type: "one_to_one",
    status: "active",
    participantIds: [ALICE, BOB],
    participantInfo: {
      [ALICE]: { nickname: "Alice", avatarUrl: "" },
      [BOB]: { nickname: "Bob", avatarUrl: "" },
    },
    matchId: "match_alice_bob",
    dataPartition: "production",
    lastMessage: "hello",
    updatedAt: new Date(),
  });
  await setDoc(doc(db, "chat_rooms", ROOM, "promises", PROMISE), {
    promiseId: PROMISE,
    messageId: "m_promise",
    requestedBy: ALICE,
    requestedTo: BOB,
    status: "requested",
    dateTime: new Date(),
    place: "신촌",
    placeCategory: "cafe",
  });
  await setDoc(doc(db, "chat_rooms", CLOSED_ROOM), {
    roomId: CLOSED_ROOM,
    type: "one_to_one",
    status: "closed",
    participantIds: [ALICE, BOB],
    participantInfo: {
      [ALICE]: { nickname: "Alice", avatarUrl: "" },
      [BOB]: { nickname: "Bob", avatarUrl: "" },
    },
    closedAt: new Date(),
  });
  await setDoc(doc(db, "chat_rooms", GROUP_ROOM), {
    roomId: GROUP_ROOM,
    type: "group",
    roomType: "season_meeting_group",
    status: "active",
    writable: true,
    participantIds: [ALICE, BOB, CAROL],
    participantInfo: {
      [ALICE]: { nickname: "Alice", avatarUrl: "" },
      [BOB]: { nickname: "Bob", avatarUrl: "" },
      [CAROL]: { nickname: "Carol", avatarUrl: "" },
    },
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

function promiseRequestMessage(extra = {}) {
  return {
    senderId: ALICE,
    text: "약속 요청",
    type: "promise_request",
    promiseId: "promise_new",
    dateTime: Timestamp.fromDate(new Date(Date.now() + 86400000)),
    place: "신촌",
    placeCategory: "cafe",
    placeId: "p1",
    placeAddress: "서울 서대문구",
    placeLat: 37.55,
    placeLng: 126.93,
    status: "requested",
    isEdited: false,
    editedAt: null,
    createdAt: new Date(),
    updatedAt: new Date(),
    ...extra,
  };
}

// ---------------------------------------------------------------------------
// Room metadata
// ---------------------------------------------------------------------------

test("a 1:1 participant may update chat metadata and the promise mirror", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      lastMessage: "약속 요청",
      lastMessageAt: new Date(),
      updatedAt: new Date(),
    })
  );
  await assertSucceeds(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      activePromise: { promiseId: PROMISE, status: "confirmed", place: "신촌" },
      updatedAt: new Date(),
    })
  );
  await assertSucceeds(
    updateDoc(doc(alice, "chat_rooms", ROOM), { activePromise: deleteField(), updatedAt: new Date() })
  );
});

test("a 1:1 participant cannot reopen a closed room or change its lifecycle", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(updateDoc(doc(alice, "chat_rooms", CLOSED_ROOM), { status: "active" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", CLOSED_ROOM), { status: "active", updatedAt: new Date() }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { status: "closed" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { writable: false }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { writable: true, lastMessage: "x" }));
});

test("a 1:1 participant cannot change the room type discriminator (block-check bypass)", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { type: "group" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { roomType: "season_meeting_group" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { dataPartition: "play_review" }));
});

test("a 1:1 participant cannot rewrite the peer's displayed identity or the match/meeting links", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      participantInfo: {
        [ALICE]: { nickname: "Alice", avatarUrl: "" },
        [BOB]: { nickname: "Impostor", avatarUrl: "https://evil.example/x.png" },
      },
    })
  );
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { [`participantInfo.${BOB}.nickname`]: "Impostor" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { matchId: "match_someone_else" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { meetingId: "meeting_1" }));
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { unlockedBy: ALICE, heartCost: 0 }));
});

test("a participant cannot flip the real-photo disclosure fields", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      photoBlurUnlocked: true,
      photoBlurUnlockedAt: new Date(),
      photoBlurUnlockedBy: ALICE,
    })
  );
  await assertFails(updateDoc(doc(alice, "chat_rooms", ROOM), { photoBlurUnlocked: true, updatedAt: new Date() }));
});

test("a non-participant cannot touch a room at all", async () => {
  await withClearedDb(seed);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(updateDoc(doc(mallory, "chat_rooms", ROOM), { lastMessage: "hi" }));
  await assertFails(getDoc(doc(mallory, "chat_rooms", ROOM)));
});

// ---------------------------------------------------------------------------
// Message creation
// ---------------------------------------------------------------------------

test("free text cannot be created by a client under any type: text, unknown, system, promise_confirmed", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  const base = { senderId: ALICE, text: "unmoderated words", createdAt: new Date(), updatedAt: new Date() };
  for (const type of ["text", "free", "image", "sticker", "system", "promise_confirmed", "promise_in_progress", "promise_completed", "promise_reminder"]) {
    await assertFails(setDoc(doc(alice, "chat_rooms", ROOM, "messages", `m_${type}`), { ...base, type }), type);
  }
  // No type at all is refused as well (the client UI would render it as text).
  await assertFails(setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_untyped"), base));
});

test("a client cannot impersonate the server or another participant as sender", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_sys"), promiseRequestMessage({ senderId: "system" }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_bob"), promiseRequestMessage({ senderId: BOB }))
  );
});

test("a legitimate promise request card is accepted; extra fields, oversized text, wrong status or types are refused", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_ok"), promiseRequestMessage()));
  await assertSucceeds(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_ok_min"), {
      senderId: ALICE, text: "약속 요청", type: "promise_request", promiseId: "p2",
      dateTime: Timestamp.now(), place: "홍대", placeCategory: "bar", status: "requested",
      isEdited: false, editedAt: null, createdAt: new Date(), updatedAt: new Date(),
    })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_extra"), promiseRequestMessage({ imageUrl: "https://evil.example/a.png" }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_marker"), promiseRequestMessage({ unreadAccountedAt: new Date() }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_long"), promiseRequestMessage({ text: "x".repeat(101) }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_status"), promiseRequestMessage({ status: "confirmed" }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_date"), promiseRequestMessage({ dateTime: "tomorrow" }))
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_edited"), promiseRequestMessage({ isEdited: true }))
  );
});

test("a promise deletion card is accepted only for a promise party with the exact fields", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  const card = {
    senderId: BOB, type: "promise_deleted", text: "약속이 삭제되었어요", promiseId: PROMISE,
    dateTime: Timestamp.now(), place: "신촌", placeCategory: "cafe", status: "cancelled",
    createdAt: new Date(), updatedAt: new Date(),
  };
  await assertSucceeds(setDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_del"), card));
  await assertFails(setDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_del2"), { ...card, text: "x".repeat(101) }));
  await assertFails(setDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_del3"), { ...card, note: "extra" }));
  await assertFails(setDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_del4"), { ...card, promiseId: "promise_missing" }));
});

test("a closed room accepts no client message or promise, while the active room does", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  await assertFails(setDoc(doc(alice, "chat_rooms", CLOSED_ROOM, "messages", "m1"), promiseRequestMessage()));
  await assertFails(
    setDoc(doc(alice, "chat_rooms", CLOSED_ROOM, "promises", "p_closed"), {
      promiseId: "p_closed", messageId: "m1", requestedBy: ALICE, requestedTo: BOB,
      dateTime: Timestamp.now(), place: "신촌", placeCategory: "cafe", status: "requested",
      createdAt: new Date(), updatedAt: new Date(), isEdited: false, editedAt: null, acceptedAt: null,
    })
  );
  await assertSucceeds(
    setDoc(doc(alice, "chat_rooms", ROOM, "promises", "p_open"), {
      promiseId: "p_open", messageId: "m1", requestedBy: ALICE, requestedTo: BOB,
      dateTime: Timestamp.now(), place: "신촌", placeCategory: "cafe", status: "requested",
      createdAt: new Date(), updatedAt: new Date(), isEdited: false, editedAt: null, acceptedAt: null,
    })
  );
});

test("a group room participant is bound by the same message schema and metadata allowlist", async () => {
  await withClearedDb(seed);
  const carol = await kakaoSession(CAROL);
  await assertFails(
    setDoc(doc(carol, "chat_rooms", GROUP_ROOM, "messages", "g1"), { senderId: CAROL, type: "shout", text: "hey", createdAt: new Date() })
  );
  await assertFails(updateDoc(doc(carol, "chat_rooms", GROUP_ROOM), { writable: false }));
  await assertFails(updateDoc(doc(carol, "chat_rooms", GROUP_ROOM), { participantIds: [ALICE, BOB, CAROL, MALLORY] }));
  await assertSucceeds(updateDoc(doc(carol, "chat_rooms", GROUP_ROOM), { lastMessage: "약속 요청", updatedAt: new Date() }));
});

test("P0-2 own read-state write still works beside the new allowlist", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  await assertSucceeds(
    updateDoc(doc(bob, "chat_rooms", ROOM), {
      [`unreadCounts.${BOB}`]: 0,
      [`lastReadAt.${BOB}`]: (await import("firebase/firestore")).serverTimestamp(),
    })
  );
  const alice = await kakaoSession(ALICE);
  const snap = await assertSucceeds(getDoc(doc(alice, "chat_rooms", ROOM)));
  assert.equal(snap.data().unreadCounts[BOB], 0);
});
