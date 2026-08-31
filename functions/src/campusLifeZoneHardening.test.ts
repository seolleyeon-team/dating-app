import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";

import {
  loadCampusLifeZoneActivation,
  loadCampusLifeZoneEnforced,
  campusLifeZonePolicyVersionFromConfig,
  resetCampusLifeZoneActivationCache,
} from "./campusLifeZoneActivation";
import {
  normalizeCampusLifeZones,
  readPersistedCampusLifeZones,
} from "./campusLifeZones";
import {
  bestGroup,
  checkGroupConstraints,
  sharedCampusLifeZones,
  type Candidate,
} from "./blindMeeting/matching";

const DATE = "2026-08-01";

type Stub = {
  collection: (name: string) => {
    doc: (id: string) => { get: () => Promise<{ data: () => unknown }> };
  };
};

function okDb(data: Record<string, unknown> | null): Stub {
  return {
    collection: () => ({
      doc: () => ({ get: async () => ({ data: () => data }) }),
    }),
  };
}

function failingDb(): Stub {
  return {
    collection: () => ({
      doc: () => ({
        get: async () => {
          throw new Error("deadline exceeded");
        },
      }),
    }),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const asDb = (stub: Stub) => stub as any;

describe("activation read failure semantics", () => {
  beforeEach(() => resetCampusLifeZoneActivationCache());

  it("문서가 없으면 명시적 OFF 다 (장애가 아니다)", async () => {
    const activation = await loadCampusLifeZoneActivation(asDb(okDb(null)));
    assert.equal(activation.state, "off");
    assert.equal(activation.staleFallback, false);
  });

  it("boolean true 일 때만 ENFORCED 다", async () => {
    assert.equal(
      (await loadCampusLifeZoneActivation(asDb(okDb({ campusLifeZoneEnforced: true }))))
        .state,
      "enforced"
    );
    resetCampusLifeZoneActivationCache();
    assert.equal(
      (
        await loadCampusLifeZoneActivation(
          asDb(okDb({ campusLifeZoneEnforced: "true" }))
        )
      ).state,
      "off"
    );
  });

  it("cold start + 조회 실패 = unknown (어느 쪽으로도 가정하지 않는다)", async () => {
    const activation = await loadCampusLifeZoneActivation(asDb(failingDb()));
    assert.equal(activation.state, "unknown");
    assert.equal(activation.staleFallback, false);
  });

  it("last-known ON + 조회 실패 -> ON 을 유지한다", async () => {
    let now = 1_000_000;
    const first = await loadCampusLifeZoneActivation(
      asDb(okDb({ campusLifeZoneEnforced: true })),
      { now }
    );
    assert.equal(first.state, "enforced");

    // TTL 만료 후 조회 실패
    now += 60_000;
    const second = await loadCampusLifeZoneActivation(asDb(failingDb()), { now });
    assert.equal(second.state, "enforced", "장애가 정책을 끄면 안 된다");
    assert.equal(second.staleFallback, true);
  });

  it("last-known OFF + 조회 실패 -> OFF 를 유지한다", async () => {
    let now = 2_000_000;
    assert.equal(
      (await loadCampusLifeZoneActivation(asDb(okDb({})), { now })).state,
      "off"
    );
    now += 60_000;
    const second = await loadCampusLifeZoneActivation(asDb(failingDb()), { now });
    assert.equal(
      second.state,
      "off",
      "준비 단계에서 장애가 정책을 갑자기 켜서도 안 된다"
    );
    assert.equal(second.staleFallback, true);
  });

  it("TTL 안에서는 재조회하지 않는다", async () => {
    let reads = 0;
    const counting: Stub = {
      collection: () => ({
        doc: () => ({
          get: async () => {
            reads += 1;
            return { data: () => ({ campusLifeZoneEnforced: true }) };
          },
        }),
      }),
    };
    const now = 3_000_000;
    await loadCampusLifeZoneActivation(asDb(counting), { now });
    await loadCampusLifeZoneActivation(asDb(counting), { now: now + 1_000 });
    assert.equal(reads, 1);
  });

  it("boolean helper 는 unknown 처리를 호출부가 정하게 한다", async () => {
    resetCampusLifeZoneActivationCache();
    assert.equal(
      await loadCampusLifeZoneEnforced(asDb(failingDb()), { unknownAs: "enforced" }),
      true
    );
    resetCampusLifeZoneActivationCache();
    assert.equal(
      await loadCampusLifeZoneEnforced(asDb(failingDb()), { unknownAs: "off" }),
      false
    );
  });

  it("정책 버전은 정수일 때만 읽는다", () => {
    assert.equal(
      campusLifeZonePolicyVersionFromConfig({ campusLifeZonePolicyVersion: 4 }),
      4
    );
    assert.equal(
      campusLifeZonePolicyVersionFromConfig({ campusLifeZonePolicyVersion: "4" }),
      0
    );
    assert.equal(campusLifeZonePolicyVersionFromConfig(null), 0);
  });
});

describe("canonical campus life zone values", () => {
  it("canonical 값만 통과한다", () => {
    assert.deepEqual(readPersistedCampusLifeZones(["sinchon"]), ["sinchon"]);
    assert.deepEqual(readPersistedCampusLifeZones(["songdo", "sinchon"]), [
      "sinchon",
      "songdo",
    ]);
  });

  it("손상된 값은 값 전체를 무효로 본다", () => {
    for (const value of [
      ["garbage"],
      ["sinchon", "garbage"],
      ["SINCHON"],
      [""],
      ["sinchon", ""],
      ["sinchon", null],
      ["sinchon", 1],
      [],
    ]) {
      assert.deepEqual(readPersistedCampusLifeZones(value), [], String(value));
    }
  });

  it("스키마가 다른 타입은 무효다 (raw string 포함)", () => {
    for (const value of ["sinchon", 123, null, undefined, true, { z: "sinchon" }]) {
      assert.deepEqual(readPersistedCampusLifeZones(value), [], String(value));
    }
  });

  it("normalize 는 메모리 목록에 같은 규칙을 적용한다", () => {
    assert.deepEqual(normalizeCampusLifeZones([" sinchon "]), ["sinchon"]);
    assert.deepEqual(normalizeCampusLifeZones(["garbage"]), []);
  });
});

function candidate(userId: string, overrides: Partial<Candidate> = {}): Candidate {
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
    interestIds: ["커피"],
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
function team(
  prefix: string,
  zones: string[],
  gender: Candidate["gender"] = "male"
): Candidate[] {
  const roles: Candidate["initiative"][] = ["initiator", "adaptive", "listener"];
  return roles.map((initiative, index) =>
    candidate(`${prefix}${index}`, {
      gender,
      initiative,
      campusLifeZones: zones,
    })
  );
}

describe("matching rejects malformed zone values", () => {
  it("손상된 값끼리도 매칭되지 않는다", () => {
    const pool = [...team("a", ["garbage"]), ...team("b", ["garbage"], "female")];
    assert.deepEqual(sharedCampusLifeZones(pool), []);
    assert.ok(
      checkGroupConstraints(pool, DATE, false, 6, true).includes(
        "campusLifeZoneMissing"
      )
    );
    assert.equal(bestGroup(pool, DATE, false), null);
  });

  it("canonical 값 하나라도 섞이면 그 멤버는 생활권이 없는 것으로 본다", () => {
    const pool = [
      ...team("a", ["sinchon"]),
      ...team("b", ["sinchon", "garbage"], "female"),
    ];
    assert.equal(bestGroup(pool, DATE, false), null);
  });

  it("정상 canonical 값은 그대로 매칭된다", () => {
    const pool = [
      ...team("a", ["sinchon"]),
      ...team("b", ["sinchon", "songdo"], "female"),
    ];
    assert.ok(bestGroup(pool, DATE, false) != null);
  });
});
