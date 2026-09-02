import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Static call-graph audit of the Yonsei-email-primary architecture
/// (identity contract §1/§7): the client binary must contain NO path from a
/// Kakao token to a Firebase session, and Kakao OAuth must never assign
/// authentication state.
void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('/login routes to the email login screen and no Kakao login screen '
      'exists in the router', () {
    final router = read('lib/router/app_router.dart');

    final loginCase = router.indexOf('case RouteNames.login:');
    expect(loginCase, isNonNegative);
    final routed = router.indexOf('StudentVerificationScreen()', loginCase);
    expect(routed, isNonNegative);

    expect(router, isNot(contains('KakaoAuthScreen')));
    expect(router, contains('case RouteNames.kakaoFriendConnect:'));
    expect(router, contains('KakaoFriendConnectionScreen()'));
    // Legacy /kakao-auth deep links are absorbed by the email login screen.
    expect(router, contains('case RouteNames.kakaoAuth:'));
  });

  test('the Kakao login screen and its Firestore bootstrap are deleted', () {
    expect(
      File(
        '$root/lib/features/auth/screens/kakao_auth_screen.dart',
      ).existsSync(),
      isFalse,
    );
    expect(
      File(
        '$root/lib/features/auth/services/kakao_login_firestore_bootstrap.dart',
      ).existsSync(),
      isFalse,
    );
    expect(File('$root/lib/router/route_guards.dart').existsSync(), isFalse);
  });

  test('auth_service has no Kakao→Firebase token bridge', () {
    final source = read('lib/services/auth_service.dart');

    expect(source, isNot(contains('createFirebaseCustomToken')));
    expect(source, isNot(contains('ensureFirebaseSessionForKakao')));
    expect(source, isNot(contains('ensureFirebaseSessionForVerifiedUser')));
    expect(source, isNot(contains('loginWithKakaoTalk')));
    expect(source, isNot(contains('loginWithKakaoAccount')));
    expect(source, isNot(contains('savePhoneHash')));
    expect(source, isNot(contains('saveUserPhoneHash')));
    // The canonical session check is Firebase-only.
    expect(source, contains('Future<bool> ensureCanonicalAppSession()'));
  });

  test('sendPrimaryStudentEmailLink has no Kakao or session precondition', () {
    final source = read('lib/services/auth_service.dart');
    final start = source.indexOf('Future<void> sendPrimaryStudentEmailLink(');
    expect(start, isNonNegative);
    final end = source.indexOf(
      'Future<PrimaryStudentEmailAuthCompletion>',
      start,
    );
    final section = source.substring(start, end == -1 ? source.length : end);

    expect(section, isNot(contains('getKakaoUserId')));
    expect(section, isNot(contains('getAppUserId')));
    expect(section, isNot(contains('accessToken')));
    expect(section, contains("httpsCallable('sendPrimaryStudentEmailLink')"));
    expect(section, contains('@yonsei.ac.kr'));
  });

  test('completePrimaryStudentEmailAuth asserts uid == appUserId', () {
    final source = read('lib/services/auth_service.dart');
    final start = source.indexOf(
      'Future<PrimaryStudentEmailAuthCompletion> completePrimaryStudentEmailAuth(',
    );
    expect(start, isNonNegative);
    final end = source.indexOf('bool isSignInWithEmailLink', start);
    final section = source.substring(start, end == -1 ? source.length : end);

    expect(
      section,
      contains("httpsCallable('completePrimaryStudentEmailAuth')"),
    );
    expect(section, contains('signInWithCustomToken'));
    expect(section, contains('getIdToken(true)'));
    expect(section, contains('uid != completion.appUserId'));
    expect(section, contains('primary_email_auth_uid_mismatch'));
    // Kakao never appears in the primary completion path.
    expect(section, isNot(contains('kakao')));
    expect(section, isNot(contains('Kakao')));
  });

  test('friend connection service never authenticates', () {
    final source = read('lib/services/kakao_friend_connection_service.dart');

    expect(source, isNot(contains('signInWithCustomToken')));
    expect(source, isNot(contains('createFirebaseCustomToken')));
    expect(source, isNot(contains('isAuthenticated')));
    expect(source, isNot(contains('_isAuthenticated')));
    // Canonical session is a strict precondition of every step.
    expect(source, contains("StateError('primary_email_auth_required')"));
    expect(source, contains('_requireCanonicalSession'));
    expect(source, contains("httpsCallable('linkKakaoFriendIdentity')"));
    expect(source, contains("httpsCallable('createKakaoFriendPairsOnce')"));
    expect(source, contains("httpsCallable('setKakaoFriendAvoidanceEnabled')"));
    // No profile/phone collection from Kakao.
    expect(source, isNot(contains('phoneNumber')));
    expect(source, isNot(contains('phoneHash')));
    expect(source, isNot(contains('profileImageUrl')));
    expect(source, isNot(contains('UserApi.instance.me()')));
  });

  test('provider bootstrap authenticates from FirebaseAuth, never from the '
      'Kakao cache', () {
    final source = read('lib/providers/auth_provider.dart');
    final statusStart = source.indexOf('Future<void> _checkAuthStatus()');
    expect(statusStart, isNonNegative);
    final statusEnd = source.indexOf('_isTruthyMarker', statusStart);
    final statusSection = source.substring(
      statusStart,
      statusEnd == -1 ? source.length : statusEnd,
    );

    expect(statusSection, contains('FirebaseAuth.instance.currentUser'));
    expect(statusSection, isNot(contains('ensureFirebaseSessionForKakao')));
    expect(statusSection, isNot(contains('loginWithKakao')));
    // The session precedes _isAuthenticated = true.
    expect(
      statusSection.indexOf('FirebaseAuth.instance.currentUser'),
      lessThan(statusSection.indexOf('_isAuthenticated = true;')),
    );

    // setKakaoLogin (Kakao-driven authentication entrypoint) is gone.
    expect(source, isNot(contains('setKakaoLogin')));
    expect(source, contains('applyPrimaryEmailAuthCompletion'));
    expect(source, contains('primary_email_auth_uid_mismatch'));
  });

  test(
    'splash gates on FirebaseAuth and performs no Kakao session restore',
    () {
      final source = read('lib/features/splash/splash_screen.dart');

      expect(source, contains('FirebaseAuth.instance.currentUser'));
      expect(source, isNot(contains('ensureFirebaseSessionForKakao')));
      expect(source, isNot(contains('getKakaoUserId')));
      expect(source, contains('RouteNames.terms'));
      expect(source, contains('RouteNames.studentVerification'));
      expect(source, contains('resolveNextRoute'));
    },
  );

  test('email login screen has no Kakao precondition and no Kakao CTA', () {
    final source = read(
      'lib/features/auth/screens/student_verification_screen.dart',
    );

    expect(source, isNot(contains('getKakaoUserId')));
    expect(source, isNot(contains('expectedKakaoUserId')));
    expect(source, isNot(contains('ensureFirebaseSessionForVerifiedUser')));
    expect(source, isNot(contains('카카오 로그인')));
    expect(source, isNot(contains('카카오로 시작')));
    expect(source, contains('sendPrimaryStudentEmailLink'));
    expect(source, contains('completePrimaryStudentEmailLink'));
    expect(source, contains('applyPrimaryEmailAuthCompletion'));
    // Pending friend invites re-enter the setup ladder, never jump to /main.
    expect(source, isNot(contains('pushNamedAndRemoveUntil(RouteNames.main')));
    expect(source, contains('resolveNextRoute'));
  });

  test('native email-link observers share one single-use completion gate', () {
    final authService = read('lib/services/auth_service.dart');
    final provider = read('lib/providers/auth_provider.dart');
    final screen = read(
      'lib/features/auth/screens/student_verification_screen.dart',
    );

    expect(authService, contains('_primaryEmailLinkInFlight'));
    expect(authService, contains('_lastCompletedPrimaryEmailLinkToken'));
    expect(authService, contains('hasVerifiedEmailSession'));
    expect(provider, contains('completePrimaryStudentEmailLink'));
    expect(screen, contains('completePrimaryStudentEmailLink'));
    expect(provider, isNot(contains('_authService.signInWithEmailLink(')));
    expect(screen, isNot(contains('_authService.signInWithEmailLink(')));
  });

  test('adult verification gate hands the next step back to the resolver', () {
    final source = read(
      'lib/features/auth/screens/adult_verification_gate_screen.dart',
    );
    expect(source, isNot(contains('RouteNames.kakaoAuth')));
    // Post-auth gate: the single resolver decides what follows (Kakao friend
    // connection for a fresh account), never the screen itself.
    expect(source, contains('resolveNextRoute'));
    final confirmStart = source.indexOf(
      'Future<void> _confirmVerificationAndContinue()',
    );
    final actionStart = source.indexOf(
      'Future<void> _handlePrimaryAction()',
      confirmStart,
    );
    expect(confirmStart, isNonNegative);
    expect(actionStart, greaterThan(confirmStart));
    final confirmation = source.substring(confirmStart, actionStart);
    expect(confirmation, contains('verifyPendingSessionAfterLogin'));
    expect(
      confirmation.indexOf('verifyPendingSessionAfterLogin'),
      lessThan(confirmation.indexOf('_continueThroughResolver')),
    );
    expect(confirmation, contains('if (!result.isVerified) return;'));
    expect(source, contains('await _confirmVerificationAndContinue();'));
    expect(source, isNot(contains('pushReplacementNamed(RouteNames.login)')));
  });

  test('terms CTA no longer promises a Kakao login', () {
    final source = read('lib/features/onboarding/screens/terms_screen.dart');
    expect(source, isNot(contains('동의하고 카카오 로그인')));
    expect(source, contains('동의하고 시작하기'));
  });

  test('connection screen copy is 친구 연결, never 카카오 로그인', () {
    final source = read(
      'lib/features/auth/screens/kakao_friend_connection_screen.dart',
    );
    expect(source, contains('카카오 친구 연결'));
    expect(source, contains('아는 사람 추천 차단'));
    expect(source, isNot(contains('카카오 로그인')));
    expect(source, isNot(contains('나중에 하기')));
    // Kakao OAuth success never sets authenticated state.
    expect(source, isNot(contains('isAuthenticated = true')));
  });

  test('the dead GoRouter stays dead (not wired from main)', () {
    final main = read('lib/main.dart');
    expect(main, isNot(contains("routes/app_router.dart")));
  });
}
