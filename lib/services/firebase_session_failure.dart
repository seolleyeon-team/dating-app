enum FirebaseSessionFailureReason {
  kakaoAccessTokenMissing,
  kakaoAccessTokenInvalid,
  appCheckUnavailable,
  appCheckRejected,
  callableUnauthenticated,
  callableFailed,
  customTokenEmpty,
  firebaseSignInFailed,
  sessionInspectionFailed,
  identityMismatch,
}

/// Sanitized failure returned by the Kakao-to-Firebase session bridge.
class FirebaseSessionFailure implements Exception {
  const FirebaseSessionFailure({
    required this.reason,
    this.errorCode,
  });

  final FirebaseSessionFailureReason reason;
  final String? errorCode;

  /// The caller may retry these failures without discarding the cached Kakao
  /// identity. This does not make the current Firebase session trusted.
  bool get isTransient => switch (reason) {
    FirebaseSessionFailureReason.appCheckUnavailable ||
    FirebaseSessionFailureReason.appCheckRejected ||
    FirebaseSessionFailureReason.callableUnauthenticated ||
    FirebaseSessionFailureReason.callableFailed ||
    FirebaseSessionFailureReason.sessionInspectionFailed => true,
    _ => false,
  };

  String get userMessage => switch (reason) {
    FirebaseSessionFailureReason.kakaoAccessTokenMissing =>
      '카카오 인증 정보를 확인하지 못했어요. 다시 로그인해 주세요.',
    FirebaseSessionFailureReason.kakaoAccessTokenInvalid =>
      '카카오 인증이 만료됐어요. 다시 로그인해 주세요.',
    FirebaseSessionFailureReason.appCheckUnavailable =>
      '개발 환경 보안 인증을 준비하지 못했어요. 네트워크 상태를 확인한 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.appCheckRejected =>
      '개발 환경 보안 인증을 확인하지 못했어요. 앱을 다시 실행한 뒤 다시 시도해 주세요.',
    FirebaseSessionFailureReason.callableUnauthenticated =>
      'Firebase 인증 세션을 만들지 못했어요. 잠시 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.callableFailed =>
      '로그인 세션을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.customTokenEmpty =>
      '로그인 세션 응답이 올바르지 않아요. 잠시 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.firebaseSignInFailed =>
      'Firebase 인증을 완료하지 못했어요. 잠시 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.sessionInspectionFailed =>
      '네트워크 상태를 확인한 후 다시 시도해 주세요.',
    FirebaseSessionFailureReason.identityMismatch =>
      '현재 Firebase 세션이 카카오 계정과 일치하지 않아요. 다시 로그인해 주세요.',
  };

  String get diagnosticCode => reason.name;

  @override
  String toString() => userMessage;
}
