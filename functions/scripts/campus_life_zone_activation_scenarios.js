/**
 * 생활권 rollout activation — Functions 시나리오 (Firestore 에뮬레이터).
 *
 * 컴파일된 production 코드(lib/)를 그대로 불러 flag OFF / ON 두 상태에서
 * 3:3 시즌 미팅 룰렛과 3:3 블라인드 취향 미팅 매칭이 어떻게 달라지는지 본다.
 * OFF 는 "생활권 조건만" 비활성이어야 하고, 나머지 조건은 그대로여야 한다.
 *
 * 실행 (Firestore 에뮬레이터 필요. JDK 21 미만이면 firebase-tools 13 을 쓴다):
 *   cd functions && npm run build
 *   firebase emulators:exec --only firestore --project seolleyeon-activation-test  *     "node scripts/campus_life_zone_activation_scenarios.js"
 *
 * production 프로젝트에 붙이지 않는다. 에뮬레이터 전용이다.
 */

const assert = require("node:assert/strict");
const admin = require("firebase-admin");

// production 코드(lib/index.js)가 default app 을 초기화하므로 먼저 불러온다.
const index = require("../lib/index.js");
const activation = require("../lib/campusLifeZoneActivation.js");
const orchestrator = require("../lib/blindMeeting/orchestrator.js");

const db = admin.firestore();

const DATE_KEY = (() => {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return y + m + d;
})();

// 블라인드 미팅은 YYYY-MM-DD 형식의 날짜 키를 쓴다 (시즌 미팅은 compact).
const BLIND_DATE_KEY = (() => {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return y + "-" + m + "-" + d;
})();

async function clear() {
  const collections = await db.listCollections();
  for (const col of collections) {
    const docs = await col.listDocuments();
    for (const doc of docs) {
      await db.recursiveDelete(doc);
    }
  }
}

async function setEnforced(value) {
  if (value === null) {
    await db.doc("recommendationConfig/current").delete();
  } else {
    await db.doc("recommendationConfig/current").set({
      campusLifeZoneEnforced: value,
    });
  }
  activation.resetCampusLifeZoneActivationCache();
}

function member(uid, zones) {
  return {
    uid: uid,
    displayName: uid,
    photoUrl: null,
    universityId: "yonsei",
    universityName: "연세대학교",
    mannerScore: 36.5,
    isVerified: true,
    shortIntro: null,
    birthYear: 2002,
    major: "컴퓨터과학과",
    campusLifeZones: zones,
  };
}

async function seedUser(uid, zones, gender) {
  await db.doc("users/" + uid).set({
    userId: uid,
    nickname: uid,
    gender: gender,
    birthYear: 2002,
    isVerified: true,
    isStudentVerified: true,
    studentEmail: uid + "@yonsei.ac.kr",
    schoolVerified: true,
    isActive: true,
    status: "active",
    universityId: "yonsei",
    universityName: "연세대학교",
    mannerScore: 36.5,
    initialSetupComplete: true,
    onboarding: { campusLifeZones: zones, major: "컴퓨터과학과" },
    campusLifeZones: zones,
  });
}

async function seedTeam(setupId, uids, zones, gender) {
  for (const uid of uids) {
    await seedUser(uid, zones, gender);
  }
  await db.doc("eventTeamSetups/" + setupId).set({
    leaderUserId: uids[0],
    acceptedUserIds: uids,
    status: "ready",
    memberCount: 3,
  });
  await db.doc("meetingGroups/" + setupId).set({
    groupId: setupId,
    sourceSetupId: setupId,
    memberUids: uids,
    memberCount: 3,
    size: 3,
    status: "open",
    active: true,
    isEligibleForMeetingRec: true,
    sharedCampusLifeZones: zones,
    membersSnapshot: uids.map(function (uid) {
      return member(uid, zones);
    }),
  });
}

async function seedRecommendation(fromSetupId, candidateGroupIds) {
  await db
    .doc("meetingDailyRecs/" + fromSetupId + "/days/" + DATE_KEY)
    .set({
      status: "ready",
      candidates: candidateGroupIds.map(function (groupId, i) {
        return {
          groupId: groupId,
          scoreTotal: 1 - i * 0.1,
          position: i + 1,
          isExplore: false,
          matchedPairs: [],
        };
      }),
    });
}

async function spin(uid, teamSetupId) {
  return await index.spinSeasonMeetingRoulette.run({
    auth: { uid: uid, token: {} },
    data: { teamSetupId: teamSetupId },
    rawRequest: { body: {} },
    acceptsStreaming: false,
  });
}

async function scenarioSeasonCrossZone() {
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], ["songdo"], "female");
  await seedRecommendation("teamA", ["teamB"]);

  // OFF: 생활권이 달라도 기존처럼 룰렛이 돌아간다.
  await setEnforced(false);
  const off = await spin("a1", "teamA");
  assert.ok(off && off.result, "OFF 면 결과가 나와야 한다");
  console.log("  season OFF cross-zone -> ok");

  // ON: 생활권이 다르면 후보가 없다.
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], ["songdo"], "female");
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(true);
  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /추천 가능한 상대 팀이 없어요/.test(String(err.message));
    },
    "ON 이면 다른 생활권 팀은 후보에서 제외돼야 한다"
  );
  console.log("  season ON cross-zone -> blocked");
}

async function scenarioSeasonMissingZone() {
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], [], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], [], "female");
  await seedRecommendation("teamA", ["teamB"]);

  // OFF: 생활권이 아예 없어도 기존 사용자가 막히지 않는다.
  await setEnforced(false);
  const off = await spin("a1", "teamA");
  assert.ok(off && off.result, "OFF 면 생활권이 없어도 결과가 나와야 한다");
  console.log("  season OFF missing-zone -> ok");

  await setEnforced(true);
  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /생활권 정보가 필요해요/.test(String(err.message));
    },
    "ON 이면 생활권 미설정 팀은 fail-closed"
  );
  console.log("  season ON missing-zone -> blocked");
}

async function scenarioSeasonSameZoneAlwaysWorks() {
  for (const flag of [false, true]) {
    await clear();
    await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
    await seedTeam("teamB", ["b1", "b2", "b3"], ["sinchon", "songdo"], "female");
    await seedRecommendation("teamA", ["teamB"]);
    await setEnforced(flag);
    const res = await spin("a1", "teamA");
    assert.ok(res && res.result, "flag=" + flag + " 에서 같은 생활권 팀은 항상 연결된다");
  }
  console.log("  season same-zone (dual-zone bridge) -> ok in both states");
}

async function scenarioSeasonOffKeepsOtherRules() {
  // OFF 가 생활권 외의 조건까지 풀어주면 안 된다: 멤버가 겹치는 팀은 제외.
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
  await seedTeam("teamB", ["a1", "b2", "b3"], ["songdo"], "female");
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(false);
  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /추천 가능한 상대 팀이 없어요/.test(String(err.message));
    },
    "OFF 여도 멤버가 겹치는 팀은 제외돼야 한다"
  );
  console.log("  season OFF keeps non-zone rules -> ok");
}

async function scenarioMissingConfigDocIsOff() {
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], [], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], [], "female");
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(null); // 문서 자체가 없는 상태 = 배포 직후
  const res = await spin("a1", "teamA");
  assert.ok(res && res.result, "config 문서가 없으면 OFF 로 동작해야 한다");
  console.log("  season missing config doc -> treated as OFF");
}

async function seedBlindApplication(uid, zones, gender, dateKeys, initiative) {
  await seedUser(uid, zones, gender);
  await db.doc("blindMeetingApplications/" + uid).set({
    userId: uid,
    status: "applied",
    stage: "searchingCandidates",
    open: true,
    requestedDateKeys: dateKeys,
    isAlcoholFree: false,
    appliedAt: admin.firestore.FieldValue.serverTimestamp(),
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
  await db.doc("blindMeetingDna/" + uid).set({
    userId: uid,
    conversationAtmosphere: "calm",
    conversationInitiative: initiative,
    meetingPurpose: "both",
    alcoholCompanionPreference: "noPreference",
    smokingCompanionPreference: "noPreference",
    drinkingLevelSnapshot: "sometimes",
    smokingStatusSnapshot: "nonSmoker",
    interestIds: ["커피", "영화"],
    mbtiSnapshot: "ENFP",
    availableDateKeys: dateKeys,
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
}

const ROLES = ["initiator", "adaptive", "listener"];

async function seedBlindPool(maleZones, femaleZones) {
  for (let i = 0; i < 3; i += 1) {
    await seedBlindApplication("m" + i, maleZones, "male", [BLIND_DATE_KEY], ROLES[i]);
    await seedBlindApplication("f" + i, femaleZones, "female", [BLIND_DATE_KEY], ROLES[i]);
  }
}

async function scenarioBlindCrossZone() {
  for (const flag of [false, true]) {
    await clear();
    await seedBlindPool(["sinchon"], ["songdo"]);
    await setEnforced(flag);
    const meetingIds = await orchestrator.runMatchingForDate(BLIND_DATE_KEY);
    if (flag) {
      assert.equal(meetingIds.length, 0, "ON 이면 생활권이 다른 6인은 매칭되지 않는다");
      console.log("  blind ON cross-zone -> no meeting");
    } else {
      assert.ok(meetingIds.length > 0, "OFF 면 기존처럼 매칭된다");
      console.log("  blind OFF cross-zone -> matched");
    }
  }
}

async function scenarioBlindMissingZone() {
  for (const flag of [false, true]) {
    await clear();
    await seedBlindPool([], []);
    await setEnforced(flag);
    const meetingIds = await orchestrator.runMatchingForDate(BLIND_DATE_KEY);
    if (flag) {
      assert.equal(meetingIds.length, 0, "ON 이면 생활권 미설정은 fail-closed");
      console.log("  blind ON missing-zone -> no meeting");
    } else {
      assert.ok(meetingIds.length > 0, "OFF 면 생활권이 없어도 매칭된다");
      console.log("  blind OFF missing-zone -> matched");
    }
  }
}

async function scenarioBlindSameZone() {
  for (const flag of [false, true]) {
    await clear();
    await seedBlindPool(["sinchon"], ["sinchon"]);
    await setEnforced(flag);
    const meetingIds = await orchestrator.runMatchingForDate(BLIND_DATE_KEY);
    assert.ok(meetingIds.length > 0, "같은 생활권은 flag=" + flag + " 에서 항상 매칭된다");
  }
  console.log("  blind same-zone -> matched in both states");
}

/**
 * 생활권 보충(repair) 이후 publicProfiles 투영까지 실제로 이어지는지.
 *
 * 클라이언트는 타인 문서를 publicProfiles 로만 읽으므로, users 에만 값이
 * 생기고 투영이 빠지면 ON 전환 시 모든 후보가 fail-closed 로 사라진다.
 */
async function scenarioRepairSyncsPublicProfile() {
  const sync = require("../lib/publicProfileSync.js");
  await clear();

  // 생활권이 계산된 적이 없는 기존 사용자 (필드 자체가 없다).
  await db.doc("users/repair-user").set({
    userId: "repair-user",
    nickname: "repair-user",
    gender: "female",
    birthYear: 2002,
    isVerified: true,
    isStudentVerified: true,
    studentEmail: "repair-user@yonsei.ac.kr",
    isActive: true,
    status: "active",
    initialSetupComplete: true,
    onboarding: { nickname: "repair-user", major: "컴퓨터과학과" },
  });
  await sync.syncPublicProfileForUser(
    db,
    "repair-user",
    (await db.doc("users/repair-user").get()).data()
  );
  const before = await db.doc("publicProfiles/repair-user").get();
  const beforeOnboarding = (before.data() || {}).onboarding || {};
  assert.equal(
    beforeOnboarding.campusLifeZones,
    undefined,
    "보충 전에는 생활권 필드가 없다"
  );

  // 보충 write (온보딩 저장 경로가 users 문서에 기록한 결과와 같은 모양).
  await db.doc("users/repair-user").set(
    { onboarding: { campusLifeZones: ["sinchon", "songdo"] } },
    { merge: true }
  );
  const afterData = (await db.doc("users/repair-user").get()).data();
  const result = await sync.syncPublicProfileForUser(db, "repair-user", afterData);
  assert.equal(result, "upserted");

  const after = await db.doc("publicProfiles/repair-user").get();
  const zones = after.data().onboarding.campusLifeZones;
  assert.deepEqual(
    zones,
    ["sinchon", "songdo"],
    "이중 생활권이 잘리지 않고 그대로 투영돼야 한다"
  );

  // 같은 값으로 다시 저장하면 쓰기가 발생하지 않는다.
  const again = await sync.syncPublicProfileForUser(db, "repair-user", afterData);
  assert.equal(again, "unchanged");
  console.log("  repair -> users -> publicProfiles (dual-zone 보존) -> ok");
}

/**
 * 손상된 생활권 값은 활성화 상태에서 생활권으로 인정되지 않는다.
 *
 * canonical 은 sinchon / songdo 뿐이다. 손상된 문서를 부분적으로 신뢰해
 * 실제로 만날 수 없는 팀을 붙이면 안 된다.
 */
async function scenarioMalformedZonesFailClosed() {
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["garbage"], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], ["garbage"], "female");
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(true);

  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /생활권 정보가 필요해요/.test(String(err.message));
    },
    "ON 에서 손상된 값은 생활권으로 인정되지 않는다"
  );
  console.log("  season ON malformed zones -> fail-closed");

  // 한쪽만 손상된 경우도 붙지 않는다.
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], ["sinchon", "garbage"], "female");
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(true);
  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /추천 가능한 상대 팀이 없어요/.test(String(err.message));
    },
    "canonical 이 아닌 토큰이 섞이면 그 팀은 후보가 아니다"
  );
  console.log("  season ON partially malformed -> excluded");
}

/**
 * raw string 으로 저장된 손상 문서는 생활권이 없는 것으로 본다 (§12).
 */
async function scenarioRawStringZoneIsInvalid() {
  await clear();
  await seedTeam("teamA", ["a1", "a2", "a3"], ["sinchon"], "male");
  await seedTeam("teamB", ["b1", "b2", "b3"], ["sinchon"], "female");
  // users 문서를 손상된 스키마로 덮어쓴다 (List 가 아니라 문자열).
  for (const uid of ["b1", "b2", "b3"]) {
    await db.doc("users/" + uid).set(
      { onboarding: { campusLifeZones: "sinchon" } },
      { merge: true }
    );
  }
  await db.doc("meetingGroups/teamB").set(
    {
      sharedCampusLifeZones: "sinchon",
      membersSnapshot: ["b1", "b2", "b3"].map(function (uid) {
        const m = member(uid, []);
        m.campusLifeZones = "sinchon";
        return m;
      }),
    },
    { merge: true }
  );
  await seedRecommendation("teamA", ["teamB"]);
  await setEnforced(true);

  await assert.rejects(
    function () {
      return spin("a1", "teamA");
    },
    function (err) {
      return /추천 가능한 상대 팀이 없어요/.test(String(err.message));
    },
    "raw string 스키마는 생활권으로 인정되지 않는다"
  );
  console.log("  season ON raw-string zone -> excluded");
}

/**
 * 활성화 상태를 확인하지 못하면 어느 쪽으로도 가정하지 않는다.
 *
 * 에뮬레이터에서는 config 문서 읽기만 실패시키기 어려우므로, activation
 * 모듈의 cold-start 판정을 직접 확인한다 (같은 코드 경로).
 */
async function scenarioActivationUnknownIsNotFailOpen() {
  const failing = {
    collection: function () {
      return {
        doc: function () {
          return {
            get: async function () {
              throw new Error("deadline exceeded");
            },
          };
        },
      };
    },
  };

  activation.resetCampusLifeZoneActivationCache();
  const cold = await activation.loadCampusLifeZoneActivation(failing);
  assert.equal(cold.state, "unknown", "cold start + 조회 실패는 unknown 이다");

  // last-known ON 이면 조회가 실패해도 ON 을 유지한다.
  activation.resetCampusLifeZoneActivationCache();
  await setEnforced(true);
  const known = await activation.loadCampusLifeZoneActivation(db);
  assert.equal(known.state, "enforced");
  const afterFailure = await activation.loadCampusLifeZoneActivation(failing, {
    now: Date.now() + 60_000,
  });
  assert.equal(
    afterFailure.state,
    "enforced",
    "활성화된 뒤의 일시적 장애가 정책을 끄면 안 된다"
  );
  assert.equal(afterFailure.staleFallback, true);

  // last-known OFF 면 조회가 실패해도 OFF 를 유지한다.
  activation.resetCampusLifeZoneActivationCache();
  await setEnforced(false);
  assert.equal((await activation.loadCampusLifeZoneActivation(db)).state, "off");
  const offAfterFailure = await activation.loadCampusLifeZoneActivation(failing, {
    now: Date.now() + 60_000,
  });
  assert.equal(
    offAfterFailure.state,
    "off",
    "준비 단계의 장애가 정책을 켜서도 안 된다"
  );
  activation.resetCampusLifeZoneActivationCache();
  console.log("  activation unknown / last-known-good -> ok");
}

/**
 * 정책 상태를 모르면 블라인드 매칭은 이번 실행을 건너뛴다.
 * (cross-zone 미팅을 만드는 것도, 정상 신청자를 전부 떨어뜨리는 것도 안 된다)
 */
async function scenarioBlindSkipsWhenActivationUnknown() {
  await clear();
  await seedBlindPool(["sinchon"], ["sinchon"]);
  await setEnforced(false);
  const matched = await orchestrator.runMatchingForDate(BLIND_DATE_KEY);
  assert.ok(matched.length > 0, "정상 상태에서는 매칭된다");

  // 같은 입력에서 activation 조회만 실패하게 만든다.
  await clear();
  await seedBlindPool(["sinchon"], ["sinchon"]);
  activation.resetCampusLifeZoneActivationCache();
  const original = activation.loadCampusLifeZoneActivation;
  activation.loadCampusLifeZoneActivation = async function () {
    return { state: "unknown", policyVersion: 0, staleFallback: false };
  };
  try {
    const skipped = await orchestrator.runMatchingForDate(BLIND_DATE_KEY);
    assert.equal(skipped.length, 0, "상태를 모르면 6인을 확정하지 않는다");
  } finally {
    activation.loadCampusLifeZoneActivation = original;
  }
  console.log("  blind activation unknown -> matching skipped");
}

async function main() {
  const scenarios = [
    ["season / 생활권이 다른 팀", scenarioSeasonCrossZone],
    ["season / 생활권 미설정", scenarioSeasonMissingZone],
    ["season / 같은 생활권", scenarioSeasonSameZoneAlwaysWorks],
    ["season / OFF 가 다른 규칙을 풀지 않음", scenarioSeasonOffKeepsOtherRules],
    ["season / config 문서 없음", scenarioMissingConfigDocIsOff],
    ["blind / 생활권이 다른 6인", scenarioBlindCrossZone],
    ["blind / 생활권 미설정 6인", scenarioBlindMissingZone],
    ["blind / 같은 생활권 6인", scenarioBlindSameZone],
    ["repair / publicProfiles 투영", scenarioRepairSyncsPublicProfile],
    ["hardening / 손상된 생활권 값", scenarioMalformedZonesFailClosed],
    ["hardening / raw string 스키마", scenarioRawStringZoneIsInvalid],
    ["hardening / activation unknown", scenarioActivationUnknownIsNotFailOpen],
    ["hardening / blind activation unknown", scenarioBlindSkipsWhenActivationUnknown],
  ];
  let failed = 0;
  for (const entry of scenarios) {
    console.log("\n[scenario] " + entry[0]);
    try {
      await entry[1]();
    } catch (err) {
      failed += 1;
      console.error("  FAILED: " + (err && err.message));
      if (process.env.VERBOSE) console.error(err);
    }
  }
  console.log(
    "\n" + (failed === 0 ? "ALL SCENARIOS PASSED" : failed + " SCENARIO(S) FAILED")
  );
  process.exit(failed === 0 ? 0 : 1);
}

main().catch(function (err) {
  console.error(err);
  process.exit(1);
});
