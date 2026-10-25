// P0-2 (2026-10 production audit): room-level unread state rules.
//
// chat_rooms/{roomId}.unreadCounts.{uid} is server-incremented; a participant
// may only reset its OWN key to 0 and stamp its OWN lastReadAt. Nobody can
// touch another participant's keys, forge a positive count, or reach these
// keys through the general room-update branch. Old clients keep writing
// per-message readBy (retired: refused by the rules since 2026-10-25).
import test from "node:test";

import {
  anon,
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
  serverTimestamp,
  setDoc,
  updateDoc,
  Timestamp,
} from "firebase/firestore";

const A = "kakao_chat_a";
const B = "kakao_chat_b";
const C = "kakao_chat_c";
const OUTSIDER = "kakao_outsider";
const ROOM = "dm_kakao_chat_a_kakao_chat_b";

async function seedRoom(extra = {}, { legacy = false } = {}) {
  return withClearedDb(async (db) => {
    for (const uid of [A, B, C, OUTSIDER]) await seedActiveUser(db, uid);
    const modelFields = legacy
      ? {}
      : {
          unreadModelVersion: 1,
          unreadCounts: { [A]: 3, [B]: 0 },
          lastReadAt: { [B]: Timestamp.fromMillis(Date.now() - 60_000) },
        };
    await setDoc(doc(db, "chat_rooms", ROOM), {
      roomId: ROOM,
      type: "one_to_one",
      status: "active",
      participantIds: [A, B],
      participantInfo: { [A]: { nickname: "에이" }, [B]: { nickname: "비" } },
      lastMessage: "hi",
      lastMessageAt: Timestamp.now(),
      updatedAt: Timestamp.now(),
      ...modelFields,
      ...extra,
    });
    await setDoc(doc(db, "chat_rooms", ROOM, "messages", "m1"), {
      senderId: B,
      text: "hi",
      type: "text",
      createdAt: Timestamp.now(),
    });
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("legit: a participant resets its own unread counter and stamps its own lastReadAt", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  await assertSucceeds(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      [`unreadCounts.${A}`]: 0,
      [`lastReadAt.${A}`]: serverTimestamp(),
    })
  );
});

test("legit: the reset works on a legacy room that has no unread fields yet", async () => {
  await seedRoom({}, { legacy: true });
  const db = await kakaoSession(A);
  await assertSucceeds(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      [`unreadCounts.${A}`]: 0,
      [`lastReadAt.${A}`]: serverTimestamp(),
    })
  );
});

test("P0-2: A cannot reset B's unread counter", async () => {
  await seedRoom({ unreadCounts: { [A]: 0, [B]: 5 } });
  const db = await kakaoSession(A);
  await assertFails(updateDoc(doc(db, "chat_rooms", ROOM), { [`unreadCounts.${B}`]: 0 }));
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      [`unreadCounts.${A}`]: 0,
      [`unreadCounts.${B}`]: 0,
      [`lastReadAt.${A}`]: serverTimestamp(),
    })
  );
});

test("P0-2: A cannot forge B's lastReadAt", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  await assertFails(updateDoc(doc(db, "chat_rooms", ROOM), { [`lastReadAt.${B}`]: serverTimestamp() }));
});

test("P0-2: a participant cannot set its own counter to anything but 0", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  for (const value of [1, 99, -1, "0", null]) {
    await assertFails(
      updateDoc(doc(db, "chat_rooms", ROOM), {
        [`unreadCounts.${A}`]: value,
        [`lastReadAt.${A}`]: serverTimestamp(),
      })
    );
  }
});

test("P0-2: lastReadAt must be the server time, not a client-chosen instant", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      [`unreadCounts.${A}`]: 0,
      [`lastReadAt.${A}`]: Timestamp.fromMillis(Date.now() + 3_600_000),
    })
  );
});

test("P0-2: the unread model fields cannot ride along with an ordinary room update", async () => {
  await seedRoom({ unreadCounts: { [A]: 0, [B]: 5 } });
  const db = await kakaoSession(A);
  // The general branch (lastMessage/updatedAt) must not let these keys through.
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      lastMessage: "x",
      updatedAt: serverTimestamp(),
      [`unreadCounts.${B}`]: 0,
    })
  );
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      lastMessage: "x",
      updatedAt: serverTimestamp(),
      unreadModelVersion: 7,
    })
  );
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      lastMessage: "x",
      updatedAt: serverTimestamp(),
      unreadCounts: deleteField(),
    })
  );
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM), { unreadBackfilledAt: serverTimestamp() })
  );
});

test("P0-2: a non-participant and an unauthenticated client cannot touch read state", async () => {
  await seedRoom();
  const outsider = await kakaoSession(OUTSIDER);
  await assertFails(
    updateDoc(doc(outsider, "chat_rooms", ROOM), {
      [`unreadCounts.${OUTSIDER}`]: 0,
      [`lastReadAt.${OUTSIDER}`]: serverTimestamp(),
    })
  );
  await assertFails(
    updateDoc(doc(outsider, "chat_rooms", ROOM), { [`unreadCounts.${A}`]: 0 })
  );
  const nobody = await anon();
  await assertFails(updateDoc(doc(nobody, "chat_rooms", ROOM), { [`unreadCounts.${A}`]: 0 }));
});

test("P0-2: a participant of a blocked 1:1 room can still clear its own badge", async () => {
  // Blocking stops messaging, not the victim's ability to dismiss what they
  // already received; the existing update branch denies blocked rooms, so the
  // read-state branch must stand on its own.
  await seedRoom();
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled(async (ctx) => {
    await setDoc(doc(ctx.firestore(), "blocks", A, "targets", B), { createdAt: Timestamp.now() });
  });
  const db = await kakaoSession(A);
  await assertSucceeds(
    updateDoc(doc(db, "chat_rooms", ROOM), {
      [`unreadCounts.${A}`]: 0,
      [`lastReadAt.${A}`]: serverTimestamp(),
    })
  );
});

test("P0-2 retirement: per-message readBy receipts are refused; read state lives on the room", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM, "messages", "m1"), {
      readBy: [B, A],
      updatedAt: serverTimestamp(),
    })
  );
});

test("P0-2: clients cannot stamp the server-only accounting marker on a message", async () => {
  await seedRoom();
  const db = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM, "messages", "m1"), {
      unreadAccountedAt: serverTimestamp(),
    })
  );
  await assertFails(
    updateDoc(doc(db, "chat_rooms", ROOM, "messages", "m1"), {
      readBy: [B, A],
      updatedAt: serverTimestamp(),
      unreadAccountedAt: serverTimestamp(),
    })
  );
});
