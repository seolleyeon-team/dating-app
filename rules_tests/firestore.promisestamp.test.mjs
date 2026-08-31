import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  deleteDoc,
  deleteField,
  doc,
  getDoc,
  setDoc,
  updateDoc,
} from "firebase/firestore";

// 3:3 시즌 미팅 방 = 6인. 안전도장 위조는 6명 uid 를 한 번에 박는 공격이다.
const A = "kakao_a";
const B = "kakao_b";
const C = "kakao_c";
const D = "kakao_d";
const E = "kakao_e";
const F = "kakao_f";
const ALL_SIX = [A, B, C, D, E, F];
const MALLORY = "kakao_mallory";

const ROOM = "room_season_33";
const BLIND_ROOM = "room_blind_locked";
const PROMISE = "promise_1";

function promiseSeed(overrides = {}) {
  return {
    promiseId: PROMISE,
    messageId: "msg_1",
    requestedBy: A,
    requestedTo: B,
    dateTime: new Date("2026-09-10T12:00:00Z"),
    place: "신촌",
    placeCategory: "cafe",
    status: "requested",
    createdAt: new Date("2026-09-01T00:00:00Z"),
    updatedAt: new Date("2026-09-01T00:00:00Z"),
    isEdited: false,
    editedAt: null,
    acceptedAt: null,
    ...overrides,
  };
}

async function seedRooms(db) {
  await setDoc(doc(db, "chat_rooms", ROOM), {
    roomId: ROOM,
    participantIds: ALL_SIX,
    lastMessage: "hello",
  });
  await setDoc(doc(db, "chat_rooms", ROOM, "promises", PROMISE), promiseSeed());

  await setDoc(doc(db, "chat_rooms", BLIND_ROOM), {
    roomId: BLIND_ROOM,
    roomType: "blind_meeting_group",
    participantIds: [A, B],
    writable: false,
  });
  await setDoc(
    doc(db, "chat_rooms", BLIND_ROOM, "promises", PROMISE),
    promiseSeed({ requestedBy: A, requestedTo: B })
  );
}

/** 확정(confirmed) 상태 + 기존 도장 목록을 가진 약속으로 갈아끼운다. */
async function seedConfirmedPromise(stamp = {}) {
  await withClearedDb(async (db) => {
    await seedRooms(db);
    await setDoc(
      doc(db, "chat_rooms", ROOM, "promises", PROMISE),
      promiseSeed({
        status: "confirmed",
        acceptedAt: new Date("2026-09-02T00:00:00Z"),
        participantIds: ALL_SIX,
        safetyStamp: {
          meetupStampedUserIds: [],
          goodbyeStampedUserIds: [],
          ...stamp,
        },
      })
    );
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// 참가자 게이트 (기존 동작 — 회귀 방지)
// ---------------------------------------------------------------------------

test("a non-participant cannot read a promise", async () => {
  await withClearedDb(seedRooms);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(getDoc(doc(mallory, "chat_rooms", ROOM, "promises", PROMISE)));
});

test("a non-participant cannot create a promise", async () => {
  await withClearedDb(seedRooms);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(
    setDoc(
      doc(mallory, "chat_rooms", ROOM, "promises", "promise_evil"),
      promiseSeed({
        promiseId: "promise_evil",
        requestedBy: MALLORY,
        requestedTo: A,
      })
    )
  );
});

test("a non-participant cannot update a promise", async () => {
  await withClearedDb(seedRooms);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(
    updateDoc(doc(mallory, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
    })
  );
});

test("nobody can delete a promise", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(deleteDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE)));
});

// ---------------------------------------------------------------------------
// create — 정직한 경로는 통과해야 한다 / requestedBy 위조는 막는다
// ---------------------------------------------------------------------------

test("a participant CAN create a normal promise for themselves", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertSucceeds(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_2"),
      promiseSeed({ promiseId: "promise_2", requestedBy: C, requestedTo: D })
    )
  );
});

test("a participant CAN create a promise carrying the optional place fields", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertSucceeds(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_3"),
      promiseSeed({
        promiseId: "promise_3",
        requestedBy: C,
        requestedTo: D,
        placeId: "kakao_place_1",
        placeAddress: "서울시 서대문구",
        placeLat: 37.55,
        placeLng: 126.93,
      })
    )
  );
});

test("a participant cannot create a promise attributed to another uid", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_4"),
      promiseSeed({ promiseId: "promise_4", requestedBy: D, requestedTo: E })
    )
  );
});

test("a promise cannot be created already confirmed", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_5"),
      promiseSeed({
        promiseId: "promise_5",
        requestedBy: C,
        requestedTo: D,
        status: "confirmed",
      })
    )
  );
});

test("a promise cannot be created with a pre-filled safetyStamp", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_6"),
      promiseSeed({
        promiseId: "promise_6",
        requestedBy: C,
        requestedTo: D,
        safetyStamp: { meetupStampedUserIds: ALL_SIX },
      })
    )
  );
});

test("a promise cannot be created against a uid outside the room", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_7"),
      promiseSeed({
        promiseId: "promise_7",
        requestedBy: C,
        requestedTo: MALLORY,
      })
    )
  );
});

// ---------------------------------------------------------------------------
// accept — 자기 요청 자기 수락 금지
// ---------------------------------------------------------------------------

test("the requester CANNOT accept their own request", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "confirmed",
      acceptedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a bystander participant CANNOT accept someone else's request", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    updateDoc(doc(c, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "confirmed",
      acceptedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("the requestedTo user CAN accept the request", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "confirmed",
      acceptedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("the requester cannot self-accept by swapping requestedTo to themselves", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      requestedBy: B,
      requestedTo: A,
      status: "confirmed",
      acceptedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

// ---------------------------------------------------------------------------
// 불변 필드
// ---------------------------------------------------------------------------

test("createdAt cannot be mutated on update", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      createdAt: new Date("2020-01-01T00:00:00Z"),
      updatedAt: new Date(),
    })
  );
});

test("promiseId cannot be mutated on update", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      promiseId: "promise_forged",
      updatedAt: new Date(),
    })
  );
});

test("messageId cannot be mutated on update", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      messageId: "msg_forged",
      updatedAt: new Date(),
    })
  );
});

test("requestedBy cannot be reassigned to a third party", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      requestedBy: C,
      updatedAt: new Date(),
    })
  );
});

test("requestedTo cannot be reassigned to a third party", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      requestedTo: C,
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot claim authorship without the honest editor swap", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  // requestedTo 를 그대로 둔 채 requestedBy 만 자기 것으로 바꾸는 위조.
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      requestedBy: B,
      updatedAt: new Date(),
    })
  );
});

test("the recipient CAN edit the promise, which swaps requestedBy/requestedTo", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  // chat_service.dart:updatePromise 의 정직한 경로.
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      requestedBy: B,
      requestedTo: A,
      dateTime: new Date("2026-09-11T12:00:00Z"),
      place: "홍대",
      placeCategory: "restaurant",
      status: "requested",
      acceptedAt: null,
      isEdited: true,
      editedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

// ---------------------------------------------------------------------------
// 안전도장 — APPEND SELF ONLY  (헤드라인 P0)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 안전도장 — 클라이언트 직접 write 전면 차단
//
// 도장은 submitSafetyStamp callable(서버)만 쓴다. safetyStamp /
// participantIds / meetupCompletedAt / completedAt 은 promiseClientMutableKeys()
// 에서 빠졌으므로, 아래 write 는 "내 uid 하나만 추가" 하는 정직한 형태여도
// 전부 거부된다. 예전에는 이 자리에 append-self-only 를 허용하는 테스트가
// 있었지만, 그 계약 자체가 서버 권위로 대체됐다.
// ---------------------------------------------------------------------------

test("a participant CANNOT append even their own uid to meetupStampedUserIds", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: { meetupStampedUserIds: [A], goodbyeStampedUserIds: [] },
      updatedAt: new Date(),
    })
  );
});

test("a participant CANNOT append even their own uid to goodbyeStampedUserIds", async () => {
  await seedConfirmedPromise({ meetupStampedUserIds: ALL_SIX });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: {
        meetupStampedUserIds: ALL_SIX,
        goodbyeStampedUserIds: [A],
      },
      updatedAt: new Date(),
    })
  );
});

test("a participant CANNOT write all six uids into meetupStampedUserIds at once", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: { meetupStampedUserIds: ALL_SIX, goodbyeStampedUserIds: [] },
      updatedAt: new Date(),
    })
  );
});

test("a participant CANNOT delete another user's meetup stamp", async () => {
  await seedConfirmedPromise({ meetupStampedUserIds: ALL_SIX });
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: { meetupStampedUserIds: [B], goodbyeStampedUserIds: [] },
      updatedAt: new Date(),
    })
  );
});

test("a participant CANNOT append another user's uid to meetupStampedUserIds", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: { meetupStampedUserIds: [B], goodbyeStampedUserIds: [] },
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot forge another user's meetup verification record", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: {
        meetupStampedUserIds: [A],
        goodbyeStampedUserIds: [],
        meetupVerificationByUserId: { [B]: { rssi: -40 } },
      },
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set meetupCompletedAt", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      meetupCompletedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set completedAt", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      completedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot flip status to in_progress by claiming everyone stamped", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "in_progress",
      safetyStamp: { meetupStampedUserIds: ALL_SIX, goodbyeStampedUserIds: [] },
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot flip status to completed", async () => {
  await seedConfirmedPromise({ meetupStampedUserIds: ALL_SIX });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "completed",
      updatedAt: new Date(),
    })
  );
});

test("an honest room update still works after the server recorded a stamp", async () => {
  // 회귀 방지: activePromise.safetyStamp 존재 여부만 보면, 서버가 도장을 한 번
  // 쓴 뒤로 그 방의 모든 클라이언트 write(메시지 전송 포함)가 막힌다.
  await withClearedDb(async (db) => {
    await seedRooms(db);
    await setDoc(doc(db, "chat_rooms", ROOM), {
      roomId: ROOM,
      participantIds: ALL_SIX,
      lastMessage: "hello",
      activePromise: {
        promiseId: PROMISE,
        status: "confirmed",
        safetyStamp: { meetupStampedUserIds: [A], goodbyeStampedUserIds: [] },
      },
    });
  });
  const b = await kakaoSession(B);
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM), {
      lastMessage: "곧 도착!",
      lastMessageAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot change the server-written stamp mirror", async () => {
  await withClearedDb(async (db) => {
    await seedRooms(db);
    await setDoc(doc(db, "chat_rooms", ROOM), {
      roomId: ROOM,
      participantIds: ALL_SIX,
      lastMessage: "hello",
      activePromise: {
        promiseId: PROMISE,
        status: "confirmed",
        safetyStamp: { meetupStampedUserIds: [A], goodbyeStampedUserIds: [] },
      },
    });
  });
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", ROOM), {
      activePromise: {
        promiseId: PROMISE,
        status: "in_progress",
        safetyStamp: { meetupStampedUserIds: ALL_SIX },
      },
      updatedAt: new Date(),
    })
  );
});

test("a terminal promise's date and place cannot be rewritten", async () => {
  await withClearedDb(async (db) => {
    await seedRooms(db);
    await setDoc(
      doc(db, "chat_rooms", ROOM, "promises", PROMISE),
      promiseSeed({ status: "completed" })
    );
  });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      place: "다른 장소",
      dateTime: new Date("2026-09-20T12:00:00Z"),
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot spoof the room's activePromise stamp mirror", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM), {
      activePromise: {
        promiseId: PROMISE,
        status: "in_progress",
        safetyStamp: { meetupStampedUserIds: ALL_SIX },
      },
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot write a participantIds list that is not the room's", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      participantIds: [A, MALLORY],
      updatedAt: new Date(),
    })
  );
});

// ---------------------------------------------------------------------------
// 서버 전용 필드
// ---------------------------------------------------------------------------

test("a client cannot set exactReminderTaskToken", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      exactReminderTaskToken: "forged-token",
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set exactReminderScheduledForMs", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      exactReminderScheduledForMs: 1,
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set oneHourReminderSentAt", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      oneHourReminderSentAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set completionMode", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      completionMode: "auto_without_goodbye_stamp",
      updatedAt: new Date(),
    })
  );
});

test("a client cannot set exactReminderTaskToken at create time", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    setDoc(
      doc(c, "chat_rooms", ROOM, "promises", "promise_8"),
      promiseSeed({
        promiseId: "promise_8",
        requestedBy: C,
        requestedTo: D,
        exactReminderTaskToken: "forged-token",
      })
    )
  );
});

// ---------------------------------------------------------------------------
// 정직한 라이프사이클 (회귀 방지)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 약속 거절 / 취소 — 행위자 바인딩
//
// 이전에는 promiseStatusTransitionOk 안의
//   status in ['rejected','cancelled','requested']
// 한 줄이 방 참가자 누구에게나 열려 있어서, 6인 방에서 제3자가 남의 약속을
// 거절·취소하거나 날짜·장소를 바꿔치기할 수 있었다.
// 이제 거절은 받은 사람(requestedTo), 취소는 제안한 사람(requestedBy)만 한다.
// ---------------------------------------------------------------------------

test("the requestedTo user CAN reject the request", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "rejected",
      updatedAt: new Date(),
    })
  );
});

test("the requester CANNOT reject their own request", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "rejected",
      updatedAt: new Date(),
    })
  );
});

test("a bystander participant CANNOT reject someone else's promise", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    updateDoc(doc(c, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "rejected",
      updatedAt: new Date(),
    })
  );
});

test("a non-participant CANNOT reject a promise", async () => {
  await withClearedDb(seedRooms);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(
    updateDoc(doc(mallory, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "rejected",
      updatedAt: new Date(),
    })
  );
});

test("the requester CAN cancel their own pending promise", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertSucceeds(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      cancelledAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("the recipient CAN also cancel the promise (both parties may cancel)", async () => {
  // main 의 cancelPromise 제품 계약: 취소는 양 당사자 모두 가능하다.
  // 제3자(동석 참가자·비참가자) 차단은 아래 두 테스트가 계속 보장한다.
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      cancelledAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a bystander participant CANNOT cancel someone else's promise", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    updateDoc(doc(c, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      cancelledAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a non-participant CANNOT cancel a promise", async () => {
  await withClearedDb(seedRooms);
  const mallory = await kakaoSession(MALLORY);
  await assertFails(
    updateDoc(doc(mallory, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      updatedAt: new Date(),
    })
  );
});

test("a party CAN cancel a confirmed promise on safety-stamp timeout", async () => {
  await seedConfirmedPromise();
  const b = await kakaoSession(B);
  await assertSucceeds(
    updateDoc(doc(b, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      cancelledReason: "safety_stamp_timeout",
      cancelledAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a bystander CANNOT use the safety-stamp timeout reason to cancel", async () => {
  await seedConfirmedPromise();
  const c = await kakaoSession(C);
  await assertFails(
    updateDoc(doc(c, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "cancelled",
      cancelledReason: "safety_stamp_timeout",
      cancelledAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a bystander CANNOT rewrite the date and place of someone else's promise", async () => {
  await withClearedDb(seedRooms);
  const c = await kakaoSession(C);
  await assertFails(
    updateDoc(doc(c, "chat_rooms", ROOM, "promises", PROMISE), {
      dateTime: new Date("2026-09-11T20:00:00Z"),
      place: "다른 곳",
      updatedAt: new Date(),
    })
  );
});

test("a terminal promise cannot be resurrected by editing it back to requested", async () => {
  await withClearedDb(async (db) => {
    await seedRooms(db);
    await setDoc(
      doc(db, "chat_rooms", ROOM, "promises", PROMISE),
      promiseSeed({ status: "cancelled" })
    );
  });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      status: "requested",
      dateTime: new Date("2026-09-12T12:00:00Z"),
      updatedAt: new Date(),
    })
  );
});

// ---------------------------------------------------------------------------
// 헤어짐 사유 — 서버 전용 (safetyStamp 안에 저장되므로)
// ---------------------------------------------------------------------------

test("a participant CANNOT write their own goodbye follow-up reason directly", async () => {
  await seedConfirmedPromise({ meetupStampedUserIds: ALL_SIX });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: {
        meetupStampedUserIds: ALL_SIX,
        goodbyeStampedUserIds: [],
        goodbyeFollowUpByUserId: {
          [A]: { status: "submitted", reasonCode: "forgot_to_stamp" },
        },
      },
      updatedAt: new Date(),
    })
  );
});

test("a participant cannot submit a goodbye follow-up on behalf of another user", async () => {
  await seedConfirmedPromise({ meetupStampedUserIds: ALL_SIX });
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE), {
      safetyStamp: {
        meetupStampedUserIds: ALL_SIX,
        goodbyeStampedUserIds: [],
        goodbyeFollowUpByUserId: {
          [B]: { status: "submitted", reasonCode: "phone_off" },
        },
      },
      updatedAt: new Date(),
    })
  );
});

test("a read-only blind meeting room still blocks promise creation", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  await assertFails(
    setDoc(
      doc(a, "chat_rooms", BLIND_ROOM, "promises", "promise_blind"),
      promiseSeed({
        promiseId: "promise_blind",
        requestedBy: A,
        requestedTo: B,
      })
    )
  );
});

test("a read-only blind meeting room still blocks promise updates", async () => {
  await withClearedDb(seedRooms);
  const b = await kakaoSession(B);
  await assertFails(
    updateDoc(doc(b, "chat_rooms", BLIND_ROOM, "promises", PROMISE), {
      status: "confirmed",
      acceptedAt: new Date(),
      updatedAt: new Date(),
    })
  );
});

test("a participant CAN read a promise in their own room", async () => {
  await withClearedDb(seedRooms);
  const a = await kakaoSession(A);
  const snap = await assertSucceeds(
    getDoc(doc(a, "chat_rooms", ROOM, "promises", PROMISE))
  );
  assert.equal(snap.data().requestedBy, A);
});

// ---------------------------------------------------------------------------
// activePromise 미러 — 정상 경로를 막지 않는지 (회귀 방지)
//
// chat_service.dart 는 약속 수정/삭제/도착도장 시한초과 취소에서
// activePromise 를 FieldValue.delete() 한다. 미러에 도장을 못 싣게 막으면서
// 이 세 경로까지 막으면 모든 채팅방에서 약속 수정·삭제가 깨진다.
// ---------------------------------------------------------------------------

test("a party CAN clear activePromise when cancelling on safety-stamp timeout", async () => {
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertSucceeds(
    updateDoc(doc(a, "chat_rooms", ROOM), {
      activePromise: deleteField(),
      lastMessage: "약속이 삭제되었어요",
      updatedAt: new Date(),
    })
  );
});

test("a participant CANNOT replace activePromise with a non-map value", async () => {
  // 비-map 을 허용하면 그 방의 이후 모든 activePromise 규칙 평가가 에러가 되어
  // 안전도장 경로가 영구히 잠긴다 (한 명이 나머지 다섯 명을 막을 수 있다).
  await seedConfirmedPromise();
  const a = await kakaoSession(A);
  await assertFails(
    updateDoc(doc(a, "chat_rooms", ROOM), {
      activePromise: "x",
      updatedAt: new Date(),
    })
  );
});
