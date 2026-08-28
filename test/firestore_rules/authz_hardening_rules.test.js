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
    await setDoc(doc(db, "publicProfiles", VICTIM), {
      nickname: "victim-public",
      profileImageUrl: "",
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

  it("인증 사용자도 emailLinkTokens 를 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "emailLinkTokens", "forged-token-2"), {
        email: VICTIM_EMAIL,
        kakaoUserId: VICTIM,
        createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromDate(new Date(Date.now() + 60000)),
      })
    );
  });

  it("본인 kakaoUserId 로도 emailLinkTokens 를 만들 수 없다 (서버 전용)", async () => {
    await assertFails(
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

  it("authenticated users read cross-user profiles through publicProfiles", async () => {
    // Cross-user reads are served through the publicProfiles projection.
    await assertSucceeds(getDoc(doc(as(ATTACKER), "publicProfiles", VICTIM)));
  });

  it("authenticated users cannot read another user private users document", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "users", VICTIM)));
  });

  it("인증 사용자도 users 후보 목록을 조회할 수 없다", async () => {
    await assertFails(
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

  it("본인 차단 등록은 callable 전용이고 목록 조회만 허용한다", async () => {
    await assertFails(
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
        type: "impression",
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

// ---------------------------------------------------------------------------
// 7. 채팅 — 참가자 제한과 senderId 위조
//
// participantIds 모델: chat_service.dart:447 이 [me, partner]..sort() 로 만든다.
// 목록 조회는 where('participantIds' arrayContains uid) 를 쓴다.
// ---------------------------------------------------------------------------
describe("chat_rooms / messages", () => {
  const ROOM = "room-victim-and-third";
  const THIRD = "third-party-3333";

  beforeEach(async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      const db = ctx.firestore();
      await setDoc(doc(db, "chat_rooms", ROOM), {
        participantIds: [THIRD, VICTIM].sort(),
        roomType: "direct",
      });
      await setDoc(doc(db, "chat_rooms", ROOM, "messages", "m1"), {
        senderId: VICTIM,
        text: "비공개 대화 내용",
      });
    });
  });

  it("익명 사용자는 채팅방을 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(anon(), "chat_rooms", ROOM)));
  });

  it("비참가자는 채팅방을 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "chat_rooms", ROOM)));
  });

  it("참가자는 채팅방을 읽을 수 있다", async () => {
    await assertSucceeds(getDoc(doc(as(VICTIM), "chat_rooms", ROOM)));
  });

  it("익명 사용자는 메시지를 읽을 수 없다", async () => {
    await assertFails(
      getDocs(collection(anon(), "chat_rooms", ROOM, "messages"))
    );
  });

  it("비참가자는 메시지를 읽을 수 없다", async () => {
    await assertFails(
      getDocs(collection(as(ATTACKER), "chat_rooms", ROOM, "messages"))
    );
  });

  it("참가자는 메시지를 읽을 수 있다", async () => {
    await assertSucceeds(
      getDocs(collection(as(VICTIM), "chat_rooms", ROOM, "messages"))
    );
  });

  it("비참가자는 메시지를 넣을 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "chat_rooms", ROOM, "messages", "inject"), {
        senderId: ATTACKER,
        text: "끼어들기",
      })
    );
  });

  it("참가자는 자기 이름으로 메시지를 보낼 수 있다", async () => {
    await assertSucceeds(
      setDoc(doc(as(VICTIM), "chat_rooms", ROOM, "messages", "own"), {
        senderId: VICTIM,
        text: "안녕",
      })
    );
  });

  it("참가자도 다른 참가자 이름으로는 보낼 수 없다 (senderId 위조)", async () => {
    await assertFails(
      setDoc(doc(as(VICTIM), "chat_rooms", ROOM, "messages", "forged"), {
        senderId: THIRD,
        text: "사칭",
      })
    );
  });

  it("participantIds 를 추가해 방에 들어갈 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "chat_rooms", ROOM), {
        participantIds: [THIRD, VICTIM, ATTACKER].sort(),
      })
    );
  });

  it("참가자도 participantIds 를 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(VICTIM), "chat_rooms", ROOM), {
        participantIds: [VICTIM],
      })
    );
  });

  it("자신이 참가자가 아닌 방은 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "chat_rooms", "new-room"), {
        participantIds: [VICTIM, THIRD].sort(),
        roomType: "direct",
      })
    );
  });

  it("자신이 참가자인 방은 만들 수 있다", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "chat_rooms", "new-room-2"), {
        participantIds: [ATTACKER, VICTIM].sort(),
        roomType: "direct",
      })
    );
  });

  it("방 삭제는 누구에게도 허용하지 않는다", async () => {
    await assertFails(deleteDoc(doc(as(VICTIM), "chat_rooms", ROOM)));
  });

  it("메시지 삭제는 누구에게도 허용하지 않는다", async () => {
    await assertFails(
      deleteDoc(doc(as(VICTIM), "chat_rooms", ROOM, "messages", "m1"))
    );
  });
});

// ---------------------------------------------------------------------------
// 8. 신고와 문의
// ---------------------------------------------------------------------------
describe("reports / app_inquiries", () => {
  beforeEach(async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      const db = ctx.firestore();
      await setDoc(doc(db, "reports", "r1"), {
        reporterId: VICTIM,
        reportedId: ATTACKER,
        reason: "부적절한 메시지",
        status: "pending",
      });
      await setDoc(doc(db, "app_inquiries", "q1"), {
        inquirerId: VICTIM,
        category: "기타",
        content: "문의 내용",
        allowContact: true,
        sourceScreen: "my_page",
        platform: "android",
        status: "pending",
      });
    });
  });

  it("피신고자는 자기 신고를 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "reports", "r1")));
  });

  it("피신고자는 자기 신고를 지울 수 없다", async () => {
    await assertFails(deleteDoc(doc(as(ATTACKER), "reports", "r1")));
  });

  it("피신고자는 신고 상태를 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "reports", "r1"), { status: "dismissed" })
    );
  });

  it("신고자도 신고 문서를 읽을 수 없다 (moderation 상태 비공개)", async () => {
    await assertFails(getDoc(doc(as(VICTIM), "reports", "r1")));
  });

  it("신고 목록 조회를 거부한다", async () => {
    await assertFails(getDocs(collection(as(ATTACKER), "reports")));
  });

  it("신고 생성은 reportAndBlockUser callable 전용이다", async () => {
    await assertFails(
      setDoc(doc(as(VICTIM), "reports", "r-new"), {
        reporterId: VICTIM,
        reportedId: ATTACKER,
        reason: "스팸",
        status: "pending",
      })
    );
  });

  it("reporterId 를 위조한 신고는 거부한다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "reports", "r-forged"), {
        reporterId: VICTIM,
        reportedId: "some-other-user",
        reason: "위조",
        status: "pending",
      })
    );
  });

  it("남의 문의는 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "app_inquiries", "q1")));
  });

  it("본인 문의도 운영 정보 보호를 위해 직접 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(VICTIM), "app_inquiries", "q1")));
  });

  it("문의 상태는 클라이언트가 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(VICTIM), "app_inquiries", "q1"), { status: "resolved" })
    );
  });
});

// ---------------------------------------------------------------------------
// 9. 무물 / interactions / 커뮤니티 actor 위조
// ---------------------------------------------------------------------------
describe("asks / interactions / bamboo_posts", () => {
  beforeEach(async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      const db = ctx.firestore();
      await setDoc(doc(db, "asks", "a1"), {
        fromUserId: VICTIM,
        toUserId: "someone-else",
        text: "비공개 질문",
        status: "sent",
      });
      await setDoc(doc(db, "interactions", "i1"), {
        fromUserId: VICTIM,
        toUserId: "someone-else",
        action: "like",
        source: "profile",
      });
      await setDoc(doc(db, "bamboo_posts", "p1"), {
        postId: "p1",
        authorId: VICTIM,
        content: "게시글",
        category: "잡담",
        tags: [],
        likeCount: 5,
        commentCount: 2,
        score7d: 10,
        isDeleted: false,
      });
    });
  });

  it("제3자는 무물을 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "asks", "a1")));
  });

  it("fromUserId 를 위조한 무물은 거부한다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "asks", "a-forged"), {
        fromUserId: VICTIM,
        toUserId: "someone-else",
        text: "사칭 질문",
        status: "sent",
      })
    );
  });

  it("본인 이름의 무물은 허용한다", async () => {
    await assertSucceeds(
      setDoc(doc(as(ATTACKER), "asks", "a-own"), {
        fromUserId: ATTACKER,
        toUserId: VICTIM,
        text: "질문",
        status: "sent",
      })
    );
  });

  it("제3자는 interactions 를 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "interactions", "i1")));
  });

  it("fromUserId 를 위조한 interaction 은 거부한다 (가짜 매치 차단)", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "interactions", "i-forged"), {
        fromUserId: VICTIM,
        toUserId: ATTACKER,
        action: "like",
        source: "profile",
        createdAt: serverTimestamp(),
      })
    );
  });

  it("익명 사용자는 커뮤니티 글을 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(anon(), "bamboo_posts", "p1")));
  });

  it("authorId 를 위조한 글은 거부한다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "bamboo_posts", "p-forged"), {
        postId: "p-forged",
        authorId: VICTIM,
        content: "사칭 글",
        category: "잡담",
        tags: [],
        likeCount: 0,
        commentCount: 0,
        score7d: 0,
        isDeleted: false,
      })
    );
  });

  it("likeCount 를 임의 값으로 조작할 수 없다 (인기 순위 조작)", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "bamboo_posts", "p1"), { likeCount: 99999 })
    );
  });

  it("score7d 는 클라이언트가 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "bamboo_posts", "p1"), { score7d: 99999 })
    );
  });

  it("likeCount 를 1 증가시키는 것은 허용한다 (좋아요 정상 흐름)", async () => {
    await assertSucceeds(
      updateDoc(doc(as(ATTACKER), "bamboo_posts", "p1"), { likeCount: 6 })
    );
  });

  it("작성자가 아니면 글을 soft delete 할 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "bamboo_posts", "p1"), { isDeleted: true })
    );
  });

  it("남의 좋아요를 취소할 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(
        doc(ctx.firestore(), "bamboo_posts", "p1", "likes", VICTIM),
        { userId: VICTIM }
      );
    });
    await assertFails(
      deleteDoc(doc(as(ATTACKER), "bamboo_posts", "p1", "likes", VICTIM))
    );
  });
});

// ---------------------------------------------------------------------------
// 10. matches
// ---------------------------------------------------------------------------
describe("matches", () => {
  beforeEach(async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), "matches", "m1"), {
        userIds: [VICTIM, "someone-else"],
        matchType: "ai",
        status: "active",
      });
    });
  });

  it("제3자는 매치를 읽을 수 없다", async () => {
    await assertFails(getDoc(doc(as(ATTACKER), "matches", "m1")));
  });

  it("당사자는 매치를 읽을 수 있다", async () => {
    await assertSucceeds(getDoc(doc(as(VICTIM), "matches", "m1")));
  });

  it("제3자는 매치 상태를 바꿀 수 없다", async () => {
    await assertFails(
      updateDoc(doc(as(ATTACKER), "matches", "m1"), { status: "unmatched" })
    );
  });

  it("자신이 포함되지 않은 매치는 만들 수 없다", async () => {
    await assertFails(
      setDoc(doc(as(ATTACKER), "matches", "m-forged"), {
        userIds: [VICTIM, "someone-else"],
        matchType: "ai",
        status: "active",
      })
    );
  });
});
