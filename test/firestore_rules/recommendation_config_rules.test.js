/**
 * 생활권 hard filter 의 rollout activation 문서 — Firestore 보안 규칙
 *
 * `recommendationConfig/current` 는 서버(Admin SDK)만 쓴다. 클라이언트는
 * 안내를 "차단"으로 보여줄지 "준비 안내"로 보여줄지 정하려고 읽기만 한다.
 * 일반 사용자가 이 문서를 바꿔 정책을 켜거나 끌 수 있으면 안 된다.
 *
 * 실행:
 *   cd test/firestore_rules && npm install && npm test
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
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
} = require("firebase/firestore");

const USER = "user-kakao-2222";

let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-recommendation-config",
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
  // 서버만 쓸 수 있는 문서이므로 준비도 규칙 우회로 한다.
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    await setDoc(doc(ctx.firestore(), "recommendationConfig/current"), {
      campusLifeZoneEnforced: false,
    });
  });
});

describe("recommendationConfig/current (생활권 rollout activation)", () => {
  it("로그인 사용자는 현재 상태를 읽을 수 있다", async () => {
    const db = testEnv.authenticatedContext(USER).firestore();
    const snap = await assertSucceeds(
      getDoc(doc(db, "recommendationConfig/current"))
    );
    assertEqualsFalse(snap.data().campusLifeZoneEnforced);
  });

  it("비로그인 사용자는 읽을 수 없다", async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(getDoc(doc(db, "recommendationConfig/current")));
  });

  it("클라이언트는 activation 을 켤 수 없다", async () => {
    const db = testEnv.authenticatedContext(USER).firestore();
    await assertFails(
      updateDoc(doc(db, "recommendationConfig/current"), {
        campusLifeZoneEnforced: true,
      })
    );
  });

  it("클라이언트는 activation 을 끌 수도, 덮어쓸 수도 없다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), "recommendationConfig/current"), {
        campusLifeZoneEnforced: true,
      });
    });
    const db = testEnv.authenticatedContext(USER).firestore();
    await assertFails(
      updateDoc(doc(db, "recommendationConfig/current"), {
        campusLifeZoneEnforced: false,
      })
    );
    await assertFails(
      setDoc(doc(db, "recommendationConfig/current"), {
        campusLifeZoneEnforced: false,
      })
    );
    await assertFails(deleteDoc(doc(db, "recommendationConfig/current")));
  });

  it("다른 config 문서를 새로 만들어 정책을 우회할 수 없다", async () => {
    const db = testEnv.authenticatedContext(USER).firestore();
    await assertFails(
      setDoc(doc(db, "recommendationConfig/injected"), {
        campusLifeZoneEnforced: false,
      })
    );
  });

  it("컬렉션 전체를 훑을 수는 없다", async () => {
    const db = testEnv.authenticatedContext(USER).firestore();
    await assertFails(getDocs(collection(db, "recommendationConfig")));
  });
});

function assertEqualsFalse(value) {
  const assert = require("node:assert/strict");
  assert.equal(value, false);
}
