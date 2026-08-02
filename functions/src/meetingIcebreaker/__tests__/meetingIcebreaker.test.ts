/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 서버 로직 테스트
 * 실행: npm --prefix functions test
 *
 * Node 20+ 내장 테스트 러너(node:test)를 사용한다 (추가 의존성 없음).
 * Firestore를 건드리지 않는 순수 로직만 검증한다.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  BLIND_MEETING_ACTIVE_STATUSES,
  classifySeasonMeetingRoom,
  isBlindMeetingParticipantBlocked,
  isBlindMeetingStatusActive,
  isBlindMeetingStatusTerminal,
  isSeasonMeetingPromiseActive,
  isSeasonMeetingPromiseTerminal,
  isUserBlockedForPrompts,
  readPromiseSafetyStampUserIds,
  readPromiseStatus,
} from "../eligibility";
import {
  DEFAULT_MEETING_ICEBREAKER_POLICY,
  areIcebreakerNotificationsEnabled,
  computeExpiresAtMs,
  computeFirstPromptAtMs,
  computeNextPromptAtMs,
  decidePromptDispatch,
  isAlcoholFreeCopyForced,
  isBombPassEnabled,
  isRouletteEnabled,
  meetingIcebreakerPolicyFromConfigDoc,
  promptIntervalMs,
  promptSequenceBucket,
  scheduleDelaySecondsFor,
} from "../policy";
import {
  MEETING_ICEBREAKER_DEEPLINK_TYPE,
  MEETING_ICEBREAKER_NOTIFICATION_TYPE,
  MEETING_ICEBREAKER_PROMPT_BODY,
  MEETING_ICEBREAKER_PROMPT_TITLE,
  buildPromptCollapseKey,
  buildPromptNotificationId,
  buildPromptPushIdempotencyKey,
} from "../notifications";
import {
  MEETING_ICEBREAKER_QUEUE,
  MEETING_ICEBREAKER_QUEUE_PATH,
  isMeetingIcebreakerPromptTaskPayload,
} from "../tasks";
import {
  BLIND_TASTE_MEETING_TYPE,
  MEETING_ICEBREAKER_COLLECTIONS,
  MEETING_ICEBREAKER_PARTICIPANT_COUNT,
  SEASON_MEETING_TYPE,
  asInt,
  asStrArray,
  buildMeetingIcebreakerSessionId,
  isMeetingIcebreakerMeetingType,
} from "../types";
import { resolveSessionId } from "../verify";
import { notificationCategoryForType } from "../../shared/notify";

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;

function sixParticipants(): string[] {
  return ["a1", "a2", "a3", "b1", "b2", "b3"];
}

function participants(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `u${i}`);
}

describe("적용 대상 판정 (시즌 미팅 채팅방)", () => {
  it("시즌 미팅 전용 roomType은 통과한다", () => {
    const result = classifySeasonMeetingRoom({
      roomType: "season_meeting_group",
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, true);
    if (result.eligible) {
      assert.equal(
        result.participantIds.length,
        MEETING_ICEBREAKER_PARTICIPANT_COUNT
      );
    }
  });

  it("eventType이 season_meeting인 단체 방도 통과한다", () => {
    const result = classifySeasonMeetingRoom({
      type: "group",
      eventType: "season_meeting",
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, true);
  });

  it("3:3 매칭 문서가 연결된 단체 방도 통과한다", () => {
    const result = classifySeasonMeetingRoom({
      type: "group",
      threeVsThreeMatchId: "match_1",
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, true);
  });

  it("블라인드 미팅 채팅방은 이 경로에서 처리하지 않는다", () => {
    const result = classifySeasonMeetingRoom({
      roomType: "blind_meeting_group",
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, false);
    if (!result.eligible) assert.equal(result.reason, "blind_meeting_room");
  });

  it("1:1 채팅방은 거부한다", () => {
    const result = classifySeasonMeetingRoom({
      type: "one_to_one",
      participantIds: ["a1", "b1"],
    });
    assert.equal(result.eligible, false);
    if (!result.eligible) assert.equal(result.reason, "direct_room");
  });

  it("일반 이벤트 단체 방은 거부한다", () => {
    const result = classifySeasonMeetingRoom({
      type: "group",
      eventType: "general_event",
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, false);
    if (!result.eligible) assert.equal(result.reason, "not_season_meeting");
  });

  it("표시가 전혀 없는 방은 기본적으로 거부한다", () => {
    const result = classifySeasonMeetingRoom({
      participantIds: sixParticipants(),
    });
    assert.equal(result.eligible, false);
    if (!result.eligible) assert.equal(result.reason, "not_season_meeting");
  });

  it("3:3(6명)이 아니면 거부한다", () => {
    for (const count of [0, 2, 4, 5, 7, 8]) {
      const result = classifySeasonMeetingRoom({
        roomType: "season_meeting_group",
        participantIds: participants(count),
      });
      assert.equal(result.eligible, false, `${count}명인데 통과됨`);
      if (!result.eligible) {
        assert.equal(result.reason, "participant_count_mismatch");
      }
    }
  });

  it("방 문서가 없으면 거부한다", () => {
    for (const raw of [null, undefined, "x", 1, []]) {
      const result = classifySeasonMeetingRoom(raw);
      assert.equal(result.eligible, false);
      if (!result.eligible) assert.equal(result.reason, "missing_room");
    }
  });
});

describe("약속 안전도장 읽기", () => {
  it("도착 도장 사용자 목록을 읽는다", () => {
    const ids = readPromiseSafetyStampUserIds(
      { safetyStamp: { meetupStampedUserIds: ["a1", "b1"] } },
      "meetup"
    );
    assert.deepEqual(ids, ["a1", "b1"]);
  });

  it("legacy stampedUserIds로 폴백한다", () => {
    const ids = readPromiseSafetyStampUserIds(
      { safetyStamp: { stampedUserIds: ["a1"] } },
      "meetup"
    );
    assert.deepEqual(ids, ["a1"]);
  });

  it("신규 필드가 있으면 legacy를 무시한다", () => {
    const ids = readPromiseSafetyStampUserIds(
      {
        safetyStamp: {
          meetupStampedUserIds: ["a2"],
          stampedUserIds: ["a1"],
        },
      },
      "meetup"
    );
    assert.deepEqual(ids, ["a2"]);
  });

  it("종료 도장 목록을 읽는다", () => {
    const ids = readPromiseSafetyStampUserIds(
      { safetyStamp: { goodbyeStampedUserIds: ["a1", "a1", "b2"] } },
      "goodbye"
    );
    assert.deepEqual(ids, ["a1", "b2"]);
  });

  it("안전도장이 없으면 빈 목록이다", () => {
    assert.deepEqual(readPromiseSafetyStampUserIds({}, "meetup"), []);
    assert.deepEqual(readPromiseSafetyStampUserIds(null, "goodbye"), []);
  });

  it("진행 중 상태를 구분한다", () => {
    assert.equal(isSeasonMeetingPromiseActive({ status: "confirmed" }), true);
    assert.equal(isSeasonMeetingPromiseActive({ status: "in_progress" }), true);
    assert.equal(isSeasonMeetingPromiseActive({ status: "completed" }), false);
    assert.equal(isSeasonMeetingPromiseActive({ status: "pending" }), false);
  });

  it("종료 상태를 구분한다", () => {
    assert.equal(isSeasonMeetingPromiseTerminal({ status: "completed" }), true);
    assert.equal(isSeasonMeetingPromiseTerminal({ status: "cancelled" }), true);
    assert.equal(
      isSeasonMeetingPromiseTerminal({ status: "in_progress" }),
      false
    );
  });

  it("status는 소문자로 정규화한다", () => {
    assert.equal(readPromiseStatus({ status: " In_Progress " }), "in_progress");
  });
});

describe("블라인드 미팅 상태 판정", () => {
  it("도착 이후 구간에서만 활성화한다", () => {
    assert.deepEqual(BLIND_MEETING_ACTIVE_STATUSES, [
      "checkin_open",
      "in_progress",
    ]);
    assert.equal(isBlindMeetingStatusActive("checkin_open"), true);
    assert.equal(isBlindMeetingStatusActive("in_progress"), true);
    assert.equal(isBlindMeetingStatusActive("schedule_confirmed"), false);
    assert.equal(isBlindMeetingStatusActive("chat_open"), false);
  });

  it("종료 상태를 구분한다", () => {
    for (const status of [
      "completed",
      "followup_open",
      "read_only",
      "archived",
      "cancelled",
    ]) {
      assert.equal(isBlindMeetingStatusTerminal(status), true, status);
    }
    assert.equal(isBlindMeetingStatusTerminal("in_progress"), false);
  });

  it("교체·취소·노쇼·정지 참가자는 발송 대상이 아니다", () => {
    for (const status of [
      "cancelled",
      "cancel_requested",
      "replacement_pending",
      "replaced",
      "no_show",
      "restricted",
    ]) {
      assert.equal(isBlindMeetingParticipantBlocked(status), true, status);
    }
    assert.equal(isBlindMeetingParticipantBlocked("attended"), false);
    assert.equal(isBlindMeetingParticipantBlocked("confirmed"), false);
  });

  it("탈퇴·정지 계정에는 발송하지 않는다", () => {
    assert.equal(isUserBlockedForPrompts({ isWithdrawn: true }), true);
    assert.equal(isUserBlockedForPrompts({ loginDisabled: true }), true);
    assert.equal(isUserBlockedForPrompts({ isSuspended: true }), true);
    assert.equal(isUserBlockedForPrompts({ isBanned: true }), true);
    assert.equal(isUserBlockedForPrompts({}), false);
    // 문서가 없으면 보내지 않는다.
    assert.equal(isUserBlockedForPrompts(undefined), true);
  });
});

describe("알림 주기 정책", () => {
  const policy = DEFAULT_MEETING_ICEBREAKER_POLICY;

  it("기본값은 15분 주기 / 최대 6시간이다", () => {
    assert.equal(policy.promptIntervalMinutes, 15);
    assert.equal(policy.firstPromptDelayMinutes, 15);
    assert.equal(policy.maxPromptDurationHours, 6);
    assert.equal(promptIntervalMs(policy), 15 * MINUTE);
  });

  it("시작 도장 15분 뒤 첫 알림, 6시간 뒤 종료", () => {
    const startedAt = Date.UTC(2026, 6, 31, 12, 0, 0);
    assert.equal(
      computeFirstPromptAtMs(startedAt, policy),
      startedAt + 15 * MINUTE
    );
    assert.equal(computeExpiresAtMs(startedAt, policy), startedAt + 6 * HOUR);
  });

  it("이후 15분마다 반복한다", () => {
    const startedAt = Date.UTC(2026, 6, 31, 12, 0, 0);
    let at = computeFirstPromptAtMs(startedAt, policy);
    const times = [at];
    for (let i = 0; i < 5; i++) {
      at = computeNextPromptAtMs({
        nowMs: at,
        previousPromptAtMs: at,
        policy,
      });
      times.push(at);
    }
    assert.deepEqual(
      times.map((t) => (t - startedAt) / MINUTE),
      [15, 30, 45, 60, 75, 90]
    );
  });

  it("운영 설정으로 주기와 최대 시간을 바꿀 수 있다", () => {
    const merged = meetingIcebreakerPolicyFromConfigDoc({
      promptIntervalMinutes: 20,
      maxPromptDurationHours: 3,
      notificationsEnabled: 0,
    });
    assert.equal(merged.promptIntervalMinutes, 20);
    assert.equal(merged.maxPromptDurationHours, 3);
    assert.equal(merged.notificationsEnabled, 0);
    // 지정하지 않은 값은 기본값을 유지한다.
    assert.equal(merged.minPromptGapMinutes, policy.minPromptGapMinutes);
  });

  it("잘못된 설정 값은 무시하고 최소값을 보장한다", () => {
    const merged = meetingIcebreakerPolicyFromConfigDoc({
      promptIntervalMinutes: 0,
      maxPromptDurationHours: -5,
      firstPromptDelayMinutes: "10",
    });
    assert.equal(merged.promptIntervalMinutes, 1);
    assert.equal(merged.maxPromptDurationHours, 6);
    assert.equal(merged.firstPromptDelayMinutes, 15);
  });

  it("설정 문서가 없으면 기본값을 쓴다", () => {
    assert.deepEqual(meetingIcebreakerPolicyFromConfigDoc(null), policy);
    assert.deepEqual(meetingIcebreakerPolicyFromConfigDoc("x"), policy);
  });

  it("feature flag를 해석한다", () => {
    assert.equal(areIcebreakerNotificationsEnabled(policy), true);
    assert.equal(isRouletteEnabled(policy), true);
    assert.equal(isBombPassEnabled(policy), true);
    assert.equal(isAlcoholFreeCopyForced(policy), false);

    const noNotifications = { ...policy, notificationsEnabled: 0 };
    assert.equal(areIcebreakerNotificationsEnabled(noNotifications), false);
    assert.equal(isRouletteEnabled(noNotifications), true);

    // 룰렛 전체를 끄면 알림과 폭탄 게임도 함께 꺼진다.
    const noRoulette = { ...policy, rouletteEnabled: 0 };
    assert.equal(isRouletteEnabled(noRoulette), false);
    assert.equal(areIcebreakerNotificationsEnabled(noRoulette), false);
    assert.equal(isBombPassEnabled(noRoulette), false);

    const noBomb = { ...policy, bombPassEnabled: 0 };
    assert.equal(isBombPassEnabled(noBomb), false);
    assert.equal(areIcebreakerNotificationsEnabled(noBomb), true);

    assert.equal(
      isAlcoholFreeCopyForced({ ...policy, alcoholFreeCopyForced: 1 }),
      true
    );
  });
});

describe("알림 발송 판정", () => {
  const policy = DEFAULT_MEETING_ICEBREAKER_POLICY;
  const startedAt = Date.UTC(2026, 6, 31, 12, 0, 0);
  const expiresAt = computeExpiresAtMs(startedAt, policy);

  it("예약 시각에 도달하면 발송한다", () => {
    const scheduledFor = startedAt + 15 * MINUTE;
    const decision = decidePromptDispatch({
      nowMs: scheduledFor,
      scheduledForMs: scheduledFor,
      expiresAtMs: expiresAt,
      lastPromptAtMs: null,
      policy,
    });
    assert.equal(decision.action, "send");
    if (decision.action === "send") {
      assert.equal(decision.skippedPrompts, 0);
      assert.equal(decision.nextPromptAtMs, scheduledFor + 15 * MINUTE);
    }
  });

  it("너무 이르게 실행되면 다시 예약한다", () => {
    const scheduledFor = startedAt + 15 * MINUTE;
    const decision = decidePromptDispatch({
      nowMs: scheduledFor - 5 * MINUTE,
      scheduledForMs: scheduledFor,
      expiresAtMs: expiresAt,
      lastPromptAtMs: null,
      policy,
    });
    assert.equal(decision.action, "reschedule");
    if (decision.action === "reschedule") {
      assert.equal(decision.reason, "too_early");
      assert.equal(decision.nextPromptAtMs, scheduledFor);
    }
  });

  it("허용 오차 안이면 발송한다", () => {
    const scheduledFor = startedAt + 15 * MINUTE;
    const decision = decidePromptDispatch({
      nowMs: scheduledFor - 30 * 1000,
      scheduledForMs: scheduledFor,
      expiresAtMs: expiresAt,
      lastPromptAtMs: null,
      policy,
    });
    assert.equal(decision.action, "send");
  });

  it("직전에 보냈으면 rate limit으로 건너뛴다", () => {
    const scheduledFor = startedAt + 15 * MINUTE;
    const decision = decidePromptDispatch({
      nowMs: scheduledFor,
      scheduledForMs: scheduledFor,
      expiresAtMs: expiresAt,
      lastPromptAtMs: scheduledFor - 2 * MINUTE,
      policy,
    });
    assert.equal(decision.action, "reschedule");
    if (decision.action === "reschedule") {
      assert.equal(decision.reason, "rate_limited");
      assert.ok(decision.nextPromptAtMs > scheduledFor);
    }
  });

  it("최대 지속 시간을 넘으면 종료한다", () => {
    const decision = decidePromptDispatch({
      nowMs: expiresAt + MINUTE,
      scheduledForMs: expiresAt - MINUTE,
      expiresAtMs: expiresAt,
      lastPromptAtMs: null,
      policy,
    });
    assert.equal(decision.action, "stop");
    if (decision.action === "stop") {
      assert.equal(decision.reason, "max_duration_reached");
    }
  });

  it("누락된 알림을 몰아 보내지 않는다", () => {
    // 예약 시각보다 47분 늦게 실행됨 = 3주기 누락
    const scheduledFor = startedAt + 15 * MINUTE;
    const nowMs = scheduledFor + 47 * MINUTE;
    const decision = decidePromptDispatch({
      nowMs,
      scheduledForMs: scheduledFor,
      expiresAtMs: expiresAt,
      lastPromptAtMs: null,
      policy,
    });

    assert.equal(decision.action, "send");
    if (decision.action === "send") {
      // 발송은 1건이고, 건너뛴 주기 수만 기록한다.
      assert.equal(decision.skippedPrompts, 3);
      // 다음 주기는 원래 cadence에 맞춰 미래로 재계산된다.
      assert.equal(decision.nextPromptAtMs, scheduledFor + 60 * MINUTE);
      assert.ok(decision.nextPromptAtMs > nowMs);
    }
  });

  it("다음 알림 시각은 항상 미래다", () => {
    const scheduledFor = startedAt + 15 * MINUTE;
    for (const lateMinutes of [0, 1, 14, 15, 16, 60, 121, 300]) {
      const nowMs = scheduledFor + lateMinutes * MINUTE;
      const next = computeNextPromptAtMs({
        nowMs,
        previousPromptAtMs: scheduledFor,
        policy,
      });
      assert.ok(next > nowMs, `${lateMinutes}분 지연에서 과거 시각이 나왔다`);
      // cadence 정렬이 유지된다.
      assert.equal((next - scheduledFor) % (15 * MINUTE), 0);
    }
  });

  it("Cloud Tasks 지연 시간은 음수가 되지 않는다", () => {
    assert.equal(scheduleDelaySecondsFor(1000, 5000), 0);
    assert.equal(scheduleDelaySecondsFor(65_000, 5_000), 60);
  });

  it("순번은 bucket으로만 기록한다", () => {
    assert.equal(promptSequenceBucket(1), "1");
    assert.equal(promptSequenceBucket(3), "2-4");
    assert.equal(promptSequenceBucket(7), "5-8");
    assert.equal(promptSequenceBucket(12), "9-16");
    assert.equal(promptSequenceBucket(40), "17+");
  });
});

describe("알림 idempotency", () => {
  it("같은 (세션, 참가자, 순번)은 같은 key를 만든다", () => {
    assert.equal(
      buildPromptNotificationId("blind_m1", "u1", 3),
      buildPromptNotificationId("blind_m1", "u1", 3)
    );
  });

  it("순번이 다르면 key가 달라진다", () => {
    assert.notEqual(
      buildPromptNotificationId("blind_m1", "u1", 3),
      buildPromptNotificationId("blind_m1", "u1", 4)
    );
  });

  it("참가자와 세션이 다르면 key가 달라진다", () => {
    assert.notEqual(
      buildPromptNotificationId("blind_m1", "u1", 1),
      buildPromptNotificationId("blind_m1", "u2", 1)
    );
    assert.notEqual(
      buildPromptNotificationId("blind_m1", "u1", 1),
      buildPromptNotificationId("season_p1", "u1", 1)
    );
  });

  it("인앱과 푸시 key를 분리한다", () => {
    assert.notEqual(
      buildPromptNotificationId("blind_m1", "u1", 1),
      buildPromptPushIdempotencyKey("blind_m1", "u1", 1)
    );
  });

  it("collapse key는 세션 단위다", () => {
    assert.equal(
      buildPromptCollapseKey("blind_m1"),
      buildPromptCollapseKey("blind_m1")
    );
    assert.notEqual(
      buildPromptCollapseKey("blind_m1"),
      buildPromptCollapseKey("blind_m2")
    );
  });

  it("알림 문구와 타입이 앱 정의와 같다", () => {
    assert.equal(
      MEETING_ICEBREAKER_NOTIFICATION_TYPE,
      "meeting_icebreaker_roulette"
    );
    assert.equal(
      MEETING_ICEBREAKER_DEEPLINK_TYPE,
      "meeting_icebreaker_roulette"
    );
    assert.equal(MEETING_ICEBREAKER_PROMPT_TITLE, "설레연 미팅 도우미");
    assert.equal(MEETING_ICEBREAKER_PROMPT_BODY, "미팅에서 어색할 때 눌러보세요!");
  });

  it("알림 설정 카테고리는 이벤트를 따른다", () => {
    assert.equal(
      notificationCategoryForType(MEETING_ICEBREAKER_NOTIFICATION_TYPE),
      "events"
    );
  });
});

describe("세션 식별자", () => {
  it("미팅 유형별 접두어를 붙인다", () => {
    assert.equal(
      buildMeetingIcebreakerSessionId(SEASON_MEETING_TYPE, "p1"),
      "season_p1"
    );
    assert.equal(
      buildMeetingIcebreakerSessionId(BLIND_TASTE_MEETING_TYPE, "m1"),
      "blind_m1"
    );
  });

  it("두 유형의 id가 겹치지 않는다", () => {
    assert.notEqual(
      buildMeetingIcebreakerSessionId(SEASON_MEETING_TYPE, "x"),
      buildMeetingIcebreakerSessionId(BLIND_TASTE_MEETING_TYPE, "x")
    );
  });

  it("허용된 미팅 유형만 인정한다", () => {
    assert.equal(isMeetingIcebreakerMeetingType("seasonMeeting"), true);
    assert.equal(isMeetingIcebreakerMeetingType("blindTasteMeeting"), true);
    assert.equal(isMeetingIcebreakerMeetingType("randomMeeting"), false);
    assert.equal(isMeetingIcebreakerMeetingType("generalEvent"), false);
    assert.equal(isMeetingIcebreakerMeetingType(null), false);
  });

  it("sessionId가 없으면 meetingId + 유형으로 복원한다", () => {
    assert.equal(
      resolveSessionId({ sessionId: "blind_m1" }),
      "blind_m1"
    );
    assert.equal(
      resolveSessionId({ meetingId: "m1", meetingType: "blindTasteMeeting" }),
      "blind_m1"
    );
    assert.equal(
      resolveSessionId({ meetingId: "p1", meetingType: "seasonMeeting" }),
      "season_p1"
    );
    // 유형을 모르면 복원할 수 없다 (임의 미팅 접근 방지).
    assert.equal(resolveSessionId({ meetingId: "m1" }), null);
    assert.equal(resolveSessionId({}), null);
  });

  it("collection group 이름이 블라인드 미팅과 겹치지 않는다", () => {
    assert.equal(
      MEETING_ICEBREAKER_COLLECTIONS.promptParticipants,
      "promptParticipants"
    );
    assert.notEqual(
      MEETING_ICEBREAKER_COLLECTIONS.promptParticipants,
      "participants"
    );
  });
});

describe("Cloud Tasks payload", () => {
  const valid = {
    sessionId: "blind_m1",
    uid: "u1",
    scheduleVersion: 2,
    promptSequence: 3,
    scheduledForMs: 1_800_000_000_000,
    taskToken: "abc123",
  };

  it("queue 이름과 경로가 일치한다", () => {
    assert.equal(MEETING_ICEBREAKER_QUEUE, "dispatchMeetingIcebreakerPrompt");
    assert.ok(
      MEETING_ICEBREAKER_QUEUE_PATH.endsWith(`/${MEETING_ICEBREAKER_QUEUE}`)
    );
  });

  it("정상 payload를 통과시킨다", () => {
    assert.equal(isMeetingIcebreakerPromptTaskPayload(valid), true);
  });

  it("필수 값이 없으면 거부한다", () => {
    assert.equal(isMeetingIcebreakerPromptTaskPayload(undefined), false);
    assert.equal(
      isMeetingIcebreakerPromptTaskPayload({ ...valid, sessionId: "" }),
      false
    );
    assert.equal(
      isMeetingIcebreakerPromptTaskPayload({ ...valid, uid: "" }),
      false
    );
    assert.equal(
      isMeetingIcebreakerPromptTaskPayload({ ...valid, taskToken: "" }),
      false
    );
    assert.equal(
      isMeetingIcebreakerPromptTaskPayload({ ...valid, scheduledForMs: 0 }),
      false
    );
    assert.equal(
      isMeetingIcebreakerPromptTaskPayload({
        ...valid,
        scheduleVersion: Number.NaN,
      }),
      false
    );
  });
});

describe("파싱 헬퍼", () => {
  it("문자열 배열을 중복 없이 정리한다", () => {
    assert.deepEqual(asStrArray(["a", " a ", "b", "", null]), ["a", "b"]);
    assert.deepEqual(asStrArray("a"), []);
  });

  it("정수를 안전하게 읽는다", () => {
    assert.equal(asInt(3), 3);
    assert.equal(asInt(3.7), 3);
    assert.equal(asInt("5"), 5);
    assert.equal(asInt("x", 9), 9);
    assert.equal(asInt(undefined, 1), 1);
  });
});
