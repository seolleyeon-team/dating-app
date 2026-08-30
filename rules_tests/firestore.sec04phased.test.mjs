/**
 * SEC-04 Phase D 후보 규칙의 계약. **아직 배포되지 않는다.**
 *
 * 이 스위트는 `firestore.rules` 가 아니라
 * `fixtures/sec04-phase-d.candidate.rules` 를 로드한다. 지금 운영 중인 규칙은
 * 그대로 두고, cutover 승인 전에 "그 규칙으로 바꾸면 실제로 무엇이 막히고
 * 무엇이 통과하는가" 를 미리 증명해 두기 위한 것이다.
 *
 * 여기서 확인하는 핵심은 두 가지다.
 *
 * 1. public 문서에 raw UID 를 다시 넣을 수 없다. 익명 글의 작성자를 join 으로
 *    특정할 수 있었던 원인이 그 필드였고, 되돌아오면 원점이다.
 * 2. 규칙이 클라이언트 버전을 신뢰하지 않는다. buildNumber 를 믿는 순간
 *    아무 클라이언트나 숫자를 적어 넣고 통과한다. 규칙은 쓰기의 모양만 본다 —
 *    비공개 매핑을 같은 커밋에 남길 수 있는 클라이언트만 글을 쓸 수 있고,
 *    그 능력 자체가 capability 증명이다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";

import { doc, getDoc, setDoc, writeBatch } from "firebase/firestore";

const here = dirname(fileURLToPath(import.meta.url));
const candidatePath = resolve(here, "fixtures/sec04-phase-d.candidate.rules");
const candidateRules = readFileSync(candidatePath, "utf8");

const OWNER = "kakao_owner";
const STRANGER = "kakao_stranger";
const POST = "post1";
const COMMENT = "comment1";

const POST_MAP = "bamboo_post_authors";
const COMMENT_MAP = "bamboo_comment_authors";
const commentMapId = (postId, commentId) => `${postId}__${commentId}`;

let env;

async function getEnv() {
  if (!env) {
    env = await initializeTestEnvironment({
      // 운영 규칙 스위트와 섞이지 않도록 별도 프로젝트를 쓴다.
      projectId: "seolleyeon-sec04-phased-candidate",
      firestore: { rules: candidateRules, host: "127.0.0.1", port: 8080 },
    });
  }
  return env;
}

async function session(uid) {
  const e = await getEnv();
  return e.authenticatedContext(uid, { kakaoUserId: uid }).firestore();
}

async function clear() {
  const e = await getEnv();
  await e.clearFirestore();
}

/** Phase C 이후의 글 본문 — authorId 가 없다. */
function postBody(postId) {
  return {
    postId,
    content: "익명으로 남기는 글",
    category: "free",
    tags: [],
    likeCount: 0,
    commentCount: 0,
    score7d: 0,
    isDeleted: false,
  };
}

function commentBody(commentId) {
  return {
    commentId,
    content: "익명 댓글",
    parentCommentId: null,
    likeCount: 0,
    isDeleted: false,
  };
}

test.after(async () => {
  if (env) await env.cleanup();
});

test("Phase D: 매핑을 함께 쓰는 글은 통과한다", async () => {
  await clear();
  const owner = await session(OWNER);
  const batch = writeBatch(owner);
  batch.set(doc(owner, "bamboo_posts", POST), postBody(POST));
  batch.set(doc(owner, POST_MAP, POST), { postId: POST, ownerUid: OWNER });
  await assertSucceeds(batch.commit());
});

test("Phase D: 매핑 없이 글만 쓰면 거부된다", async () => {
  // 구버전 클라이언트가 하는 쓰기다. 통과시키면 주인 없는 글이 남는다.
  await clear();
  const owner = await session(OWNER);
  await assertFails(
    setDoc(doc(owner, "bamboo_posts", POST), postBody(POST))
  );
});

test("Phase D: public authorId 를 넣으면 거부된다", async () => {
  // 이 필드가 돌아오면 authorId → publicProfiles join 이 다시 살아난다.
  await clear();
  const owner = await session(OWNER);
  const batch = writeBatch(owner);
  batch.set(doc(owner, "bamboo_posts", POST), {
    ...postBody(POST),
    authorId: OWNER,
  });
  batch.set(doc(owner, POST_MAP, POST), { postId: POST, ownerUid: OWNER });
  await assertFails(batch.commit());
});

test("Phase D: 남의 이름으로 매핑을 붙일 수 없다", async () => {
  await clear();
  const stranger = await session(STRANGER);
  const batch = writeBatch(stranger);
  batch.set(doc(stranger, "bamboo_posts", POST), postBody(POST));
  batch.set(doc(stranger, POST_MAP, POST), {
    postId: POST,
    ownerUid: OWNER,
  });
  await assertFails(batch.commit());
});

test("Phase D: 이미 있는 남의 글에 뒤늦게 소유권을 붙일 수 없다", async () => {
  // Phase A 는 public authorId 와 대조해서 막았다. 그 필드가 사라진 뒤에는
  // "글이 이 커밋에서 새로 만들어지는 중" 이라는 사실로 막는다.
  await clear();
  const e = await getEnv();
  await e.withSecurityRulesDisabled(async (ctx) => {
    await setDoc(doc(ctx.firestore(), "bamboo_posts", POST), postBody(POST));
    await setDoc(doc(ctx.firestore(), POST_MAP, POST), {
      postId: POST,
      ownerUid: OWNER,
    });
  });
  const stranger = await session(STRANGER);
  await assertFails(
    setDoc(doc(stranger, POST_MAP, "post2"), {
      postId: "post2",
      ownerUid: STRANGER,
    })
  );
});

test("Phase D: 매핑을 함께 쓰는 댓글은 통과한다", async () => {
  await clear();
  const owner = await session(OWNER);
  const create = writeBatch(owner);
  create.set(doc(owner, "bamboo_posts", POST), postBody(POST));
  create.set(doc(owner, POST_MAP, POST), { postId: POST, ownerUid: OWNER });
  await create.commit();

  const batch = writeBatch(owner);
  batch.set(
    doc(owner, "bamboo_posts", POST, "comments", COMMENT),
    commentBody(COMMENT)
  );
  batch.set(doc(owner, COMMENT_MAP, commentMapId(POST, COMMENT)), {
    postId: POST,
    commentId: COMMENT,
    ownerUid: OWNER,
  });
  await assertSucceeds(batch.commit());
});

test("Phase D: 매핑 없이 댓글만 쓰면 거부된다", async () => {
  await clear();
  const e = await getEnv();
  await e.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), "bamboo_posts", POST), postBody(POST))
  );
  const owner = await session(OWNER);
  await assertFails(
    setDoc(
      doc(owner, "bamboo_posts", POST, "comments", COMMENT),
      commentBody(COMMENT)
    )
  );
});

test("Phase D: 댓글에 public authorId 를 넣으면 거부된다", async () => {
  await clear();
  const e = await getEnv();
  await e.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), "bamboo_posts", POST), postBody(POST))
  );
  const owner = await session(OWNER);
  const batch = writeBatch(owner);
  batch.set(doc(owner, "bamboo_posts", POST, "comments", COMMENT), {
    ...commentBody(COMMENT),
    authorId: OWNER,
  });
  batch.set(doc(owner, COMMENT_MAP, commentMapId(POST, COMMENT)), {
    postId: POST,
    commentId: COMMENT,
    ownerUid: OWNER,
  });
  await assertFails(batch.commit());
});

test("Phase D: 타인은 소유권 매핑을 읽을 수 없다", async () => {
  await clear();
  const e = await getEnv();
  await e.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), POST_MAP, POST), {
      postId: POST,
      ownerUid: OWNER,
    })
  );
  const stranger = await session(STRANGER);
  await assertFails(getDoc(doc(stranger, POST_MAP, POST)));
});

test("Phase D 규칙은 클라이언트가 신고한 버전을 신뢰하지 않는다", () => {
  // 규칙이 buildNumber 를 보는 순간, 아무 클라이언트나 그 숫자를 적어 넣고
  // 통과할 수 있다. 보안 근거로 쓸 수 없는 값이다.
  //
  // 설명하는 주석에는 그 단어들이 나온다. 보려는 것은 규칙 자체이므로
  // 주석을 걷어내고 검사한다.
  const logic = candidateRules
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
  for (const forbidden of [
    "buildNumber",
    "appVersion",
    "versionCode",
    "clientVersion",
    "schemaVersion",
    "minimumSupportedBuild",
  ]) {
    assert.ok(
      !logic.includes(forbidden),
      `Phase D rules must not read client-reported ${forbidden}`
    );
  }
});

test("Phase D 후보 규칙은 배포 대상이 아니다", () => {
  // firebase.json 이 배포하는 것은 firestore.rules 뿐이다. 이 파일이 그
  // 자리로 옮겨가는 순간이 곧 cutover 이고, 그건 별도 승인 사항이다.
  const firebaseJson = JSON.parse(
    readFileSync(resolve(here, "../firebase.json"), "utf8")
  );
  assert.equal(firebaseJson.firestore.rules, "firestore.rules");

  const deployed = readFileSync(resolve(here, "../firestore.rules"), "utf8");
  assert.ok(
    deployed.includes("'authorId': authorIdStr") === false,
    "sanity: deployed rules file was read"
  );
  // 운영 규칙은 아직 public authorId 를 요구한다 — Phase A 상태 그대로다.
  assert.ok(
    deployed.includes("request.resource.data.authorId == request.auth.uid"),
    "deployed rules should still be in the Phase A shape"
  );
});
