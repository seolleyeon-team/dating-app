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
  collection,
  doc,
  getDoc,
  getDocs,
  orderBy,
  query,
  setDoc,
  updateDoc,
  where,
} from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const MALLORY = "kakao_mallory";
const ROOM = "dm_alice_bob";
const PROMISE = "promise_alice_bob";

async function seedChatRoom(db) {
  await seedActiveUser(db, ALICE);
  await seedActiveUser(db, BOB);
  await setDoc(doc(db, "chat_rooms", ROOM), {
    roomId: ROOM,
    participantIds: [ALICE, BOB],
    lastMessage: "hello",
    participantInfo: {
      [ALICE]: { nickname: "Alice", avatarUrl: "" },
      [BOB]: { nickname: "Bob", avatarUrl: "" },
    },
    updatedAt: new Date(),
  });
  await setDoc(doc(db, "chat_rooms", ROOM, "messages", "m_text"), {
    senderId: ALICE,
    type: "text",
    text: "original evidence",
  });
  await setDoc(doc(db, "chat_rooms", ROOM, "messages", "m_promise"), {
    senderId: ALICE,
    type: "promise_request",
    text: "약속 요청",
    status: "requested",
    place: "신촌",
    placeCategory: "cafe",
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
}

test("a participant can list rooms with an array-contains participant query", async () => {
  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);

  const snap = await assertSucceeds(
    getDocs(
      query(
        collection(alice, "chat_rooms"),
        where("participantIds", "array-contains", ALICE),
        orderBy("updatedAt", "desc")
      )
    )
  );

  assert.equal(snap.size, 1);
  assert.equal(snap.docs[0].id, ROOM);
});

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// SEC-P1-02 — message text must not be rewritten by the other participant
// ---------------------------------------------------------------------------

test("a participant cannot rewrite another user's chat text", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  // This is the evidence-tampering path the audit found: update was open to
  // any participant, so Bob could erase Alice's words after a report.
  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      text: "I never said that",
    })
  );
});

test("a participant cannot reassign senderId on a text message", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      senderId: BOB,
    })
  );
});

test("P0-2 retirement: per-message receipts are tolerated only as an old build's own-uid append (NEW-18), nothing else", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  // Anything but "append exactly my uid" is refused: replacing the list,
  // naming another user, or touching another field alongside.
  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      readBy: [ALICE, BOB],
      updatedAt: new Date(),
    })
  );
  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      readBy: [ALICE],
      updatedAt: new Date(),
    })
  );
  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      readBy: [BOB],
      text: "rewritten",
    })
  );
  // Transitional: the old build's own receipt append (seed has no readBy → [BOB]).
  await assertSucceeds(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      readBy: [BOB],
      updatedAt: new Date(),
    })
  );

  const alice = await kakaoSession(ALICE);
  const snap = await assertSucceeds(
    getDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_text"))
  );
  assert.equal(snap.data().text, "original evidence");
});

test("P0-2 retirement: a promise message is accepted without readBy; with readBy only as the old build's own uid (NEW-18)", async () => {
  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);
  const base = {
    senderId: ALICE,
    type: "promise_request",
    text: "약속 요청",
    promiseId: "promise_new",
    status: "requested",
    place: "신촌",
    placeCategory: "cafe",
    isEdited: false,
    editedAt: null,
    createdAt: new Date(),
    updatedAt: new Date(),
  };
  await assertSucceeds(setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_promise_new"), base));
  // Transitional tolerance (NEW-18): exactly [own uid], as the old build writes it.
  await assertSucceeds(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_promise_old_build"), { ...base, readBy: [ALICE] })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_promise_forged_1"), { ...base, readBy: [BOB] })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_promise_forged_2"), { ...base, readBy: [ALICE, BOB] })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", ROOM, "messages", "m_promise_forged_3"), { ...base, readBy: [] })
  );
});

test("an existing promise message can move through its lifecycle", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  await assertSucceeds(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_promise"), {
      type: "promise_confirmed",
      text: "약속이 확정되었어요",
      status: "confirmed",
      updatedAt: new Date(),
    })
  );
});

test("both promise parties can cancel and record the cancellation", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  await assertSucceeds(
    updateDoc(doc(bob, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      updatedAt: new Date(),
    })
  );
  await assertSucceeds(
    setDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_deleted_by_bob"), {
      senderId: BOB,
      type: "promise_deleted",
      text: "약속이 삭제되었어요",
      promiseId: PROMISE,
      status: "cancelled",
    })
  );

  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(
    updateDoc(doc(alice, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      updatedAt: new Date(),
    })
  );
});

test("a room participant who is not a promise party cannot cancel it", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "chat_rooms", ROOM), {
      roomId: ROOM,
      participantIds: [ALICE, BOB, MALLORY],
      updatedAt: new Date(),
    });
    await setDoc(doc(db, "chat_rooms", ROOM, "promises", PROMISE), {
      promiseId: PROMISE,
      requestedBy: ALICE,
      requestedTo: BOB,
      status: "confirmed",
    });
  });
  const mallory = await kakaoSession(MALLORY);

  await assertFails(
    updateDoc(doc(mallory, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      updatedAt: new Date(),
    })
  );
});

test("a plain text message cannot be converted into a promise to bypass the gate", async () => {
  await withClearedDb(seedChatRoom);
  const bob = await kakaoSession(BOB);

  await assertFails(
    updateDoc(doc(bob, "chat_rooms", ROOM, "messages", "m_text"), {
      type: "promise_request",
      text: "rewritten via fake promise",
      status: "requested",
    })
  );
});

// ---------------------------------------------------------------------------
// SEC-P1-03 — participantIds immutable
// ---------------------------------------------------------------------------

test("a participant cannot add a third party to the room", async () => {
  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);

  // Adding Mallory would give her read access to the full message history.
  await assertFails(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      participantIds: [ALICE, BOB, MALLORY],
    })
  );
});

test("a participant cannot remove the other participant", async () => {
  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);

  await assertFails(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      participantIds: [ALICE],
    })
  );
});

test("a participant can still update lastMessage without touching participantIds", async () => {
  await withClearedDb(seedChatRoom);
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    updateDoc(doc(alice, "chat_rooms", ROOM), {
      lastMessage: "new last message",
      updatedAt: new Date(),
    })
  );
});
