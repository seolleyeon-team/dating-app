import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_upload_submission_guard.dart';

void main() {
  test('a slot accepts one submission until it is released', () {
    final guard = AvatarUploadSubmissionGuard();

    expect(guard.tryAcquire(0), isTrue);
    expect(guard.tryAcquire(0), isFalse);
    expect(guard.isLocked(0), isTrue);

    guard.release(0);

    expect(guard.isLocked(0), isFalse);
    expect(guard.tryAcquire(0), isTrue);
  });

  test('different slots can be submitted independently', () {
    final guard = AvatarUploadSubmissionGuard();

    expect(guard.tryAcquire(0), isTrue);
    expect(guard.tryAcquire(1), isTrue);
    expect(guard.isLocked(0), isTrue);
    expect(guard.isLocked(1), isTrue);
  });
}
