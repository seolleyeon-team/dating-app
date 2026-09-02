/**
 * 3:3 블라인드 취향 미팅 — Firestore 보안 규칙 테스트
 *
 * 실행 요건:
 *   - firebase-tools (npx firebase 로도 가능)
 *   - Java 11 이상 (Firestore emulator 요구사항)
 *
 * 실행:
 *   cd test/firestore_rules && npm install
 *   npx firebase emulators:exec --only firestore \
 *     --project seolleyeon-rules-test "node --test blind_meeting_rules.test.js"
 *
 * 주의: 같은 emulator project를 쓰는 다른 테스트 파일과 동시에 실행하면
 *       seed 데이터가 서로 간섭한다. 파일 단위로 실행할 것.
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
  getDocs,
  query,
  where,
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
      requestedDateKeys: ["2026-08-02", "2026-08-05"],
      availabilityMode: "date_only",
      scheduleSelectionVersion: 2,
    });
    await setDoc(doc(db, "blindMeetingParties", "party1"), {
      partyId: "party1",
      leaderUserId: A1,
      acceptedUserIds: [A1, A2],
      pendingInviteeIds: [B1],
      status: "forming",
    });
    await setDoc(doc(db, "blindMeetingPartyInvites", "partyInvite1"), {
      partyId: "party1",
      inviterUserId: A1,
      inviteeUserId: B1,
      status: "pending",
    });
    await setDoc(doc(db, "blindMeetingPartyMemberships", A1), {
      partyId: "party1",
      active: true,
    });
    await setDoc(doc(db, "blindMeetingPartyMatching", "party1"), {
      effectivePreferences: { smokingCompanionPreference: "nonSmokersOnly" },
    });
    await setDoc(doc(db, "blindMeetings", MEETING_ID), {
      meetingId: MEETING_ID,
      status: "chatOpen",
      serverStatus: "chat_open",
      participantIds: [A1, A2, B1],
      teamAUserIds: [A1, A2],
      teamBUserIds: [B1],
      groupChatId: `blind_${MEETING_ID}`,
      matchedDateKey: "2026-08-02",
      commonAvailableDateKeys: ["2026-08-02", "2026-08-05"],
      availabilityMode: "date_only",
      scheduleSelectionVersion: 2,
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

describe("친구 파티", () => {
  it("수락한 멤버는 파티를 읽고 외부인과 초대 대기자는 읽지 못한다", async () => {
    await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetingParties", "party1"))
    );
    await assertSucceeds(
      getDoc(doc(authed(A2), "blindMeetingParties", "party1"))
    );
    await assertFails(
      getDoc(doc(authed(B1), "blindMeetingParties", "party1"))
    );
    await assertFails(
      getDoc(doc(authed(OUTSIDER), "blindMeetingParties", "party1"))
    );
  });

  it("acceptedUserIds 조건을 건 본인 파티 목록 조회만 허용한다", async () => {
    await assertSucceeds(
      getDocs(
        query(
          collection(authed(A1), "blindMeetingParties"),
          where("acceptedUserIds", "array-contains", A1)
        )
      )
    );
    await assertFails(getDocs(collection(authed(A1), "blindMeetingParties")));
  });

  it("초대자와 초대받은 사람만 초대장을 읽는다", async () => {
    await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetingPartyInvites", "partyInvite1"))
    );
    await assertSucceeds(
      getDoc(doc(authed(B1), "blindMeetingPartyInvites", "partyInvite1"))
    );
    await assertFails(
      getDoc(doc(authed(A2), "blindMeetingPartyInvites", "partyInvite1"))
    );
  });

  it("파티·초대는 클라이언트가 만들거나 수정할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingParties", "party1"), {
        acceptedUserIds: [A1, OUTSIDER],
      })
    );
    await assertFails(
      setDoc(doc(authed(A1), "blindMeetingPartyInvites", "forged"), {
        partyId: "party1",
        inviterUserId: A1,
        inviteeUserId: OUTSIDER,
        status: "accepted",
      })
    );
  });

  it("membership lock과 집계된 취향은 파티 멤버에게도 비공개다", async () => {
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingPartyMemberships", A1))
    );
    await assertFails(
      getDoc(doc(authed(A1), "blindMeetingPartyMatching", "party1"))
    );
  });
});

describe("참여 가능 날짜 (date-only)", () => {
  // 날짜 검증은 submitBlindMeetingApplication callable에서만 수행된다.
  // Rules는 클라이언트 쓰기를 전면 차단해 검증 우회 자체를 막는다.

  it("본인 DNA의 availableDateKeys를 직접 쓸 수 없다", async () => {
    await assertFails(
      setDoc(doc(authed(A1), "blindMeetingDna", A1), {
        availableDateKeys: ["2026-08-02"],
      })
    );
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingDna", A1), {
        availableDateKeys: ["2026-08-02"],
      })
    );
  });

  it("신청 문서의 requestedDateKeys를 직접 쓸 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingApplications", A1), {
        requestedDateKeys: ["2026-08-02"],
      })
    );
  });

  it("잘못된 날짜 형식도 애초에 쓸 수 없다", async () => {
    for (const bad of [
      ["2026-2-30"],
      ["20260802"],
      ["2026-02-30"],
      ["2026-08-02", "2026-08-02"],
      "2026-08-02",
      [42],
    ]) {
      await assertFails(
        updateDoc(doc(authed(A1), "blindMeetingApplications", A1), {
          requestedDateKeys: bad,
        })
      );
    }
  });

  it("legacy 시간대 필드로 검증을 우회할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingApplications", A1), {
        requestedSlotIds: ["2026-08-02#evening"],
      })
    );
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetingDna", A1), {
        availableSlotIds: ["2026-08-02#evening"],
        availableSlots: ["2026-08-02#evening"],
      })
    );
  });

  it("다른 사용자의 날짜를 수정할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(A2), "blindMeetingApplications", A1), {
        requestedDateKeys: ["2026-08-09"],
      })
    );
    await assertFails(
      setDoc(doc(authed(A2), "blindMeetingDna", A1), {
        availableDateKeys: ["2026-08-09"],
      })
    );
  });

  it("비인증 사용자는 신청 문서를 읽거나 쓸 수 없다", async () => {
    const anon = testEnv.unauthenticatedContext().firestore();
    await assertFails(getDoc(doc(anon, "blindMeetingApplications", A1)));
    await assertFails(
      setDoc(doc(anon, "blindMeetingApplications", A1), {
        requestedDateKeys: ["2026-08-02"],
      })
    );
    await assertFails(
      setDoc(doc(anon, "blindMeetingDna", A1), {
        availableDateKeys: ["2026-08-02"],
      })
    );
  });

  it("매칭 후 공통 날짜를 임의로 바꿔 그룹 조건을 깨뜨릴 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetings", MEETING_ID), {
        commonAvailableDateKeys: ["2027-01-01"],
      })
    );
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetings", MEETING_ID), {
        matchedDateKey: "2027-01-01",
      })
    );
    await assertFails(
      updateDoc(doc(authed(A1), "blindMeetings", MEETING_ID), {
        slotId: "2027-01-01#evening",
      })
    );
  });

  it("참가자는 미팅의 공통 날짜를 읽을 수 있다", async () => {
    const snap = await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetings", MEETING_ID))
    );
    assert.deepEqual(snap.data().commonAvailableDateKeys, [
      "2026-08-02",
      "2026-08-05",
    ]);
    assert.equal(snap.data().availabilityMode, "date_only");
  });

  it("본인 신청 문서에서 선택 날짜를 복구할 수 있다", async () => {
    const snap = await assertSucceeds(
      getDoc(doc(authed(A1), "blindMeetingApplications", A1))
    );
    assert.deepEqual(snap.data().requestedDateKeys, [
      "2026-08-02",
      "2026-08-05",
    ]);
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
