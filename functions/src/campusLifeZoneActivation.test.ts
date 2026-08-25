import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  CAMPUS_LIFE_ZONE_ENFORCED_FIELD,
  RECOMMENDATION_CONFIG_COLLECTION,
  RECOMMENDATION_CONFIG_DOC,
  campusLifeZoneEnforcedFromConfig,
} from "./campusLifeZoneActivation";
import {
  bestGroup,
  checkGroupConstraints,
  evaluateReplacement,
  groupScore,
  isGroupAllowed,
  type Candidate,
} from "./blindMeeting/matching";
import { CURRENT_MATCHING_CONFIG } from "./blindMeeting/matchingConfig";

const DATE = "2026-08-01";

function candidate(
  userId: string,
  overrides: Partial<Candidate> = {}
): Candidate {
  return {
    userId,
    atmosphere: "calm",
    initiative: "adaptive",
    purpose: "both",
    alcoholPreference: "noPreference",
    smokingPreference: "noPreference",
    drinkingLevel: "sometimes",
    smokingStatus: "nonSmoker",
    interestIds: ["커피", "영화"],
    mbti: "ENFP",
    availableDateKeys: [DATE],
    campusLifeZones: ["sinchon"],
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
    ...overrides,
  };
}

function zonedTeam(prefix: string, zones: string[]): Candidate[] {
  const roles: Candidate["initiative"][] = [
    "initiator",
    "adaptive",
    "listener",
  ];
  return roles.map((initiative, index) =>
    candidate(`${prefix}${index}`, { initiative, campusLifeZones: zones })
  );
}

describe("campus life zone rollout activation", () => {
  it("config 문서가 없거나 비어 있으면 OFF 로 본다", () => {
    assert.equal(campusLifeZoneEnforcedFromConfig(null), false);
    assert.equal(campusLifeZoneEnforcedFromConfig(undefined), false);
    assert.equal(campusLifeZoneEnforcedFromConfig({}), false);
  });

  it("정확히 boolean true 일 때만 ON 이다", () => {
    assert.equal(
      campusLifeZoneEnforcedFromConfig({
        [CAMPUS_LIFE_ZONE_ENFORCED_FIELD]: true,
      }),
      true
    );
    assert.equal(
      campusLifeZoneEnforcedFromConfig({
        [CAMPUS_LIFE_ZONE_ENFORCED_FIELD]: false,
      }),
      false
    );
    // 느슨한 값은 활성화로 보지 않는다 (오탈자로 켜지면 안 된다).
    assert.equal(
      campusLifeZoneEnforcedFromConfig({
        [CAMPUS_LIFE_ZONE_ENFORCED_FIELD]: "true",
      }),
      false
    );
    assert.equal(
      campusLifeZoneEnforcedFromConfig({
        [CAMPUS_LIFE_ZONE_ENFORCED_FIELD]: 1,
      }),
      false
    );
  });

  it("config 위치가 기존 관례를 따른다", () => {
    assert.equal(RECOMMENDATION_CONFIG_COLLECTION, "recommendationConfig");
    assert.equal(RECOMMENDATION_CONFIG_DOC, "current");
  });
});

describe("blind meeting activation matrix", () => {
  const sinchonTeam = () => zonedTeam("s", ["sinchon"]);
  const songdoTeam = () => zonedTeam("o", ["songdo"]);

  it("OFF 면 생활권이 달라도 6인 구성이 가능하다", () => {
    const pool = [...sinchonTeam(), ...songdoTeam()];
    // ON (기본값) 에서는 불가
    assert.equal(bestGroup(pool, DATE, false), null);
    // OFF 면 기존 정책만 적용되어 구성된다
    const group = bestGroup(pool, DATE, false, CURRENT_MATCHING_CONFIG, false);
    assert.ok(group != null, "OFF 에서는 기존 동작이 유지되어야 한다");
  });

  it("OFF 면 생활권 정보가 없어도 구성 가능하다", () => {
    const pool = [...zonedTeam("a", []), ...zonedTeam("b", [])];
    assert.equal(bestGroup(pool, DATE, false), null);
    assert.ok(bestGroup(pool, DATE, false, CURRENT_MATCHING_CONFIG, false) != null);
  });

  it("OFF 가 생활권 외의 조건까지 풀어주지는 않는다", () => {
    const blocked = [
      ...sinchonTeam(),
      ...zonedTeam("o", ["songdo"]).map((member, index) =>
        index === 0
          ? { ...member, blockedUserIds: ["s0"] }
          : member
      ),
    ];
    const violations = checkGroupConstraints(
      blocked,
      DATE,
      false,
      6,
      false // 생활권 OFF
    );
    assert.ok(
      violations.includes("blockedContact"),
      "차단 조건은 OFF 와 무관하게 유지된다"
    );
    assert.ok(!violations.includes("campusLifeZoneMismatch"));
  });

  it("OFF 면 생활권 위반이 constraint 목록에 나타나지 않는다", () => {
    const members = [...sinchonTeam(), ...songdoTeam()];
    assert.ok(
      checkGroupConstraints(members, DATE, false, 6, true).includes(
        "campusLifeZoneMismatch"
      )
    );
    assert.ok(
      !checkGroupConstraints(members, DATE, false, 6, false).includes(
        "campusLifeZoneMismatch"
      )
    );
    assert.equal(isGroupAllowed(members, DATE, false, 6, false), true);
  });

  it("대체 참가자 경로도 activation 을 따른다", () => {
    const teamA = zonedTeam("a", ["sinchon"]);
    const teamB = zonedTeam("b", ["sinchon"]);
    const baseline = groupScore(
      teamA,
      teamB,
      CURRENT_MATCHING_CONFIG,
      false
    ).finalGroupScore;
    const crossZone = candidate("x", { campusLifeZones: ["songdo"] });

    const onResult = evaluateReplacement({
      teamA,
      teamB,
      vacantUserId: "a0",
      candidate: crossZone,
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
      config: CURRENT_MATCHING_CONFIG,
    });
    assert.equal(onResult.accepted, false);

    const offResult = evaluateReplacement({
      teamA,
      teamB,
      vacantUserId: "a0",
      candidate: crossZone,
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
      config: CURRENT_MATCHING_CONFIG,
      campusLifeZoneEnforced: false,
    });
    assert.equal(offResult.accepted, true, "OFF 면 생활권으로 거부하지 않는다");
  });

  it("ON 은 기존에 검증된 hard filter semantics 그대로다", () => {
    assert.equal(bestGroup([...sinchonTeam(), ...songdoTeam()], DATE, false), null);
    const ok = bestGroup(
      [...zonedTeam("a", ["sinchon"]), ...zonedTeam("b", ["sinchon", "songdo"])],
      DATE,
      false
    );
    assert.ok(ok != null, "dual-zone bridge 는 ON 에서도 허용된다");
  });
});
