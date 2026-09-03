/**
 * 블라인드 3:3 — 매칭 후 수락/거절 단계 없음(NO_ACCEPTANCE) + 신청 취소 계약.
 * 실행: npm --prefix functions test
 *
 * 2026-09-03 정책:
 *   매칭 성공 → 미팅 즉시 confirmed → 같은 트랜잭션에서 6인 채팅방 생성.
 *   사용자에게 참가 수락/거절을 묻지 않는다. 신청 취소는 매칭 전에만 있고
 *   성공 시 신청에 쓴 하트를 정확히 한 번 돌려준다.
 *
 * 이 파일은
 *  - public callable 에 accept/decline/openChat action 이 없고
 *  - orchestrator 가 awaiting_acceptance / invited 를 새로 쓰지 않으며
 *  - 매칭 tx 가 채팅방 문서를 함께 쓰고
 *  - 알림에 수락/거절 요청 문구가 없고
 *  - Flutter production 코드에 수락/거절 액션·문구가 없음
 * 을 소스 스캔으로 고정하고, 하트 환불 판정(pure) 을 검증한다.
 * legacy 어댑터(legacyAcceptance.ts / legacyDeposit*.ts)만 예외다.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, it } from "node:test";

import { BLIND_MEETING_ACTIONS } from "../callables";
import { BLIND_MEETING_NOTIFICATION_TEMPLATES } from "../notifications";
import { decideHeartRefund } from "../store";
import {
  CANCEL_ALREADY_MATCHED_CODE,
  CANCELLABLE_APPLICATION_STATUSES,
  LEGACY_ONLY_MATCHING_STAGES,
  LEGACY_ONLY_MEETING_STATUSES,
  LEGACY_ONLY_PARTICIPANT_STATUSES,
  MEETING_BOUND_APPLICATION_STATUSES,
  isApplicationActive,
} from "../types";

const SRC_DIR = resolve(__dirname, "../../../src/blindMeeting");
const LIB_DIR = resolve(__dirname, "..");
const REPO_ROOT = resolve(__dirname, "../../../..");
const FLUTTER_BLIND_DIR = resolve(REPO_ROOT, "lib/features/blind_meeting");

/** 수락 단계를 아는 것이 허용되는 서버 모듈 (LEGACY_COMPATIBILITY_ONLY). */
const LEGACY_SERVER_FILES = new Set([
  "legacyAcceptance.ts",
  "legacyDepositStatus.ts",
  "legacyDepositNormalizer.ts",
]);

function isTestFile(name: string): boolean {
  return name.endsWith(".test.ts") || name.endsWith(".emulator-test.ts");
}

function compiled(file: string): string {
  return readFileSync(resolve(LIB_DIR, file), "utf8");
}

function walkDart(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walkDart(full, out);
    else if (name.endsWith(".dart")) out.push(full);
  }
  return out;
}

describe("blind 3:3 public API has no acceptance stage", () => {
  it("dispatcher exposes no accept / decline / openChat action", () => {
    for (const action of BLIND_MEETING_ACTIONS) {
      assert.doesNotMatch(action, /accept|decline|respondInvitation|openBlindMeetingChat/i, action);
    }
    assert.ok(BLIND_MEETING_ACTIONS.includes("cancelBlindMeetingApplication"));
    assert.ok(BLIND_MEETING_ACTIONS.includes("submitBlindMeetingApplication"));
  });

  it("orchestrator exports no acceptance entrypoints", () => {
    const source = compiled("orchestrator.js");
    for (const symbol of [
      "acceptInvitation",
      "declineInvitation",
      "advanceAfterAcceptance",
      "openGroupChatAfterAcceptance",
      "confirmMeetingAfterAcceptance",
      "withdrawMatchedBlindMeetingParty",
    ]) {
      assert.doesNotMatch(source, new RegExp(`\\b${symbol}\\b`), symbol);
    }
  });

  it("matching tx creates the meeting as confirmed and writes the room in the same tx", () => {
    const source = compiled("orchestrator.js");
    assert.doesNotMatch(source, /MEETING_STATUS_TO_APP\.awaiting_acceptance/);
    assert.doesNotMatch(source, /serverStatus:\s*["']awaiting_acceptance["']/);
    assert.doesNotMatch(source, /PARTICIPANT_STATUS_TO_APP\.invited/);
    assert.doesNotMatch(source, /serverStatus:\s*["']invited["']/);
    assert.doesNotMatch(source, /kind:\s*["']acceptance_request["']/);
    // 미팅 문서와 채팅방 문서가 같은 runTransaction 안에서 써진다.
    // (컴파일된 JS 는 `(0, store_1.db)().runTransaction(` 형태다.)
    const txStart = source.search(/const claimed = await [^\n]*runTransaction\(/);
    assert.ok(txStart > 0, "claim transaction exists");
    const txEnd = source.indexOf("if (!claimed)", txStart);
    assert.ok(txEnd > txStart, "claim transaction is followed by the claim check");
    const txBody = source.slice(txStart, txEnd);
    assert.match(txBody, /serverStatus:\s*["']confirmed["']/);
    assert.match(txBody, /groupChatRoomDocument\)?\(/);
    assert.match(txBody, /groupChatId:\s*roomId/);
  });

  it("legacy statuses are written only by the legacy adapters", () => {
    const offenders: string[] = [];
    for (const name of readdirSync(SRC_DIR)) {
      if (!name.endsWith(".ts") || isTestFile(name)) continue;
      if (LEGACY_SERVER_FILES.has(name) || name === "types.ts") continue;
      const source = readFileSync(resolve(SRC_DIR, name), "utf8");
      source.split(/\r?\n/).forEach((line, index) => {
        if (
          /MEETING_STATUS_TO_APP\.awaiting_acceptance|serverStatus:\s*["']awaiting_acceptance["']|PARTICIPANT_STATUS_TO_APP\.(invited|accepted)\b|serverStatus:\s*["'](invited|accepted)["']|stage:\s*["']awaitingConfirmation["']/.test(
            line
          )
        ) {
          offenders.push(`${name}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    assert.deepEqual(offenders, [], offenders.join("\n"));
  });

  it("legacy-only status lists match the contract", () => {
    assert.deepEqual([...LEGACY_ONLY_MEETING_STATUSES], [
      "application_open",
      "forming",
      "awaiting_acceptance",
    ]);
    assert.deepEqual([...LEGACY_ONLY_PARTICIPANT_STATUSES], ["invited", "accepted"]);
    assert.deepEqual([...LEGACY_ONLY_MATCHING_STAGES], ["awaitingConfirmation"]);
  });
});

describe("blind 3:3 notifications carry no acceptance copy", () => {
  it("no template asks the user to accept or decline", () => {
    const kinds = Object.keys(BLIND_MEETING_NOTIFICATION_TEMPLATES);
    assert.ok(!kinds.includes("acceptance_request"));
    for (const [kind, template] of Object.entries(
      BLIND_MEETING_NOTIFICATION_TEMPLATES
    )) {
      assert.doesNotMatch(template.title, /수락|거절|참가 여부/, kind);
      assert.doesNotMatch(template.body, /수락|거절|참가 여부/, kind);
    }
    assert.match(BLIND_MEETING_NOTIFICATION_TEMPLATES.matched.title, /매칭됐어요/);
    assert.match(BLIND_MEETING_NOTIFICATION_TEMPLATES.chat_created.title, /채팅방/);
  });
});

describe("blind 3:3 application cancellation contract", () => {
  it("only open-pool statuses are cancellable; matched statuses are meeting-bound", () => {
    assert.deepEqual([...CANCELLABLE_APPLICATION_STATUSES], ["applied", "waitlisted"]);
    for (const status of CANCELLABLE_APPLICATION_STATUSES) {
      assert.equal(isApplicationActive(status), true);
      assert.equal(MEETING_BOUND_APPLICATION_STATUSES.includes(status), false);
    }
    assert.ok(MEETING_BOUND_APPLICATION_STATUSES.includes("confirmed"));
    assert.equal(isApplicationActive("cancelled"), false);
    assert.equal(CANCELLABLE_APPLICATION_STATUSES.includes("cancelled"), false);
    assert.equal(CANCEL_ALREADY_MATCHED_CODE, "CANNOT_CANCEL_ALREADY_MATCHED");
  });

  it("cancel handler returns a deterministic outcome instead of a bare ok", () => {
    const source = compiled("callables.js");
    assert.match(source, /heartRefunded/);
    assert.match(source, /outcome: result\.outcome/);
  });
});

describe("heart refund decision (pure)", () => {
  const charged = { heartChargeCount: 1, heartCost: 30 };

  it("refunds exactly the charged amount when the spend exists and no refund exists", () => {
    const decision = decideHeartRefund({
      applicationRaw: charged,
      spendExists: true,
      refundExists: false,
    });
    assert.deepEqual(decision, {
      applicable: true,
      reason: "refund",
      chargeCount: 1,
      amount: 30,
    });
  });

  it("never refunds twice for the same charge", () => {
    const decision = decideHeartRefund({
      applicationRaw: charged,
      spendExists: true,
      refundExists: true,
    });
    assert.equal(decision.applicable, false);
    assert.equal(decision.reason, "already_refunded");
  });

  it("fails closed when the original spend ledger is missing", () => {
    const decision = decideHeartRefund({
      applicationRaw: charged,
      spendExists: false,
      refundExists: false,
    });
    assert.equal(decision.applicable, false);
    assert.equal(decision.reason, "spend_missing");
  });

  it("does nothing for applications that were never charged", () => {
    for (const raw of [{}, { heartChargeCount: 0, heartCost: 30 }, { heartChargeCount: 2, heartCost: 0 }]) {
      const decision = decideHeartRefund({
        applicationRaw: raw,
        spendExists: true,
        refundExists: false,
      });
      assert.equal(decision.applicable, false, JSON.stringify(raw));
      assert.equal(decision.reason, "no_charge");
    }
  });
});

describe("Flutter blind meeting production code has no accept / decline action", () => {
  it("no acceptance callable, button copy, or analytics event remains", () => {
    const offenders: string[] = [];
    const pattern =
      /acceptInvitation|declineInvitation|acceptBlindMeetingInvitation|declineBlindMeetingInvitation|openBlindMeetingChat|invitationAccepted|참가할게요|참가하지 않을게요|참가를 수락|수락해주세요/;
    for (const file of walkDart(FLUTTER_BLIND_DIR)) {
      const lines = readFileSync(file, "utf8").split(/\r?\n/);
      lines.forEach((line, index) => {
        if (pattern.test(line)) {
          offenders.push(`${file}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    assert.deepEqual(offenders, [], offenders.join("\n"));
  });

  it("chat list tabs are backed by a real room classifier, not a mock", () => {
    const classifier = resolve(REPO_ROOT, "lib/features/chat/utils/chat_room_tab.dart");
    const source = readFileSync(classifier, "utf8");
    assert.match(source, /blind_meeting_group/);
    const screen = readFileSync(
      resolve(REPO_ROOT, "lib/features/chat/screens/premium_chat_list_screen.dart"),
      "utf8"
    );
    assert.match(screen, /chat_room_tab\.dart/);
    assert.doesNotMatch(screen, /TODO: Navigate to (1:1|3:3) chat/);
  });
});

describe("legacy deposit normalizer never resurrects the acceptance stage", () => {
  it("compiled normalizer has no awaiting_acceptance write and no acceptance window", () => {
    const source = readFileSync(
      resolve(__dirname, "..", "legacyDepositNormalizer.js"),
      "utf8"
    );
    assert.doesNotMatch(source, /serverStatus:\s*["']awaiting_acceptance["']/);
    assert.doesNotMatch(source, /MEETING_STATUS_TO_APP\.awaiting_acceptance/);
    assert.doesNotMatch(source, /acceptanceWindowStartedAt|acceptanceDeadline|acceptanceWindow/);
    // outcome 이름에도 폐기된 상태가 없다.
    assert.doesNotMatch(source, /["']awaiting_acceptance["']/);
  });
});

describe("acceptance timeout is fully removed (closure ②)", () => {
  it("policy has no acceptance window knob", () => {
    const policy = compiled("policy.js");
    assert.doesNotMatch(policy, /acceptanceWindowMs/);
  });

  it("scheduler has no response-window expiry step and never cancels for an acceptance timeout", () => {
    const scheduled = compiled("scheduled.js");
    assert.doesNotMatch(scheduled, /acceptanceWindow|responseWindows|acceptance_window_expired|expireBlindMeetingResponseWindows/);
    // legacy 정규화 단계만 남는다.
    assert.match(scheduled, /legacyAcceptance/);
  });

  it("no live or legacy module writes acceptance-stage fields", () => {
    for (const file of [
      "orchestrator.js",
      "legacyAcceptance.js",
      "legacyDepositNormalizer.js",
      "meetingConfirmation.js",
      "scheduled.js",
      "store.js",
    ]) {
      const source = compiled(file);
      assert.doesNotMatch(source, /acceptanceDeadline|acceptanceWindowStartedAt|acceptanceWindowMs/, file);
    }
  });
});

describe("recentlyMet means an actual meeting, not a match", () => {
  function compiled(file: string): string {
    return readFileSync(resolve(__dirname, "..", file), "utf8");
  }

  it("confirmation / chat opening does not record met users", () => {
    assert.doesNotMatch(compiled("meetingConfirmation.js"), /recordMetUsers/);
    assert.doesNotMatch(compiled("legacyAcceptance.js"), /recordMetUsers/);
    assert.doesNotMatch(compiled("legacyDepositNormalizer.js"), /recordMetUsers/);
  });

  it("recordMetUsers is called from the attendance (safety stamp) path only", () => {
    const orchestrator = compiled("orchestrator.js");
    const calls = orchestrator.match(/recordMetUsers\)?\(/g) ?? [];
    assert.equal(calls.length, 1, "exactly one call site in orchestrator");
    const stampStart = orchestrator.indexOf("async function markSafetyStamp(");
    const stampEnd = orchestrator.indexOf("async function maybeStartMeeting(");
    assert.ok(stampStart >= 0 && stampEnd > stampStart);
    assert.match(
      orchestrator.slice(stampStart, stampEnd),
      /recordMetUsers\)?\(/,
      "the call lives inside markSafetyStamp"
    );
    for (const file of ["scheduled.js", "store.js", "callables.js", "ops.js", "party.js"]) {
      const source = compiled(file);
      const uses = (source.match(/recordMetUsers\)?\(/g) ?? []).length;
      // store.js 는 정의(function recordMetUsers) 만 갖는다.
      const expected = file === "store.js" ? 1 : 0;
      assert.equal(uses, expected, `${file} must not call recordMetUsers`);
    }
  });
});
