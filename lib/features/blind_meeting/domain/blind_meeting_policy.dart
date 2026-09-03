// =============================================================================
// 3:3 블라인드 취향 미팅 — 운영 정책 (취소 / 노쇼 / lifecycle)
// 경로: lib/features/blind_meeting/domain/blind_meeting_policy.dart
//
// 기간과 제재 값은 코드 곳곳에 흩어놓지 않고 이 설정 하나로 관리한다.
// 서버 구현(functions/src/blindMeeting/policy.ts)이 같은 값을 사용한다.
//
// 블라인드 미팅에는 금전 개념도 매칭 후 수락 단계도 없다. 매칭이 commit 되면
// 바로 확정되고, 취소·노쇼는 좌석 해제·대체 충원·참여 제한(신뢰/안전)만 결정한다.
// =============================================================================

/// 취소·노쇼 처리 결과.
enum BlindMeetingCancellationOutcome {
  /// 좌석을 놓고 나간다. 대체 충원 대상.
  released,

  /// 연락 없는 노쇼. 참여 제한 대상.
  noShow,

  /// 사고·응급 상황. 운영자 검토 기록을 남긴다.
  opsReview,
}

/// 취소 시점과 대체 성공 여부에 따른 처리 결정.
class BlindMeetingCancellationDecision {
  final BlindMeetingCancellationOutcome outcome;

  /// 대기자 충원을 시작해야 하는지.
  final bool triggersWaitlistFill;

  /// 참여 제한을 적용해야 하는지.
  final bool appliesRestriction;

  const BlindMeetingCancellationDecision({
    required this.outcome,
    required this.triggersWaitlistFill,
    required this.appliesRestriction,
  });
}

/// 반복 노쇼 제재 결정.
class BlindMeetingNoShowSanction {
  /// 참여 제한 일수. 0이면 제한 없음.
  final int restrictedDays;

  /// 운영자 검토가 필요한 단계인지.
  final bool requiresOpsReview;

  const BlindMeetingNoShowSanction({
    required this.restrictedDays,
    this.requiresOpsReview = false,
  });
}

/// 블라인드 미팅 운영 정책.
class BlindMeetingPolicy {
  /// 참석 재확인 1차 시점 (미팅 전).
  final Duration firstAttendanceCheckBefore;

  /// 참석 재확인 2차 시점 (미팅 전).
  final Duration secondAttendanceCheckBefore;

  /// 참석 재확인 응답 제한 시간.
  final Duration attendanceResponseWindow;

  /// 참석 재확인 재알림 횟수.
  final int attendanceReminderRetries;

  /// 긴급 취소 경계. 미팅 시작까지 이보다 적게 남은 취소는 긴급 대체 탐색으로 처리한다.
  final Duration lateCancellationBefore;

  /// 미팅 종료 후 후속 대화 푸시까지의 지연.
  final Duration followUpPushDelay;

  /// 후속 선택 가능 기간.
  final Duration followUpWindow;

  /// 후속 선택 마감 전 리마인더 시점 (마감까지 남은 시간).
  final Duration followUpReminderBeforeClose;

  /// 미팅 종료 후 단체 채팅을 계속 쓸 수 있는 기간.
  final Duration groupChatWritableAfterMeeting;

  /// 미팅 종료 후 단체 채팅 보관 처리 시점.
  final Duration groupChatArchiveAfterMeeting;

  /// 당일 긴급 대체 후보 탐색 기간 (미팅 시작 시각 기준 전후).
  final Duration urgentReplacementSearchWindow;

  /// 첫 번째 노쇼 참여 제한 일수.
  final int firstNoShowRestrictionDays;

  /// 90일 내 두 번째 노쇼 참여 제한 일수.
  final int secondNoShowRestrictionDays;

  /// 반복 노쇼 판정 기간.
  final Duration noShowLookback;

  const BlindMeetingPolicy({
    this.firstAttendanceCheckBefore = const Duration(hours: 24),
    this.secondAttendanceCheckBefore = const Duration(hours: 3),
    this.attendanceResponseWindow = const Duration(hours: 2),
    this.attendanceReminderRetries = 1,
    this.lateCancellationBefore = const Duration(hours: 6),
    this.followUpPushDelay = const Duration(minutes: 15),
    this.followUpWindow = const Duration(hours: 24),
    this.followUpReminderBeforeClose = const Duration(hours: 4),
    this.groupChatWritableAfterMeeting = const Duration(hours: 48),
    this.groupChatArchiveAfterMeeting = const Duration(days: 7),
    this.urgentReplacementSearchWindow = const Duration(minutes: 45),
    this.firstNoShowRestrictionDays = 14,
    this.secondNoShowRestrictionDays = 30,
    this.noShowLookback = const Duration(days: 90),
  });

  /// 현재 운영 정책.
  static const BlindMeetingPolicy current = BlindMeetingPolicy();

  /// 취소·노쇼 처리 결정.
  ///
  /// 금전 결과가 없으므로 [untilMeeting] 과 [replacementFound] 는 결정을
  /// 바꾸지 않는다 (호출부의 긴급 대체 판단·로그용).
  BlindMeetingCancellationDecision resolveCancellation({
    required Duration untilMeeting,
    required bool replacementFound,
    bool isNoShowWithoutContact = false,
    bool emergencyReviewRequested = false,
  }) {
    if (emergencyReviewRequested) {
      return const BlindMeetingCancellationDecision(
        outcome: BlindMeetingCancellationOutcome.opsReview,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
    }

    if (isNoShowWithoutContact) {
      return const BlindMeetingCancellationDecision(
        outcome: BlindMeetingCancellationOutcome.noShow,
        triggersWaitlistFill: false,
        appliesRestriction: true,
      );
    }

    return const BlindMeetingCancellationDecision(
      outcome: BlindMeetingCancellationOutcome.released,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    );
  }

  /// 노쇼 횟수에 따른 제재.
  ///
  /// [recentNoShowCount] 는 [noShowLookback] 기간 내 노쇼 횟수(이번 건 포함).
  BlindMeetingNoShowSanction resolveNoShowSanction({
    required int recentNoShowCount,
  }) {
    if (recentNoShowCount <= 1) {
      return BlindMeetingNoShowSanction(
        restrictedDays: firstNoShowRestrictionDays,
      );
    }
    if (recentNoShowCount == 2) {
      return BlindMeetingNoShowSanction(
        restrictedDays: secondNoShowRestrictionDays,
      );
    }
    return BlindMeetingNoShowSanction(
      restrictedDays: secondNoShowRestrictionDays * 2,
      requiresOpsReview: true,
    );
  }
}
