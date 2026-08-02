/**
 * 3:3 미팅 아이스브레이킹 룰렛 — Firestore 보안 규칙 테스트
 * 경로: test/firestore_rules/meeting_icebreaker_rules.test.js
 *
 * 실행 요건:
 *   - firebase-tools (npx firebase 로도 가능)
 *   - Java 11 이상 (Firestore emulator 요구사항)
 *
 * 실행:
 *   cd test/firestore_rules && npm install
 *   npx firebase emulators:exec --only firestore \
 *     --project seolleyeon-rules-test \
 *     "node --test meeting_icebreaker_rules.test.js"
 *
 * 검증 목표
 *   - 반복 알림 상태는 서버만 쓴다 (isActive / nextPromptAt / stopReason 등)
 *   - 참가자는 자신의 문서만 읽는다 (다른 참가자의 알림 설정은 비공개)
 *   - analytics는 개인정보와 폭탄 숨겨진 시간이 없을 때만 append 가능
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
  addDoc,
  collection,
  doc,
  getDoc,
  setDoc,
  updateDoc,
} = require("firebase/firestore");

const SESSION_ID = "blind_m1";
const OWNER = "a1";
const OTHER = "b1";

let testEnv;

const sessionPath = ["meetingIcebreakerSessions", SESSION_ID];
const participantPath = [...sessionPath, "promptParticipants"];

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
    await setDoc(doc(db, ...sessionPath), {
      sessionId: SESSION_ID,
      meetingType: "blindTasteMeeting",
      meetingId: "m1",
      isAlcoholFree: false,
    });
    await setDoc(doc(db, ...participantPath, OWNER), {
      sessionId: SESSION_ID,
      meetingId: "m1",
      meetingType: "blindTasteMeeting",
      uid: OWNER,
      isActive: true,
      optedOut: false,
      promptSequence: 1,
      scheduleVersion: 2,
    });
    await setDoc(doc(db, ...participantPath, OTHER), {
      sessionId: SESSION_ID,
      meetingId: "m1",
      meetingType: "blindTasteMeeting",
      uid: OTHER,
      isActive: true,
      optedOut: true,
      promptSequence: 3,
      scheduleVersion: 4,
    });
    await setDoc(doc(db, "meetingIcebreakerConfig", "current"), {
      promptIntervalMinutes: 15,
      maxPromptDurationHours: 6,
    });
  });
});

after(async () => {
  if (testEnv) await testEnv.cleanup();
});

function authed(uid) {
  return testEnv.authenticatedContext(uid).firestore();
}

function anon() {
  return testEnv.unauthenticatedContext().firestore();
}

describe("반복 알림 세션", () => {
  it("세션 메타 문서는 클라이언트가 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(authed(OWNER), ...sessionPath)));
  });

  it("자신의 알림 상태는 읽을 수 있다", async () => {
    const snap = await assertSucceeds(
      getDoc(doc(authed(OWNER), ...participantPath, OWNER))
    );
    assert.equal(snap.data().uid, OWNER);
  });

  it("다른 참가자의 알림 설정은 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(authed(OWNER), ...participantPath, OTHER)));
  });

  it("로그인하지 않으면 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(anon(), ...participantPath, OWNER)));
  });

  it("isActive를 직접 켤 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(OWNER), ...participantPath, OWNER), {
        isActive: true,
      })
    );
  });

  it("nextPromptAt / promptSequence / stopReason을 바꿀 수 없다", async () => {
    for (const patch of [
      { nextPromptAt: new Date() },
      { promptSequence: 99 },
      { stopReason: "opted_out" },
      { scheduleVersion: 99 },
      { expiresAt: new Date() },
    ]) {
      await assertFails(
        updateDoc(doc(authed(OWNER), ...participantPath, OWNER), patch)
      );
    }
  });

  it("optedOut도 직접 바꿀 수 없다 (callable만 가능)", async () => {
    await assertFails(
      updateDoc(doc(authed(OWNER), ...participantPath, OWNER), {
        optedOut: true,
      })
    );
  });

  it("다른 사용자의 알림 상태를 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(authed(OWNER), ...participantPath, "zz"), {
        uid: "zz",
        isActive: true,
      })
    );
  });

  it("세션 문서를 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(authed(OWNER), "meetingIcebreakerSessions", "blind_fake"), {
        sessionId: "blind_fake",
        meetingType: "blindTasteMeeting",
        meetingId: "fake",
      })
    );
  });
});

describe("운영 설정", () => {
  it("정책 문서는 읽기 전용으로 공개된다", async () => {
    const snap = await assertSucceeds(
      getDoc(doc(authed(OWNER), "meetingIcebreakerConfig", "current"))
    );
    assert.equal(snap.data().promptIntervalMinutes, 15);
  });

  it("정책 문서를 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(authed(OWNER), "meetingIcebreakerConfig", "current"), {
        promptIntervalMinutes: 1,
      })
    );
  });
});

describe("analytics", () => {
  it("허용된 이벤트는 append 할 수 있다", async () => {
    for (const event of [
      "meeting_icebreaker_prompt_opened",
      "meeting_roulette_spin_completed",
      "meeting_game_result_shown",
      "bomb_timer_exploded",
    ]) {
      await assertSucceeds(
        addDoc(collection(authed(OWNER), "meetingIcebreakerAnalytics"), {
          event,
          params: { meeting_type: "blindTasteMeeting", game_type: "bombPass" },
        })
      );
    }
  });

  it("다른 기능의 이벤트 이름은 거부한다", async () => {
    await assertFails(
      addDoc(collection(authed(OWNER), "meetingIcebreakerAnalytics"), {
        event: "chat_message_sent",
        params: {},
      })
    );
  });

  it("폭탄 숨겨진 시간을 담으면 거부한다", async () => {
    await assertFails(
      addDoc(collection(authed(OWNER), "meetingIcebreakerAnalytics"), {
        event: "bomb_timer_exploded",
        params: { hiddenSeconds: 7 },
      })
    );
    await assertFails(
      addDoc(collection(authed(OWNER), "meetingIcebreakerAnalytics"), {
        event: "bomb_timer_exploded",
        params: { bombSeconds: 7 },
      })
    );
  });

  it("개인정보를 담으면 거부한다", async () => {
    for (const params of [
      { userId: OWNER },
      { nickname: "민지" },
      { participantIds: [OWNER, OTHER] },
      { place: "홍대 카페" },
      { fcmToken: "token" },
    ]) {
      await assertFails(
        addDoc(collection(authed(OWNER), "meetingIcebreakerAnalytics"), {
          event: "meeting_roulette_shown",
          params,
        })
      );
    }
  });

  it("analytics를 조회하거나 수정할 수 없다", async () => {
    await assertFails(
      getDoc(doc(authed(OWNER), "meetingIcebreakerAnalytics", "any"))
    );
  });
});
