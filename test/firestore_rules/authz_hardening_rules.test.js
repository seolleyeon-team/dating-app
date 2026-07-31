/**
 * 권한 하드닝 — Firestore 보안 규칙 공격 테스트
 *
 * 2026-07 감사에서 확인한 계정 탈취 체인과 그 주변 노출을 재현한다.
 * 모든 테스트는 "공격이 거부되는가"를 검증하고, 정상 흐름이 계속 동작하는지도
 * 함께 확인한다 (fail-closed 로 바꾸면서 앱을 깨지 않았는지).
 *
 * 실행:
 *   cd test/firestore_rules && npm install && npm test
 *
 * ⚠ 사전 조건: Firestore emulator 는 JDK 21+ 를 요구한다.
 *   firebase-tools 는 Java 21 미만을 더 이상 지원하지 않는다.
 *   감사 시점 이 개발 머신에는 JDK 1.8 만 있어서 이 파일은 아직
 *   실행되지 않았다 (docs/audits/opus5/03-baseline-results.md 의 B-JDK21).
 *   배포 전에 반드시 JDK 21+ 환경에서 통과시켜야 한다.
 */

const { readFileSync } = require("node:fs");
const path = require("node:path");
const { after, before, beforeEach, describe, it } = require("node:test");

const {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} = require("@firebase/rules-unit-testing");
const {
  collection,
  doc,
  getDoc,
  getDocs,
  limit,
  query,
  setDoc,
  updateDoc,
  deleteDoc,
  serverTimestamp,
  Timestamp,
} = require("firebase/firestore");

const VICTIM = "victim-kakao-1111";
const ATTACKER = "attacker-kakao-9999";
const VICTIM_EMAIL = "victim@yonsei.ac.kr";

let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-authz-hardening",
    firestore: {
      rules: readFileSync(
        path.resolve(__dirname, "../../firestore.rules"),
        "utf8"
      ),
    },
  });
});

after(async () => {
  if (testEnv) await testEnv.cleanup();
});

beforeEach(async () => {
  await testEnv.clearFirestore();
  // 규칙을 우회해서 시드한다.
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "users", VICTIM), {
      kakaoUserId: VICTIM,
      nickname: "피해자",
      studentEmail: VICTIM_EMAIL,
      isStudentVerified: true,
      onboarding: { nickname: "피해자", birthYear: "2002", major: "컴퓨터과학" },
    });
    await setDoc(doc(db, "users", ATTACKER), {
      kakaoUserId: ATTACKER,
      nickname: "공격자",
      studentEmail: "attacker@yonsei.ac.kr",
      isStudentVerified: true,
      onboarding: { nickname: "공격자" },
    });
    await setDoc(doc(db, "users", VICTIM, "deviceTokens", "victim-fcm-token"), {
      userId: VICTIM,
      token: "victim-fcm-token",
    });
    await setDoc(doc(db, "blocks", VICTIM, "targets", ATTACKER), {
      fromUserId: VICTIM,
      toUserId: ATTACKER,
    });
    await setDoc(
      doc(db, "modelRecs", VICTIM, "daily", "2026-07-31", "sources", "rrf"),
      { items: [{ candidateUid: "someone", rank: 1, score: 0.9 }] }
    );
    await setDoc(doc(db, "recEvents", VICTIM, "events", "e1"), {
      userId: VICTIM,
      targetUserId: "someone",
      eventType: "like",
    });
  });
});

const anon = () => testEnv.unauthenticatedContext().firestore();
const as = (uid) => testEnv.authenticatedContext(uid).firestore();

// ---------------------------------------------------------------------------
// 1. 계정 탈취 체인
// ---------------------------------------------------------------------------
describe("계정 탈취 체인", () => {
  it("익명 사용자는 users 를 나열할 수 없다 (체인 1단계 차단)", async () => {
    await assertFails(getDocs(query(collection(anon(), "users"), limit(30))));
  });

  it("익명 사용자는 임의 users 문서를 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(anon(), "users", VICTIM)));
  });

  it("익명 사용자는 emailLinkTokens 문서를 만들 수 없다 (체인 2단계 차단)", async () => {
    await assertFails(
      setDoc(doc(anon(), "emailLinkTokens", "forged-token"), {
        email: VICTIM_EMAIL,
        kakaoUserId: VICTIM,
        createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
      })
    );
  });

  it("인증 사용자도 남의 kakaoUserId 로 emailLinkTokens 를 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "emailLinkTokens", "forged-token-2"), {
        email: VICTIM_EMAIL,
        kakaoUserId: VICTIM,
        createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
      })
    );
  });

  it("본인 kakaoUserId 로는 emailLinkTokens 를 만들 수 있다 (학생 인증 유지)", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "emailLinkTokens", "own-token"), {
        email: "attacker@yonsei.ac.kr",
        kakaoUserId: ATTACKER,
        createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
      })
    );
  });

  it("expiresAt 이 timestamp 가 아니면 거부한다 (만료 우회 차단)", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "emailLinkTokens", "bad-expiry"), {
        email: "attacker@yonsei.ac.kr",
        kakaoUserId: ATTACKER,
        createdAt: serverTimestamp(),
        expiresAt: "not-a-timestamp",
      })
    );
  });

  it("허용되지 않은 필드를 끼워넣으면 거부한다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "emailLinkTokens", "extra-field"), {
        email: "attacker@yonsei.ac.kr",
        kakaoUserId: ATTACKER,
        createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
        isStudentVerified: true,
      })
    );
  });

  it("남의 emailLinkTokens 를 지울 수 없다 (인증 방해 차단)", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), "emailLinkTokens", "victim-token"), {
        email: VICTIM_EMAIL,
        kakaoUserId: VICTIM,
        createdAt: Timestamp.now(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
      });
    });
    await assertFails(
      deleteDoc(doc(as(ATTACKER), "emailLinkTokens", "victim-token"))
    );
  });
});

// ---------------------------------------------------------------------------
// 2. users 보호 필드
// ---------------------------------------------------------------------------
describe("users 보호 필드", () => {
  it("익명 사용자는 남의 학교 인증 상태를 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(anon(), "users", VICTIM), { isStudentVerified: true })
    );
  });

  it("공격자는 피해자 문서를 수정할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", VICTIM), { nickname: "hacked" })
    );
  });

  it("공격자는 피해자 계정을 잠글 수 없다 (loginDisabled)", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", VICTIM), { loginDisabled: true })
    );
  });

  it("본인도 loginDisabled 를 추가할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), { loginDisabled: true })
    );
  });

  it("본인도 role 을 추가할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), { role: "admin" })
    );
  });

  it("본인도 isAdmin 을 추가할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), { isAdmin: true })
    );
  });

  it("본인도 studentEmail 을 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), {
        studentEmail: "someone-else@yonsei.ac.kr",
      })
    );
  });

  it("본인도 mannerScore 를 조작할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), { mannerScore: 999 })
    );
  });

  it("본인은 onboarding 프로필을 수정할 수 있다 (정상 흐름 유지)", async () => {
    await assertSucceeds(
      updateDoc(doc(as(ATTACKER), "users", ATTACKER), {
        onboarding: { nickname: "새 닉네임" },
        onboardingUpdatedAt: serverTimestamp(),
      })
    );
  });

  it("인증 사용자는 본인 문서를 읽을 수 있다", async () => {
    await assertSucceeds(getDoc(doc(as(ATTACKER), "users", ATTACKER)));
  });

  it("인증 사용자는 다른 사용자 프로필을 읽을 수 있다 (추천·탐색 유지)", async () => {
    // 필드 단위 분리는 후속 과제(R-FS-2). 지금은 인증만 요구한다.
    await assertSucceeds(getDoc(doc(as(ATTACKER), "users", VICTIM)));
  });

  it("인증 사용자의 limit 30 후보 조회는 허용한다 (fallback 추천 유지)", async () => {
    await assertSucceeds(
      getDocs(query(collection(as(ATTACKER), "users"), limit(30)))
    );
  });

  it("limit 을 초과하는 나열은 거부한다 (대량 수집 억제)", async () => {
    await assertFails(
      getDocs(query(collection(as(ATTACKER), "users"), limit(500)))
    );
  });
});

// ---------------------------------------------------------------------------
// 3. deviceTokens — 푸시 하이재킹
// ---------------------------------------------------------------------------
describe("deviceTokens", () => {
  it("공격자는 피해자 FCM 토큰을 읽을 수 없다", async () => {
    await assertFails(
      getDocs(collection(as(ATTACKER), "users", VICTIM, "deviceTokens"))
    );
  });

  it("공격자는 피해자 uid 아래에 토큰을 등록할 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "users", VICTIM, "deviceTokens", "attacker-t"), {
        userId: VICTIM,
        token: "attacker-t",
      })
    );
  });

  it("공격자는 피해자 토큰을 지울 수 없다 (푸시 차단 공격)", async () => {
    await assertFails(
      deleteDoc(
        doc(as(ATTACKER), "users", VICTIM, "deviceTokens", "victim-fcm-token")
      )
    );
  });

  it("본인 토큰 등록은 허용한다 (정상 흐름 유지)", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "users", ATTACKER, "deviceTokens", "own-t"), {
        userId: ATTACKER,
        token: "own-t",
      })
    );
  });
});

// ---------------------------------------------------------------------------
// 4. blocks — 차단 무력화
// ---------------------------------------------------------------------------
describe("blocks", () => {
  it("공격자는 자신에 대한 피해자의 차단을 지울 수 없다", async () => {
    await assertFails(
      deleteDoc(doc(as(ATTACKER), "blocks", VICTIM, "targets", ATTACKER))
    );
  });

  it("공격자는 피해자의 차단 목록을 읽을 수 없다", async () => {
    await assertFails(
      getDocs(collection(as(ATTACKER), "blocks", VICTIM, "targets"))
    );
  });

  it("본인 차단 등록·조회는 허용한다", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "blocks", ATTACKER, "targets", VICTIM), {
        fromUserId: ATTACKER,
        toUserId: VICTIM,
      })
    );
    await assertSucceeds(
      getDocs(collection(as(ATTACKER), "blocks", ATTACKER, "targets"))
    );
  });
});

// ---------------------------------------------------------------------------
// 5. 추천 데이터
// ---------------------------------------------------------------------------
describe("추천 데이터", () => {
  it("공격자는 피해자의 추천 결과를 읽을 수 없다", async () => {
    await assertFails(
      getDoc(
        doc(
          as(ATTACKER),
          "modelRecs",
          VICTIM,
          "daily",
          "2026-07-31",
          "sources",
          "rrf"
        )
      )
    );
  });

  it("본인 추천 결과는 읽을 수 있다", async () => {
    await assertSucceeds(
      getDoc(
        doc(
          as(VICTIM),
          "modelRecs",
          VICTIM,
          "daily",
          "2026-07-31",
          "sources",
          "rrf"
        )
      )
    );
  });

  it("익명 사용자는 recEvents 를 쓸 수 없다", async () => {
    await assertFails(
      setDoc(doc(anon(), "recEvents", VICTIM, "events", "forged"), {
        userId: VICTIM,
        targetUserId: "someone",
        eventType: "like",
      })
    );
  });

  it("공격자는 피해자 recEvents 를 위조할 수 없다 (가짜 매치 생성 차단)", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "recEvents", VICTIM, "events", "forged"), {
        userId: VICTIM,
        targetUserId: ATTACKER,
        eventType: "like",
      })
    );
  });

  it("공격자는 피해자 recEvents 를 읽을 수 없다", async () => {
    await assertFails(
      getDoc(doc(as(ATTACKER), "recEvents", VICTIM, "events", "e1"))
    );
  });

  it("본인 recEvents 기록은 허용한다 (학습 로그 유지)", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "recEvents", ATTACKER, "events", "own"), {
        userId: ATTACKER,
        targetUserId: VICTIM,
        eventType: "impression",
      })
    );
  });

  it("문서의 userId 가 경로와 다르면 거부한다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "recEvents", ATTACKER, "events", "spoofed"), {
        userId: VICTIM,
        targetUserId: "someone",
        eventType: "like",
      })
    );
  });
});

// ---------------------------------------------------------------------------
// 6. 알림함
// ---------------------------------------------------------------------------
describe("notifications", () => {
  it("공격자는 피해자 알림함을 읽을 수 없다", async () => {
    await assertFails(
      getDocs(collection(as(ATTACKER), "users", VICTIM, "notifications"))
    );
  });

  it("공격자는 피해자에게 알림을 꽂을 수 없다 (스팸·피싱 차단)", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "users", VICTIM, "notifications", "spam"), {
        type: "chat",
        title: "당첨되었습니다",
        body: "링크를 눌러주세요",
        isRead: false,
      })
    );
  });

  it("본인 알림 읽음 처리는 허용한다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(
        doc(ctx.firestore(), "users", VICTIM, "notifications", "n1"),
        { type: "chat", title: "t", body: "b", isRead: false }
      );
    });
    await assertSucceeds(
      updateDoc(doc(as(VICTIM), "users", VICTIM, "notifications", "n1"), {
        isRead: true,
      })
    );
  });
});
