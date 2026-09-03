/**
 * 블라인드 3:3 — 보증금 없음(NO_DEPOSIT) 계약.
 * 실행: npm --prefix functions test
 *
 * 블라인드 취향 미팅은 매칭이 commit 되면 결제 절차 없이 바로 확정되고
 * 단체 채팅방이 열린다. 이 파일은 그 계약이 다시 무너지지 않도록
 *  - live FSM 에 deposit 상태가 없고
 *  - public callable / ops callable 에 deposit·refund action 이 없고
 *  - 정책·알림·소스에 보증금/환급 business logic 이 없음
 * 을 고정한다. legacy 문서 호환 어댑터(legacyDeposit*.ts)만 예외다.
 *
 * 단, 2026-09-03 정책으로 "매칭 전 신청 취소 시 신청에 쓴 하트 환불" 은
 * 제품 요구사항이 됐다. 이는 보증금(deposit) 환급이 아니라 하트 ledger 의
 * 되돌림이며, HEART_REFUND_ALLOW 패턴에 걸리는 줄(heartRefund* 식별자,
 * "하트 … 환불" 문구)만 스캔에서 제외한다. deposit/보증금/환급 은 여전히
 * 금지다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import {
  ALLOWED_APPLICATION_TRANSITIONS,
  ALLOWED_MEETING_TRANSITIONS,
  ALLOWED_PARTICIPANT_TRANSITIONS,
  BLIND_MEETING_COLLECTIONS,
  MEETING_STATUS_TO_APP,
  PARTICIPANT_STATUS_TO_APP,
  canTransitionMeeting,
  canTransitionParticipant,
} from "../types";
import { DEFAULT_POLICY, resolveCancellation } from "../policy";
import { BLIND_MEETING_NOTIFICATION_TEMPLATES } from "../notifications";
import {
  normalizeLegacyMeetingStatus,
  normalizeLegacyParticipantStatus,
} from "../legacyDepositStatus";

const DEPOSIT_PATTERN = /deposit|refund|보증금|환급/i;

/**
 * 보증금 환급(deposit refund) 문맥. `refund` 라는 단어 자체는 2026-09-03 부터
 * 하트 환불(신청 취소) 코드에 정당하게 등장하므로, deposit/결제/보증금/환급
 * 과 같은 줄에 있을 때만 위반으로 본다.
 */
const DEPOSIT_REFUND_CONTEXT = /deposit|payment|intent|provider|보증금|환급|결제/i;

function isDepositOffence(line: string): boolean {
  if (!DEPOSIT_PATTERN.test(line)) return false;
  if (/deposit|보증금|환급/i.test(line)) return true;
  // 'refund' 만 등장하는 줄: 보증금/결제 문맥이 함께 있을 때만 위반.
  return DEPOSIT_REFUND_CONTEXT.test(line);
}

const SRC_DIR = resolve(__dirname, "../../../src/blindMeeting");
const LIB_DIR = resolve(__dirname, "..");

/** legacy 문서 호환 전용 어댑터. 여기에만 deposit 문자열이 남을 수 있다. */
const LEGACY_ADAPTER_FILES = new Set([
  "legacyDepositStatus.ts",
  "legacyDepositNormalizer.ts",
]);

function isTestFile(name: string): boolean {
  return name.endsWith(".test.ts") || name.endsWith(".emulator-test.ts");
}

/**
 * deposit 패턴에 걸리는 줄 중 legacy 어댑터 모듈을 import 하는 줄은 제외한다.
 * (읽기 시점 정규화를 위해 store/scheduled 가 어댑터를 참조해야 한다.)
 */
function offendingLines(source: string): string[] {
  return source
    .split(/\r?\n/)
    .map((line, index) => ({ line, index }))
    .filter(({ line }) => isDepositOffence(line))
    .filter(({ line }) => !/legacyDeposit(Status|Normalizer)/.test(line))
    .map(({ line, index }) => `${index + 1}: ${line.trim()}`);
}

describe("blind 3:3 live FSM has no deposit state", () => {
  it("meeting statuses contain no deposit stage", () => {
    for (const status of Object.keys(MEETING_STATUS_TO_APP)) {
      assert.doesNotMatch(status, DEPOSIT_PATTERN, status);
    }
    for (const app of Object.values(MEETING_STATUS_TO_APP)) {
      assert.doesNotMatch(app, DEPOSIT_PATTERN, app);
    }
  });

  it("participant statuses contain no deposit stage", () => {
    for (const status of Object.keys(PARTICIPANT_STATUS_TO_APP)) {
      assert.doesNotMatch(status, DEPOSIT_PATTERN, status);
    }
  });

  it("legacy awaiting_acceptance → confirmed is its only forward edge (no deposit stage)", () => {
    assert.deepEqual(
      [...ALLOWED_MEETING_TRANSITIONS.awaiting_acceptance].sort(),
      ["confirmed", "forming"]
    );
    assert.equal(canTransitionMeeting("awaiting_acceptance", "confirmed"), true);
  });

  it("accepted participant goes straight to confirmed", () => {
    assert.equal(canTransitionParticipant("accepted", "confirmed"), true);
    for (const edges of Object.values(ALLOWED_PARTICIPANT_TRANSITIONS)) {
      for (const to of edges) assert.doesNotMatch(to, DEPOSIT_PATTERN);
    }
    for (const edges of Object.values(ALLOWED_APPLICATION_TRANSITIONS)) {
      for (const to of edges) assert.doesNotMatch(to, DEPOSIT_PATTERN);
    }
  });

  it("no live collection constant points at the deposit ledger", () => {
    for (const [key, value] of Object.entries(BLIND_MEETING_COLLECTIONS)) {
      assert.doesNotMatch(key, DEPOSIT_PATTERN, key);
      assert.doesNotMatch(value, DEPOSIT_PATTERN, value);
    }
  });
});

describe("blind 3:3 policy is payment-independent", () => {
  it("policy has no deposit / refund knobs", () => {
    for (const key of Object.keys(DEFAULT_POLICY)) {
      assert.doesNotMatch(key, DEPOSIT_PATTERN, key);
    }
    // 매칭 = 확정: 수락 창 정책은 더 이상 존재하지 않는다.
    assert.equal("acceptanceWindowMs" in DEFAULT_POLICY, false);
  });

  it("cancellation decision carries no refund amount", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 2 * 60 * 60 * 1000,
      replacementFound: false,
    });
    for (const key of Object.keys(decision)) {
      assert.doesNotMatch(key, DEPOSIT_PATTERN, key);
    }
    assert.doesNotMatch(decision.outcome, DEPOSIT_PATTERN);
  });

  it("ordinary cancellation releases the seat without restriction", () => {
    for (const untilMeetingMs of [null, 0, 2 * 3600e3, 10 * 3600e3, 30 * 3600e3]) {
      for (const replacementFound of [true, false]) {
        const decision = resolveCancellation({
          policy: DEFAULT_POLICY,
          untilMeetingMs,
          replacementFound,
        });
        assert.equal(decision.outcome, "released");
        assert.equal(decision.triggersWaitlistFill, true);
        assert.equal(decision.appliesRestriction, false);
      }
    }
  });

  it("no_show is a trust/safety decision, not a forfeiture", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: null,
      replacementFound: false,
      isNoShowWithoutContact: true,
    });
    assert.equal(decision.outcome, "no_show");
    assert.equal(decision.appliesRestriction, true);
    assert.equal(decision.triggersWaitlistFill, false);
  });

  it("emergency still routes to ops review without money semantics", () => {
    const decision = resolveCancellation({
      policy: DEFAULT_POLICY,
      untilMeetingMs: 30 * 60 * 1000,
      replacementFound: false,
      emergencyReviewRequested: true,
    });
    assert.equal(decision.outcome, "ops_review");
    assert.equal(decision.appliesRestriction, false);
    assert.equal(decision.triggersWaitlistFill, true);
  });
});

describe("blind 3:3 notifications carry no deposit copy", () => {
  it("no template kind, type, title, or body mentions a deposit or refund", () => {
    for (const [kind, template] of Object.entries(
      BLIND_MEETING_NOTIFICATION_TEMPLATES
    )) {
      assert.doesNotMatch(kind, DEPOSIT_PATTERN, kind);
      assert.doesNotMatch(template.type, DEPOSIT_PATTERN, template.type);
      assert.doesNotMatch(template.title, DEPOSIT_PATTERN, template.title);
      assert.doesNotMatch(template.body, DEPOSIT_PATTERN, template.body);
    }
  });
});

describe("blind 3:3 callables expose no deposit action", () => {
  function compiled(file: string): string {
    return readFileSync(resolve(LIB_DIR, file), "utf8");
  }

  it("public dispatcher has no startBlindMeetingDeposit / beginDeposit", () => {
    const source = compiled("callables.js");
    assert.doesNotMatch(source, /startBlindMeetingDeposit/);
    assert.doesNotMatch(source, /beginDeposit/);
    assert.deepEqual(offendingLines(source), []);
  });

  it("ops dispatcher has no refund override", () => {
    const source = compiled("ops.js");
    assert.doesNotMatch(source, /overrideBlindMeetingRefund/);
    assert.deepEqual(offendingLines(source), []);
  });

  it("orchestrator / scheduled / store run no deposit or refund business logic", () => {
    for (const file of [
      "orchestrator.js",
      "scheduled.js",
      "store.js",
      "policy.js",
      "notifications.js",
      "types.js",
      "runtime.js",
      "matching.js",
      "party.js",
      "genderBalance.js",
      "legacyAcceptance.js",
      "meetingConfirmation.js",
    ]) {
      const source = compiled(file);
      assert.doesNotMatch(source, /refundDeposit|startDeposit|beginDeposit/, file);
      assert.doesNotMatch(source, /advanceWithoutDeposit|advanceAfterDeposit/, file);
      assert.doesNotMatch(source, /awaiting_deposits|deposit_pending/, file);
      assert.deepEqual(offendingLines(source), [], file);
    }
  });

  it("payments module no longer exists", () => {
    const files = readdirSync(SRC_DIR);
    assert.equal(files.includes("payments.ts"), false);
  });
});

describe("blind 3:3 server source scan", () => {
  it("only the legacy adapters may mention deposits", () => {
    const offenders: string[] = [];
    for (const name of readdirSync(SRC_DIR)) {
      if (!name.endsWith(".ts")) continue;
      if (isTestFile(name)) continue;
      if (LEGACY_ADAPTER_FILES.has(name)) continue;
      const source = readFileSync(resolve(SRC_DIR, name), "utf8");
      for (const line of offendingLines(source)) {
        offenders.push(`${name}:${line}`);
      }
    }
    assert.deepEqual(offenders, [], offenders.join("\n"));
  });

  it("legacy adapters exist and are the only place that knows the old states", () => {
    const files = readdirSync(SRC_DIR);
    for (const name of LEGACY_ADAPTER_FILES) {
      assert.ok(files.includes(name), `${name} must exist`);
    }
  });
});

describe("legacy deposit state normalization (pure)", () => {
  it("maps legacy awaiting_deposits (both spellings) to awaiting_acceptance", () => {
    assert.equal(
      normalizeLegacyMeetingStatus("awaiting_deposits"),
      "awaiting_acceptance"
    );
    assert.equal(
      normalizeLegacyMeetingStatus("awaitingDeposits"),
      "awaiting_acceptance"
    );
  });

  it("leaves canonical statuses untouched", () => {
    for (const status of Object.keys(MEETING_STATUS_TO_APP)) {
      assert.equal(normalizeLegacyMeetingStatus(status), status);
    }
    assert.equal(normalizeLegacyMeetingStatus("garbage"), "garbage");
  });

  it("maps legacy deposit_pending participants to accepted", () => {
    assert.equal(
      normalizeLegacyParticipantStatus("deposit_pending"),
      "accepted"
    );
    assert.equal(normalizeLegacyParticipantStatus("depositPending"), "accepted");
    for (const status of Object.keys(PARTICIPANT_STATUS_TO_APP)) {
      assert.equal(normalizeLegacyParticipantStatus(status), status);
    }
  });
});
