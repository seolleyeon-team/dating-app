import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";
import { doc, getDoc, setDoc, updateDoc } from "firebase/firestore";

const OPERATOR = "operations_uid";
const MEMBER = "member_uid";
const ATTACKER = "attacker_uid";
const ROOM = `support_${OPERATOR}_${MEMBER}`;

async function seedSupportRoom(db) {
  await setDoc(doc(db, "admin", OPERATOR), {
    accountType: "operations",
    active: true,
  });
  await setDoc(doc(db, "chat_rooms", ROOM), {
    roomId: ROOM,
    roomType: "support",
    type: "support",
    status: "active",
    supportStatus: "open",
    participantIds: [MEMBER, OPERATOR],
    userId: MEMBER,
    operatorId: OPERATOR,
    lastMessage: "문의가 전달되었습니다.",
    updatedAt: new Date(),
  });
}

test("support room is visible only to its user and operator", async () => {
  await withClearedDb(seedSupportRoom);
  const member = await kakaoSession(MEMBER);
  const attacker = await kakaoSession(ATTACKER);

  await assertSucceeds(getDoc(doc(member, "chat_rooms", ROOM)));
  await assertFails(getDoc(doc(attacker, "chat_rooms", ROOM)));
});

test("a support participant cannot reassign its operator or case fields", async () => {
  await withClearedDb(seedSupportRoom);
  const member = await kakaoSession(MEMBER);

  await assertFails(
    updateDoc(doc(member, "chat_rooms", ROOM), {
      operatorId: ATTACKER,
    }),
  );
  await assertFails(
    updateDoc(doc(member, "chat_rooms", ROOM), {
      latestInquiryId: "forged_case",
    }),
  );
  await assertSucceeds(
    updateDoc(doc(member, "chat_rooms", ROOM), {
      lastMessage: "운영팀에 답장했어요.",
      updatedAt: new Date(),
    }),
  );
});

test("a support participant can reply with bounded text but cannot forge a case card", async () => {
  await withClearedDb(seedSupportRoom);
  const member = await kakaoSession(MEMBER);

  await assertSucceeds(
    setDoc(doc(member, "chat_rooms", ROOM, "messages", "reply"), {
      senderId: MEMBER,
      type: "text",
      text: "답변을 기다릴게요.",
      readBy: [MEMBER],
      createdAt: new Date(),
      updatedAt: new Date(),
    }),
  );
  await assertFails(
    setDoc(doc(member, "chat_rooms", ROOM, "messages", "forged-card"), {
      senderId: MEMBER,
      type: "support_inquiry",
      text: "위조된 문의",
      readBy: [MEMBER],
      supportCase: { content: "forged" },
    }),
  );
});

test("admin metadata is not readable or writable from a client", async () => {
  await withClearedDb(seedSupportRoom);
  const member = await kakaoSession(MEMBER);

  await assertFails(getDoc(doc(member, "admin", OPERATOR)));
  await assertFails(
    setDoc(doc(member, "admin", MEMBER), {
      accountType: "operations",
      active: true,
    }),
  );
});

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});
