/**
 * 최종 no_show 참가자의 권한 회수 계약
 * 실행: npm --prefix functions test
 *
 * 이 프로젝트에는 "검토 중 노쇼"와 "최종 노쇼"를 구분하는 상태가 없다.
 * `no_show` 는 스케줄러가 체크인 창을 넘긴 참가자에게 한 번 쓰는 최종 판정이고,
 * 그와 동시에 보증금 몰수·노쇼 카운트·이용 제한이 함께 적용된다.
 * 따라서 이 상태에 도달하면 그 사람은 더 이상 활성 3:3 참가자가 아니다.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ALLOWED_PARTICIPANT_TRANSITIONS,
  CHAT_MEMBERSHIP_STATUSES,
  canTransitionParticipant,
  holdsChatMembership,
} from "../types";
import { BLIND_MEETING_BLOCKED_PARTICIPANT_STATUSES } from "../../meetingIcebreaker/eligibility";

describe("최종 no_show 는 단체 채팅 멤버십을 잃는다", () => {
  it("no_show 는 채팅 멤버십 상태가 아니다", () => {
    assert.equal(holdsChatMembership("no_show"), false);
    assert.equal(CHAT_MEMBERSHIP_STATUSES.includes("no_show"), false);
  });

  it("정상 참가자는 영향을 받지 않는다", () => {
    for (const status of ["confirmed", "attended", "completed"] as const) {
      assert.equal(
        holdsChatMembership(status),
        true,
        `${status} 는 채팅에 남아야 한다`
      );
    }
  });

  it("자리에서 빠진 다른 상태도 멤버십이 없다", () => {
    for (const status of ["cancelled", "replaced"] as const) {
      assert.equal(holdsChatMembership(status), false);
    }
  });

  it("멤버십 상태 집합이 정확히 셋이다", () => {
    assert.deepEqual([...CHAT_MEMBERSHIP_STATUSES].sort(), [
      "attended",
      "completed",
      "confirmed",
    ]);
  });
});

describe("최종 no_show 는 스스로 되돌릴 수 없다", () => {
  it("no_show -> attended 전이는 없다", () => {
    // 예전에는 이 edge 때문에 노쇼 처리된 참가자가 도착 안전도장을 눌러
    // 스스로 attended 로 복귀하고 (공개 신뢰 카운터를 올린 채) 룰렛 알림까지
    // 되살릴 수 있었다.
    assert.equal(canTransitionParticipant("no_show", "attended"), false);
    assert.equal(
      ALLOWED_PARTICIPANT_TRANSITIONS.no_show.includes("attended"),
      false
    );
  });

  it("no_show -> confirmed / completed 도 불가능하다", () => {
    assert.equal(canTransitionParticipant("no_show", "confirmed"), false);
    assert.equal(canTransitionParticipant("no_show", "completed"), false);
  });

  it("제재 전이만 남는다", () => {
    assert.deepEqual(ALLOWED_PARTICIPANT_TRANSITIONS.no_show, ["restricted"]);
  });

  it("정상 참가자의 도장 경로는 그대로다", () => {
    assert.equal(canTransitionParticipant("confirmed", "attended"), true);
    assert.equal(canTransitionParticipant("attended", "completed"), true);
  });
});

describe("최종 no_show 는 룰렛 대상이 아니다", () => {
  it("아이스브레이킹 차단 상태에 포함된다", () => {
    assert.ok(
      BLIND_MEETING_BLOCKED_PARTICIPANT_STATUSES.includes("no_show"),
      "no_show 는 룰렛/반복 알림에서 차단돼야 한다"
    );
  });

  it("정상 참가자는 차단되지 않는다", () => {
    for (const status of ["confirmed", "attended", "completed"]) {
      assert.equal(
        BLIND_MEETING_BLOCKED_PARTICIPANT_STATUSES.includes(status),
        false,
        `${status} 는 차단 대상이 아니다`
      );
    }
  });
});
