import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/utils/safety_stamp_availability.dart';

void main() {
  Map<String, dynamic> goodbyePromise(DateTime meetupCompletedAt) {
    return <String, dynamic>{
      'status': 'in_progress',
      'dateTime': DateTime(2026, 8, 29, 12),
      'participantIds': <String>['u1', 'u2'],
      'safetyStamp': <String, dynamic>{
        'meetupStampedUserIds': <String>['u1', 'u2'],
        'meetupCompletedAt': meetupCompletedAt,
      },
    };
  }

  test('헤어짐 안전도장은 만남 확인 후 24시간 동안 계속 열 수 있다', () {
    final completedAt = DateTime(2026, 8, 29, 12);

    final availability = evaluateSafetyStampAvailability(
      goodbyePromise(completedAt),
      now: completedAt.add(const Duration(hours: 2)),
    );

    expect(availability.phase, SafetyStampPhase.goodbye);
    expect(availability.isVisible, isTrue);
    expect(availability.canOpen, isTrue);
  });

  test('헤어짐 안전도장은 만남 확인 24시간 후에는 숨긴다', () {
    final completedAt = DateTime(2026, 8, 29, 12);

    final availability = evaluateSafetyStampAvailability(
      goodbyePromise(completedAt),
      now: completedAt.add(const Duration(hours: 24, seconds: 1)),
    );

    expect(availability.isVisible, isFalse);
    expect(availability.canOpen, isFalse);
  });
}
