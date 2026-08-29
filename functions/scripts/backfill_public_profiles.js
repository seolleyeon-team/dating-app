/**
 * publicProfiles 투영 백필 (derived data only).
 *
 * `publicProfiles/{uid}` 는 `users/{uid}` 에서 파생된 공개 투영이고,
 * `onUserPublicProfileSync` 트리거가 users 문서가 **쓰일 때만** 갱신한다.
 * 따라서 트리거 배포 이후 한 번도 수정되지 않은 계정은 투영 문서가 아예 없고,
 * 투영 스키마가 바뀐 뒤(예: campusLifeZones 추가) 다시 쓰이지 않은 계정은
 * 옛 스키마로 남는다. 1:1 추천은 상대 프로필을 publicProfiles 로만 읽으므로
 * 투영이 없으면 그 후보는 피드에서 사라진다.
 *
 * 이 스크립트는 **파생 데이터만** 다시 만든다.
 *   source: users/{uid}            (읽기만)
 *   target: publicProfiles/{uid}   (쓰기)
 *
 * 사용자 입력값을 추론하지 않는다. 생활권을 grade/department 로 계산하지 않고,
 * users 에 이미 저장된 값을 그대로 투영할 뿐이다. 투영 규칙은 production
 * 트리거와 **같은 함수**(buildPublicProfileFromUser / syncPublicProfileForUser)를
 * 그대로 쓴다 — 여기서 다시 구현하면 두 경로가 갈라진다.
 *
 * 기본은 dry-run 이다. 실제로 쓰려면 --apply 를 준다.
 *
 * 실행:
 *   cd functions && npm run build
 *   node scripts/backfill_public_profiles.js --project seolleyeon-final
 *   node scripts/backfill_public_profiles.js --project seolleyeon-final --apply
 *
 * 출력은 집계값만이며 uid 등 개인 식별 정보를 남기지 않는다.
 */
const admin = require("firebase-admin");
const { isDeepStrictEqual } = require("node:util");

const args = process.argv.slice(2);

function flag(name) {
  return args.includes("--" + name);
}

function option(name, fallback) {
  const index = args.indexOf("--" + name);
  if (index === -1 || index + 1 >= args.length) return fallback;
  return args[index + 1];
}

const PROJECT = option("project", process.env.GCLOUD_PROJECT);
const APPLY = flag("apply");
const LIMIT = option("limit", null);

if (!PROJECT) {
  console.error("--project 가 필요하다");
  process.exit(2);
}

admin.initializeApp({ projectId: PROJECT });
const db = admin.firestore();

const {
  buildPublicProfileFromUser,
  syncPublicProfileForUser,
} = require("../lib/publicProfileSync.js");

function zonesOf(data) {
  const onboarding =
    data && typeof data.onboarding === "object" && data.onboarding !== null
      ? data.onboarding
      : {};
  const raw = onboarding.campusLifeZones;
  return Array.isArray(raw) ? raw : null;
}

async function main() {
  const counts = {
    scanned: 0,
    alreadyCorrect: 0,
    wouldUpsert: 0,
    wouldDelete: 0,
    missingPublicProfile: 0,
    staleSchema: 0,
    sourceHasZone: 0,
    projectionWouldGainZone: 0,
    unchangedNoProjection: 0,
    errors: 0,
  };

  let query = db.collection("users");
  if (LIMIT) query = query.limit(Number(LIMIT));
  const snapshot = await query.get();

  for (const doc of snapshot.docs) {
    counts.scanned += 1;
    const uid = doc.id;
    const userData = doc.data() || {};

    let payload;
    try {
      payload = buildPublicProfileFromUser(uid, userData);
    } catch (error) {
      counts.errors += 1;
      continue;
    }

    const existingSnap = await db.collection("publicProfiles").doc(uid).get();
    const exists = existingSnap.exists;
    if (!exists) counts.missingPublicProfile += 1;

    if (zonesOf(userData) != null) counts.sourceHasZone += 1;

    if (payload == null) {
      // 탈퇴/비공개 계정: 투영이 있으면 지워야 한다.
      if (exists) counts.wouldDelete += 1;
      else counts.unchangedNoProjection += 1;
      if (APPLY) {
        try {
          await syncPublicProfileForUser(db, uid, userData);
        } catch (error) {
          counts.errors += 1;
        }
      }
      continue;
    }

    const currentData = exists ? existingSnap.data() || {} : null;
    let identical = false;
    if (currentData) {
      const { updatedAt: _ignored, ...currentProjection } = currentData;
      identical = isDeepStrictEqual(currentProjection, payload);
      if (!identical) counts.staleSchema += 1;
    }

    if (identical) {
      counts.alreadyCorrect += 1;
      continue;
    }

    counts.wouldUpsert += 1;
    const projectedZones =
      payload.onboarding && Array.isArray(payload.onboarding.campusLifeZones)
        ? payload.onboarding.campusLifeZones
        : null;
    const currentZones =
      currentData &&
      currentData.onboarding &&
      Array.isArray(currentData.onboarding.campusLifeZones)
        ? currentData.onboarding.campusLifeZones
        : null;
    if (projectedZones != null && currentZones == null) {
      counts.projectionWouldGainZone += 1;
    }

    if (APPLY) {
      try {
        await syncPublicProfileForUser(db, uid, userData);
      } catch (error) {
        counts.errors += 1;
      }
    }
  }

  console.log(
    JSON.stringify(
      { project: PROJECT, mode: APPLY ? "apply" : "dry-run", ...counts },
      null,
      2
    )
  );
  process.exit(counts.errors > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error("backfill failed:", error && error.message);
  process.exit(1);
});
