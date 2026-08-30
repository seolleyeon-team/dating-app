/**
 * 앱 호환성 정책 문서의 접근 규칙.
 *
 * 이 문서는 앱이 켜지자마자, 로그인 전에 읽어야 한다. 그래서 공개 읽기다.
 * 담기는 값은 최소 지원 빌드 번호와 스토어 주소뿐이며 전부 공개 정보다.
 *
 * 반대로 클라이언트가 이 문서를 쓸 수 있으면 아무나 자기 앱의 게이트를 풀거나
 * 남의 앱을 잠글 수 있다. 쓰기는 서버(Admin SDK) 전용이다.
 *
 * 목록 조회를 막는 이유는 기존 운영 설정 문서들과 같다 — 문서 하나를 지목해
 * 읽는 것과 컬렉션을 훑는 것은 다른 권한이다.
 */
import test from "node:test";

import {
  anon,
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { collection, doc, getDoc, getDocs, setDoc } from "firebase/firestore";

const COLLECTION = "appCompatibilityConfig";

const POLICY = {
  policyVersion: 1,
  messageVersion: 1,
  android: {
    minimumSupportedBuild: 14,
    recommendedBuild: 20,
    storeUrl: "https://play.google.com/store/apps/details?id=com.seolleyeon.app",
  },
  ios: { minimumSupportedBuild: 14, recommendedBuild: 20, storeUrl: "" },
  requiredCapabilities: ["bambooPrivateOwnershipV1"],
};

async function seedPolicy() {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, COLLECTION, "production"), POLICY);
    await setDoc(doc(db, COLLECTION, "staging"), POLICY);
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("로그인 전에도 정책을 읽을 수 있다", async () => {
  // 앱을 켜자마자 판정해야 하는데 그 시점에는 세션이 없다.
  await seedPolicy();
  const client = await anon();
  await assertSucceeds(getDoc(doc(client, COLLECTION, "production")));
});

test("로그인한 사용자도 읽을 수 있다", async () => {
  await seedPolicy();
  const client = await kakaoSession("kakao_alice");
  await assertSucceeds(getDoc(doc(client, COLLECTION, "production")));
});

test("staging 정책도 같은 방식으로 읽힌다", async () => {
  // 두 flavor 가 같은 프로젝트를 쓰므로 문서로 갈라둔다.
  await seedPolicy();
  const client = await anon();
  await assertSucceeds(getDoc(doc(client, COLLECTION, "staging")));
});

test("컬렉션 전체 조회는 막는다", async () => {
  await seedPolicy();
  const client = await kakaoSession("kakao_alice");
  await assertFails(getDocs(collection(client, COLLECTION)));
});

test("클라이언트는 정책을 만들 수 없다", async () => {
  // 쓸 수 있으면 아무나 자기 게이트를 풀 수 있다.
  await withClearedDb();
  const client = await kakaoSession("kakao_alice");
  await assertFails(
    setDoc(doc(client, COLLECTION, "production"), {
      android: { minimumSupportedBuild: 0 },
    })
  );
});

test("클라이언트는 정책을 고칠 수 없다", async () => {
  await seedPolicy();
  const client = await kakaoSession("kakao_alice");
  await assertFails(
    setDoc(
      doc(client, COLLECTION, "production"),
      { android: { minimumSupportedBuild: 0 } },
      { merge: true }
    )
  );
});

test("남의 앱을 잠그는 방향으로도 쓸 수 없다", async () => {
  await seedPolicy();
  const client = await kakaoSession("kakao_alice");
  await assertFails(
    setDoc(
      doc(client, COLLECTION, "production"),
      { android: { minimumSupportedBuild: 999999 } },
      { merge: true }
    )
  );
});

test("로그인하지 않은 클라이언트도 쓸 수 없다", async () => {
  await seedPolicy();
  const client = await anon();
  await assertFails(
    setDoc(doc(client, COLLECTION, "production"), { policyVersion: 2 })
  );
});
