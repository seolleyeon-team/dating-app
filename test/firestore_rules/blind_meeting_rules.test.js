/**
 * 3:3 블라인드 취향 미팅 — Firestore 보안 규칙 테스트
 *
 * 실행 요건 (이 환경에서는 충족되지 않아 실행하지 못했음):
 *   - firebase-tools 설치 (npm i -g firebase-tools)
 *   - Java 11 이상 (Firestore emulator 요구사항, 현재 환경은 Java 8)
 *
 * 실행:
 *   cd test/firestore_rules && npm install && npm test
 */

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { after, before, describe, it } = require("node:test");

const {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} = require("@firebase/rules-unit-testing");
const {
  doc,
  getDoc,
  setDoc,
  updateDoc,
  addDoc,
  collection,
} = require("firebase/firestore");

const MEETING_ID = "m1";
const A1 = "a1";
const A2 = "a2";
const B1 = "b1";
const OUTSIDER = "zz";

let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-rules-test",
    firestore: {
      rules: readFileSync(
        path.resolve(__dirname, "../../firestore.rules"),
        "utf8"
      ),
    },
  });

  await testEnv.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    await setDoc(doc(db, "blindMeetingDna", A1), {
      userId: A1,
      meetingPurpose: "both",
    });
    await setDoc(doc(db, "blindMeetingApplications", A1), {
      userId: A1,
      open: true,
    });
    await setDoc(doc(db, "blindMeetings", MEETING_ID), {
      meetingId: MEETING_ID,
      status: "chatOpen",
      serverStatus: "chat_open",
      participantIds: [A1, A2, B1],
      teamAUserIds: [A1, A2],
      teamBUserIds: [B1],
      groupChatId: `blind_${MEETING_ID}`,
    });
    await setDoc(
      doc(db, "blindMeetings", MEETING_ID, "participants", A1),
      { userId: A1, status: "confirmed", depositStatus: "paid" }
    );
    await setDoc(
      doc(db, "blindMeetings", MEETING_ID, "publicProfiles", B1),
      { userId: B1, nickname: "하늘" }
    );
    await setDoc(
      doc(db, "blindMeetings", MEETING_ID, "matchingResult", "summary"),
      { finalGroupScore: 0.9 }
    );
    await setDoc(
      doc(db, "blindMeetings", MEETING_ID, "followUpChoices", A1),
      { chooserUid: A1, selectedUids: [B1] }
    );
    await setDoc(
      doc(db, "blindMeetings", MEETING_ID, "mutualMatches", `${A1}|${B1}`),
      { userIds: [A1, B1], chatRoomId: "dm_a1_b1" }
    );
    await setDoc(doc(db, "chat_rooms", `blind_${MEETING_ID}`), {
      roomId: `blind_${MEETING_ID}`,
      roomType: "blind_meeting_group",
      meetingId: MEETING_ID,
      status: "active",
      writable: true,
      participantIds: [A1, A2, B1],
    });
    await setDoc(doc(db, "blindMeetingReplacementOffers", "offer1"), {
      candidateUid: OUTSIDER,
      meetingId: MEETING_ID,
      offerStatus: "offered",
    });
  });
});

after(async () => {
  await testEnv?.cleanup();
});

function authed(uid) {
  return testEnv.authenticatedContext(uid).firestore();
}

describe("비공개 미팅 DNA", () => {
  it("본인은 읽을 수 있다", async () => {
    await assertSucceeds(getDoc(doc(authed(A1), "blindMeetingDna", A1)));
  });

  it("다른 참가자의 DNA 조회는 거부된다", async () => {
    await assertFails(getDoc(doc(authed(A2), "blindMeetingDna", A1)));
  });

  it("클라이언트 쓰기는 거부된다", async () => {
    await assertFails(
      setDoc(doc(authed(A1), "blindMeetingDna", A1), { meetingPurpose: "romance" })
    );
  });
});

describe("신청 문서", () => {
  it("본인만 읽을 수 있고 쓰기는 거부된다", async () => {
    await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetingApplications", A1))
    );
    await assertFails(getDoc(doc(authed(A2), "blindMeetingApplications", A1)));
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingApplications", A1), { open: false })
    );
  });
});

describe("미팅 문서", () => {
  it("참가자만 조회할 수 있다", async () => {
    await assertSucceeds(getDoc(doc(authed(A1), "blindMeetings", MEETING_ID)));
    await assertFails(
      getDoc(doc(authed(OUTSIDER), "blindMeetings", MEETING_ID))
    );
  });

  it("participant 배열 변경은 거부된다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetings", MEETING_ID), {
        participantIds: [A1],
      })
    );
  });

  it("status 직접 변경은 거부된다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetings", MEETING_ID), {
        status: "completed",
      })
    );
  });

  it("payment/attendance 상태 위조는 거부된다", async () => {
    await assertFails(
      updateDoc(
        doc(authed(A1), "blindMeetings", MEETING_ID, "participants", A1),
        { depositStatus: "paid" }
      )
    );
    await assertFails(
      updateDoc(
        doc(authed(A1), "blindMeetings", MEETING_ID, "participants", A1),
        { checkInStatus: "completed" }
      )
    );
  });

  it("내부 매칭 점수는 읽을 수 없다", async () => {
    await assertFails(
      getDoc(
        doc(authed(A1), "blindMeetings", MEETING_ID, "matchingResult", "summary")
      )
    );
  });

  it("공개 프로필은 참가자만 읽을 수 있다", async () => {
    await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetings", MEETING_ID, "publicProfiles", B1))
    );
    await assertFails(
      getDoc(
        doc(authed(OUTSIDER), "blindMeetings", MEETING_ID, "publicProfiles", B1)
      )
    );
  });
});

describe("후속 선택", () => {
  it("자신의 선택만 읽을 수 있다", async () => {
    await assertSucceeds(
      getDoc(
        doc(authed(A1), "blindMeetings", MEETING_ID, "followUpChoices", A1)
      )
    );
    await assertFails(
      getDoc(
        doc(authed(A2), "blindMeetings", MEETING_ID, "followUpChoices", A1)
      )
    );
  });

  it("클라이언트가 직접 제출할 수 없다", async () => {
    await assertFails(
      setDoc(
        doc(authed(A2), "blindMeetings", MEETING_ID, "followUpChoices", A2),
        { chooserUid: A2, selectedUids: [B1] }
      )
    );
  });

  it("상호 선택 결과는 직접 읽을 수 없다", async () => {
    await assertFails(
      getDoc(
        doc(
          authed(A1),
          "blindMeetings",
          MEETING_ID,
          "mutualMatches",
          `${A1}|${B1}`
        )
      )
    );
  });
});

describe("단체 채팅", () => {
  it("확정 참가자는 메시지를 보낼 수 있다", async () => {
    await assertSucceeds(
      addDoc(
        collection(authed(A1), "chat_rooms", `blind_${MEETING_ID}`, "messages"),
        { senderId: A1, text: "안녕하세요", type: "text", readBy: [A1] }
      )
    );
  });

  it("참가자가 아니면 메시지를 보낼 수 없다", async () => {
    await assertFails(
      addDoc(
        collection(
          authed(OUTSIDER),
          "chat_rooms",
          `blind_${MEETING_ID}`,
          "messages"
        ),
        { senderId: OUTSIDER, text: "안녕하세요", type: "text", readBy: [] }
      )
    );
  });

  it("senderId 위조는 거부된다", async () => {
    await assertFails(
      addDoc(
        collection(authed(A1), "chat_rooms", `blind_${MEETING_ID}`, "messages"),
        { senderId: B1, text: "위조", type: "text", readBy: [] }
      )
    );
  });

  it("participantIds 변경은 거부된다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "chat_rooms", `blind_${MEETING_ID}`), {
        participantIds: [A1],
      })
    );
  });

  it("읽기 전용 전환 후에는 메시지를 보낼 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (context) => {
      await updateDoc(
        doc(context.firestore(), "chat_rooms", `blind_${MEETING_ID}`),
        { writable: false, status: "read_only" }
      );
    });
    await assertFails(
      addDoc(
        collection(authed(A1), "chat_rooms", `blind_${MEETING_ID}`, "messages"),
        { senderId: A1, text: "닫힌 뒤", type: "text", readBy: [A1] }
      )
    );
    await testEnv.withSecurityRulesDisabled(async (context) => {
      await updateDoc(
        doc(context.firestore(), "chat_rooms", `blind_${MEETING_ID}`),
        { writable: true, status: "active" }
      );
    });
  });

  it("클라이언트는 블라인드 미팅 채팅방을 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(authed(A1), "chat_rooms", "blind_fake"), {
        roomType: "blind_meeting_group",
        participantIds: [A1],
        writable: true,
      })
    );
  });

  it("교체된 참가자는 접근이 끊긴다", async () => {
    await testEnv.withSecurityRulesDisabled(async (context) => {
      await updateDoc(
        doc(context.firestore(), "chat_rooms", `blind_${MEETING_ID}`),
        { participantIds: [A2, B1] }
      );
    });
    await assertFails(
      addDoc(
        collection(authed(A1), "chat_rooms", `blind_${MEETING_ID}`, "messages"),
        { senderId: A1, text: "교체 이후", type: "text", readBy: [A1] }
      )
    );
  });
});

describe("대체 참가 제안", () => {
  it("제안받은 본인만 조회할 수 있다", async () => {
    await assertSucceeds(
      getDoc(doc(authed(OUTSIDER), "blindMeetingReplacementOffers", "offer1"))
    );
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingReplacementOffers", "offer1"))
    );
  });

  it("제안 상태를 직접 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(
        doc(authed(OUTSIDER), "blindMeetingReplacementOffers", "offer1"),
        { offerStatus: "accepted" }
      )
    );
  });
});

describe("결제 / 안전 / 운영 문서", () => {
  it("서버 전용 컬렉션은 읽을 수 없다", async () => {
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingDeposits", `${MEETING_ID}_${A1}`))
    );
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingSafetyFlags", MEETING_ID))
    );
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingOpsReviews", "r1"))
    );
    await assertFails(
      getDoc(doc(authed(A1), "notificationDispatchLog", "k1"))
    );
  });

  it("관리자 권한을 클라이언트 필드로 위조할 수 없다", async () => {
    await assertFails(
      setDoc(doc(authed(A1), "blindMeetingOpsReviews", "forged"), {
        admin: true,
        status: "closed",
      })
    );
  });
});
