/**
 * 카카오 로그인 플로우 — Firestore 보안 규칙 테스트
 *
 * kakao_auth_screen.dart `_login()` 이 users/{kakaoUserId} 에 실제로 수행하는
 * 읽기/쓰기를 그대로 재현해서, 현재 규칙이 이 플로우를 허용하는지 확인한다.
 *
 * `permission-denied` 회귀를 잡는 것이 목적이므로, Firebase 세션이 붙은 경우와
 * 붙지 않은 경우(request.auth == null) 둘 다 검증한다. 카카오 로그인은 커스텀
 * 토큰 교환이 실패하면 비인증 상태로 계속 진행되기 때문이다.
 *
 * 실행: cd test/firestore_rules && npm install && npm test
 *   (Firestore emulator 는 JDK 11+ 필요)
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
  deleteField,
  doc,
  getDoc,
  serverTimestamp,
  setDoc,
} = require("firebase/firestore");

const KAKAO_USER_ID = "1234567890";

let testEnv;

before(async () => {
  // 다른 규칙 테스트 파일과 Firestore 상태가 섞이지 않도록 별도 projectId 를 쓴다.
  // (clearFirestore() 가 같은 projectId 의 시드 데이터를 지워버린다)
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-kakao-login-rules",
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
});

/** UserService.upsertKakaoUser 신규 생성 페이로드 */
function shellDoc() {
  return {
    kakaoUserId: KAKAO_USER_ID,
    nickname: "테스터",
    profileImageUrl: "https://example.com/a.jpg",
    email: "tester@example.com",
    createdAt: serverTimestamp(),
    lastLoginAt: serverTimestamp(),
  };
}

/** UserService.setLastActivePlatform 페이로드 */
function lastActivePlatformDoc() {
  return {
    lastActivePlatform: "ios",
    lastActivePlatformUpdatedAt: serverTimestamp(),
  };
}

/** UserService.saveLegalConsents 페이로드 (중첩 deleteField 포함) */
function legalConsentsDoc() {
  return {
    legalConsents: {
      termsOfService: true,
      privacyPolicy: true,
      kakaoNamePhone: true,
      ageOver18: true,
      ageOver14: deleteField(),
      agreedAt: serverTimestamp(),
      version: "1.0.0",
    },
  };
}

async function seedShell() {
  await testEnv.withSecurityRulesDisabled(async (context) => {
    await setDoc(doc(context.firestore(), "users", KAKAO_USER_ID), shellDoc());
  });
}

/** 로그인 플로우 전체를 순서대로 재현한다. */
function loginFlowCases(makeDb) {
  it("1. users/{id} 존재 확인 read", async () => {
    await seedShell();
    await assertSucceeds(getDoc(doc(makeDb(), "users", KAKAO_USER_ID)));
  });

  it("2. 신규 가입 셸 문서 create", async () => {
    await assertSucceeds(
      setDoc(doc(makeDb(), "users", KAKAO_USER_ID), shellDoc())
    );
  });

  it("3. setLastActivePlatform merge update", async () => {
    await seedShell();
    await assertSucceeds(
      setDoc(doc(makeDb(), "users", KAKAO_USER_ID), lastActivePlatformDoc(), {
        merge: true,
      })
    );
  });

  it("4. saveLegalConsents merge update", async () => {
    await seedShell();
    await assertSucceeds(
      setDoc(doc(makeDb(), "users", KAKAO_USER_ID), legalConsentsDoc(), {
        merge: true,
      })
    );
  });

  it("5. 신규 가입 전체 순서 (create → platform → consents)", async () => {
    const ref = () => doc(makeDb(), "users", KAKAO_USER_ID);
    await assertSucceeds(setDoc(ref(), shellDoc()));
    await assertSucceeds(
      setDoc(ref(), lastActivePlatformDoc(), { merge: true })
    );
    await assertSucceeds(setDoc(ref(), legalConsentsDoc(), { merge: true }));
  });
}

describe("카카오 로그인 — Firebase 세션 없음 (request.auth == null)", () => {
  loginFlowCases(() => testEnv.unauthenticatedContext().firestore());
});

describe("카카오 로그인 — 커스텀 토큰 세션 있음 (uid == kakaoUserId)", () => {
  loginFlowCases(() =>
    testEnv
      .authenticatedContext(KAKAO_USER_ID, { kakaoUserId: KAKAO_USER_ID })
      .firestore()
  );
});

describe("규칙이 여전히 막아야 하는 것", () => {
  it("허용 목록에 없는 필드가 섞인 create 는 거부된다", async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      setDoc(doc(db, "users", KAKAO_USER_ID), {
        ...shellDoc(),
        isAdmin: true,
      })
    );
  });

  it("문서 ID 와 다른 kakaoUserId 로는 create 할 수 없다", async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      setDoc(doc(db, "users", KAKAO_USER_ID), {
        ...shellDoc(),
        kakaoUserId: "9999999999",
      })
    );
  });

  it("허용 목록 밖 필드는 기존 값 변경으로도 쓸 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (c) => {
      await setDoc(doc(c.firestore(), "users", KAKAO_USER_ID), {
        ...shellDoc(),
        isAdmin: false,
      });
    });
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      setDoc(doc(db, "users", KAKAO_USER_ID), { isAdmin: true }, { merge: true })
    );
  });
});

/**
 * 회귀 방지: `changedKeys()` 는 "양쪽에 존재하고 값이 바뀐 키"만 반환하므로
 * 새로 추가되는 필드가 허용 목록 검사를 통째로 우회했다. (빈 집합의 hasOnly 는
 * 항상 true) 반드시 `affectedKeys()`(added ∪ removed ∪ changed) 여야 한다.
 */
describe("허용 목록 우회 방지 — 새 필드 주입 (affectedKeys 회귀 테스트)", () => {
  it("users: 비인증 클라이언트가 새 필드를 심을 수 없다", async () => {
    await seedShell();
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      setDoc(doc(db, "users", KAKAO_USER_ID), { isAdmin: true }, { merge: true })
    );
  });

  it("users: 허용 목록 밖 필드는 필드 삭제로도 건드릴 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (c) => {
      await setDoc(doc(c.firestore(), "users", KAKAO_USER_ID), {
        ...shellDoc(),
        internalFlag: "keep",
      });
    });
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      setDoc(
        doc(db, "users", KAKAO_USER_ID),
        { internalFlag: deleteField() },
        { merge: true }
      )
    );
  });

  it("notifications: 새 필드를 심을 수 없다", async () => {
    const ref = ["users", KAKAO_USER_ID, "notifications", "n1"];
    await testEnv.withSecurityRulesDisabled(async (c) => {
      await setDoc(doc(c.firestore(), ...ref), {
        type: "like",
        title: "t",
        body: "b",
        isRead: false,
      });
    });
    const db = testEnv.unauthenticatedContext().firestore();
    await assertSucceeds(
      setDoc(doc(db, ...ref), { isRead: true }, { merge: true })
    );
    await assertFails(
      setDoc(doc(db, ...ref), { injected: true }, { merge: true })
    );
  });

  it("asks: 새 필드를 심을 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (c) => {
      await setDoc(doc(c.firestore(), "asks", "a1"), {
        fromUserId: "u1",
        toUserId: "u2",
        text: "hi",
        status: "sent",
      });
    });
    const db = testEnv.unauthenticatedContext().firestore();
    await assertSucceeds(
      setDoc(doc(db, "asks", "a1"), { status: "read" }, { merge: true })
    );
    await assertFails(
      setDoc(doc(db, "asks", "a1"), { injected: true }, { merge: true })
    );
  });

  it("matches: 새 필드를 심을 수 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (c) => {
      await setDoc(doc(c.firestore(), "matches", "m1"), {
        userIds: ["u1", "u2"],
        matchType: "mutual",
        status: "active",
      });
    });
    const db = testEnv.unauthenticatedContext().firestore();
    await assertSucceeds(
      setDoc(doc(db, "matches", "m1"), { status: "unmatched" }, { merge: true })
    );
    await assertFails(
      setDoc(doc(db, "matches", "m1"), { injected: true }, { merge: true })
    );
  });
});
