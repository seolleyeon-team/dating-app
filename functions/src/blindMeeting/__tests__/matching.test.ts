/**
 * 3:3 블라인드 취향 미팅 — 서버 매칭 엔진 테스트
 * 실행: npm --prefix functions test
 *
 * Node 20+ 내장 테스트 러너(node:test)를 사용한다 (추가 의존성 없음).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

import {
  Candidate,
  alcoholCompatibility,
  alcoholFreePool,
  alcoholToleranceScore,
  atmosphereCompatibility,
  bestGroup,
  checkGroupConstraints,
  groupCommonDateKeys,
  checkPairConstraints,
  evaluateReplacement,
  groupScore,
  initiativeBalanceScore,
  initiativeCompatibility,
  interestSimilarity,
  internalTeamScore,
  mbtiCompatibility,
  proposeGroups,
  purposeCompatibility,
  rankReplacements,
  smokingCompatibility,
  standardPool,
  waitingTimeBonus,
} from "../matching";
import {
  CURRENT_MATCHING_CONFIG,
  crossWeightsTotal,
  teamWeightsTotal,
} from "../matchingConfig";
import { interestTaxonomyFingerprint } from "../interestTaxonomy";
import {
  DEFAULT_POLICY,
  policyFromConfigDoc,
  refundAmountFor,
  resolveCancellation,
  resolveNoShowSanction,
} from "../policy";
import { buildNotificationIdempotencyKey } from "../../shared/notify";
import {
  BLIND_MEETING_AVAILABILITY_WINDOW_DAYS,
  canTransitionMeeting,
  commonDateKeys,
  dateKeyOfSlotId,
  dateKeysFromLegacySlots,
  fallbackSlotIdFor,
  isDateKeyWithinWindow,
  isValidDateKey,
  isValidSlotId,
  legacySlotIdsForDate,
  normalizeDateKeys,
  readDateKeys,
  selectableDateKeys,
  slotStartAt,
} from "../types";

const SLOT = "2026-08-01#evening";

/** 매칭 기준 날짜. 세부 시간은 매칭 조건이 아니다. */
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
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
    ...overrides,
  };
}

function balancedTeam(prefix: string): Candidate[] {
  return [
    candidate(`${prefix}1`, { initiative: "initiator" }),
    candidate(`${prefix}2`, { initiative: "adaptive" }),
    candidate(`${prefix}3`, { initiative: "listener" }),
  ];
}

describe("매칭 설정", () => {
  it("가중치 합이 1.0", () => {
    assert.ok(
      Math.abs(teamWeightsTotal(CURRENT_MATCHING_CONFIG.teamWeights) - 1) < 1e-9
    );
    assert.ok(
      Math.abs(crossWeightsTotal(CURRENT_MATCHING_CONFIG.crossWeights) - 1) <
        1e-9
    );
    assert.ok(
      Math.abs(
        teamWeightsTotal(CURRENT_MATCHING_CONFIG.alcoholFreeTeamWeights) - 1
      ) < 1e-9
    );
    assert.ok(
      Math.abs(
        crossWeightsTotal(CURRENT_MATCHING_CONFIG.alcoholFreeCrossWeights) - 1
      ) < 1e-9
    );
  });

  it("algorithmVersion이 고정되어 있다", () => {
    assert.equal(CURRENT_MATCHING_CONFIG.algorithmVersion, "blind_taste_v1");
  });
});

describe("관심사 taxonomy 사본", () => {
  it("Dart 원본과 같은 fingerprint를 가진다", () => {
    const fingerprint = interestTaxonomyFingerprint();
    assert.equal(fingerprint.categories, 9);
    assert.equal(fingerprint.labels, 150);
    assert.deepEqual(fingerprint.perCategory, {
      indoor: 19,
      outdoor: 31,
      food: 21,
      sports: 29,
      screen: 13,
      music: 11,
      game: 6,
      creative: 13,
      social: 7,
    });
  });
});

describe("미팅 목적 호환 matrix", () => {
  it("연애만 × 친구만 은 직접 충돌", () => {
    const result = purposeCompatibility("romance", "friendship");
    assert.equal(result.isDirectConflict, true);
    assert.equal(result.score, 0);
  });

  it("같은 목적은 높은 호환", () => {
    assert.equal(purposeCompatibility("romance", "romance").score, 1);
    assert.equal(purposeCompatibility("friendship", "friendship").score, 1);
    assert.equal(purposeCompatibility("both", "both").score, 1);
  });

  it("한쪽이 둘 다면 호환", () => {
    assert.equal(purposeCompatibility("romance", "both").score, 0.8);
    assert.equal(purposeCompatibility("friendship", "both").score, 0.8);
  });
});

describe("개별 요소 점수", () => {
  it("관심사: 같으면 1, 한쪽이 비면 0", () => {
    assert.equal(interestSimilarity(["커피"], ["커피"]), 1);
    assert.equal(interestSimilarity([], ["커피"]), 0);
  });

  it("관심사: 같은 카테고리면 0보다 크다", () => {
    const score = interestSimilarity(["커피"], ["와인"]);
    assert.ok(score > 0 && score < 1);
  });

  it("대화 분위기: 정반대는 낮고 either는 높다", () => {
    assert.equal(atmosphereCompatibility("calm", "calm"), 1);
    assert.equal(atmosphereCompatibility("calm", "lively"), 0.35);
    assert.ok(atmosphereCompatibility("either", "lively") > 0.8);
  });

  it("먼저 말하는 성향: 주도↔경청 최고, 경청↔경청 최저", () => {
    assert.equal(initiativeCompatibility("initiator", "listener"), 1);
    assert.equal(initiativeCompatibility("listener", "listener"), 0.25);
    assert.equal(
      initiativeCompatibility("initiator", "adaptive"),
      initiativeCompatibility("adaptive", "initiator")
    );
  });

  it("음주: 전원 비음주 선호는 음주자와 0", () => {
    assert.equal(alcoholToleranceScore("allSober", "sometimes"), 0);
    assert.equal(alcoholToleranceScore("allSober", "none"), 1);
    assert.equal(
      alcoholCompatibility(
        candidate("a", { alcoholPreference: "lightOkay", drinkingLevel: "none" }),
        candidate("b", { drinkingLevel: "often" })
      ),
      0.2
    );
  });

  it("흡연: 금연 중은 흡연자로 보지 않는다", () => {
    assert.equal(
      smokingCompatibility(
        candidate("a", { smokingPreference: "nonSmokersOnly" }),
        candidate("b", { smokingStatus: "quitting" })
      ),
      1
    );
    assert.equal(
      smokingCompatibility(
        candidate("a", { smokingPreference: "nonSmokersOnly" }),
        candidate("b", { smokingStatus: "smoker" })
      ),
      0
    );
  });

  it("MBTI: 값이 없으면 중립 0.5", () => {
    assert.equal(mbtiCompatibility(null, "ENFP"), 0.5);
    assert.equal(mbtiCompatibility("XXXX", "ENFP"), 0.5);
    assert.ok(mbtiCompatibility("ENFP", "INFJ") > 0.5);
  });
});

describe("팀 균형", () => {
  it("주도/상황/경청 1명씩이 최고", () => {
    const balanced = initiativeBalanceScore(
      ["initiator", "adaptive", "listener"],
      CURRENT_MATCHING_CONFIG
    );
    assert.ok(Math.abs(balanced - 1) < 1e-9);
  });

  it("전원 경청은 전원 주도보다 낮다", () => {
    const passive = initiativeBalanceScore(
      ["listener", "listener", "listener"],
      CURRENT_MATCHING_CONFIG
    );
    const dominant = initiativeBalanceScore(
      ["initiator", "initiator", "initiator"],
      CURRENT_MATCHING_CONFIG
    );
    assert.ok(passive < dominant);
    assert.ok(passive < 0.3);
  });

  it("미팅 목적이 충돌하면 목적 일관성 0", () => {
    const score = internalTeamScore(
      [
        candidate("c1", { purpose: "romance" }),
        candidate("c2", { purpose: "friendship" }),
        candidate("c3", { purpose: "both" }),
      ],
      CURRENT_MATCHING_CONFIG,
      false
    );
    assert.equal(score.purposeConsistency, 0);
  });
});

describe("6인 구성 점수", () => {
  it("crossTeamScore = 평균×0.70 + 최저×0.30", () => {
    const score = groupScore(
      balancedTeam("a"),
      balancedTeam("b"),
      CURRENT_MATCHING_CONFIG,
      false
    );
    const values = Object.values(score.participantOpponentScores);
    const mean = values.reduce((x, y) => x + y, 0) / values.length;
    const min = Math.min(...values);
    assert.ok(
      Math.abs(score.crossTeamScore - (mean * 0.7 + min * 0.3)) < 1e-9
    );
    assert.ok(Math.abs(score.minimumParticipantScore - min) < 1e-9);
  });

  it("finalGroupScore = 내부 평균×0.40 + crossTeam×0.60", () => {
    const score = groupScore(
      balancedTeam("a"),
      balancedTeam("b"),
      CURRENT_MATCHING_CONFIG,
      false
    );
    const internalMean = (score.teamAInternal + score.teamBInternal) / 2;
    assert.ok(
      Math.abs(
        score.finalGroupScore - (internalMean * 0.4 + score.crossTeamScore * 0.6)
      ) < 1e-9
    );
  });

  it("대기 시간 보정은 최대치를 넘지 않는다", () => {
    const bonus = waitingTimeBonus(
      [candidate("w1", { waitedMinutes: 100000 })],
      CURRENT_MATCHING_CONFIG
    );
    assert.ok(
      Math.abs(bonus - CURRENT_MATCHING_CONFIG.maxWaitingBonus) < 1e-9
    );
  });
});

describe("hard constraint", () => {
  it("차단 관계는 같은 미팅에 들어갈 수 없다", () => {
    const violations = checkPairConstraints(
      candidate("a", { blockedUserIds: ["b"] }),
      candidate("b")
    );
    assert.ok(violations.includes("blockedContact"));
  });

  it("최근에 만난 사용자는 제외된다", () => {
    const violations = checkPairConstraints(
      candidate("a", { recentlyMetUserIds: ["b"] }),
      candidate("b")
    );
    assert.ok(violations.includes("recentlyMet"));
  });

  it("비흡연자 전용 조건 위반", () => {
    const violations = checkPairConstraints(
      candidate("a", { smokingPreference: "nonSmokersOnly" }),
      candidate("b", { smokingStatus: "smoker" })
    );
    assert.ok(violations.includes("smokingRejected"));
  });

  it("학교 인증/제재/날짜 불가 후보는 제외된다", () => {
    const violations = checkGroupConstraints(
      [
        candidate("a", { schoolVerified: false }),
        candidate("b", { eligible: false }),
        candidate("c", { availableDateKeys: ["2026-09-09"] }),
      ],
      DATE,
      false,
      3
    );
    assert.ok(violations.includes("notSchoolVerified"));
    assert.ok(violations.includes("notEligible"));
    assert.ok(violations.includes("dateUnavailable"));
  });

  it("기준 날짜를 못 쓰는 후보는 dateUnavailable 로 걸러진다", () => {
    const violations = checkGroupConstraints(
      [
        candidate("a", { availableDateKeys: [DATE, "2026-08-02"] }),
        candidate("b", { availableDateKeys: [DATE, "2026-08-03"] }),
        candidate("c", { availableDateKeys: ["2026-08-04"] }),
      ],
      DATE,
      false,
      3
    );
    assert.ok(violations.includes("dateUnavailable"));
  });

  it("전원이 기준 날짜를 쓸 수 있으면 공통 날짜는 항상 존재한다", () => {
    // hot path에서 교집합을 다시 계산하지 않아도 되는 근거.
    const members = [
      candidate("a", { availableDateKeys: [DATE, "2026-08-02"] }),
      candidate("b", { availableDateKeys: [DATE, "2026-08-03"] }),
      candidate("c", { availableDateKeys: [DATE] }),
    ];
    assert.equal(checkGroupConstraints(members, DATE, false, 3).length, 0);
    assert.deepEqual(groupCommonDateKeys(members), [DATE]);
  });

  it("동일 사용자 중복 참가를 막는다", () => {
    const violations = checkGroupConstraints(
      [candidate("a"), candidate("a"), candidate("b")],
      DATE,
      false,
      3
    );
    assert.ok(violations.includes("duplicateParticipant"));
  });
});

describe("날짜 전용 availability", () => {
  it("내일부터 21일, 총 21개 날짜를 만든다", () => {
    const nowMs = Date.UTC(2026, 6, 30, 3, 0, 0); // KST 2026-07-30 12:00
    const keys = selectableDateKeys(nowMs);
    assert.equal(keys.length, BLIND_MEETING_AVAILABILITY_WINDOW_DAYS);
    assert.equal(keys[0], "2026-07-31");
    assert.equal(keys[keys.length - 1], "2026-08-20");
  });

  it("오늘과 범위 밖 날짜를 거부한다", () => {
    const nowMs = Date.UTC(2026, 6, 30, 3, 0, 0);
    assert.equal(isDateKeyWithinWindow("2026-07-30", nowMs), false);
    assert.equal(isDateKeyWithinWindow("2026-07-29", nowMs), false);
    assert.equal(isDateKeyWithinWindow("2026-07-31", nowMs), true);
    assert.equal(isDateKeyWithinWindow("2026-08-20", nowMs), true);
    assert.equal(isDateKeyWithinWindow("2026-08-21", nowMs), false);
  });

  it("KST 자정 경계에서 날짜가 밀리지 않는다", () => {
    // UTC 2026-07-30 15:30 == KST 2026-07-31 00:30
    const nowMs = Date.UTC(2026, 6, 30, 15, 30, 0);
    assert.equal(selectableDateKeys(nowMs)[0], "2026-08-01");
  });

  it("달력에 없는 날짜와 형식 오류를 거부한다", () => {
    assert.equal(isValidDateKey("2026-02-30"), false);
    assert.equal(isValidDateKey("2026-13-01"), false);
    assert.equal(isValidDateKey("20260801"), false);
    assert.equal(isValidDateKey("2028-02-29"), true); // 윤년
  });

  it("중복을 제거하고 오름차순 정렬한다", () => {
    assert.deepEqual(
      normalizeDateKeys(["2026-08-03", "2026-08-01", "2026-08-03", "bad"]),
      ["2026-08-01", "2026-08-03"]
    );
  });

  it("legacy 슬롯에서 날짜만 복원한다", () => {
    assert.deepEqual(
      dateKeysFromLegacySlots([
        "2026-08-01#evening",
        "2026-08-01#lunch",
        "2026-08-05#afternoon",
      ]),
      ["2026-08-01", "2026-08-05"]
    );
  });

  it("날짜 전용 필드가 없으면 legacy 슬롯을 읽는다", () => {
    assert.deepEqual(readDateKeys(undefined, ["2026-08-02#evening"]), [
      "2026-08-02",
    ]);
    assert.deepEqual(readDateKeys(["2026-08-09"], ["2026-08-02#evening"]), [
      "2026-08-09",
    ]);
  });

  it("여섯 명 공통 날짜 교집합을 계산한다", () => {
    const common = commonDateKeys([
      ["2026-08-01", "2026-08-02", "2026-08-03"],
      ["2026-08-02", "2026-08-03"],
      ["2026-08-02", "2026-08-03", "2026-08-09"],
      ["2026-08-03", "2026-08-02"],
      ["2026-08-02"],
      ["2026-08-02", "2026-08-05"],
    ]);
    assert.deepEqual(common, ["2026-08-02"]);
  });

  it("공통 날짜가 없으면 빈 배열", () => {
    assert.deepEqual(
      commonDateKeys([["2026-08-01"], ["2026-08-02"]]),
      []
    );
  });

  it("legacy 슬롯 조회용 id를 만든다", () => {
    assert.deepEqual(legacySlotIdsForDate("2026-08-01"), [
      "2026-08-01#lunch",
      "2026-08-01#afternoon",
      "2026-08-01#evening",
      "2026-08-01#lateEvening",
    ]);
    assert.deepEqual(legacySlotIdsForDate("bad"), []);
  });

  it("슬롯 id에서 날짜를 뽑는다", () => {
    assert.equal(dateKeyOfSlotId(SLOT), "2026-08-01");
    assert.equal(dateKeyOfSlotId("2026-08-01#none"), null);
  });
});

describe("무알코올 후보군 분리", () => {
  it("전원 비음주 요구자는 일반 후보군에서 빠진다", () => {
    const strict = candidate("sober", {
      alcoholPreference: "allSober",
      drinkingLevel: "none",
    });
    const drinker = candidate("drinker");
    assert.deepEqual(
      standardPool([strict, drinker]).map((c) => c.userId),
      ["drinker"]
    );
  });

  it("무알코올 후보군에는 비음주만 남는다", () => {
    const pool = [
      candidate("s1", { drinkingLevel: "none" }),
      candidate("d1", { drinkingLevel: "often" }),
    ];
    assert.deepEqual(
      alcoholFreePool(pool).map((c) => c.userId),
      ["s1"]
    );
  });

  it("비음주 후보가 5명이면 구성되지 않는다 (자동 대체 없음)", () => {
    const pool = Array.from({ length: 5 }, (_, i) =>
      candidate(`s${i}`, {
        alcoholPreference: "allSober",
        drinkingLevel: "none",
      })
    );
    assert.equal(bestGroup(pool, DATE, true), null);
  });
});

describe("optimizer", () => {
  function pool(size: number): Candidate[] {
    const roles: Candidate["initiative"][] = [
      "initiator",
      "adaptive",
      "listener",
    ];
    return Array.from({ length: size }, (_, i) =>
      candidate(`u${i}`, { initiative: roles[i % 3] })
    );
  }

  it("6명이면 3:3 구성이 만들어진다", () => {
    const group = bestGroup(pool(6), DATE, false);
    assert.ok(group != null);
    assert.equal(group!.teamA.length, 3);
    assert.equal(group!.teamB.length, 3);
  });

  it("5명이면 구성되지 않는다", () => {
    assert.equal(bestGroup(pool(5), DATE, false), null);
  });

  it("입력 순서가 달라도 결과가 같다 (deterministic)", () => {
    const first = bestGroup(pool(9), DATE, false);
    const second = bestGroup([...pool(9)].reverse(), DATE, false);
    assert.ok(first != null && second != null);
    assert.equal(first!.key, second!.key);
  });

  it("동점이면 정렬된 id로 tie-break", () => {
    const identical = Array.from({ length: 6 }, (_, i) => candidate(`u${i}`));
    const group = bestGroup(identical, DATE, false);
    assert.equal(group!.key, "u0|u1|u2|u3|u4|u5");
  });

  it("연애만/친구만 사용자는 같은 미팅에 배정되지 않는다", () => {
    const roles: Candidate["initiative"][] = [
      "initiator",
      "adaptive",
      "listener",
    ];
    const candidates = [
      ...Array.from({ length: 3 }, (_, i) =>
        candidate(`r${i}`, { purpose: "romance", initiative: roles[i] })
      ),
      ...Array.from({ length: 3 }, (_, i) =>
        candidate(`f${i}`, { purpose: "friendship", initiative: roles[i] })
      ),
    ];
    assert.equal(bestGroup(candidates, DATE, false), null);
  });

  it("여러 구성은 서로 겹치지 않는다", () => {
    const groups = proposeGroups(pool(18), DATE, false, 3);
    assert.equal(groups.length, 3);
    const all = groups.flatMap((g) => [
      ...g.teamA.map((m) => m.userId),
      ...g.teamB.map((m) => m.userId),
    ]);
    assert.equal(new Set(all).size, all.length);
  });
});

describe("대체 후보", () => {
  const teamA = balancedTeam("a");
  const teamB = balancedTeam("b");
  const baseline = groupScore(
    teamA,
    teamB,
    CURRENT_MATCHING_CONFIG,
    false
  ).finalGroupScore;

  it("전체 6인 점수 기준으로 판정한다", () => {
    const evaluation = evaluateReplacement({
      teamA,
      teamB,
      vacantUserId: "b3",
      candidate: candidate("new", { initiative: "listener" }),
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
    });
    assert.deepEqual(evaluation.violations, []);
    assert.equal(evaluation.accepted, true);
  });

  it("hard constraint 위반은 긴급 상황에서도 거부된다", () => {
    const evaluation = evaluateReplacement({
      teamA,
      teamB,
      vacantUserId: "b3",
      candidate: candidate("bad", { eligible: false }),
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
      urgent: true,
    });
    assert.equal(evaluation.accepted, false);
    assert.ok(evaluation.violations.includes("notEligible"));
  });

  it("긴급 기준이 일반 기준보다 관대하다", () => {
    assert.ok(
      CURRENT_MATCHING_CONFIG.replacementUrgentRatio <
        CURRENT_MATCHING_CONFIG.replacementNormalRatio
    );
  });

  it("기존 참가자는 후보에서 제외된다", () => {
    const ranked = rankReplacements({
      teamA,
      teamB,
      vacantUserId: "b3",
      candidates: [candidate("a1"), candidate("c1", { initiative: "listener" })],
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
    });
    assert.ok(!ranked.some((r) => r.candidate.userId === "a1"));
  });

  it("상위 후보를 제한 개수만큼 순위대로 돌려준다", () => {
    const ranked = rankReplacements({
      teamA,
      teamB,
      vacantUserId: "b3",
      candidates: Array.from({ length: 6 }, (_, i) =>
        candidate(`cand${i}`, {
          initiative: "listener",
          waitedMinutes: i * 100,
        })
      ),
      baselineFinalGroupScore: baseline,
      dateKey: DATE,
      alcoholFree: false,
      limit: 3,
    });
    assert.equal(ranked.length, 3);
    for (let i = 1; i < ranked.length; i++) {
      assert.ok(ranked[i - 1].adjustedScore >= ranked[i].adjustedScore);
    }
  });
});

describe("Dart 기준 구현과의 골든 벡터 일치", () => {
  const fixture = JSON.parse(
    readFileSync(
      path.resolve(__dirname, "../../../../shared/blind_meeting_matching_vectors.json"),
      "utf8"
    )
  ) as {
    slotId: string;
    algorithmVersion: string;
    cases: {
      name: string;
      alcoholFree: boolean;
      teamA: Record<string, unknown>[];
      teamB: Record<string, unknown>[];
    }[];
    expected: Record<
      string,
      {
        internalTeamA: number;
        internalTeamB: number;
        crossTeamScore: number;
        minimumParticipantScore: number;
        finalGroupScore: number;
        participantOpponentScores: Record<string, number>;
      }
    >;
  };

  function hydrate(raw: Record<string, unknown>): Candidate {
    return candidate(String(raw.userId), {
      atmosphere: raw.atmosphere as Candidate["atmosphere"],
      initiative: raw.initiative as Candidate["initiative"],
      purpose: raw.purpose as Candidate["purpose"],
      alcoholPreference:
        raw.alcoholPreference as Candidate["alcoholPreference"],
      smokingPreference:
        raw.smokingPreference as Candidate["smokingPreference"],
      drinkingLevel: raw.drinkingLevel as Candidate["drinkingLevel"],
      smokingStatus: raw.smokingStatus as Candidate["smokingStatus"],
      interestIds: raw.interestIds as string[],
      mbti: (raw.mbti as string | null) ?? null,
      // 골든 벡터는 점수 계산만 검증한다. 날짜는 전원 동일하게 둔다.
      availableDateKeys: [DATE],
    });
  }

  it("algorithmVersion이 일치한다", () => {
    assert.equal(
      fixture.algorithmVersion,
      CURRENT_MATCHING_CONFIG.algorithmVersion
    );
  });

  for (const testCase of fixture.cases) {
    it(`${testCase.name} 벡터가 기대값과 같다`, () => {
      const expected = fixture.expected[testCase.name];
      assert.ok(expected, `expected vector missing: ${testCase.name}`);

      const teamA = testCase.teamA.map(hydrate);
      const teamB = testCase.teamB.map(hydrate);
      const internalA = internalTeamScore(
        teamA,
        CURRENT_MATCHING_CONFIG,
        testCase.alcoholFree
      );
      const internalB = internalTeamScore(
        teamB,
        CURRENT_MATCHING_CONFIG,
        testCase.alcoholFree
      );
      const group = groupScore(
        teamA,
        teamB,
        CURRENT_MATCHING_CONFIG,
        testCase.alcoholFree
      );

      assert.ok(Math.abs(internalA.total - expected.internalTeamA) < 1e-9);
      assert.ok(Math.abs(internalB.total - expected.internalTeamB) < 1e-9);
      assert.ok(
        Math.abs(group.crossTeamScore - expected.crossTeamScore) < 1e-9
      );
      assert.ok(
        Math.abs(
          group.minimumParticipantScore - expected.minimumParticipantScore
        ) < 1e-9
      );
      assert.ok(
        Math.abs(group.finalGroupScore - expected.finalGroupScore) < 1e-9
      );
      for (const [userId, value] of Object.entries(
        expected.participantOpponentScores
      )) {
        assert.ok(
          Math.abs(group.participantOpponentScores[userId] - value) < 1e-9,
          `${testCase.name}/${userId}`
        );
      }
    });
  }
});

describe("약속잡기 미확정 구간 취소", () => {
  // 날짜 전용 정책에서는 보증금을 낸 뒤에도 시간이 미확정인 구간이 있다.
  // 이 구간을 '남은 시간 0'으로 취급하면 무환급이 되어 위약금을 잘못 물린다.
  it("시작 시각이 없으면 전액 환급이다", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: null,
      replacementFound: false,
    });
    assert.equal(decision.outcome, "full_refund");
    assert.equal(decision.refundBasisPoints, 10000);
    assert.equal(decision.appliesRestriction, false);
  });

  it("시작 시각이 없어도 대체 성공 여부와 무관하게 전액 환급이다", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: null,
      replacementFound: true,
    });
    assert.equal(decision.outcome, "full_refund");
  });

  it("남은 시간 0(확정된 미팅 직전)은 여전히 무환급이다", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 0,
      replacementFound: false,
    });
    assert.equal(decision.outcome, "no_refund");
  });

  it("노쇼는 시작 시각이 없어도 제재 대상이다", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: null,
      replacementFound: false,
      isNoShowWithoutContact: true,
    });
    assert.equal(decision.outcome, "no_refund");
    assert.equal(decision.appliesRestriction, true);
  });
});

describe("약속잡기 자동 확정 정책", () => {
  it("투표 기한과 인라인 매칭 상한이 정의되어 있다", () => {
    assert.ok(DEFAULT_POLICY.scheduleVoteWindowMs > 0);
    assert.ok(DEFAULT_POLICY.inlineMatchingDateLimit >= 1);
    assert.ok(
      DEFAULT_POLICY.inlineMatchingDateLimit <
        BLIND_MEETING_AVAILABILITY_WINDOW_DAYS
    );
  });

  it("fallback 슬롯은 유효한 슬롯 id다", () => {
    const slotId = fallbackSlotIdFor("2026-08-02");
    assert.equal(isValidSlotId(slotId), true);
    assert.equal(dateKeyOfSlotId(slotId), "2026-08-02");
  });

  it("legacy 호환 조회는 정책으로 끌 수 있다", () => {
    const off = policyFromConfigDoc({ legacySlotCompatEnabled: 0 });
    assert.equal(off.legacySlotCompatEnabled, 0);
  });
});

describe("취소 및 환급 정책", () => {
  it("24시간 이전은 전액 환급", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 30 * 60 * 60 * 1000,
      replacementFound: false,
    });
    assert.equal(decision.outcome, "full_refund");
    assert.equal(decision.refundBasisPoints, 10000);
  });

  it("6~24시간 전은 대체 성공 시 전액, 실패 시 일부", () => {
    const found = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 10 * 60 * 60 * 1000,
      replacementFound: true,
    });
    const failed = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 10 * 60 * 60 * 1000,
      replacementFound: false,
    });
    assert.equal(found.outcome, "full_refund");
    assert.equal(failed.outcome, "partial_refund");
    assert.ok(failed.refundBasisPoints < 10000 && failed.refundBasisPoints > 0);
  });

  it("6시간 이내 대체 실패는 미환급", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 2 * 60 * 60 * 1000,
      replacementFound: false,
    });
    assert.equal(decision.outcome, "no_refund");
    assert.equal(decision.appliesRestriction, false);
  });

  it("연락 없는 노쇼는 미환급 + 참여 제한", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 0,
      replacementFound: false,
      isNoShowWithoutContact: true,
    });
    assert.equal(decision.outcome, "no_refund");
    assert.equal(decision.appliesRestriction, true);
  });

  it("응급 상황은 운영자 검토", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 30 * 60 * 1000,
      replacementFound: false,
      emergencyReviewRequested: true,
    });
    assert.equal(decision.outcome, "ops_review");
  });

  it("환급액은 basis point로 계산된다", () => {
    assert.equal(refundAmountFor(5000, 5000), 2500);
    assert.equal(refundAmountFor(5000, 0), 0);
  });

  it("노쇼 제재 단계", () => {
    assert.equal(resolveNoShowSanction(DEFAULT_POLICY, 1).restrictedDays, 14);
    assert.equal(resolveNoShowSanction(DEFAULT_POLICY, 2).restrictedDays, 30);
    const repeated = resolveNoShowSanction(DEFAULT_POLICY, 3);
    assert.ok(repeated.restrictedDays > 30);
    assert.equal(repeated.requiresOpsReview, true);
  });
});

describe("상태 전환", () => {
  it("정상 파이프라인만 허용한다", () => {
    assert.equal(canTransitionMeeting("forming", "awaiting_acceptance"), true);
    assert.equal(canTransitionMeeting("forming", "confirmed"), false);
    assert.equal(canTransitionMeeting("archived", "chat_open"), false);
    assert.equal(canTransitionMeeting("chat_open", "cancelled"), true);
  });
});

describe("슬롯 파싱", () => {
  it("형식을 검증한다", () => {
    assert.equal(isValidSlotId(SLOT), true);
    assert.equal(isValidSlotId("20260801#evening"), false);
    assert.equal(isValidSlotId("2026-08-01#none"), false);
  });

  it("KST 시작 시각을 UTC로 환산한다", () => {
    const start = slotStartAt(SLOT);
    assert.ok(start != null);
    // KST 18:00 == UTC 09:00
    assert.equal(start!.toISOString(), "2026-08-01T09:00:00.000Z");
  });
});

describe("알림 idempotency", () => {
  it("같은 이벤트는 같은 key를 만든다", () => {
    const a = buildNotificationIdempotencyKey([
      "blind_meeting",
      "matched",
      "m1",
      "u1",
      undefined,
    ]);
    const b = buildNotificationIdempotencyKey([
      "blind_meeting",
      "matched",
      "m1",
      "u1",
    ]);
    assert.equal(a, b);
    assert.equal(a, "blind_meeting_matched_m1_u1");
  });

  it("구분자가 다르면 key가 달라진다", () => {
    const a = buildNotificationIdempotencyKey(["x", "m1", "u1", "first"]);
    const b = buildNotificationIdempotencyKey(["x", "m1", "u1", "second"]);
    assert.notEqual(a, b);
  });
});
