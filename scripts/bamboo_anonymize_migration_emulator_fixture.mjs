/**
 * SEC-04 마이그레이션 end-to-end 증명 (Firestore 에뮬레이터 전용).
 *
 * 순수 함수 테스트(`bamboo_anonymize_migration.test.mjs`)가 분류와 게이트를
 * 덮는다면, 여기서는 실제 Firestore 를 상대로 다음을 확인한다.
 *
 * - dry-run 은 정말 아무것도 쓰지 않는다
 * - 레거시 문서에 매핑이 생기고 public authorId 는 그대로다
 * - 이미 이관된 문서는 다시 만들지 않는다 (재실행 안전)
 * - 소유자가 어긋나는 매핑은 덮어쓰지 않고 conflict 로 보고한다
 * - authorId 가 깨진 문서는 소유자를 추측하지 않는다
 * - 배치 경계를 넘겨도 빠뜨리지 않는다
 * - 대나무숲이 아닌 comments 하위 컬렉션은 건드리지 않는다
 * - 로그에 uid 가 새지 않는다
 *
 * 실행:
 *   firebase emulators:exec --only firestore \
 *     --project seolleyeon-bamboo-migration-test \
 *     "node scripts/bamboo_anonymize_migration_emulator_fixture.mjs"
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const script = resolve(here, "bamboo_anonymize_migration.mjs");

const PROJECT = "seolleyeon-bamboo-migration-test";
const OWNER = "kakao_owner";
const OTHER = "kakao_other";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  console.error(
    "FIRESTORE_EMULATOR_HOST is not set; run this under emulators:exec"
  );
  process.exit(1);
}

const require = createRequire(import.meta.url);
const admin = require("../functions/node_modules/firebase-admin");
admin.initializeApp({ projectId: PROJECT });
const db = admin.firestore();

const POST_MAP = "bamboo_post_authors";
const COMMENT_MAP = "bamboo_comment_authors";

/** 배치 경계를 넘기려고 일부러 배치 크기보다 많이 만든다. */
const LEGACY_POST_COUNT = 5;
const BATCH_SIZE = 2;

function postBody(postId, authorId) {
  const body = {
    postId,
    content: "익명으로 남기는 글",
    category: "free",
    tags: [],
    likeCount: 0,
    commentCount: 0,
    score7d: 0,
    isDeleted: false,
  };
  if (authorId !== undefined) body.authorId = authorId;
  return body;
}

function commentBody(commentId, authorId) {
  const body = {
    commentId,
    content: "익명 댓글",
    parentCommentId: null,
    likeCount: 0,
    isDeleted: false,
  };
  if (authorId !== undefined) body.authorId = authorId;
  return body;
}

async function clearAll() {
  for (const name of ["bamboo_posts", POST_MAP, COMMENT_MAP, "chat_rooms"]) {
    const snap = await db.collection(name).get();
    for (const doc of snap.docs) {
      const subs = await doc.ref.listCollections();
      for (const sub of subs) {
        const subSnap = await sub.get();
        await Promise.all(subSnap.docs.map((d) => d.ref.delete()));
      }
      await doc.ref.delete();
    }
  }
}

async function seed() {
  await clearAll();

  // 이관 대상. 배치 크기보다 많다.
  for (let i = 0; i < LEGACY_POST_COUNT; i += 1) {
    await db
      .collection("bamboo_posts")
      .doc(`legacy-${i}`)
      .set(postBody(`legacy-${i}`, OWNER));
    await db
      .collection("bamboo_posts")
      .doc(`legacy-${i}`)
      .collection("comments")
      .doc("c0")
      .set(commentBody("c0", OWNER));
  }

  // 이미 이관됨.
  await db
    .collection("bamboo_posts")
    .doc("migrated-1")
    .set(postBody("migrated-1", OWNER));
  await db
    .collection(POST_MAP)
    .doc("migrated-1")
    .set({ postId: "migrated-1", ownerUid: OWNER });

  // public authorId 가 이미 사라진 Phase C 형태.
  await db
    .collection("bamboo_posts")
    .doc("phasec-1")
    .set(postBody("phasec-1", undefined));
  await db
    .collection(POST_MAP)
    .doc("phasec-1")
    .set({ postId: "phasec-1", ownerUid: OWNER });

  // 매핑이 다른 사람을 가리킨다. 절대 덮어쓰면 안 된다.
  await db
    .collection("bamboo_posts")
    .doc("conflict-1")
    .set(postBody("conflict-1", OWNER));
  await db
    .collection(POST_MAP)
    .doc("conflict-1")
    .set({ postId: "conflict-1", ownerUid: OTHER });

  // authorId 를 읽을 수 없다.
  await db
    .collection("bamboo_posts")
    .doc("malformed-1")
    .set(postBody("malformed-1", undefined));

  // 대나무숲이 아닌 comments 하위 컬렉션. collectionGroup 에 함께 걸린다.
  await db
    .collection("chat_rooms")
    .doc("room-1")
    .collection("comments")
    .doc("c1")
    .set({ commentId: "c1", authorId: OWNER });
}

function run(extraArgs) {
  const args = [script, "--project", PROJECT, ...extraArgs];
  let stdout = "";
  let status = 0;
  try {
    stdout = execFileSync(process.execPath, args, {
      cwd: repoRoot,
      encoding: "utf8",
      env: process.env,
    });
  } catch (error) {
    stdout = error.stdout ?? "";
    status = error.status ?? 1;
  }
  const start = stdout.indexOf("{");
  assert.ok(start >= 0, `no JSON summary in output:\n${stdout}`);
  return { summary: JSON.parse(stdout.slice(start)), status, stdout };
}

async function mappingCount(collection) {
  const snap = await db.collection(collection).get();
  return snap.size;
}

async function main() {
  await seed();

  // 1) dry-run 은 아무것도 쓰지 않는다.
  const dry = run(["--batch-size", String(BATCH_SIZE)]);
  assert.equal(dry.summary.mode, "dry-run");
  assert.equal(dry.summary.emulator, true);
  assert.equal(dry.summary.posts.pending, LEGACY_POST_COUNT);
  assert.equal(dry.summary.posts.created, 0);
  assert.equal(await mappingCount(POST_MAP), 3, "dry-run wrote post mappings");
  assert.equal(await mappingCount(COMMENT_MAP), 0);

  // 2) apply. 배치 크기보다 많은 문서를 빠짐없이 처리해야 한다.
  const applied = run(["--apply", "--batch-size", String(BATCH_SIZE)]);
  assert.equal(applied.summary.mode, "apply");
  assert.equal(applied.summary.posts.scanned, LEGACY_POST_COUNT + 4);
  assert.equal(applied.summary.posts.created, LEGACY_POST_COUNT);
  assert.equal(applied.summary.posts.alreadyMigrated, 2);
  assert.equal(applied.summary.posts.conflict, 1);
  assert.equal(applied.summary.posts.malformed, 1);
  assert.equal(applied.summary.posts.raced, 0);

  // 대나무숲 댓글만 세어야 한다. chat_rooms 하위 comments 는 대상이 아니다.
  assert.equal(applied.summary.comments.scanned, LEGACY_POST_COUNT);
  assert.equal(applied.summary.comments.created, LEGACY_POST_COUNT);

  // conflict 가 있으면 조용히 성공으로 끝내지 않는다.
  assert.equal(applied.status, 2);

  assert.equal(await mappingCount(POST_MAP), 3 + LEGACY_POST_COUNT);
  assert.equal(await mappingCount(COMMENT_MAP), LEGACY_POST_COUNT);

  // 3) 매핑 내용과, public authorId 가 그대로인지 확인한다. Phase A 는
  //    구버전 클라이언트를 깨뜨리지 않아야 한다.
  const mapped = await db.collection(POST_MAP).doc("legacy-0").get();
  assert.equal(mapped.data().ownerUid, OWNER);
  assert.equal(mapped.data().backfilled, true);
  const post = await db.collection("bamboo_posts").doc("legacy-0").get();
  assert.equal(post.data().authorId, OWNER, "public authorId was modified");

  // 4) 충돌 매핑은 그대로여야 한다.
  const conflict = await db.collection(POST_MAP).doc("conflict-1").get();
  assert.equal(conflict.data().ownerUid, OTHER, "conflict mapping overwritten");

  // 5) 소유자를 모르는 문서에는 매핑을 만들지 않았다.
  assert.equal(
    (await db.collection(POST_MAP).doc("malformed-1").get()).exists,
    false
  );

  // 6) 재실행. 새로 만드는 것이 없어야 한다.
  const again = run(["--apply", "--batch-size", String(BATCH_SIZE)]);
  assert.equal(again.summary.posts.created, 0, "second run created mappings");
  assert.equal(again.summary.posts.pending, 0);
  assert.equal(
    again.summary.posts.alreadyMigrated,
    LEGACY_POST_COUNT + 2,
    "second run did not recognise its own writes"
  );
  assert.equal(again.summary.comments.created, 0);
  assert.equal(await mappingCount(POST_MAP), 3 + LEGACY_POST_COUNT);
  assert.equal(await mappingCount(COMMENT_MAP), LEGACY_POST_COUNT);

  // 7) 페이지 경계. 한 페이지에 다 안 들어와도 빠뜨리면 안 된다. 여기서
  //    새면 production 에서 조용히 일부 글만 이관된다.
  for (const name of [POST_MAP, COMMENT_MAP]) {
    const snap = await db.collection(name).get();
    await Promise.all(snap.docs.map((d) => d.ref.delete()));
  }
  const paged = run(["--apply", "--page-size", "2", "--batch-size", "2"]);
  // legacy-* 와 migrated-1, conflict-1 은 authorId 가 남아 있어 다시 만들어
  // 진다. phasec-1 은 public authorId 가 없으므로 매핑을 지우고 나면 소유자를
  // 알 길이 없어 malformed 로 남는다 — 추측해서 만들면 안 된다.
  assert.equal(
    paged.summary.posts.created,
    LEGACY_POST_COUNT + 2,
    "pagination skipped posts"
  );
  assert.equal(paged.summary.posts.malformed, 2);
  assert.equal(
    paged.summary.posts.scanned,
    LEGACY_POST_COUNT + 4,
    "pagination skipped posts during scan"
  );
  assert.equal(
    paged.summary.comments.created,
    LEGACY_POST_COUNT,
    "pagination skipped comments"
  );

  // 8) 로그에 uid 가 새면 안 된다. 이 도구가 없애려는 연결을 로그에
  //    그대로 복사하는 셈이 된다.
  for (const output of [dry.stdout, applied.stdout, again.stdout, paged.stdout]) {
    assert.ok(!output.includes(OWNER), "owner uid leaked into stdout");
    assert.ok(!output.includes(OTHER), "other uid leaked into stdout");
  }

  console.log("bamboo migration emulator fixture: OK");
}

main().then(
  () => process.exit(0),
  (error) => {
    console.error(error);
    process.exit(1);
  }
);
