import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_policy.dart';

void main() {
  const policy = BlindMeetingPolicy.current;

  group('보증금 설정', () {
    test('금액은 코드에 고정되지 않고 앱 결제 설정에서 온다', () {
      expect(policy.depositAmount, greaterThan(0));
    });

    test('환급 비율은 basis point로 계산된다', () {
      const half = BlindMeetingCancellationDecision(
        outcome: BlindMeetingRefundOutcome.partialRefund,
        refundBasisPoints: 5000,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      );
      expect(half.refundAmountFor(5000), 2500);
      expect(half.refundAmountFor(0), 0);
    });
  });

  group('취소 및 환급 정책', () {
    test('24시간 이전 취소는 전액 환급 + 대기자 충원', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(hours: 30),
        replacementFound: false,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.fullRefund);
      expect(decision.refundBasisPoints, 10000);
      expect(decision.triggersWaitlistFill, isTrue);
      expect(decision.appliesRestriction, isFalse);
    });

    test('6~24시간 전 취소는 대체 성공 시 전액 환급', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(hours: 10),
        replacementFound: true,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.fullRefund);
    });

    test('6~24시간 전 취소는 대체 실패 시 일부 차감', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(hours: 10),
        replacementFound: false,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.partialRefund);
      expect(decision.refundBasisPoints, lessThan(10000));
      expect(decision.refundBasisPoints, greaterThan(0));
    });

    test('6시간 이내 취소는 대체 성공 시 일부 환급', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(hours: 2),
        replacementFound: true,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.partialRefund);
    });

    test('6시간 이내 취소는 대체 실패 시 원칙적으로 미환급', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(hours: 2),
        replacementFound: false,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.noRefund);
      expect(decision.refundBasisPoints, 0);
      expect(decision.appliesRestriction, isFalse);
    });

    test('연락 없는 노쇼는 미환급 + 참여 제한', () {
      final decision = policy.resolveCancellation(
        untilMeeting: Duration.zero,
        replacementFound: false,
        isNoShowWithoutContact: true,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.noRefund);
      expect(decision.appliesRestriction, isTrue);
      expect(decision.triggersWaitlistFill, isFalse);
    });

    test('사고·응급 상황은 운영자 검토로 넘긴다', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(minutes: 30),
        replacementFound: false,
        emergencyReviewRequested: true,
      );
      expect(decision.outcome, BlindMeetingRefundOutcome.opsReview);
      expect(decision.appliesRestriction, isFalse);
    });
  });

  group('반복 노쇼 제재', () {
    test('첫 번째 노쇼는 14일 제한', () {
      expect(
        policy.resolveNoShowSanction(recentNoShowCount: 1).restrictedDays,
        14,
      );
    });

    test('90일 이내 두 번째 노쇼는 30일 제한', () {
      expect(
        policy.resolveNoShowSanction(recentNoShowCount: 2).restrictedDays,
        30,
      );
      expect(policy.noShowLookback, const Duration(days: 90));
    });

    test('반복 노쇼는 장기 제한 + 운영 검토', () {
      final sanction = policy.resolveNoShowSanction(recentNoShowCount: 3);
      expect(sanction.restrictedDays, greaterThan(30));
      expect(sanction.requiresOpsReview, isTrue);
    });
  });

  group('lifecycle 타이밍', () {
    test('참석 재확인은 24시간 전과 3시간 전', () {
      expect(policy.firstAttendanceCheckBefore, const Duration(hours: 24));
      expect(policy.secondAttendanceCheckBefore, const Duration(hours: 3));
    });

    test('후속 대화 푸시는 약 15분 후, 선택 기간은 24시간', () {
      expect(policy.followUpPushDelay, const Duration(minutes: 15));
      expect(policy.followUpWindow, const Duration(hours: 24));
    });

    test('단체 채팅은 48시간 후 읽기 전용, 7일 후 보관', () {
      expect(policy.groupChatWritableAfterMeeting, const Duration(hours: 48));
      expect(policy.groupChatArchiveAfterMeeting, const Duration(days: 7));
      expect(
        policy.groupChatArchiveAfterMeeting,
        greaterThan(policy.groupChatWritableAfterMeeting),
      );
    });
  });
}
