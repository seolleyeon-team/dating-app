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
    // 생활권 테스트 fixture. 성비는 별도 테스트에서 다룬다.
    gender: "male",
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

// 3:3 에서 한 팀은 동성 3명이다. 6인 pool 은 남성 팀 + 여성 팀으로 만든다.
function zonedTeam(
  prefix: string,
  zones: string[],
  gender: Candidate["gender"] = "male"
): Candidate[] {
  const roles: Candidate["initiative"][] = [
    "initiator",
    "adaptive",
    "listener",
  ];
  return roles.map((initiative, index) =>
    candidate(`${prefix}${index}`, {
      gender,
      initiative,
      campusLifeZones: zones,
    })
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
  const songdoTeam = () => zonedTeam("o", ["songdo"], "female");

  it("OFF 면 생활권이 달라도 6인 구성이 가능하다", () => {
    const pool = [...sinchonTeam(), ...songdoTeam()];
    // ON (기본값) 에서는 불가
    assert.equal(bestGroup(pool, DATE, false), null);
    // OFF 면 기존 정책만 적용되어 구성된다
    const group = bestGroup(pool, DATE, false, CURRENT_MATCHING_CONFIG, false);
    assert.ok(group != null, "OFF 에서는 기존 동작이 유지되어야 한다");
  });

  it("OFF 면 생활권 정보가 없어도 구성 가능하다", () => {
    const pool = [...zonedTeam("a", []), ...zonedTeam("b", [], "female")];
    assert.equal(bestGroup(pool, DATE, false), null);
    assert.ok(bestGroup(pool, DATE, false, CURRENT_MATCHING_CONFIG, false) != null);
  });

  it("OFF 가 생활권 외의 조건까지 풀어주지는 않는다", () => {
    const blocked = [
      ...sinchonTeam(),
      ...zonedTeam("o", ["songdo"], "female").map((member, index) =>
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
    const teamB = zonedTeam("b", ["sinchon"], "female");
    const baseline = groupScore(
      teamA,
      teamB,
      CURRENT_MATCHING_CONFIG,
      false
    ).finalGroupScore;
    // 빈자리는 teamA(남성)의 a0 이므로 대체 후보도 남성이어야 한다.
    const crossZone = candidate("x", {
      gender: "male",
      campusLifeZones: ["songdo"],
    });

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
      [
        ...zonedTeam("a", ["sinchon"]),
        ...zonedTeam("b", ["sinchon", "songdo"], "female"),
      ],
      DATE,
      false
    );
    assert.ok(ok != null, "dual-zone bridge 는 ON 에서도 허용된다");
  });
});
