/**
 * SEC-04 — 대나무숲 소유권 매핑 백필 (Phase A).
 *
 * public `bamboo_posts` / `comments` 에 raw UID 가 `authorId` 로 남아 있는 한,
 * 누구나 읽을 수 있는 `publicProfiles/{uid}` 와 join 해서 익명 글의 작성자를
 * 특정할 수 있다. 최종적으로는 public 에서 authorId 를 지워야 하고, 그때
 * "내가 쓴 글" 을 잃지 않으려면 그 전에 소유권이 비공개 매핑에 옮겨져 있어야
 * 한다. 이 스크립트가 그 옮기는 일을 한다.
 *
 * 이 스크립트는 public authorId 를 건드리지 않는다 — 매핑을 만들기만 한다.
 * 따라서 실행해도 구버전 클라이언트는 그대로 동작한다.
 *
 * 안전장치:
 * - 기본은 DRY-RUN. `--apply` 없이는 아무것도 쓰지 않는다.
 * - `--project` 는 필수이고 allowlist 밖 프로젝트는 거부한다.
 * - production 에 쓰려면 `--apply` 와 `--allow-production` 을 모두 줘야 한다.
 * - 이미 있는 매핑은 절대 덮어쓰지 않는다. 소유자가 다르면 conflict 로 세고
 *   건너뛴다. 덮어쓰면 남의 글이 내 글이 된다.
 * - 로그는 집계만 남긴다. uid ↔ postId 목록을 찍으면 이 스크립트가 없애려는
 *   연결을 로그에 그대로 복사하는 셈이다.
 *
 * 에뮬레이터 사용:
 *   firebase emulators:exec --only firestore \
 *     --project seolleyeon-bamboo-migration-test \
 *     "node scripts/bamboo_anonymize_migration.mjs \
 *        --project seolleyeon-bamboo-migration-test --apply"
 */
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const POST_COLLECTION = "bamboo_posts";
export const COMMENT_COLLECTION = "comments";
export const POST_MAPPING_COLLECTION = "bamboo_post_authors";
export const COMMENT_MAPPING_COLLECTION = "bamboo_comment_authors";

/** Firestore 배치 상한은 500. 여유를 두고 400 으로 자른다. */
export const DEFAULT_BATCH_SIZE = 400;

export const PRODUCTION_PROJECTS = new Set(["seolleyeon-final"]);

/**
 * 오타 하나로 엉뚱한 프로젝트에 쓰는 일을 막는다. 새 대상이 생기면 여기에
 * 명시적으로 추가해야 한다.
 */
export const ALLOWED_PROJECTS = new Set([
  ...PRODUCTION_PROJECTS,
  "seolleyeon-bamboo-migration-test",
  "seolleyeon-rules-test",
]);

export function commentMappingId(postId, commentId) {
  return `${postId}__${commentId}`;
}

function cleanUid(value) {
  return typeof value === "string" ? value.trim() : "";
}

function parsePositiveInteger(value, optionName) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${optionName} must be an integer >= 1`);
  }
  return parsed;
}

export function parseArgs(argv, env = process.env) {
  const options = {
    projectId: "",
    credentialsPath: env.GOOGLE_APPLICATION_CREDENTIALS ?? "",
    apply: false,
    allowProduction: false,
    batchSize: DEFAULT_BATCH_SIZE,
    pageSize: 200,
    conflictIdsOut: "",
    help: false,
  };

  const valueOptions = new Map([
    ["--project", "projectId"],
    ["--credentials", "credentialsPath"],
    ["--batch-size", "batchSize"],
    ["--page-size", "pageSize"],
    ["--conflict-ids-out", "conflictIdsOut"],
  ]);

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") {
      options.help = true;
      continue;
    }
    if (argument === "--apply") {
      options.apply = true;
      continue;
    }
    if (argument === "--allow-production") {
      options.allowProduction = true;
      continue;
    }
    if (valueOptions.has(argument)) {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) {
        throw new Error(`${argument} requires a value`);
      }
      index += 1;
      const key = valueOptions.get(argument);
      if (key === "batchSize" || key === "pageSize") {
        options[key] = parsePositiveInteger(value, argument);
      } else {
        options[key] = value;
      }
      continue;
    }
    throw new Error(`Unknown argument: ${argument}`);
  }

  if (options.batchSize > 500) {
    throw new Error("--batch-size must not exceed the Firestore limit of 500");
  }

  return options;
}

export function isEmulatorTarget(env = process.env) {
  return Boolean(env.FIRESTORE_EMULATOR_HOST);
}

/**
 * 실행 전 게이트. 던지는 에러가 곧 거부 사유다.
 */
export function assertRunnable(options, env = process.env) {
  if (!options.projectId) {
    throw new Error("--project is required");
  }
  if (!ALLOWED_PROJECTS.has(options.projectId)) {
    throw new Error(
      `--project ${options.projectId} is not in the allowlist; ` +
        "add it explicitly if this is intended"
    );
  }

  if (!options.apply) return;

  // 에뮬레이터로 가는 쓰기는 실데이터를 건드리지 않는다.
  if (isEmulatorTarget(env)) return;

  const production = PRODUCTION_PROJECTS.has(options.projectId);
  if (production && !options.allowProduction) {
    throw new Error(
      "refusing to write to production without --allow-production"
    );
  }
  if (production && !options.credentialsPath) {
    throw new Error(
      "production writes require an explicit --credentials service account"
    );
  }
}

/**
 * 문서 하나의 처리 방법을 정한다.
 *
 * - pending: 매핑이 없고 authorId 가 멀쩡하다. 만들면 된다.
 * - alreadyMigrated: 이미 같은 소유자로 매핑이 있다. 다시 돌려도 안전하다.
 * - conflict: 매핑이 다른 소유자를 가리키거나 매핑 자체가 깨졌다. 건드리지
 *   않는다 — 덮어쓰면 남의 글이 내 글이 된다.
 * - malformed: authorId 를 읽을 수 없어 소유자를 정할 수 없다.
 */
export function classifyDoc({ authorId, mapping }) {
  const legacy = cleanUid(authorId);

  if (mapping !== undefined && mapping !== null) {
    const mapped = cleanUid(mapping.ownerUid);
    if (!mapped) return "conflict";
    if (!legacy) return "alreadyMigrated";
    return mapped === legacy ? "alreadyMigrated" : "conflict";
  }

  return legacy ? "pending" : "malformed";
}

export function emptySummary() {
  return {
    scanned: 0,
    pending: 0,
    created: 0,
    alreadyMigrated: 0,
    conflict: 0,
    malformed: 0,
    raced: 0,
  };
}

export function chunk(items, size) {
  if (!Number.isInteger(size) || size < 1) {
    throw new Error("chunk size must be an integer >= 1");
  }
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

/**
 * bamboo_posts/{postId}/comments/{commentId} 형태만 받아들인다.
 * collectionGroup 은 이름이 같은 다른 하위 컬렉션도 함께 끌어온다.
 */
export function parseCommentPath(path) {
  const parts = String(path).split("/");
  if (
    parts.length !== 4 ||
    parts[0] !== POST_COLLECTION ||
    parts[2] !== COMMENT_COLLECTION
  ) {
    return null;
  }
  const postId = parts[1];
  const commentId = parts[3];
  if (!postId || !commentId) return null;
  return { postId, commentId };
}

function requireAdmin() {
  const require = createRequire(import.meta.url);
  // functions/ 에 설치된 admin SDK 를 빌려 쓴다. 루트에는 없다.
  return require("../functions/node_modules/firebase-admin");
}

async function writeMappings(firestore, entries, options, summary) {
  if (!options.apply || entries.length === 0) return;

  for (const group of chunk(entries, options.batchSize)) {
    const batch = firestore.batch();
    for (const entry of group) {
      // create 는 이미 있으면 실패한다. set 과 달리 절대 덮어쓰지 않는다.
      batch.create(entry.ref, entry.payload);
    }
    try {
      await batch.commit();
      summary.created += group.length;
    } catch {
      // 배치 하나가 실패했다고 나머지를 포기하지 않는다. 스캔과 쓰기 사이에
      // 새 매핑이 생겼을 뿐일 수 있으므로 한 건씩 다시 시도한다.
      for (const entry of group) {
        try {
          await entry.ref.create(entry.payload);
          summary.created += 1;
        } catch {
          summary.raced += 1;
        }
      }
    }
  }
}

async function migratePosts(firestore, options, now) {
  const summary = emptySummary();
  const conflictIds = [];
  let cursor = null;

  for (;;) {
    let pageQuery = firestore
      .collection(POST_COLLECTION)
      .orderBy("__name__")
      .limit(options.pageSize);
    if (cursor) pageQuery = pageQuery.startAfter(cursor);

    const page = await pageQuery.get();
    if (page.empty) break;
    cursor = page.docs[page.docs.length - 1];

    const mappingRefs = page.docs.map((doc) =>
      firestore.collection(POST_MAPPING_COLLECTION).doc(doc.id)
    );
    const mappingSnaps = await firestore.getAll(...mappingRefs);
    const mappings = new Map(
      mappingSnaps.map((snap) => [
        snap.id,
        snap.exists ? snap.data() : undefined,
      ])
    );

    const entries = [];
    for (const doc of page.docs) {
      summary.scanned += 1;
      const authorId = doc.data()?.authorId;
      const verdict = classifyDoc({ authorId, mapping: mappings.get(doc.id) });
      if (verdict === "conflict") {
        summary.conflict += 1;
        conflictIds.push(doc.id);
        continue;
      }
      if (verdict !== "pending") {
        summary[verdict] += 1;
        continue;
      }
      summary.pending += 1;
      entries.push({
        ref: firestore.collection(POST_MAPPING_COLLECTION).doc(doc.id),
        payload: {
          postId: doc.id,
          ownerUid: cleanUid(authorId),
          createdAt: now,
          backfilled: true,
        },
      });
    }

    await writeMappings(firestore, entries, options, summary);
    if (page.size < options.pageSize) break;
  }

  return { summary, conflictIds };
}

async function migrateComments(firestore, options, now) {
  const summary = emptySummary();
  const conflictIds = [];
  let cursor = null;

  for (;;) {
    let pageQuery = firestore
      .collectionGroup(COMMENT_COLLECTION)
      .orderBy("__name__")
      .limit(options.pageSize);
    if (cursor) pageQuery = pageQuery.startAfter(cursor);

    const page = await pageQuery.get();
    if (page.empty) break;
    cursor = page.docs[page.docs.length - 1];

    const parsed = [];
    for (const doc of page.docs) {
      const location = parseCommentPath(doc.ref.path);
      // 대나무숲 댓글이 아니면 애초에 대상이 아니다. scanned 에도 넣지 않는다.
      if (!location) continue;
      parsed.push({ doc, location });
    }

    if (parsed.length > 0) {
      const mappingRefs = parsed.map(({ location }) =>
        firestore
          .collection(COMMENT_MAPPING_COLLECTION)
          .doc(commentMappingId(location.postId, location.commentId))
      );
      const mappingSnaps = await firestore.getAll(...mappingRefs);
      const mappings = new Map(
        mappingSnaps.map((snap) => [
          snap.id,
          snap.exists ? snap.data() : undefined,
        ])
      );

      const entries = [];
      for (const { doc, location } of parsed) {
        summary.scanned += 1;
        const mappingId = commentMappingId(location.postId, location.commentId);
        const authorId = doc.data()?.authorId;
        const verdict = classifyDoc({
          authorId,
          mapping: mappings.get(mappingId),
        });
        if (verdict === "conflict") {
          summary.conflict += 1;
          conflictIds.push(mappingId);
          continue;
        }
        if (verdict !== "pending") {
          summary[verdict] += 1;
          continue;
        }
        summary.pending += 1;
        entries.push({
          ref: firestore.collection(COMMENT_MAPPING_COLLECTION).doc(mappingId),
          payload: {
            postId: location.postId,
            commentId: location.commentId,
            ownerUid: cleanUid(authorId),
            createdAt: now,
            backfilled: true,
          },
        });
      }

      await writeMappings(firestore, entries, options, summary);
    }

    if (page.size < options.pageSize) break;
  }

  return { summary, conflictIds };
}

function usage() {
  return [
    "Usage: node scripts/bamboo_anonymize_migration.mjs --project <id> [options]",
    "",
    "  --project <id>            Target Firebase project (required, allowlisted)",
    "  --apply                   Actually write. Without it this is a dry run.",
    "  --allow-production        Required in addition to --apply for production.",
    "  --credentials <path>      Service account for production writes.",
    "  --batch-size <n>          Writes per batch (default 400, max 500).",
    "  --page-size <n>           Documents read per page (default 200).",
    "  --conflict-ids-out <path> Write conflicting document ids (no UIDs) here.",
  ].join("\n");
}

export async function main(argv = process.argv.slice(2), env = process.env) {
  const options = parseArgs(argv, env);
  if (options.help) {
    console.log(usage());
    return 0;
  }

  assertRunnable(options, env);

  const admin = requireAdmin();
  if (admin.apps.length === 0) {
    admin.initializeApp({
      projectId: options.projectId,
      ...(options.credentialsPath
        ? { credential: admin.credential.cert(options.credentialsPath) }
        : {}),
    });
  }
  const firestore = admin.firestore();
  const now = admin.firestore.FieldValue.serverTimestamp();

  const posts = await migratePosts(firestore, options, now);
  const comments = await migrateComments(firestore, options, now);

  if (options.conflictIdsOut) {
    // 문서 id 만 남긴다. uid 는 쓰지 않는다.
    const lines = [
      "# SEC-04 migration conflicts (document ids only, no UIDs)",
      ...posts.conflictIds.map((id) => `${POST_MAPPING_COLLECTION}/${id}`),
      ...comments.conflictIds.map(
        (id) => `${COMMENT_MAPPING_COLLECTION}/${id}`
      ),
      "",
    ];
    writeFileSync(options.conflictIdsOut, lines.join("\n"), "utf8");
  }

  // 집계만 찍는다. uid ↔ postId 목록은 남기지 않는다.
  console.log(
    JSON.stringify(
      {
        project: options.projectId,
        mode: options.apply ? "apply" : "dry-run",
        emulator: isEmulatorTarget(env),
        posts: posts.summary,
        comments: comments.summary,
      },
      null,
      2
    )
  );

  // conflict 는 사람이 봐야 한다. 조용히 성공으로 끝내지 않는다.
  return posts.summary.conflict + comments.summary.conflict > 0 ? 2 : 0;
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  main().then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      console.error(String(error?.message ?? error));
      process.exitCode = 1;
    }
  );
}
