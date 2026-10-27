/**
 * P0-3 — 대나무숲 public 문서의 작성자 식별 정보 제거 (최종 마이그레이션).
 *
 * 이전 Phase A 스크립트(bamboo_anonymize_migration.mjs)는 비공개 매핑만 만들고
 * public authorId 는 그대로 뒀다. 그것만으로는 익명성이 생기지 않는다. 이 스크립트는
 * 레코드마다 다음을 한 트랜잭션으로 한다:
 *
 *   1. 비공개 매핑을 확인한다 (없으면 public authorId 가 실존 계정일 때만 만든다).
 *   2. 매핑과 public authorId 가 같은 사람을 가리킬 때만
 *   3. public 문서에서 작성자 식별 필드를 FieldValue.delete() 로 지운다.
 *
 * 매핑이 다른 사람을 가리키거나(conflict), 깨졌거나(malformed), public authorId 가
 * 존재하지 않는 계정이면(unverifiable) 그 레코드는 건드리지 않고 보고한다.
 * 닉네임·프로필·이메일로 소유자를 추측하지 않는다.
 *
 * 대나무숲 인앱 알림(community_comment / community_reply / community_post_like)의
 * actorId / actorName 도 지운다 (actorId=null, actorName="익명").
 *
 * 좋아요 문서는 바꾸지 않는다 — 문서 id 가 누른 사람의 uid 라서, 보호는 규칙
 * (본인만 get, list 금지)이 맡는다. 여기서는 개수만 보고한다.
 *
 * 안전장치
 * - 기본은 dry-run. `--apply` 없이는 아무것도 쓰지 않는다.
 * - `--project` 필수, allowlist 밖은 거부. production 쓰기는 `--allow-production` 필수.
 * - 레코드마다 트랜잭션 안에서 다시 읽고 다시 분류한다. 계획과 다르면(raced) 쓰지 않는다.
 * - 멱등: 이미 지워진 문서는 alreadyRedacted 로 세고 쓰지 않는다.
 * - `--checkpoint <file>`: 처리한 마지막 글 id 를 저장하고 이어서 돈다 (UID 없음).
 * - `--limit <n>`: 이번 실행에서 고칠 public 레코드 수 상한 (canary).
 * - 로그는 집계만. UID 는 어디에도 찍지 않는다. `--anomaly-ids-out` 은 문서 경로만 쓴다.
 * - `--verify`: 쓰기 없이 독립 검증. 위반이 하나라도 있으면 exit 3.
 *
 * 에뮬레이터:
 *   firebase emulators:exec --only firestore --project demo-p03-migration \
 *     "node scripts/bamboo_privacy_migration.mjs --project demo-p03-migration --apply"
 */
import { createRequire } from "node:module";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const PRODUCTION_PROJECTS = new Set(["seolleyeon-final"]);
export const ALLOWED_PROJECTS = new Set([
  ...PRODUCTION_PROJECTS,
  "demo-p03-migration",
  "seolleyeon-bamboo-migration-test",
]);

export const ROOTS = [
  {
    posts: "bamboo_posts",
    postOwners: "bamboo_post_authors",
    commentOwners: "bamboo_comment_authors",
    partition: null,
  },
  {
    posts: "playReviewBambooPosts",
    postOwners: "playReviewBambooPostAuthors",
    commentOwners: "playReviewBambooCommentAuthors",
    partition: "play_review",
  },
];

/** functions/src/bambooOwnership.ts 의 BAMBOO_PUBLIC_IDENTITY_FIELDS 와 같은 목록. */
export const PUBLIC_IDENTITY_FIELDS = [
  "authorId", "authorUid", "ownerUid", "userId", "uid", "actorId", "actorName",
  "nickname", "authorName", "authorNickname", "authorProfileUrl", "profileId",
];

export const ANONYMOUS_NOTIFICATION_TYPES = new Set([
  "community_comment",
  "community_reply",
  "community_post_like",
]);
export const ANONYMOUS_ACTOR_NAME = "익명";

const PAGE_SIZE = 200;
const NOTIFICATION_BATCH = 400;

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function identityFieldsPresent(data) {
  return PUBLIC_IDENTITY_FIELDS.filter((field) => data != null && data[field] !== undefined);
}

/**
 * 레코드 하나의 상태와 할 일을 정한다. 순수 함수 — 단위 테스트 대상.
 *
 * @param {object} input
 * @param {Record<string, unknown>} input.publicData  public 글/댓글 문서
 * @param {Record<string, unknown> | null} input.mapping 비공개 매핑 문서 (없으면 null)
 * @param {boolean} input.authorAccountExists public authorId 가 가리키는 users 문서 존재 여부
 * @param {{postId: string, commentId?: string}} input.expected
 * @returns {{status: string, action: "none" | "redact" | "createMappingAndRedact" | "skip", ownerUid?: string}}
 */
export function classifyRecord({ publicData, mapping, authorAccountExists, expected }) {
  const publicAuthor = clean(publicData?.authorId);
  const otherIdentity = identityFieldsPresent(publicData).filter((f) => f !== "authorId");
  const needsRedaction = publicAuthor !== "" || otherIdentity.length > 0;

  if (mapping != null) {
    const owner = clean(mapping.ownerUid);
    const pointsElsewhere =
      (clean(mapping.postId) && clean(mapping.postId) !== expected.postId) ||
      (expected.commentId != null && clean(mapping.commentId) && clean(mapping.commentId) !== expected.commentId);
    if (!owner || pointsElsewhere) return { status: "MALFORMED", action: "skip" };
    if (publicAuthor && publicAuthor !== owner) return { status: "MAPPING_CONFLICT", action: "skip" };
    if (!needsRedaction) return { status: "PUBLIC_AUTHOR_ABSENT", action: "none", ownerUid: owner };
    return { status: "MAPPING_VERIFIED", action: "redact", ownerUid: owner };
  }

  if (!publicAuthor) {
    // 소유자를 알 근거가 전혀 없다. 식별 필드가 있다면 그건 소유자 근거가 아니므로
    // 사람이 봐야 한다.
    return needsRedaction
      ? { status: "UNVERIFIABLE", action: "skip" }
      : { status: "UNVERIFIABLE_NO_OWNER", action: "none" };
  }
  if (!authorAccountExists) return { status: "UNVERIFIABLE", action: "skip" };
  return { status: "MAPPING_MISSING", action: "createMappingAndRedact", ownerUid: publicAuthor };
}

/** 알림 하나를 익명화해야 하는가. */
export function notificationNeedsSanitizing(data) {
  if (!ANONYMOUS_NOTIFICATION_TYPES.has(String(data?.type ?? ""))) return false;
  return data.actorId != null || (data.actorName != null && data.actorName !== ANONYMOUS_ACTOR_NAME);
}

function parsePositiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) throw new Error(`${name} must be an integer >= 1`);
  return parsed;
}

export function parseArgs(argv) {
  const options = {
    projectId: "",
    apply: false,
    verify: false,
    allowProduction: false,
    checkpoint: "",
    limit: Number.POSITIVE_INFINITY,
    anomalyIdsOut: "",
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = () => {
      const v = argv[i + 1];
      if (v === undefined || v.startsWith("--")) throw new Error(`${arg} requires a value`);
      i += 1;
      return v;
    };
    switch (arg) {
      case "--help": case "-h": options.help = true; break;
      case "--dry-run": options.apply = false; break;
      case "--apply": options.apply = true; break;
      case "--verify": options.verify = true; break;
      case "--allow-production": options.allowProduction = true; break;
      case "--project": options.projectId = value(); break;
      case "--checkpoint": options.checkpoint = value(); break;
      case "--limit": options.limit = parsePositiveInteger(value(), "--limit"); break;
      case "--anomaly-ids-out": options.anomalyIdsOut = value(); break;
      default: throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (options.apply && options.verify) throw new Error("--apply and --verify are exclusive");
  return options;
}

export function assertRunnable(options, env = process.env) {
  if (!options.projectId) throw new Error("--project is required");
  if (!ALLOWED_PROJECTS.has(options.projectId)) {
    throw new Error(`--project ${options.projectId} is not in the allowlist`);
  }
  if (!options.apply) return;
  if (env.FIRESTORE_EMULATOR_HOST) return;
  if (PRODUCTION_PROJECTS.has(options.projectId) && !options.allowProduction) {
    throw new Error("refusing to write to production without --allow-production");
  }
  if (!PRODUCTION_PROJECTS.has(options.projectId)) {
    throw new Error("non-production projects may only be written through the emulator");
  }
}

function requireAdmin() {
  const require = createRequire(import.meta.url);
  return require("../functions/node_modules/firebase-admin");
}

function emptySummary() {
  return {
    posts: 0, comments: 0,
    status: {},
    redacted: 0, mappingsCreated: 0, alreadyRedacted: 0, raced: 0, skippedByLimit: 0,
    postLikes: 0, commentLikes: 0,
  };
}

function bump(map, key) {
  map[key] = (map[key] ?? 0) + 1;
}

function loadCheckpoint(path) {
  if (!path || !existsSync(path)) return { roots: {} };
  return JSON.parse(readFileSync(path, "utf8"));
}

function saveCheckpoint(path, state) {
  if (path) writeFileSync(path, JSON.stringify(state, null, 2), "utf8");
}

/**
 * public authorId 가 실존 계정인가. 앱 프로필 문서(users/{uid}) 가 있거나, 같은
 * uid 의 Firebase Auth 계정이 있으면 실존으로 본다 — 초기 Kakao 커스텀 토큰
 * 계정은 Auth 계정만 있고 users 문서가 없을 수 있다. 둘 다 없으면 소유자 근거가
 * 없으므로 사람이 판단한다.
 */
async function authorEvidence(firestore, admin, uid) {
  if (!uid) return { users: false, auth: false };
  const users = (await firestore.collection("users").doc(uid).get()).exists;
  if (users) return { users: true, auth: false };
  try {
    await admin.auth().getUser(uid);
    return { users: false, auth: true };
  } catch {
    return { users: false, auth: false };
  }
}

/**
 * 계획 → 트랜잭션 안에서 재확인 → 쓰기. 계획과 재분류가 다르면 쓰지 않는다.
 */
async function processRecord(ctx, { publicRef, mappingRef, expected, partition }) {
  const { firestore, admin, options, summary, anomalies } = ctx;
  const [publicSnap, mappingSnap] = await Promise.all([publicRef.get(), mappingRef.get()]);
  const publicData = publicSnap.data() ?? {};
  const mapping = mappingSnap.exists ? mappingSnap.data() : null;
  const evidence = await authorEvidence(firestore, admin, clean(publicData.authorId));
  const planned = classifyRecord({
    publicData, mapping,
    authorAccountExists: evidence.users || evidence.auth,
    expected,
  });
  bump(summary.status, planned.status);
  if (planned.status === "MAPPING_MISSING" && !evidence.users) bump(summary.status, "MAPPING_MISSING_AUTH_ACCOUNT_ONLY");
  if (planned.action === "skip") {
    anomalies.push(`${planned.status} ${publicRef.path}`);
    return;
  }
  if (planned.action === "none") {
    summary.alreadyRedacted += 1;
    return;
  }
  if (!options.apply) return;
  if (ctx.counter.writes >= options.limit) {
    summary.skippedByLimit += 1;
    return;
  }

  const outcome = await firestore.runTransaction(async (tx) => {
    const [p, m] = await Promise.all([tx.get(publicRef), tx.get(mappingRef)]);
    const pData = p.data() ?? {};
    const author = clean(pData.authorId);
    const userSnap = author ? await tx.get(firestore.collection("users").doc(author)) : null;
    const again = classifyRecord({
      publicData: pData,
      mapping: m.exists ? m.data() : null,
      // Auth 존재는 트랜잭션 밖에서 확인했다 (계정 존재는 이 사이에 바뀌지 않는다).
      authorAccountExists: userSnap?.exists === true || (author === clean(publicData.authorId) && evidence.auth),
      expected,
    });
    if (!p.exists || again.action !== planned.action || again.ownerUid !== planned.ownerUid) return "raced";
    if (again.action === "createMappingAndRedact") {
      tx.create(mappingRef, {
        postId: expected.postId,
        ...(expected.commentId != null ? { commentId: expected.commentId } : {}),
        ownerUid: again.ownerUid,
        // "내가 쓴 글" 정렬은 매핑 createdAt 기준이다 — 글의 작성 시각을 옮긴다.
        createdAt: pData.createdAt ?? admin.firestore.FieldValue.serverTimestamp(),
        backfilled: true,
        migration: "p03-redaction-v1",
        ...(partition ? { dataPartition: partition } : {}),
      });
    }
    const deletes = Object.fromEntries(
      identityFieldsPresent(pData).map((field) => [field, admin.firestore.FieldValue.delete()])
    );
    tx.update(publicRef, deletes);
    return again.action;
  });
  if (outcome === "raced") {
    summary.raced += 1;
    anomalies.push(`RACED ${publicRef.path}`);
    return;
  }
  ctx.counter.writes += 1;
  summary.redacted += 1;
  if (outcome === "createMappingAndRedact") summary.mappingsCreated += 1;
}

async function migrateRoot(ctx, root, checkpoint) {
  const { firestore, admin } = ctx;
  const summary = emptySummary();
  const docId = admin.firestore.FieldPath.documentId();
  let after = checkpoint.roots[root.posts] ?? null;
  for (;;) {
    let q = firestore.collection(root.posts).orderBy(docId).limit(PAGE_SIZE);
    if (after) q = q.startAfter(after);
    const page = await q.get();
    if (page.empty) break;
    for (const post of page.docs) {
      summary.posts += 1;
      await processRecord({ ...ctx, summary }, {
        publicRef: post.ref,
        mappingRef: firestore.collection(root.postOwners).doc(post.id),
        expected: { postId: post.id },
        partition: root.partition,
      });
      summary.postLikes += (await post.ref.collection("likes").count().get()).data().count;
      const comments = await post.ref.collection("comments").get();
      for (const comment of comments.docs) {
        summary.comments += 1;
        await processRecord({ ...ctx, summary }, {
          publicRef: comment.ref,
          mappingRef: firestore.collection(root.commentOwners).doc(`${post.id}__${comment.id}`),
          expected: { postId: post.id, commentId: comment.id },
          partition: root.partition,
        });
        summary.commentLikes += (await comment.ref.collection("likes").count().get()).data().count;
      }
      after = post.id;
      checkpoint.roots[root.posts] = after;
      saveCheckpoint(ctx.options.checkpoint, checkpoint);
    }
  }
  return summary;
}

async function migrateNotifications(ctx) {
  const { firestore, admin, options } = ctx;
  const summary = { scanned: 0, bambooTypes: 0, exposed: 0, sanitized: 0 };
  const docId = admin.firestore.FieldPath.documentId();
  // 알림 경로(users/{uid}/...)에는 UID 가 들어 있으므로 checkpoint 에 남기지 않는다.
  // 익명화는 멱등이라 매 실행마다 처음부터 다시 훑어도 안전하다.
  let after = null;
  for (;;) {
    let q = firestore.collectionGroup("notifications").orderBy(docId).limit(500);
    if (after) q = q.startAfter(after);
    const page = await q.get();
    if (page.empty) break;
    const toFix = [];
    for (const n of page.docs) {
      summary.scanned += 1;
      const parts = n.ref.path.split("/");
      if (parts.length !== 4 || parts[0] !== "users") continue;
      if (ANONYMOUS_NOTIFICATION_TYPES.has(String(n.get("type") ?? ""))) summary.bambooTypes += 1;
      if (notificationNeedsSanitizing(n.data())) {
        summary.exposed += 1;
        toFix.push(n.ref);
      }
    }
    if (options.apply) {
      for (let i = 0; i < toFix.length; i += NOTIFICATION_BATCH) {
        const batch = firestore.batch();
        for (const ref of toFix.slice(i, i + NOTIFICATION_BATCH)) {
          batch.update(ref, { actorId: null, actorName: ANONYMOUS_ACTOR_NAME });
        }
        await batch.commit();
        summary.sanitized += Math.min(NOTIFICATION_BATCH, toFix.length - i);
      }
    }
    after = page.docs[page.docs.length - 1];
  }
  return summary;
}

/**
 * 독립 검증. 마이그레이션 경로(classifyRecord)를 쓰지 않고 원 데이터에서 직접 센다.
 */
export async function verify(firestore, admin) {
  const out = {
    publicPostsWithIdentity: 0,
    publicCommentsWithIdentity: 0,
    postsWithoutValidMapping: 0,
    commentsWithoutValidMapping: 0,
    mappingConflicts: 0,
    identifyingBambooNotifications: 0,
    orphanMappings: 0,
    posts: 0,
    comments: 0,
  };
  for (const root of ROOTS) {
    const posts = await firestore.collection(root.posts).get();
    const seenPostMappings = new Set();
    const seenCommentMappings = new Set();
    for (const post of posts.docs) {
      out.posts += 1;
      const pd = post.data();
      if (PUBLIC_IDENTITY_FIELDS.some((f) => pd[f] !== undefined)) out.publicPostsWithIdentity += 1;
      const m = await firestore.collection(root.postOwners).doc(post.id).get();
      seenPostMappings.add(post.id);
      const owner = m.exists ? clean(m.get("ownerUid")) : "";
      if (!owner || (clean(m.get("postId")) && m.get("postId") !== post.id)) out.postsWithoutValidMapping += 1;
      if (owner && clean(pd.authorId) && clean(pd.authorId) !== owner) out.mappingConflicts += 1;
      const comments = await post.ref.collection("comments").get();
      for (const c of comments.docs) {
        out.comments += 1;
        const cd = c.data();
        if (PUBLIC_IDENTITY_FIELDS.some((f) => cd[f] !== undefined)) out.publicCommentsWithIdentity += 1;
        const key = `${post.id}__${c.id}`;
        seenCommentMappings.add(key);
        const cm = await firestore.collection(root.commentOwners).doc(key).get();
        const cOwner = cm.exists ? clean(cm.get("ownerUid")) : "";
        if (!cOwner) out.commentsWithoutValidMapping += 1;
        if (cOwner && clean(cd.authorId) && clean(cd.authorId) !== cOwner) out.mappingConflicts += 1;
      }
    }
    for (const m of (await firestore.collection(root.postOwners).get()).docs) {
      if (!seenPostMappings.has(m.id)) out.orphanMappings += 1;
    }
    for (const m of (await firestore.collection(root.commentOwners).get()).docs) {
      if (!seenCommentMappings.has(m.id)) out.orphanMappings += 1;
    }
  }
  const docId = admin.firestore.FieldPath.documentId();
  let after = null;
  for (;;) {
    let q = firestore.collectionGroup("notifications").orderBy(docId).limit(500);
    if (after) q = q.startAfter(after);
    const page = await q.get();
    if (page.empty) break;
    for (const n of page.docs) {
      const d = n.data();
      if (ANONYMOUS_NOTIFICATION_TYPES.has(String(d.type ?? "")) &&
          (d.actorId != null || (d.actorName != null && d.actorName !== ANONYMOUS_ACTOR_NAME))) {
        out.identifyingBambooNotifications += 1;
      }
    }
    after = page.docs[page.docs.length - 1];
  }
  const violations =
    out.publicPostsWithIdentity + out.publicCommentsWithIdentity +
    out.postsWithoutValidMapping + out.commentsWithoutValidMapping +
    out.mappingConflicts + out.identifyingBambooNotifications;
  return { ...out, violations };
}

function usage() {
  return [
    "Usage: node scripts/bamboo_privacy_migration.mjs --project <id> [--dry-run|--apply|--verify]",
    "  --allow-production        Required for --apply against seolleyeon-final.",
    "  --checkpoint <file>       Resume state (last post id per root; no UIDs).",
    "  --limit <n>               Fix at most n public records in this run.",
    "  --anomaly-ids-out <file>  Write anomalous document paths (no UIDs).",
  ].join("\n");
}

export async function main(argv = process.argv.slice(2), env = process.env) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(usage());
    return 0;
  }
  assertRunnable(options, env);
  const admin = requireAdmin();
  if (admin.apps.length === 0) admin.initializeApp({ projectId: options.projectId });
  const firestore = admin.firestore();

  if (options.verify) {
    const result = await verify(firestore, admin);
    console.log(JSON.stringify({ project: options.projectId, mode: "verify", ...result }, null, 2));
    return result.violations === 0 ? 0 : 3;
  }

  const checkpoint = loadCheckpoint(options.checkpoint);
  const anomalies = [];
  // counter is shared by reference: processRecord receives per-root copies of ctx.
  const ctx = { firestore, admin, options, anomalies, counter: { writes: 0 } };
  const roots = {};
  for (const root of ROOTS) roots[root.posts] = await migrateRoot(ctx, root, checkpoint);
  const notifications = await migrateNotifications(ctx);

  if (options.anomalyIdsOut) {
    writeFileSync(options.anomalyIdsOut, ["# P0-3 anomalies (paths only, no UIDs)", ...anomalies, ""].join("\n"), "utf8");
  }
  console.log(JSON.stringify({
    project: options.projectId,
    mode: options.apply ? "apply" : "dry-run",
    emulator: Boolean(env.FIRESTORE_EMULATOR_HOST),
    roots,
    notifications,
    anomalies: anomalies.length,
  }, null, 2));
  return anomalies.length > 0 ? 2 : 0;
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().then(
    (code) => { process.exitCode = code; },
    (error) => {
      console.error(String(error?.message ?? error));
      process.exitCode = 1;
    }
  );
}
