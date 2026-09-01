/**
 * 3:3 블라인드 취향 미팅 — 성비 불변식 (3남 + 3녀) 회귀 테스트
 * 실행: npm --prefix functions test
 *
 * 최상위 system invariant:
 *   participantCount == 6 && male == 3 && female == 3 && unique == 6
 *
 * 3남 또는 3녀를 확보할 수 없으면 어떤 구성도 만들지 않는다.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  Candidate,
  bestGroup,
  checkGroupConstraints,
  proposeGroups,
} from "../matching";
import {
  BlindMeetingGender,
  classifyGenderShortage,
  normalizeBlindMeetingGender,
  readBlindMeetingGender,
  validateBlindThreeVsThreeParticipants,
} from "../genderBalance";

const DATE = "2026-08-01";

function candidate(
  userId: string,
  gender: BlindMeetingGender,
  overrides: Partial<Candidate> = {}
): Candidate {
  return {
    userId,
    gender,
    atmosphere: "calm",
    initiative: "adaptive",
    purpose: "both",
    alcoholPreference: "noPreference",
    smokingPreference: "noPreference",
    drinkingLevel: "sometimes",
    smokingStatus: "nonSmoker",
    interestIds: ["커피", "영화"],
    mbti: "ENFP",
    campusLifeZones: ["sinchon"],
    availableDateKeys: [DATE],
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
    ...overrides,
  };
}

/** 역할이 균형 잡힌 동성 N명. */
function pool(
  prefix: string,
  gender: BlindMeetingGender,
  count: number
): Candidate[] {
  const initiatives = ["initiator", "adaptive", "listener"] as const;
  return Array.from({ length: count }, (_, i) =>
    candidate(`${prefix}${i + 1}`, gender, {
      initiative: initiatives[i % 3],
    })
  );
}

function genderCounts(members: Candidate[]): { male: number; female: number } {
  return {
    male: members.filter((m) => m.gender === "male").length,
    female: members.filter((m) => m.gender === "female").length,
  };
}

/** 어떤 성공 결과든 항상 만족해야 하는 불변식. */
function assertCanonicalGroup(members: Candidate[]): void {
  assert.equal(members.length, 6, "참가자는 정확히 6명");
  assert.equal(new Set(members.map((m) => m.userId)).size, 6, "UID 6개 유일");
  const counts = genderCounts(members);
  assert.equal(counts.male, 3, `남성 3명이어야 한다 (실제 ${counts.male})`);
  assert.equal(counts.female, 3, `여성 3명이어야 한다 (실제 ${counts.female})`);
  const validation = validateBlindThreeVsThreeParticipants(
    members.map((m) => ({ userId: m.userId, gender: m.gender }))
  );
  assert.ok(validation.ok, `canonical validator 통과: ${validation.violations}`);
}

function membersOf(group: ReturnType<typeof bestGroup>): Candidate[] {
  assert.ok(group != null, "그룹이 생성되어야 한다");
  return [...group.teamA, ...group.teamB];
}

describe("성별 source of truth", () => {
  it("canonical 값만 인정한다", () => {
    assert.equal(normalizeBlindMeetingGender("male"), "male");
    assert.equal(normalizeBlindMeetingGender("FEMALE"), "female");
    assert.equal(normalizeBlindMeetingGender(" male "), "male");
  });

  it("canonical 이 아닌 값은 절대 male/female 로 추측하지 않는다", () => {
    for (const raw of [
      null,
      undefined,
      "",
      "other",
      "unknown",
      "남성",
      "여성",
      "m",
      "f",
      "MALEE",
      0,
      1,
      true,
      {},
    ]) {
      assert.equal(
        normalizeBlindMeetingGender(raw),
        null,
        `${JSON.stringify(raw)} 는 성별로 인정하지 않는다`
      );
    }
  });

  it("onboarding.gender 가 source of truth 이고 legacy 최상위로만 fallback 한다", () => {
    assert.equal(
      readBlindMeetingGender({
        onboarding: { gender: "female" },
        gender: "male",
      }),
      "female"
    );
    assert.equal(readBlindMeetingGender({ gender: "male" }), "male");
    assert.equal(
      readBlindMeetingGender({ onboarding: {}, gender: "male" }),
      "male"
    );
  });

  it("onboarding.gender 가 손상되면 다른 필드로 우회하지 않는다", () => {
    assert.equal(
      readBlindMeetingGender({
        onboarding: { gender: "unknown" },
        gender: "male",
      }),
      null
    );
  });
});

describe("canonical 3:3 참가자 검증기", () => {
  const roster = (males: number, females: number) => [
    ...Array.from({ length: males }, (_, i) => ({
      userId: `m${i + 1}`,
      gender: "male",
    })),
    ...Array.from({ length: females }, (_, i) => ({
      userId: `f${i + 1}`,
      gender: "female",
    })),
  ];

  it("3남 3녀 6명만 통과한다", () => {
    const result = validateBlindThreeVsThreeParticipants(roster(3, 3));
    assert.ok(result.ok);
    assert.deepEqual(result.counts, { male: 3, female: 3, unknown: 0 });
  });

  for (const [males, females] of [
    [4, 2],
    [2, 4],
    [5, 1],
    [1, 5],
    [6, 0],
    [0, 6],
  ]) {
    it(`${males}남 ${females}녀는 거부한다`, () => {
      const result = validateBlindThreeVsThreeParticipants(
        roster(males, females)
      );
      assert.equal(result.ok, false);
      assert.ok(result.violations.includes("genderImbalance"));
    });
  }

  it("5명/7명은 거부한다", () => {
    assert.equal(validateBlindThreeVsThreeParticipants(roster(3, 2)).ok, false);
    assert.equal(validateBlindThreeVsThreeParticipants(roster(4, 3)).ok, false);
  });

  it("중복 UID 를 6명으로 계산하지 않는다", () => {
    const dup = [
      { userId: "m1", gender: "male" },
      { userId: "m1", gender: "male" },
      { userId: "m3", gender: "male" },
      { userId: "f1", gender: "female" },
      { userId: "f2", gender: "female" },
      { userId: "f3", gender: "female" },
    ];
    const result = validateBlindThreeVsThreeParticipants(dup);
    assert.equal(result.ok, false);
    assert.ok(result.violations.includes("duplicateParticipant"));
    assert.equal(result.uniqueUserCount, 5);
  });

  it("성별 불명 참가자는 통과시키지 않는다", () => {
    const withUnknown = [
      { userId: "m1", gender: "male" },
      { userId: "m2", gender: "male" },
      { userId: "x1", gender: "other" },
      { userId: "f1", gender: "female" },
      { userId: "f2", gender: "female" },
      { userId: "f3", gender: "female" },
    ];
    const result = validateBlindThreeVsThreeParticipants(withUnknown);
    assert.equal(result.ok, false);
    assert.ok(result.violations.includes("unknownGender"));
  });

  it("부족 사유를 분류한다", () => {
    assert.equal(classifyGenderShortage(3, 3), null);
    assert.equal(classifyGenderShortage(5, 1), "INSUFFICIENT_FEMALE_CANDIDATES");
    assert.equal(classifyGenderShortage(1, 5), "INSUFFICIENT_MALE_CANDIDATES");
    assert.equal(classifyGenderShortage(6, 0), "INSUFFICIENT_FEMALE_CANDIDATES");
    assert.equal(classifyGenderShortage(0, 6), "INSUFFICIENT_MALE_CANDIDATES");
    assert.equal(
      classifyGenderShortage(2, 2),
      "INSUFFICIENT_BALANCED_CANDIDATES"
    );
  });
});

describe("그룹 제약: 성비", () => {
  it("6인 구성이 3남 3녀가 아니면 거부한다", () => {
    const members = [...pool("M", "male", 4), ...pool("F", "female", 2)];
    const violations = checkGroupConstraints(members, DATE, false, 6);
    assert.ok(violations.includes("genderImbalance"));
  });

  it("한 팀 안에 성별이 섞이면 거부한다", () => {
    const trio = [
      candidate("M1", "male"),
      candidate("M2", "male"),
      candidate("F1", "female"),
    ];
    const violations = checkGroupConstraints(trio, DATE, false, 3);
    assert.ok(violations.includes("mixedGenderTeam"));
  });

  it("정상 3남 3녀는 성비 위반이 없다", () => {
    const members = [...pool("M", "male", 3), ...pool("F", "female", 3)];
    const violations = checkGroupConstraints(members, DATE, false, 6);
    assert.equal(violations.includes("genderImbalance"), false);
    assert.equal(violations.includes("mixedGenderTeam"), false);
  });
});

describe("3남 + 3녀 선택 불변식", () => {
  it("Case 1: 남3 여3 → 3남 3녀", () => {
    const members = membersOf(
      bestGroup(
        [...pool("M", "male", 3), ...pool("F", "female", 3)],
        DATE,
        false
      )
    );
    assertCanonicalGroup(members);
  });

  it("Case 2: 남5 여5 → 3남 3녀", () => {
    const members = membersOf(
      bestGroup(
        [...pool("M", "male", 5), ...pool("F", "female", 5)],
        DATE,
        false
      )
    );
    assertCanonicalGroup(members);
  });

  it("Case 3: 남5 여1 → 그룹 없음", () => {
    assert.equal(
      bestGroup(
        [...pool("M", "male", 5), ...pool("F", "female", 1)],
        DATE,
        false
      ),
      null
    );
  });

  it("Case 4: 남1 여5 → 그룹 없음", () => {
    assert.equal(
      bestGroup(
        [...pool("M", "male", 1), ...pool("F", "female", 5)],
        DATE,
        false
      ),
      null
    );
  });

  it("남6 여0 → 그룹 없음 (점수가 높아도 6남 팀을 만들지 않는다)", () => {
    assert.equal(bestGroup(pool("M", "male", 6), DATE, false), null);
  });

  it("남0 여6 → 그룹 없음", () => {
    assert.equal(bestGroup(pool("F", "female", 6), DATE, false), null);
  });

  it("남2 여4 → 그룹 없음", () => {
    assert.equal(
      bestGroup(
        [...pool("M", "male", 2), ...pool("F", "female", 4)],
        DATE,
        false
      ),
      null
    );
  });

  it("성별 편중이 심해도(남10 여3) 정확히 3남 3녀", () => {
    const members = membersOf(
      bestGroup(
        [...pool("M", "male", 10), ...pool("F", "female", 3)],
        DATE,
        false
      )
    );
    assertCanonicalGroup(members);
  });

  it("Case 5: 차단 관계가 있어도 3남 3녀이거나 그룹 없음", () => {
    // 여성 4명 중 한 명이 남성 후보 전원과 상호 차단 → 나머지 3명으로 대체된다.
    const males = pool("M", "male", 3);
    const females = pool("F", "female", 4);
    females[0] = candidate("F1", "female", {
      initiative: "initiator",
      blockedUserIds: males.map((m) => m.userId),
    });
    const members = membersOf(bestGroup([...males, ...females], DATE, false));
    assertCanonicalGroup(members);
    assert.equal(
      members.some((m) => m.userId === "F1"),
      false,
      "차단된 후보는 그룹에 들어가지 않는다"
    );
  });

  it("차단 때문에 3녀를 못 채우면 5인 그룹을 만들지 않는다", () => {
    const males = pool("M", "male", 3);
    const females = pool("F", "female", 3);
    females[0] = candidate("F1", "female", {
      initiative: "initiator",
      blockedUserIds: [males[0].userId],
    });
    assert.equal(bestGroup([...males, ...females], DATE, false), null);
  });

  it("Case 6: 중복 UID 가 있어도 잘못된 그룹을 만들지 않는다", () => {
    const males = pool("M", "male", 3);
    const females = pool("F", "female", 3);
    // 같은 uid 가 두 번 등장 (손상된 pool).
    const corrupted = [
      ...males,
      males[0],
      ...females.slice(0, 2),
      females[0],
    ];
    const group = bestGroup(corrupted, DATE, false);
    if (group != null) {
      assertCanonicalGroup([...group.teamA, ...group.teamB]);
    }
  });

  it("같은 사용자가 male/female 양쪽에 들어가도 6인으로 계산하지 않는다", () => {
    const males = pool("M", "male", 3);
    const females = [
      candidate("M1", "female", { initiative: "initiator" }),
      candidate("F2", "female", { initiative: "adaptive" }),
      candidate("F3", "female", { initiative: "listener" }),
    ];
    const group = bestGroup([...males, ...females], DATE, false);
    assert.equal(group, null, "손상된 성별 중복 문서로 그룹을 만들지 않는다");
  });

  it("여러 그룹을 만들어도 각 그룹이 3남 3녀", () => {
    const groups = proposeGroups(
      [...pool("M", "male", 6), ...pool("F", "female", 6)],
      DATE,
      false,
      2
    );
    assert.ok(groups.length >= 1);
    for (const group of groups) {
      assertCanonicalGroup([...group.teamA, ...group.teamB]);
    }
    const all = groups.flatMap((g) =>
      [...g.teamA, ...g.teamB].map((m) => m.userId)
    );
    assert.equal(new Set(all).size, all.length);
  });

  it("teamA 와 teamB 는 각각 단일 성별이고 서로 다르다", () => {
    const group = bestGroup(
      [...pool("M", "male", 4), ...pool("F", "female", 4)],
      DATE,
      false
    );
    assert.ok(group != null);
    const teamAGenders = new Set(group.teamA.map((m) => m.gender));
    const teamBGenders = new Set(group.teamB.map((m) => m.gender));
    assert.equal(teamAGenders.size, 1);
    assert.equal(teamBGenders.size, 1);
    assert.notEqual([...teamAGenders][0], [...teamBGenders][0]);
  });

  it("결과는 deterministic 하다", () => {
    const input = [...pool("M", "male", 5), ...pool("F", "female", 5)];
    const first = bestGroup(input, DATE, false);
    const second = bestGroup([...input].reverse(), DATE, false);
    assert.ok(first != null && second != null);
    assert.equal(first.key, second.key);
  });
});

describe("성비 선택 품질", () => {
  it("점수가 낮은 후보 대신 성별별 상위 후보를 고른다", () => {
    // M4 / F4 는 분위기·관심사가 어긋나 점수가 낮다. 성비를 맞추느라
    // 굳이 이들을 넣지 않는다.
    const weak = { atmosphere: "lively" as const, interestIds: ["볼링"] };
    const males = [
      ...pool("M", "male", 3),
      candidate("M4", "male", { initiative: "adaptive", ...weak }),
    ];
    const females = [
      ...pool("F", "female", 3),
      candidate("F4", "female", { initiative: "adaptive", ...weak }),
    ];
    const members = membersOf(bestGroup([...males, ...females], DATE, false));
    assertCanonicalGroup(members);
    const ids = members.map((m) => m.userId).sort();
    assert.deepEqual(ids, ["F1", "F2", "F3", "M1", "M2", "M3"]);
  });
});
