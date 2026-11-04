/**
 * P0-3 — 대나무숲 public 문서의 작성자 식별 정보 제거 (최종 마이그레이션).
 *
 * 이전 Phase A 스크립트(bamboo_anonymize_migration.mjs)는 비공개 매핑만 만들고
 * public authorId 는 그대로 뒀다. 그것만으로는 익명성이 생기지 않는다. 이 스크립트는
 * 레코드마다 한 트랜잭션으로 소유권을 정리하고 public 식별 필드를 지운다.
 *
 * 소유권 신뢰 등급 (Phase 0A — 같은 uid 의 계정이 있다는 것만으로는 그 사람이 그 글을
 * 썼다는 증거가 아니다):
 *
 *   TRUSTED_EXISTING_MAPPING       서버가 글과 같은 커밋에 쓴 비공개 매핑이 있다.
 *   TRUSTED_HISTORICAL_PROVENANCE  매핑은 없지만, 문서가 만들어진 시각에 배포돼 있던
 *                                  Firestore 규칙이 create 에서 authorId == auth.uid 를
 *                                  강제했고(OR 분기 없음), 그 뒤 문서가 한 번도 바뀌지
 *                                  않았으며, 다른 작성자의 문서와 같은 커밋(일괄 import)
 *                                  으로 생기지 않았다 → 매핑을 만든다.
 *   LEGACY_AUTHOR_ONLY             위 근거가 없다 (예: 관리자 일괄 import). 소유자를
 *                                  지정하지 않는다. public 식별 필드는 그래도 지우고,
 *                                  서버 전용 `bamboo_ownership_unresolved` 에 미해결로
 *                                  기록한다. 매핑이 없으므로 삭제·내 글 같은 소유자
 *                                  기능은 막힌 채(fail closed) 읽기만 된다.
 *   MAPPING_CONFLICT / MALFORMED   손대지 않고 보고한다 (verify 가 위반으로 센다).
 *
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
 * - 멱등: 이미 정리된 문서는 alreadyRedacted 로 세고 쓰지 않는다.
 * - `--checkpoint <file>`: 처리한 마지막 글 id 를 저장하고 이어서 돈다 (UID 없음).
 * - `--limit <n>`: 이번 실행에서 고칠 public 레코드 수 상한 (canary).
 * - `--only-post <postId>`: 그 글(과 그 댓글)만 처리한다 (canary 대상 지정).
 * - 로그는 집계만. UID 는 어디에도 찍지 않는다. `--anomaly-ids-out` 은 문서 경로만 쓴다.
 * - `--verify`: 쓰기 없이 독립 검증. 위반이 하나라도 있으면 exit 3.
 *
 * 에뮬레이터:
 *   firebase emulators:exec --only firestore,auth --project demo-p03-migration \
 *     "node --test scripts/bamboo_privacy_migration.emulator-test.mjs"
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

/** 소유자 미확정 레코드. 서버 전용 (rules: 모든 클라이언트 접근 거부). */
export const UNRESOLVED_COLLECTION = "bamboo_ownership_unresolved";

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
const MIGRATION_TAG = "p03-redaction-v2";

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function identityFieldsPresent(data) {
  return PUBLIC_IDENTITY_FIELDS.filter((field) => data != null && data[field] !== undefined);
}

export function unresolvedDocId(rootName, postId, commentId) {
  return commentId ? `${rootName}__${postId}__${commentId}` : `${rootName}__${postId}`;
}

/**
 * 레코드 하나의 상태와 할 일을 정한다. 순수 함수 — 단위 테스트 대상.
 *
 * @param {object} input
 * @param {Record<string, unknown>} input.publicData  public 글/댓글 문서
 * @param {Record<string, unknown> | null} input.mapping 비공개 매핑 문서 (없으면 null)
 * @param {"historical" | "none"} input.provenance 매핑이 없을 때 public authorId 의 출처 근거
 * @param {boolean} input.unresolvedRecorded 미해결 기록이 이미 있는가
 * @param {{postId: string, commentId?: string}} input.expected
 * @returns {{status: string, action: "none" | "redact" | "createMappingAndRedact" | "redactUnresolved" | "skip", ownerUid?: string}}
 */
export function classifyRecord({ publicData, mapping, provenance, unresolvedRecorded = false, expected }) {
  const publicAuthor = clean(publicData?.authorId);
  const needsRedaction = identityFieldsPresent(publicData).length > 0;

  if (mapping != null) {
    const owner = clean(mapping.ownerUid);
    const pointsElsewhere =
      (clean(mapping.postId) && clean(mapping.postId) !== expected.postId) ||
      (expected.commentId != null && clean(mapping.commentId) && clean(mapping.commentId) !== expected.commentId);
    if (!owner || pointsElsewhere) return { status: "MALFORMED", action: "skip" };
    if (publicAuthor && publicAuthor !== owner) return { status: "MAPPING_CONFLICT", action: "skip" };
    if (!needsRedaction) return { status: "PUBLIC_AUTHOR_ABSENT", action: "none", ownerUid: owner };
    return { status: "TRUSTED_EXISTING_MAPPING", action: "redact", ownerUid: owner };
  }

  if (publicAuthor && provenance === "historical") {
    return { status: "TRUSTED_HISTORICAL_PROVENANCE", action: "createMappingAndRedact", ownerUid: publicAuthor };
  }
  // 소유자 근거가 없다. 소유자는 정하지 않지만, 공개 식별 정보는 남기지 않는다.
  if (needsRedaction) {
    return { status: "LEGACY_AUTHOR_ONLY", action: "redactUnresolved" };
  }
  if (unresolvedRecorded) return { status: "UNRESOLVED_RECORDED", action: "none" };
  // 식별 필드도 매핑도 없는 문서: 탈퇴 정리로 soft delete 된 글이면 정상 종착이고,
  // 살아 있는 글이면 매핑을 빠뜨린 writer 버그다 — 미해결로 덮지 않고 보고한다.
  if (publicData?.isDeleted === true) return { status: "DELETED_WITHOUT_OWNER", action: "none" };
  return { status: "OWNERLESS_WITHOUT_EVIDENCE", action: "skip" };
}

/**
 * 규칙 소스에서 `root` 의 글(또는 그 하위 댓글) create 규칙이 authorId 를 요청자에게
 * 묶는지 본다. OR 분기가 있으면 묶였다고 보지 않는다 (fail closed).
 */
export function createRuleBindsAuthor(source, rootName, kind) {
  const start = source.indexOf(`match /${rootName}/{postId}`);
  if (start < 0) return false;
  let from = start;
  if (kind === "comment") {
    from = source.indexOf("match /comments/{commentId}", start);
    if (from < 0) return false;
  }
  // 이 match 블록 머리부터 다음 하위 match 전까지에서 create 규칙을 찾는다.
  const nextMatch = source.indexOf("match /", from + 7);
  const region = source.slice(from, nextMatch < 0 ? undefined : nextMatch);
  const rule = region.match(/allow\s+[a-z ,]*\bcreate\b[a-z ,]*:([\s\S]*?);/);
  if (!rule) return false;
  const body = rule[1].replace(/\/\/.*$/gm, "");
  if (body.includes("||")) return false;
  return /request\.resource\.data\.authorId\s*==\s*request\.auth\.uid/.test(body);
}

/** 문서 생성 시각에 배포돼 있던 Firestore ruleset (createTime 이 그 이전인 마지막 것). */
export function rulesetAt(history, createdAtMs) {
  let found = null;
  for (const entry of history) {
    if (entry.createTimeMs <= createdAtMs && (!found || entry.createTimeMs > found.createTimeMs)) found = entry;
  }
  return found;
}

function timestampKey(ts) {
  return `${ts.seconds}.${String(ts.nanoseconds).padStart(9, "0")}`;
}

/**
 * 매핑 없는 레코드의 출처 근거.
 * @returns {"historical" | "none"}
 */
export function provenanceFor({ snap, rootName, kind, history, sharedCommit }) {
  const data = snap.data() ?? {};
  const author = clean(data.authorId);
  if (!author || !snap.createTime || !snap.updateTime) return "none";
  // 생성 뒤 한 번이라도 바뀌었으면 authorId 가 처음 값이라는 보장이 없다.
  if (timestampKey(snap.createTime) !== timestampKey(snap.updateTime)) return "none";
  // 다른 작성자의 문서와 같은 커밋에서 생긴 문서는 관리자 일괄 쓰기다 (클라이언트는
  // 규칙상 남의 authorId 로 쓸 수 없었으므로 규칙 근거가 적용되지 않는다).
  const authors = sharedCommit.get(timestampKey(snap.createTime));
  if (authors && authors.size > 1) return "none";
  const ruleset = rulesetAt(history, snap.createTime.toMillis());
  if (!ruleset) return "none";
  return createRuleBindsAuthor(ruleset.source, rootName, kind) ? "historical" : "none";
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
    onlyPost: "",
    anomalyIdsOut: "",
    repairLikeCounters: false,
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
      case "--only-post": options.onlyPost = value(); break;
      case "--anomaly-ids-out": options.anomalyIdsOut = value(); break;
      case "--repair-like-counters": options.repairLikeCounters = true; break;
      default: throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (options.apply && options.verify) throw new Error("--apply and --verify are exclusive");
  if (options.onlyPost && !/^[A-Za-z0-9_-]{1,128}$/.test(options.onlyPost)) {
    throw new Error("--only-post must be a document id");
  }
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

/** 배포 이력의 Firestore ruleset 들 (createTime 순). */
async function loadRulesHistory(admin) {
  const rules = admin.securityRules();
  const metas = [];
  let token;
  do {
    const page = await rules.listRulesetMetadata(100, token);
    metas.push(...page.rulesets);
    token = page.nextPageToken;
  } while (token);
  const history = [];
  for (const meta of metas) {
    const ruleset = await rules.getRuleset(meta.name);
    const source = ruleset.source.map((file) => file.content).join("\n");
    if (!source.includes("cloud.firestore")) continue;
    history.push({ name: meta.name, createTimeMs: Date.parse(meta.createTime), source });
  }
  return history.sort((a, b) => a.createTimeMs - b.createTimeMs);
}

function emptySummary() {
  return {
    posts: 0, comments: 0,
    status: {},
    redacted: 0, mappingsCreated: 0, unresolvedRecorded: 0, alreadyRedacted: 0, raced: 0, skippedByLimit: 0,
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
 * 계획 → 트랜잭션 안에서 재확인 → 쓰기. 계획과 재분류가 다르면 쓰지 않는다.
 */
async function processRecord(ctx, { publicRef, mappingRef, unresolvedRef, expected, partition, rootName, kind, sharedCommit }) {
  const { firestore, admin, options, summary, anomalies, history } = ctx;
  const [publicSnap, mappingSnap, unresolvedSnap] = await Promise.all([publicRef.get(), mappingRef.get(), unresolvedRef.get()]);
  const classify = (pSnap, mSnap, uSnap) => classifyRecord({
    publicData: pSnap.data() ?? {},
    mapping: mSnap.exists ? mSnap.data() : null,
    provenance: provenanceFor({ snap: pSnap, rootName, kind, history, sharedCommit }),
    unresolvedRecorded: uSnap.exists,
    expected,
  });
  const planned = classify(publicSnap, mappingSnap, unresolvedSnap);
  bump(summary.status, planned.status);
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
    const [p, m, u] = await Promise.all([tx.get(publicRef), tx.get(mappingRef), tx.get(unresolvedRef)]);
    const again = classify(p, m, u);
    if (!p.exists || again.action !== planned.action || again.ownerUid !== planned.ownerUid) return "raced";
    const pData = p.data() ?? {};
    if (again.action === "createMappingAndRedact") {
      tx.create(mappingRef, {
        postId: expected.postId,
        ...(expected.commentId != null ? { commentId: expected.commentId } : {}),
        ownerUid: again.ownerUid,
        // "내가 쓴 글" 정렬은 매핑 createdAt 기준이다 — 글의 작성 시각을 옮긴다.
        createdAt: pData.createdAt ?? admin.firestore.FieldValue.serverTimestamp(),
        backfilled: true,
        provenance: "historical_rules_binding",
        migration: MIGRATION_TAG,
        ...(partition ? { dataPartition: partition } : {}),
      });
    }
    if (again.action === "redactUnresolved" && !u.exists) {
      tx.create(unresolvedRef, {
        root: rootName,
        postId: expected.postId,
        commentId: expected.commentId ?? null,
        // 나중에 소유권을 확인할 때 쓰는 유일한 단서. 서버 전용 컬렉션에만 남는다.
        legacyAuthorClaim: clean(pData.authorId) || null,
        reason: "no_mapping_and_no_historical_provenance",
        recordedAt: admin.firestore.FieldValue.serverTimestamp(),
        migration: MIGRATION_TAG,
      });
    }
    const deletes = Object.fromEntries(
      identityFieldsPresent(pData).map((field) => [field, admin.firestore.FieldValue.delete()])
    );
    if (Object.keys(deletes).length > 0) tx.update(publicRef, deletes);
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
  if (outcome === "redactUnresolved") summary.unresolvedRecorded += 1;
}

/** createTime → 작성자 집합. 서로 다른 작성자가 한 커밋에 있으면 일괄 쓰기다. */
async function sharedCommitIndex(firestore, root) {
  const posts = new Map();
  const comments = new Map();
  const add = (map, snap) => {
    const key = timestampKey(snap.createTime);
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(clean(snap.get("authorId")) || `__none__${snap.ref.path}`);
  };
  for (const post of (await firestore.collection(root.posts).get()).docs) {
    add(posts, post);
    for (const comment of (await post.ref.collection("comments").get()).docs) add(comments, comment);
  }
  return { posts, comments };
}

/**
 * likeCount 와 실제 좋아요 문서 수가 다르면 보고한다. 새 규칙은 좋아요 삭제에 부모
 * likeCount -1 을 요구하므로, 카운터가 문서 수보다 작은 글에서는 좋아요 취소가 막힌다.
 * `--apply --repair-like-counters` 일 때만 likeCount 를 실제 수로 고친다.
 */
async function checkLikeCounter(ctx, summary, ref) {
  const likes = (await ref.collection("likes").count().get()).data().count;
  const snap = await ref.get();
  const counter = Number(snap.get("likeCount") ?? 0);
  if (counter !== likes) {
    summary.likeCounterDrift = (summary.likeCounterDrift ?? 0) + 1;
    if (ctx.options.apply && ctx.options.repairLikeCounters) {
      await ref.update({ likeCount: likes });
      summary.likeCountersRepaired = (summary.likeCountersRepaired ?? 0) + 1;
    }
  }
  return likes;
}

async function migrateRoot(ctx, root, checkpoint) {
  const { firestore, admin, options } = ctx;
  const summary = emptySummary();
  const shared = await sharedCommitIndex(firestore, root);
  const docId = admin.firestore.FieldPath.documentId();
  let after = checkpoint.roots[root.posts] ?? null;
  let checkpointFrozen = false;
  for (;;) {
    let q = firestore.collection(root.posts).orderBy(docId).limit(PAGE_SIZE);
    if (options.onlyPost) q = firestore.collection(root.posts).where(docId, "==", options.onlyPost);
    else if (after) q = q.startAfter(after);
    const page = await q.get();
    if (page.empty) break;
    for (const post of page.docs) {
      // --limit 에 도달하면 멈춘다. 그 뒤의 글은 다음 실행이 처리한다.
      if (options.apply && ctx.counter.writes >= options.limit) {
        ctx.limitReached = true;
        break;
      }
      const skippedBefore = summary.skippedByLimit;
      const anomaliesBefore = ctx.anomalies.length;
      summary.posts += 1;
      await processRecord({ ...ctx, summary }, {
        publicRef: post.ref,
        mappingRef: firestore.collection(root.postOwners).doc(post.id),
        unresolvedRef: firestore.collection(UNRESOLVED_COLLECTION).doc(unresolvedDocId(root.posts, post.id)),
        expected: { postId: post.id },
        partition: root.partition,
        rootName: root.posts,
        kind: "post",
        sharedCommit: shared.posts,
      });
      summary.postLikes += await checkLikeCounter(ctx, summary, post.ref);
      const comments = await post.ref.collection("comments").get();
      for (const comment of comments.docs) {
        summary.comments += 1;
        await processRecord({ ...ctx, summary }, {
          publicRef: comment.ref,
          mappingRef: firestore.collection(root.commentOwners).doc(`${post.id}__${comment.id}`),
          unresolvedRef: firestore.collection(UNRESOLVED_COLLECTION).doc(unresolvedDocId(root.posts, post.id, comment.id)),
          expected: { postId: post.id, commentId: comment.id },
          partition: root.partition,
          rootName: root.posts,
          kind: "comment",
          sharedCommit: shared.comments,
        });
        summary.commentLikes += await checkLikeCounter(ctx, summary, comment.ref);
      }
      after = post.id;
      // checkpoint 는 실제로 다 적용된 글만 지나간다. dry-run 이나 --limit 로
      // 건너뛴 레코드가 있는 글을 지나가면 다음 --apply 가 그 글을 영영 보지 않는다.
      // 이상(conflict·malformed·raced) 레코드가 있던 글도 지나가지 않는다 — 운영자가
      // 고친 뒤 다시 돌리면 그 글을 다시 봐야 한다.
      // checkpoint 는 "여기까지는 전부 끝났다" 는 표시라서, 한 글이 막히면 그 뒤로는
      // 이번 실행에서 더 전진하지 않는다.
      const complete = options.apply && summary.skippedByLimit === skippedBefore &&
        ctx.anomalies.length === anomaliesBefore;
      if (!complete) checkpointFrozen = true;
      if (!options.onlyPost && !checkpointFrozen) {
        checkpoint.roots[root.posts] = after;
        saveCheckpoint(options.checkpoint, checkpoint);
      }
    }
    if (options.onlyPost || ctx.limitReached) break;
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
 * 소유자 미확정(unresolved) 은 위반이 아니라 따로 보고한다 — 공개 식별 정보는 없어야 한다.
 */
export async function verify(firestore, admin) {
  const out = {
    publicPostsWithIdentity: 0,
    publicCommentsWithIdentity: 0,
    recordsWithoutOwnershipRecord: 0,
    mappingConflicts: 0,
    malformedMappings: 0,
    identifyingBambooNotifications: 0,
    unresolvedOwnership: 0,
    staleUnresolvedRecords: 0,
    deletedWithoutOwner: 0,
    orphanMappings: 0,
    posts: 0,
    comments: 0,
  };
  const unresolved = new Set(
    (await firestore.collection(UNRESOLVED_COLLECTION).get()).docs.map((d) => d.id)
  );
  const checkOwnership = (mappingSnap, unresolvedKey, publicData, expected) => {
    const owner = mappingSnap.exists ? clean(mappingSnap.get("ownerUid")) : "";
    if (mappingSnap.exists && (
      !owner ||
      (clean(mappingSnap.get("postId")) && clean(mappingSnap.get("postId")) !== expected.postId) ||
      (expected.commentId && clean(mappingSnap.get("commentId")) && clean(mappingSnap.get("commentId")) !== expected.commentId)
    )) {
      out.malformedMappings += 1;
      return;
    }
    if (owner) {
      if (clean(publicData.authorId) && clean(publicData.authorId) !== owner) out.mappingConflicts += 1;
      if (unresolved.has(unresolvedKey)) out.staleUnresolvedRecords += 1;
    } else if (unresolved.has(unresolvedKey)) {
      out.unresolvedOwnership += 1;
    } else if (
      publicData.isDeleted === true &&
      !PUBLIC_IDENTITY_FIELDS.some((f) => publicData[f] !== undefined)
    ) {
      // 탈퇴 정리는 글을 soft delete 하고 매핑을 지운다 — 정상 종착 상태다.
      out.deletedWithoutOwner += 1;
    } else {
      out.recordsWithoutOwnershipRecord += 1;
    }
  };
  for (const root of ROOTS) {
    const posts = await firestore.collection(root.posts).get();
    const seenPostMappings = new Set();
    const seenCommentMappings = new Set();
    for (const post of posts.docs) {
      out.posts += 1;
      const pd = post.data();
      if (PUBLIC_IDENTITY_FIELDS.some((f) => pd[f] !== undefined)) out.publicPostsWithIdentity += 1;
      seenPostMappings.add(post.id);
      checkOwnership(
        await firestore.collection(root.postOwners).doc(post.id).get(),
        unresolvedDocId(root.posts, post.id),
        pd,
        { postId: post.id }
      );
      const comments = await post.ref.collection("comments").get();
      for (const c of comments.docs) {
        out.comments += 1;
        const cd = c.data();
        if (PUBLIC_IDENTITY_FIELDS.some((f) => cd[f] !== undefined)) out.publicCommentsWithIdentity += 1;
        const key = `${post.id}__${c.id}`;
        seenCommentMappings.add(key);
        checkOwnership(
          await firestore.collection(root.commentOwners).doc(key).get(),
          unresolvedDocId(root.posts, post.id, c.id),
          cd,
          { postId: post.id, commentId: c.id }
        );
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
    out.recordsWithoutOwnershipRecord + out.mappingConflicts + out.malformedMappings +
    out.identifyingBambooNotifications;
  return { ...out, violations };
}

function usage() {
  return [
    "Usage: node scripts/bamboo_privacy_migration.mjs --project <id> [--dry-run|--apply|--verify]",
    "  --allow-production        Required for --apply against seolleyeon-final.",
    "  --checkpoint <file>       Resume state (last post id per root; no UIDs).",
    "  --limit <n>               Fix at most n public records in this run.",
    "  --only-post <postId>      Process only that post (and its comments) — canary.",
    "  --anomaly-ids-out <file>  Write anomalous document paths (no UIDs).",
  ].join("\n");
}

/**
 * @param {{ loadRulesHistory?: (admin: unknown) => Promise<Array<{name: string, createTimeMs: number, source: string}>> }} deps
 *   테스트에서 규칙 배포 이력을 주입한다 (에뮬레이터에는 Rules API 가 없다).
 */
export async function main(argv = process.argv.slice(2), env = process.env, deps = {}) {
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

  const history = await (deps.loadRulesHistory ?? loadRulesHistory)(admin);
  const checkpoint = loadCheckpoint(options.checkpoint);
  const anomalies = [];
  // counter is shared by reference: processRecord receives per-root copies of ctx.
  const ctx = { firestore, admin, options, anomalies, history, counter: { writes: 0 } };
  const roots = {};
  for (const root of ROOTS) {
    if (ctx.limitReached) break;
    roots[root.posts] = await migrateRoot(ctx, root, checkpoint);
  }
  // 범위를 좁힌 canary(--only-post / --limit) 는 알림을 고치지 않는다 — 집계만 한다.
  const canary = Boolean(options.onlyPost) || Number.isFinite(options.limit);
  const notifications = await migrateNotifications({
    ...ctx,
    options: { ...options, apply: options.apply && !canary },
  });
  if (canary && options.apply) notifications.deferredUntilFullRun = true;

  if (options.anomalyIdsOut) {
    writeFileSync(options.anomalyIdsOut, ["# P0-3 anomalies (paths only, no UIDs)", ...anomalies, ""].join("\n"), "utf8");
  }
  console.log(JSON.stringify({
    project: options.projectId,
    mode: options.apply ? "apply" : "dry-run",
    emulator: Boolean(env.FIRESTORE_EMULATOR_HOST),
    rulesetsInHistory: history.length,
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
      // Firestore 오류 메시지에는 users/{uid}/... 경로가 들어갈 수 있다.
      console.error(String(error?.message ?? error).replace(/users\/[^/\s]+/g, "users/<redacted>"));
      process.exitCode = 1;
    }
  );
}
