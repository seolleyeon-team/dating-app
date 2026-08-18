/**
 * spinSeasonMeetingRoulette 트랜잭션과 seasonPhase FSM 우회에 대한
 * source-scan 회귀 테스트.
 *
 * (repo 관례: teamMeetingRequest.test.ts 의 read-before-write 검사와 동일하게
 *  컴파일된 JS를 스캔한다. 트랜잭션 콜백이 index.ts 클로저 안에 있어
 *  직접 unit test가 불가능한 부분의 회귀 방지가 목적.)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

function readCompiled(fileName: string): string {
  return readFileSync(resolve(__dirname, fileName), "utf8");
}

function sliceSpinTransaction(indexSource: string): string {
  // tsc가 파일 상단에 `exports.X = void 0` 선언을 넣으므로
  // 실제 onCall 정의 지점을 앵커로 잡는다.
  const spinStart = indexSource.indexOf("exports.spinSeasonMeetingRoulette = (0,");
  assert.ok(spinStart >= 0, "spinSeasonMeetingRoulette must exist in index.js");
  const txStart = indexSource.indexOf("runTransaction", spinStart);
  assert.ok(txStart >= 0, "spin must use a Firestore transaction");
  // 트랜잭션 결과를 리턴하는 지점까지가 콜백 본문이다.
  const txEnd = indexSource.indexOf("viewerGroupId: requestingTeamSetupId", txStart);
  assert.ok(txEnd > txStart, "spin transaction outcome must be returned");
  const txBody = indexSource.slice(txStart, txEnd);
  assert.ok(
    txBody.length < 20000,
    "slice must cover only the spin transaction body"
  );
  return txBody;
}

describe("seasonRouletteTransaction source scan", () => {
  it("spin transaction performs every read before the first write", () => {
    const txBody = sliceSpinTransaction(readCompiled("index.js"));

    const lastRead = txBody.lastIndexOf("tx.get(");
    const firstSet = txBody.indexOf("tx.set(");
    const firstDelete = txBody.indexOf("tx.delete(");
    const firstWrite = [firstSet, firstDelete]
      .filter((index) => index >= 0)
      .reduce((min, index) => Math.min(min, index), Number.MAX_SAFE_INTEGER);

    assert.ok(lastRead >= 0, "spin transaction must read documents");
    assert.ok(
      firstWrite !== Number.MAX_SAFE_INTEGER,
      "spin transaction must write result and locks"
    );
    assert.ok(
      lastRead < firstWrite,
      `all tx.get calls must precede the first tx write ` +
        `(lastRead=${lastRead}, firstWrite=${firstWrite})`
    );
  });

  it("spin transaction defers stale lock deletion instead of deleting inline", () => {
    const txBody = sliceSpinTransaction(readCompiled("index.js"));
    assert.match(
      txBody,
      /staleLockRefs/,
      "stale lock cleanup must go through the deferred staleLockRefs list"
    );
  });

  it("seasonMeetingOperations no longer writes seasonPhase literals directly", () => {
    const source = readCompiled("seasonMeetingOperations.js");
    // phase 전이는 transitionMatchSeasonPhase 헬퍼(FSM 검증 포함)만 수행한다.
    // 직접 리터럴 write가 다시 생기면 FSM 우회이므로 실패시킨다.
    assert.doesNotMatch(
      source,
      /seasonPhase:\s*["'](cancelled|noshow_review|deposit_pending|matched)["']/,
      "seasonPhase must be written via transitionMatchSeasonPhase, not literals"
    );
    assert.match(source, /transitionMatchSeasonPhase/);
    assert.match(
      source,
      /season_phase_transition_rejected/,
      "illegal transitions must fail closed with an explicit error"
    );
  });
});
