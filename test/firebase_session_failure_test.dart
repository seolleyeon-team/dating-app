import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/firebase_session_failure.dart';

void main() {
  test(
    'failure text is safe and maps App Check rejection to user guidance',
    () {
      const failure = FirebaseSessionFailure(
        reason: FirebaseSessionFailureReason.appCheckRejected,
        errorCode: '403',
        supportCode: 'AC-R-ATTESTATION',
      );

      expect(failure.toString(), contains('개발 환경 보안 인증'));
      expect(failure.toString(), contains('진단 코드: AC-R-ATTESTATION'));
      expect(failure.toString(), isNot(contains('403')));
      expect(failure.toString(), isNot(contains('secret-token')));
    },
  );

  test('support code is sanitized before it is shown to a tester', () {
    const failure = FirebaseSessionFailure(
      reason: FirebaseSessionFailureReason.appCheckUnavailable,
      supportCode: 'ac-u-network\nsecret-token',
    );

    expect(failure.toString(), contains('진단 코드: AC-U-NETWORK-SECRET-TOKEN'));
    expect(failure.toString(), isNot(contains('\nsecret-token')));
  });

  test('transient session inspection gets retry guidance', () {
    const failure = FirebaseSessionFailure(
      reason: FirebaseSessionFailureReason.sessionInspectionFailed,
      errorCode: 'network',
    );

    expect(failure.toString(), contains('네트워크 상태'));
    expect(failure.toString(), isNot(contains('network')));
  });

  test('identity mismatch gets re-login guidance', () {
    const failure = FirebaseSessionFailure(
      reason: FirebaseSessionFailureReason.identityMismatch,
    );

    expect(failure.toString(), contains('카카오 계정과 일치'));
  });

  test('transient bridge failures preserve the cached identity for retry', () {
    expect(
      const FirebaseSessionFailure(
        reason: FirebaseSessionFailureReason.sessionInspectionFailed,
      ).isTransient,
      isTrue,
    );
    expect(
      const FirebaseSessionFailure(
        reason: FirebaseSessionFailureReason.appCheckRejected,
      ).isTransient,
      isTrue,
    );
    expect(
      const FirebaseSessionFailure(
        reason: FirebaseSessionFailureReason.identityMismatch,
      ).isTransient,
      isFalse,
    );
  });
}
