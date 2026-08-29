import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";

import {
  loadCampusLifeZoneActivation,
  resetCampusLifeZoneActivationCache,
} from "./campusLifeZoneActivation";

/**
 * activation 전환이 runbook 과 실제로 일치하는지 확인한다.
 *
 * Functions 인스턴스는 activation 을 30초 캐시한다. 따라서 config 를 켠
 * 직후에도 이미 떠 있던 인스턴스는 최대 TTL 동안 이전 값을 돌려준다.
 * runbook 이 "write 하면 즉시 활성화"라고 가정하면, 그 사이에 만들어진
 * 미팅/룰렛 결과가 이전 정책으로 확정된다.
 */
const TTL_MS = 30_000;

type Stub = {
  collection: (name: string) => {
    doc: (id: string) => { get: () => Promise<{ data: () => unknown }> };
  };
};

function configDb(value: () => Record<string, unknown> | null): Stub {
  return {
    collection: () => ({
      doc: () => ({ get: async () => ({ data: () => value() }) }),
    }),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const asDb = (stub: Stub) => stub as any;

describe("activation transition (fake clock)", () => {
  beforeEach(() => resetCampusLifeZoneActivationCache());

  it("OFF -> ON 은 TTL 이 지나야 warm 인스턴스에 반영된다", async () => {
    let enforced = false;
    const db = asDb(configDb(() => ({ campusLifeZoneEnforced: enforced })));

    const t0 = 1_000_000;
    assert.equal((await loadCampusLifeZoneActivation(db, { now: t0 })).state, "off");

    // T1: 운영자가 config 를 켠다.
    enforced = true;

    // T1+10s: 아직 캐시가 살아 있어 이전 값을 본다.
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + 10_000 })).state,
      "off",
      "TTL 안에서는 이전 값이 유지된다 (runbook 이 이걸 전제해야 한다)"
    );

    // T1+TTL 직전까지도 이전 값이다.
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS - 1 })).state,
      "off"
    );

    // TTL 이 지나면 새로 읽어 ON 이 된다.
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS + 1_000 })).state,
      "enforced"
    );
  });

  it("cold start 인스턴스는 TTL 과 무관하게 즉시 ON 을 본다", async () => {
    const db = asDb(configDb(() => ({ campusLifeZoneEnforced: true })));
    // 방금 뜬 인스턴스 = 캐시 없음
    resetCampusLifeZoneActivationCache();
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: 5_000_000 })).state,
      "enforced"
    );
  });

  it("ON -> OFF (rollback) 도 TTL 안에 반영된다", async () => {
    let enforced = true;
    const db = asDb(configDb(() => ({ campusLifeZoneEnforced: enforced })));

    const t0 = 2_000_000;
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 })).state,
      "enforced"
    );

    enforced = false; // kill switch
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + 10_000 })).state,
      "enforced",
      "TTL 안에서는 아직 이전 값"
    );
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS + 1 })).state,
      "off",
      "rollback 은 최대 TTL 안에 반영된다"
    );
  });

  it("문서 삭제(rollback)도 OFF 로 읽힌다", async () => {
    let present = true;
    const db = asDb(
      configDb(() => (present ? { campusLifeZoneEnforced: true } : null))
    );
    const t0 = 3_000_000;
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 })).state,
      "enforced"
    );
    present = false;
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS + 1 })).state,
      "off"
    );
  });

  it("전환 중 조회가 실패하면 직전 값을 유지한다 (정책이 흔들리지 않는다)", async () => {
    let mode: "on" | "fail" = "on";
    const db = asDb({
      collection: () => ({
        doc: () => ({
          get: async () => {
            if (mode === "fail") throw new Error("deadline exceeded");
            return { data: () => ({ campusLifeZoneEnforced: true }) };
          },
        }),
      }),
    });

    const t0 = 4_000_000;
    assert.equal(
      (await loadCampusLifeZoneActivation(db, { now: t0 })).state,
      "enforced"
    );
    mode = "fail";
    const stale = await loadCampusLifeZoneActivation(db, {
      now: t0 + TTL_MS + 1,
    });
    assert.equal(stale.state, "enforced");
    assert.equal(stale.staleFallback, true);
  });

  it("TTL 값이 runbook 이 가정하는 30초다", async () => {
    let reads = 0;
    const db = asDb({
      collection: () => ({
        doc: () => ({
          get: async () => {
            reads += 1;
            return { data: () => ({ campusLifeZoneEnforced: false }) };
          },
        }),
      }),
    });
    const t0 = 6_000_000;
    await loadCampusLifeZoneActivation(db, { now: t0 });
    await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS - 1 });
    assert.equal(reads, 1, "TTL 안에서는 재조회하지 않는다");
    await loadCampusLifeZoneActivation(db, { now: t0 + TTL_MS });
    assert.equal(reads, 2, "TTL 이 지나면 재조회한다");
  });
});
