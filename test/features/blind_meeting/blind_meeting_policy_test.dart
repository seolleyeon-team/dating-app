import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_policy.dart';

void main() {
  const policy = BlindMeetingPolicy.current;

  group('취소 정책 (금전 개념 없음)', () {
    test('취소 시점과 대체 성공 여부는 결과를 바꾸지 않는다', () {
      for (final until in const [
        Duration(hours: 30),
        Duration(hours: 10),
        Duration(hours: 2),
        Duration.zero,
      ]) {
        for (final replacementFound in const [true, false]) {
          final decision = policy.resolveCancellation(
            untilMeeting: until,
            replacementFound: replacementFound,
          );
          expect(decision.outcome, BlindMeetingCancellationOutcome.released);
          expect(decision.triggersWaitlistFill, isTrue);
          expect(decision.appliesRestriction, isFalse);
        }
      }
    });

    test('연락 없는 노쇼는 참여 제한 + 대기자 충원 없음', () {
      final decision = policy.resolveCancellation(
        untilMeeting: Duration.zero,
        replacementFound: false,
        isNoShowWithoutContact: true,
      );
      expect(decision.outcome, BlindMeetingCancellationOutcome.noShow);
      expect(decision.appliesRestriction, isTrue);
      expect(decision.triggersWaitlistFill, isFalse);
    });

    test('사고·응급 상황은 운영자 검토로 넘긴다', () {
      final decision = policy.resolveCancellation(
        untilMeeting: const Duration(minutes: 30),
        replacementFound: false,
        emergencyReviewRequested: true,
      );
      expect(decision.outcome, BlindMeetingCancellationOutcome.opsReview);
      expect(decision.appliesRestriction, isFalse);
      expect(decision.triggersWaitlistFill, isTrue);
    });

    test('긴급 취소 경계는 유지되고 수락 제한 시간은 존재하지 않는다', () {
      // 매칭 = 확정. 수락 창(acceptance window)은 정책에 없다.
      expect(policy.lateCancellationBefore, const Duration(hours: 6));
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
