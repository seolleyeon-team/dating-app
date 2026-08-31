import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Replaces the legacy `kakao_login_auth_gate_test.dart`: the guarded
/// invariants moved from "Kakao login must bridge Firebase first" to
/// "ONLY the canonical Yonsei-email session authenticates".
void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('friend connection requires the canonical session before any Kakao '
      'OAuth step', () {
    final service = read('lib/services/kakao_friend_connection_service.dart');

    final requireDef = service.indexOf('String _requireCanonicalSession()');
    expect(requireDef, isNonNegative);

    final oauthStart = service.indexOf('Future<void> ensureKakaoOAuthSession');
    expect(oauthStart, isNonNegative);
    final oauthEnd = service.indexOf('Future<void> _performKakaoOAuth');
    final oauthSection = service.substring(oauthStart, oauthEnd);
    final precondition = oauthSection.indexOf('_requireCanonicalSession()');
    final sdkInit = oauthSection.indexOf('ensureKakaoSdkInitialized()');
    expect(precondition, isNonNegative);
    expect(sdkInit, isNonNegative);
    expect(
      precondition,
      lessThan(sdkInit),
      reason: 'Kakao OAuth must be unreachable without primary email auth.',
    );

    final screen = read(
      'lib/features/auth/screens/kakao_friend_connection_screen.dart',
    );
    expect(screen, contains('FirebaseAuth.instance.currentUser == null'));
    expect(screen, contains('pushReplacementNamed(RouteNames.login)'));
  });

  test('friend connection preserves the KakaoTalk-vs-account fallback and '
      'bundleId special case from the legacy login', () {
    final service = read('lib/services/kakao_friend_connection_service.dart');
    expect(service, contains('isKakaoTalkInstalled'));
    expect(service, contains('loginWithKakaoTalk'));
    expect(service, contains('loginWithKakaoAccount'));
    expect(service, contains("detail.contains('bundleId')"));
    expect(service, contains('rethrow;'));
    expect(service, contains('KakaoLoginCoordinator.run'));
  });

  test('terms require identity verification before the email login screen', () {
    final terms = read('lib/features/onboarding/screens/terms_screen.dart');
    final router = read('lib/router/app_router.dart');
    final verification = read('lib/services/adult_verification_service.dart');

    expect(terms, contains('RouteNames.adultVerification'));
    expect(router, contains('AdultVerificationGateScreen'));
    expect(router, contains('case RouteNames.adultVerification'));
    expect(verification, contains("'ADULT_VERIFICATION_BYPASS'"));
    expect(verification, isNot(contains('isTemporarilyDisabled = true')));
  });

  test('splash never restores a session from Kakao or local ids', () {
    final source = read('lib/features/splash/splash_screen.dart');

    final sessionGate = source.indexOf('FirebaseAuth.instance.currentUser');
    final routing = source.indexOf('resolveNextRoute');
    expect(sessionGate, isNonNegative);
    expect(routing, isNonNegative);
    expect(
      sessionGate,
      lessThan(routing),
      reason:
          'The setup ladder may only run behind an attached Firebase session.',
    );
    expect(source, isNot(contains('ensureFirebaseSessionForKakao')));
    expect(source, isNot(contains('getKakaoUserId')));
    expect(source, isNot(contains('getAppUserId')));
    expect(source, contains('handleRejoinRestriction'));
  });

  test('AuthProvider fails closed: no session, no authentication', () {
    final source = read('lib/providers/auth_provider.dart');
    final statusStart = source.indexOf('Future<void> _checkAuthStatus()');
    expect(statusStart, isNonNegative);
    final statusEnd = source.indexOf('_isTruthyMarker', statusStart);
    final statusSection = source.substring(
      statusStart,
      statusEnd == -1 ? source.length : statusEnd,
    );

    expect(statusSection, contains('firebaseUser == null'));
    expect(statusSection, contains('_resetSessionState()'));
    expect(
      statusSection.indexOf('FirebaseAuth.instance.currentUser'),
      lessThan(statusSection.indexOf('_isAuthenticated = true;')),
      reason: 'Only an attached Firebase session may authenticate.',
    );
    // The rejoin-restriction guard survives the rewrite.
    expect(statusSection, contains('isRejoinRestricted'));
    expect(statusSection, contains('savePendingRejoinRestrictionNotice'));
    // The old double-fetch of isStudentVerified is gone.
    expect(
      RegExp('isStudentVerified\\(').allMatches(statusSection).length,
      lessThanOrEqualTo(1),
    );
  });

  test('the email-link single-consumer race guard is preserved', () {
    final source = read('lib/providers/auth_provider.dart');
    expect(source, contains('_emailLinkPendingAtBootstrap'));
    final listenerStart = source.indexOf('void _startEmailLinkListener()');
    final listenerSection = source.substring(
      listenerStart,
      source.indexOf('void _startKakaoSchemeListener()'),
    );
    expect(
      listenerSection,
      contains('if (kIsWeb || _emailLinkPendingAtBootstrap) return;'),
    );
  });

  test('Kakao OAuth callback is owned by the SDK, not app-side screens', () {
    final authProvider = read('lib/providers/auth_provider.dart');
    final activeRouter = read('lib/router/app_router.dart');
    final legacyRouter = read('lib/routes/app_router.dart');

    expect(authProvider, isNot(contains('receiveKakaoScheme')));
    expect(authProvider, contains('kakaoSchemeStream'));
    expect(activeRouter, isNot(contains('KakaoCallbackScreen')));
    expect(activeRouter, isNot(contains("name.contains('code=')")));
    expect(legacyRouter, isNot(contains('KakaoCallbackScreen')));
    expect(
      File('$root/lib/screens/auth/kakao_callback_screen.dart').existsSync(),
      isFalse,
    );
  });

  test('canonical-session gating of the one-time snapshot and avoidance '
      'toggle (replaces the deleted legacy-sync ordering test)', () {
    final service = read('lib/services/kakao_friend_connection_service.dart');

    // Every server-touching step requires the canonical Firebase session as
    // a strict precondition before any token or callable use.
    for (final method in [
      'Future<KakaoFriendSnapshotResult> createFriendSnapshotOnce()',
      'Future<String> loadFriendSnapshotStatus()',
      'Future<void> setFriendAvoidanceEnabled(bool enabled)',
    ]) {
      final start = service.indexOf(method);
      expect(start, isNonNegative, reason: method);
      final body = service.substring(start, service.indexOf('\n  }', start));
      expect(
        body,
        contains('_requireCanonicalSession()'),
        reason: '$method must be unreachable without primary email auth.',
      );
    }

    // The snapshot precondition precedes the callable invocation.
    final snapshotStart = service.indexOf(
      'Future<KakaoFriendSnapshotResult> createFriendSnapshotOnce()',
    );
    final snapshotBody = service.substring(
      snapshotStart,
      service.indexOf('\n  }', snapshotStart),
    );
    expect(
      snapshotBody.indexOf('_requireCanonicalSession()'),
      lessThan(
        snapshotBody.indexOf("httpsCallable('createKakaoFriendPairsOnce')"),
      ),
    );

    // The toggle path opens NO consent flow and fetches NO friends — it is
    // a pure preference write over server-stored pairs.
    final toggleStart = service.indexOf(
      'Future<void> setFriendAvoidanceEnabled(bool enabled)',
    );
    final toggleBody = service.substring(
      toggleStart,
      service.indexOf('\n  }', toggleStart),
    );
    expect(toggleBody, isNot(contains('ensureRequiredConsents')));
    expect(toggleBody, isNot(contains('fetchFriends')));
    expect(toggleBody, isNot(contains('loginWith')));
    expect(
      toggleBody,
      contains("httpsCallable('setKakaoFriendAvoidanceEnabled')"),
    );

    // The legacy repeated-sync client methods are gone entirely.
    final contactBlock = read('lib/services/contact_block_service.dart');
    expect(contactBlock, isNot(contains('syncKakaoTalkFriendBlocks')));
    expect(
      contactBlock,
      isNot(contains('beginKakaoFriendRecommendationPrivacySync')),
    );
    expect(contactBlock, isNot(contains('ensureFirebaseSessionForKakao')));
  });
}
