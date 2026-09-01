/**
 * 3:3 블라인드 취향 미팅 — 후보 hydration 의 fail-closed 관문 테스트
 * 실행: npm --prefix functions test
 *
 * 여기서 걸러야 점수 계산과 상위 랭킹 이전에 부적격자가 사라진다
 * (filter-before-rank). 관대한 기본값으로 보정하면 잘못된 자리에 앉힌다.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildCandidate } from "../store";
import { resolveBlindMeetingHandler, BLIND_MEETING_ACTIONS } from "../callables";

const DATE = "2026-08-01";

function dnaDoc(overrides: Record<string, unknown> = {}) {
  return {
    conversationAtmosphere: "calm",
    conversationInitiative: "adaptive",
    meetingPurpose: "both",
    alcoholCompanionPreference: "noPreference",
    smokingCompanionPreference: "noPreference",
    drinkingLevelSnapshot: "sometimes",
    smokingStatusSnapshot: "nonSmoker",
    interestIds: ["커피"],
    mbtiSnapshot: "ENFP",
    availableDateKeys: [DATE],
    ...overrides,
  };
}

function userDoc(overrides: Record<string, unknown> = {}) {
  const { onboarding, ...rest } = overrides as {
    onboarding?: Record<string, unknown>;
  } & Record<string, unknown>;
  return {
    isStudentVerified: true,
    onboarding: {
      gender: "male",
      campusLifeZones: ["sinchon"],
      lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
      ...(onboarding ?? {}),
    },
    ...rest,
  };
}

function build(
  dna: Record<string, unknown> | unknown,
  user: Record<string, unknown> | unknown
) {
  return buildCandidate({
    userId: "u1",
    dna,
    user,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    restricted: false,
    nowMs: 0,
    appliedAtMs: 0,
  });
}

describe("후보 hydration: 성별 fail-closed", () => {
  it("정상 문서는 canonical 성별을 그대로 싣는다", () => {
    const candidate = build(dnaDoc(), userDoc());
    assert.equal(candidate?.gender, "male");
  });

  it("onboarding.gender 가 female 이면 female 이다", () => {
    const candidate = build(
      dnaDoc(),
      userDoc({ onboarding: { gender: "female" } })
    );
    assert.equal(candidate?.gender, "female");
  });

  it("canonical 이 아닌 성별은 후보에서 제외한다", () => {
    for (const gender of ["other", "unknown", "", "남성", null, 1]) {
      assert.equal(
        build(dnaDoc(), userDoc({ onboarding: { gender } })),
        null,
        `${JSON.stringify(gender)} 는 후보가 될 수 없다`
      );
    }
  });

  it("성별 정보가 아예 없으면 후보에서 제외한다", () => {
    assert.equal(
      build(dnaDoc(), {
        isStudentVerified: true,
        onboarding: { campusLifeZones: ["sinchon"] },
      }),
      null
    );
  });

  it("legacy 최상위 gender 는 onboarding 에 값이 없을 때만 쓴다", () => {
    const candidate = build(dnaDoc(), {
      isStudentVerified: true,
      gender: "female",
      onboarding: {
        campusLifeZones: ["sinchon"],
        lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
      },
    });
    assert.equal(candidate?.gender, "female");
  });
});

describe("후보 hydration: 안전 조건 fail-closed", () => {
  it("흡연 여부가 손상되면 nonSmoker 로 보정하지 않고 제외한다", () => {
    assert.equal(
      build(
        dnaDoc({ smokingStatusSnapshot: "SMOKER!" }),
        userDoc({ onboarding: { lifestyle: { drinking: "sometimes" } } })
      ),
      null
    );
  });

  it("음주 정도가 없으면 sometimes 로 보정하지 않고 제외한다", () => {
    assert.equal(
      build(
        dnaDoc({ drinkingLevelSnapshot: undefined }),
        userDoc({ onboarding: { lifestyle: { smoking: "nonSmoker" } } })
      ),
      null
    );
  });

  it("동행 음주 선호가 손상되면 noPreference 로 보정하지 않고 제외한다", () => {
    assert.equal(
      build(dnaDoc({ alcoholCompanionPreference: "wat" }), userDoc()),
      null
    );
  });

  it("동행 흡연 선호가 손상되면 noPreference 로 보정하지 않고 제외한다", () => {
    assert.equal(
      build(dnaDoc({ smokingCompanionPreference: null }), userDoc()),
      null
    );
  });

  it("프로필의 최신 음주·흡연 값이 DNA 사본보다 우선한다", () => {
    // 신청 시점에는 비흡연이었지만 이후 프로필을 흡연으로 바꾼 사용자.
    const candidate = build(
      dnaDoc({ smokingStatusSnapshot: "nonSmoker" }),
      userDoc({
        onboarding: {
          lifestyle: { drinking: "often", smoking: "smoker" },
        },
      })
    );
    assert.equal(candidate?.smokingStatus, "smoker");
    assert.equal(candidate?.drinkingLevel, "often");
  });

  it("프로필에 값이 없으면 DNA 사본으로 되돌아간다", () => {
    const candidate = build(
      dnaDoc({ drinkingLevelSnapshot: "none", smokingStatusSnapshot: "smoker" }),
      userDoc({ onboarding: { lifestyle: {} } })
    );
    assert.equal(candidate?.drinkingLevel, "none");
    assert.equal(candidate?.smokingStatus, "smoker");
  });

  it("대화 성향 필드가 빠지면 제외한다 (기존 계약 유지)", () => {
    assert.equal(build(dnaDoc({ meetingPurpose: null }), userDoc()), null);
  });

  it("DNA 문서가 없으면 제외한다", () => {
    assert.equal(build(null, userDoc()), null);
  });
});

describe("callable dispatcher: prototype 오염 방어", () => {
  it("실제 action 은 해석된다", () => {
    assert.ok(BLIND_MEETING_ACTIONS.length > 0);
    for (const action of BLIND_MEETING_ACTIONS) {
      assert.equal(
        typeof resolveBlindMeetingHandler(action),
        "function",
        `${action} 은 handler 가 있어야 한다`
      );
    }
  });

  it("Object.prototype 속성은 handler 로 해석되지 않는다", () => {
    for (const action of [
      "constructor",
      "__proto__",
      "toString",
      "valueOf",
      "hasOwnProperty",
      "isPrototypeOf",
      "propertyIsEnumerable",
      "toLocaleString",
      "",
      "unknownAction",
    ]) {
      assert.equal(
        resolveBlindMeetingHandler(action),
        null,
        `${action} 은 거부돼야 한다 (인증 우회 경로)`
      );
    }
  });
});
