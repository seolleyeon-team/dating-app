/**
 * Storage 보안 규칙 공격 테스트
 *
 * 이전 storage.rules 는 중첩된 `service firebase.storage` 블록과 닫히지 않은
 * brace 3개 때문에 문법적으로 배포가 불가능했고, 내용상으로도
 * users/{userId}/onboarding/photos/** 에 대해 익명 read/create/update/delete 를
 * 모두 허용했다. 아래 첫 번째 테스트는 규칙 파일이 load 되는지부터 확인한다.
 *
 * 실행 (Firestore 와 Storage emulator 를 함께 띄운다):
 *   cd test/firestore_rules
 *   npx firebase emulators:exec --only firestore,storage \
 *     --project seolleyeon-storage-rules "node --test storage_rules.test.js"
 *
 * ⚠ 사전 조건: emulator 는 JDK 21+ 를 요구한다. 감사 시점 이 머신에는 JDK 1.8
 *   만 있어서 이 파일은 아직 실행되지 않았다 (B-JDK21).
 *
 * 실제 앱이 쓰는 Storage 경로는 두 개뿐이다 (git grep 으로 확인).
 *   - ai_profiles/{male|female}/{id}.png   (읽기 전용 더미 프로필)
 *   - users/{kakaoUserId}/onboarding/photos/{fileName}
 * 채팅 첨부와 아바타 파이프라인 경로는 저장소에 존재하지 않으므로 "기본 deny"
 * 테스트로만 덮는다.
 */

const { readFileSync } = require("node:fs");
const path = require("node:path");
const { after, before, describe, it } = require("node:test");
const assert = require("node:assert");

const {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} = require("@firebase/rules-unit-testing");
const {
  ref,
  uploadBytes,
  getBytes,
  deleteObject,
} = require("firebase/storage");

const OWNER = "owner-kakao-1111";
const OTHER = "other-kakao-9999";

// 최소 유효 PNG (1x1). 확장자가 아니라 바이트를 쓴다.
const PNG_1X1 = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d,
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4, 0x89, 0x00, 0x00, 0x00,
  0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
]);

const SVG_BYTES = new TextEncoder().encode(
  '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
);

const rulesSource = readFileSync(
  path.resolve(__dirname, "../../storage.rules"),
  "utf8"
);

let testEnv;

before(async () => {
  // 규칙이 유효하지 않으면 initializeTestEnvironment 가 여기서 실패한다.
  // 이것이 곧 "문법 load" 테스트다.
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-storage-rules",
    storage: { rules: rulesSource },
  });
});

after(async () => {
  if (testEnv) await testEnv.cleanup();
});

const anon = () => testEnv.unauthenticatedContext().storage();
const as = (uid) => testEnv.authenticatedContext(uid).storage();

const photoPath = (uid, name) => `users/${uid}/onboarding/photos/${name}`;

async function seedOwnerPhoto() {
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    await uploadBytes(
      ref(ctx.storage(), photoPath(OWNER, "seed.png")),
      PNG_1X1,
      { contentType: "image/png" }
    );
  });
}

// 주석을 제거한 실제 규칙 본문. 이 파일의 주석에는 옛 파일의 문제를 설명하려고
// `service firebase.storage` 라는 문구가 들어 있어서, 주석을 지우지 않고 세면
// 중첩 service 가 있는 것처럼 잘못 판정된다.
const rulesBody = rulesSource
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/[^\n]*/g, "");

describe("규칙 파일 자체", () => {
  it("단일 service 블록이고 중첩 service 가 없다", () => {
    const serviceCount = (
      rulesBody.match(/service\s+firebase\.storage/g) ?? []
    ).length;
    assert.strictEqual(serviceCount, 1);
  });

  it("brace 가 균형을 이룬다", () => {
    const open = (rulesBody.match(/\{/g) ?? []).length;
    const close = (rulesBody.match(/\}/g) ?? []).length;
    assert.strictEqual(open, close);
  });

  it("emulator 가 규칙을 load 했다 (문법 유효)", () => {
    assert.ok(testEnv);
  });
});

describe("원본 프로필 사진", () => {
  it("익명 사용자는 읽을 수 없다", async () => {
    await seedOwnerPhoto();
    await assertFails(getBytes(ref(anon(), photoPath(OWNER, "seed.png"))));
  });

  it("익명 사용자는 업로드할 수 없다", async () => {
    await assertFails(
      uploadBytes(ref(anon(), photoPath(OWNER, "anon.png")), PNG_1X1, {
        contentType: "image/png",
      })
    );
  });

  it("익명 사용자는 삭제할 수 없다", async () => {
    await seedOwnerPhoto();
    await assertFails(deleteObject(ref(anon(), photoPath(OWNER, "seed.png"))));
  });

  it("타인 UID 경로에 업로드할 수 없다", async () => {
    await assertFails(
      uploadBytes(ref(as(OTHER), photoPath(OWNER, "hijack.png")), PNG_1X1, {
        contentType: "image/png",
      })
    );
  });

  it("타인 사진을 삭제할 수 없다", async () => {
    await seedOwnerPhoto();
    await assertFails(
      deleteObject(ref(as(OTHER), photoPath(OWNER, "seed.png")))
    );
  });

  it("본인 경로 업로드는 허용한다", async () => {
    await assertSucceeds(
      uploadBytes(ref(as(OWNER), photoPath(OWNER, "own.png")), PNG_1X1, {
        contentType: "image/png",
      })
    );
  });

  it("본인 사진 삭제는 허용한다", async () => {
    await seedOwnerPhoto();
    await assertSucceeds(
      deleteObject(ref(as(OWNER), photoPath(OWNER, "seed.png")))
    );
  });

  // 프로필 탐색·추천 카드가 다른 사용자 사진을 보여줘야 하므로 인증된
  // 사용자의 read 는 의도적으로 허용한다. 단계적 얼굴 공개가 클라이언트
  // 전용이라는 점은 R-STORAGE-2 로 남겼다.
  it("인증 사용자는 다른 사용자 사진을 읽을 수 있다 (의도된 동작)", async () => {
    await seedOwnerPhoto();
    await assertSucceeds(
      getBytes(ref(as(OTHER), photoPath(OWNER, "seed.png")))
    );
  });
});

describe("업로드 내용 검증", () => {
  it("SVG 는 거부한다 (스크립트 실행 가능)", async () => {
    await assertFails(
      uploadBytes(ref(as(OWNER), photoPath(OWNER, "x.svg")), SVG_BYTES, {
        contentType: "image/svg+xml",
      })
    );
  });

  it("이미지가 아닌 contentType 은 거부한다", async () => {
    await assertFails(
      uploadBytes(ref(as(OWNER), photoPath(OWNER, "x.html")), SVG_BYTES, {
        contentType: "text/html",
      })
    );
  });

  it("contentType 이 없으면 거부한다", async () => {
    await assertFails(
      uploadBytes(ref(as(OWNER), photoPath(OWNER, "x.bin")), PNG_1X1)
    );
  });

  it("크기 제한을 넘으면 거부한다", async () => {
    const tooBig = new Uint8Array(13 * 1024 * 1024);
    tooBig.set(PNG_1X1, 0);
    await assertFails(
      uploadBytes(ref(as(OWNER), photoPath(OWNER, "big.png")), tooBig, {
        contentType: "image/png",
      })
    );
  });

  it("빈 파일은 거부한다", async () => {
    await assertFails(
      uploadBytes(
        ref(as(OWNER), photoPath(OWNER, "empty.png")),
        new Uint8Array(0),
        { contentType: "image/png" }
      )
    );
  });
});

describe("ai_profiles 더미 프로필", () => {
  it("익명 사용자는 읽을 수 없다 (이전에는 공개였다)", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await uploadBytes(
        ref(ctx.storage(), "ai_profiles/female/1.png"),
        PNG_1X1,
        { contentType: "image/png" }
      );
    });
    await assertFails(getBytes(ref(anon(), "ai_profiles/female/1.png")));
  });

  it("인증 사용자는 읽을 수 있다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await uploadBytes(
        ref(ctx.storage(), "ai_profiles/male/2.png"),
        PNG_1X1,
        { contentType: "image/png" }
      );
    });
    await assertSucceeds(getBytes(ref(as(OWNER), "ai_profiles/male/2.png")));
  });

  it("클라이언트 쓰기는 거부한다", async () => {
    await assertFails(
      uploadBytes(ref(as(OWNER), "ai_profiles/male/3.png"), PNG_1X1, {
        contentType: "image/png",
      })
    );
  });
});

describe("기본 deny", () => {
  it("정의되지 않은 최상위 경로 쓰기를 거부한다", async () => {
    await assertFails(
      uploadBytes(ref(as(OWNER), "random/whatever.png"), PNG_1X1, {
        contentType: "image/png",
      })
    );
  });

  it("정의되지 않은 최상위 경로 읽기를 거부한다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await uploadBytes(ref(ctx.storage(), "random/seed.png"), PNG_1X1, {
        contentType: "image/png",
      });
    });
    await assertFails(getBytes(ref(as(OWNER), "random/seed.png")));
  });

  it("채팅 첨부 경로는 아직 정의되지 않았으므로 거부한다", async () => {
    // 앱에 채팅 첨부 업로드 경로가 없다. 기능이 추가될 때
    // 기본값이 "공개"가 되지 않도록 여기서 고정해 둔다.
    await assertFails(
      uploadBytes(
        ref(as(OWNER), "chat_rooms/room1/attachments/a.png"),
        PNG_1X1,
        { contentType: "image/png" }
      )
    );
  });

  it("users 하위의 다른 경로는 소유자만 읽는다", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await uploadBytes(
        ref(ctx.storage(), `users/${OWNER}/private/note.png`),
        PNG_1X1,
        { contentType: "image/png" }
      );
    });
    await assertFails(
      getBytes(ref(as(OTHER), `users/${OWNER}/private/note.png`))
    );
    await assertSucceeds(
      getBytes(ref(as(OWNER), `users/${OWNER}/private/note.png`))
    );
  });
});
