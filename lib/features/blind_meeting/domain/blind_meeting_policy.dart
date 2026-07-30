// =============================================================================
// 3:3 블라인드 취향 미팅 — 운영 정책 (보증금 / 취소 / 노쇼 / lifecycle)
// 경로: lib/features/blind_meeting/domain/blind_meeting_policy.dart
//
// 금액과 기간은 코드 곳곳에 흩어놓지 않고 이 설정 하나로 관리한다.
// 서버 구현(functions/src/blindMeeting/policy.ts)이 같은 값을 사용하며,
// 실제 환급 실행은 서버에서 idempotent 하게 수행한다.
// =============================================================================

import '../../../constants/app_constants.dart';

/// 취소·노쇼 처리 결과.
enum BlindMeetingRefundOutcome {
  /// 전액 환급
  fullRefund,

  /// 일부 환급
  partialRefund,

  /// 미환급
  noRefund,

  /// 운영자 검토 후 예외 처리
  opsReview,
}

/// 취소 시점과 대체 성공 여부에 따른 처리 결정.
class BlindMeetingCancellationDecision {
  final BlindMeetingRefundOutcome outcome;

  /// 환급 비율 (basis point, 10000 = 100%).
  final int refundBasisPoints;

  /// 대기자 충원을 시작해야 하는지.
  final bool triggersWaitlistFill;

  /// 참여 제한을 적용해야 하는지.
  final bool appliesRestriction;

  const BlindMeetingCancellationDecision({
    required this.outcome,
    required this.refundBasisPoints,
    required this.triggersWaitlistFill,
    required this.appliesRestriction,
  });

  /// 보증금 금액에 대한 실제 환급액(원). 원 단위 내림.
  int refundAmountFor(int depositAmount) {
    if (depositAmount <= 0) return 0;
    return (depositAmount * refundBasisPoints) ~/ 10000;
  }
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
  /// 개인별 보증금 (원). 기존 결제 설정 상수를 재사용한다.
  final int depositAmount;

  /// 매칭 완료 후 최종 수락 응답 제한 시간.
  final Duration acceptanceWindow;

  /// 수락 후 보증금 결제 제한 시간.
  final Duration depositWindow;

  /// 참석 재확인 1차 시점 (미팅 전).
  final Duration firstAttendanceCheckBefore;

  /// 참석 재확인 2차 시점 (미팅 전).
  final Duration secondAttendanceCheckBefore;

  /// 참석 재확인 응답 제한 시간.
  final Duration attendanceResponseWindow;

  /// 참석 재확인 재알림 횟수.
  final int attendanceReminderRetries;

  /// 전액 환급 경계 (이 시간 이전 취소는 전액 환급).
  final Duration fullRefundBefore;

  /// 부분 환급 경계 (이 시간 이내 취소는 대체 성공 시에만 일부 환급).
  final Duration lateCancellationBefore;

  /// 6~24시간 전 취소에서 대체 실패 시 환급 비율 (basis point).
  final int lateCancellationReplacementFailedBasisPoints;

  /// 6시간 이내 취소에서 대체 성공 시 환급 비율 (basis point).
  final int urgentCancellationReplacementFoundBasisPoints;

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
    required this.depositAmount,
    this.acceptanceWindow = const Duration(hours: 12),
    this.depositWindow = const Duration(hours: 12),
    this.firstAttendanceCheckBefore = const Duration(hours: 24),
    this.secondAttendanceCheckBefore = const Duration(hours: 3),
    this.attendanceResponseWindow = const Duration(hours: 2),
    this.attendanceReminderRetries = 1,
    this.fullRefundBefore = const Duration(hours: 24),
    this.lateCancellationBefore = const Duration(hours: 6),
    this.lateCancellationReplacementFailedBasisPoints = 5000,
    this.urgentCancellationReplacementFoundBasisPoints = 5000,
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
  static const BlindMeetingPolicy current = BlindMeetingPolicy(
    depositAmount: AppConstants.meetingDeposit,
  );

  /// 취소 시점에 따른 처리 결정.
  ///
  /// [untilMeeting] 이 음수면 미팅이 이미 시작된 것으로 본다.
  BlindMeetingCancellationDecision resolveCancellation({
    required Duration untilMeeting,
    required bool replacementFound,
    bool isNoShowWithoutContact = false,
    bool emergencyReviewRequested = false,
  }) {
    if (emergencyReviewRequested) {
      return const BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.opsReview,
        refundBasisPoints: 0,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
    }

    if (isNoShowWithoutContact) {
      return const BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.noRefund,
        refundBasisPoints: 0,
        triggersWaitlistFill: false,
        appliesRestriction: true,
      );
    }

    if (untilMeeting >= fullRefundBefore) {
      return const BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.fullRefund,
        refundBasisPoints: 10000,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
    }

    if (untilMeeting >= lateCancellationBefore) {
      if (replacementFound) {
        return const BlindMeetingCancellationDecision(
          outcome: BlindMeetingRefundOutcome.fullRefund,
          refundBasisPoints: 10000,
          triggersWaitlistFill: true,
          appliesRestriction: false,
        );
      }
      return BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.partialRefund,
        refundBasisPoints: lateCancellationReplacementFailedBasisPoints,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
    }

    if (replacementFound) {
      return BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.partialRefund,
        refundBasisPoints: urgentCancellationReplacementFoundBasisPoints,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
    }

    return const BlindMeetingCancellationDecision(
      outcome: BlindMeetingRefundOutcome.noRefund,
      refundBasisPoints: 0,
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
