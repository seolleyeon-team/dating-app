import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart' hide AuthProvider;
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/providers/auth_bootstrap_policy.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/fake_auth_session.dart';

// AUD-16 / B-17 / AUD-24 (deep-link part): launch-time session resolution of
// the real AuthProvider, driven through fakes for Firebase Auth, the profile
// reads and the platform link channels.

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('classifyAuthBootstrapFailure', () {
    test('only an explicit dead-session answer ends the session', () {
      for (final code in [
        'user-token-expired',
        'user-disabled',
        'user-not-found',
        'invalid-user-token',
        'auth/user-token-expired',
      ]) {
        expect(
          classifyAuthBootstrapFailure(authError(code)),
          AuthBootstrapFailure.sessionInvalid,
          reason: code,
        );
      }
    });

    test('network, backend and unexpected failures are transient', () {
      for (final error in <Object>[
        authError('network-request-failed'),
        authError('too-many-requests'),
        authError('internal-error'),
        authError('unknown'),
        FirebaseException(plugin: 'cloud_firestore', code: 'unavailable'),
        FirebaseException(plugin: 'cloud_firestore', code: 'permission-denied'),
        TimeoutException('slow'),
        StateError('boom'),
      ]) {
        expect(
          classifyAuthBootstrapFailure(error),
          AuthBootstrapFailure.transient,
          reason: '$error',
        );
      }
    });
  });

  group('cold start', () {
    testWidgets('normal: a canonical session is authenticated once', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      final provider = h.start();
      expect(provider.bootstrapPhase, AuthBootstrapPhase.initializing);
      expect(provider.isAuthenticated, isFalse);

      await settleAsync(tester);

      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u1');
      expect(provider.isStudentVerified, isTrue);
      expect(provider.sessionVerificationDeferred, isFalse);
      expect(h.session.forcedRefreshCalls, 1);
      expect(h.auth.signOutCalls, 0);
      expect(await h.storage.getAppUserId(), 'u1');

      // Nothing left to retry.
      await settleAsync(tester, const Duration(minutes: 5));
      expect(h.session.forcedRefreshCalls, 1);
      provider.dispose();
    });

    testWidgets('no session: resolved as signed out, nothing is signed out', (
      tester,
    ) async {
      final h = AuthHarness();
      final provider = h.start();
      var settled = false;
      unawaited(provider.bootstrapSettled.then((_) => settled = true));
      await settleAsync(tester);

      expect(settled, isTrue);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.appUserId, isNull);
      expect(h.auth.signOutCalls, 0);
      provider.dispose();
    });

    testWidgets('slow network: stays initializing, then resolves', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshGate = Completer<void>();
      final provider = h.start();
      var settled = false;
      unawaited(provider.bootstrapSettled.then((_) => settled = true));

      await settleAsync(tester, const Duration(seconds: 5));
      expect(provider.bootstrapPhase, AuthBootstrapPhase.initializing);
      expect(provider.isAuthenticated, isFalse);
      expect(settled, isFalse);
      expect(h.auth.signOutCalls, 0);

      h.session.refreshGate!.complete();
      await settleAsync(tester);
      expect(settled, isTrue);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      provider.dispose();
    });
  });

  group('transient failures never sign the user out', () {
    testWidgets('stalled network: the refresh is bounded and the cached '
        'session is used instead of holding the launch', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshGate = Completer<void>();
      final provider = h.start(retryDelays: const []);

      await settleAsync(tester, const Duration(seconds: 9));
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.sessionVerificationDeferred, isTrue);
      expect(h.auth.signOutCalls, 0);

      h.session.refreshGate!.complete();
      await settleAsync(tester);
      provider.dispose();
    });

    testWidgets('stalled profile read: bounded, retryable, session kept', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profileGate = Completer<void>();
      final provider = h.start(retryDelays: const []);

      await settleAsync(tester, const Duration(seconds: 11));
      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);
      expect(provider.isAuthenticated, isFalse);
      expect(h.auth.signOutCalls, 0);
      expect(h.session.user, isNotNull);

      h.auth.profileGate!.complete();
      await settleAsync(tester);
      provider.dispose();
    });

    testWidgets('offline start: authenticated from the cached token, then '
        're-verified when the network returns', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshError = authError('network-request-failed');
      final provider = h.start();
      await settleAsync(tester);

      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u1');
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.sessionVerificationDeferred, isTrue);
      expect(h.auth.signOutCalls, 0);

      // Network is back before the first retry fires.
      h.session.refreshError = null;
      await settleAsync(tester, const Duration(seconds: 1));
      expect(h.session.forcedRefreshCalls, 2);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.sessionVerificationDeferred, isFalse);
      expect(h.auth.signOutCalls, 0);
      provider.dispose();
    });

    testWidgets('offline with no usable token: the uid this device already '
        'verified is accepted', (tester) async {
      SharedPreferences.setMockInitialValues({'kakao_user_id': 'u1'});
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshError = authError('network-request-failed');
      h.session.cachedTokenError = authError('network-request-failed');
      final provider = h.start();
      await settleAsync(tester);

      expect(provider.isAuthenticated, isTrue);
      expect(provider.sessionVerificationDeferred, isTrue);
      expect(h.auth.signOutCalls, 0);
      provider.dispose();
    });

    testWidgets('offline with no usable token and no verified uid: retryable, '
        'session kept, recovers by itself', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshError = authError('network-request-failed');
      h.session.cachedTokenError = authError('network-request-failed');
      final provider = h.start();
      await settleAsync(tester);

      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);
      expect(provider.isAuthenticated, isFalse);
      expect(h.auth.signOutCalls, 0);
      expect(h.session.user, isNotNull, reason: 'the session is kept');
      expect(await h.storage.getAppUserId(), isNull);

      h.session.refreshError = null;
      h.session.cachedTokenError = null;
      await settleAsync(tester, const Duration(seconds: 1));

      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u1');
      expect(h.auth.signOutCalls, 0);
      provider.dispose();
    });

    testWidgets('profile read failure: retryable, bounded retries, then '
        'app resume tries again', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profileError = FirebaseException(
        plugin: 'cloud_firestore',
        code: 'unavailable',
      );
      final provider = h.start();
      await settleAsync(tester);

      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);
      expect(provider.isAuthenticated, isFalse);
      expect(h.auth.profileReads, 1);

      // Budget: two retries (1s, 2s), then silence.
      await settleAsync(tester, const Duration(seconds: 1));
      expect(h.auth.profileReads, 2);
      await settleAsync(tester, const Duration(seconds: 2));
      expect(h.auth.profileReads, 3);
      await settleAsync(tester, const Duration(minutes: 10));
      expect(h.auth.profileReads, 3, reason: 'the retry is bounded');
      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);
      expect(h.auth.signOutCalls, 0);

      // App resume retries with a fresh budget and succeeds.
      h.auth.profileError = null;
      provider.handleAppResumed();
      await settleAsync(tester);
      expect(h.auth.profileReads, 4);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      expect(h.auth.signOutCalls, 0);

      // Resolved: a later resume does nothing.
      provider.handleAppResumed();
      await settleAsync(tester);
      expect(h.auth.profileReads, 4);
      provider.dispose();
    });

    testWidgets('a transient failure on a later re-check keeps an '
        'authenticated session authenticated', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isTrue);

      h.auth.profileError = TimeoutException('slow');
      await provider.refreshAfterExternalSignIn();
      await settleAsync(tester);

      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u1');
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.sessionVerificationDeferred, isTrue);
      expect(h.auth.signOutCalls, 0);
      provider.dispose();
    });

    testWidgets('retryBootstrap resolves a retryable state on demand', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profileError = StateError('boom');
      final provider = h.start(retryDelays: const []);
      await settleAsync(tester);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);

      h.auth.profileError = null;
      await provider.retryBootstrap();
      await settleAsync(tester);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(provider.isAuthenticated, isTrue);
      provider.dispose();
    });
  });

  group('a dead session ends signed out', () {
    for (final code in ['user-token-expired', 'user-disabled']) {
      testWidgets('revoked at launch ($code)', (tester) async {
        SharedPreferences.setMockInitialValues({'kakao_user_id': 'u1'});
        final h = AuthHarness()..signedInAs('u1');
        h.session.refreshError = authError(code);
        final provider = h.start();
        await settleAsync(tester);

        expect(h.auth.signOutCalls, 1);
        expect(h.session.user, isNull);
        expect(provider.isAuthenticated, isFalse);
        expect(provider.appUserId, isNull);
        expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
        expect(await h.storage.getAppUserId(), isNull);

        // Signed out is final: no retry.
        await settleAsync(tester, const Duration(minutes: 5));
        expect(h.session.forcedRefreshCalls, 1);
        provider.dispose();
      });
    }

    testWidgets('revoked while deferred: the re-verification signs out', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.session.refreshError = authError('network-request-failed');
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isTrue);

      h.session.refreshError = authError('user-token-expired');
      await settleAsync(tester, const Duration(seconds: 1));

      expect(h.auth.signOutCalls, 1);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      provider.dispose();
    });

    testWidgets('a non-canonical (temporary email-link) session is still '
        'signed out', (tester) async {
      final h = AuthHarness()..signedInAs('temp');
      h.session.claims = {'email': 'someone@yonsei.ac.kr'};
      final provider = h.start();
      await settleAsync(tester);

      expect(h.auth.signOutCalls, 1);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      provider.dispose();
    });

    testWidgets('a rejoin-restricted account is still signed out', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.rejoinRestricted.add('u1');
      final provider = h.start();
      await settleAsync(tester);

      expect(h.auth.signOutCalls, 1);
      expect(provider.isAuthenticated, isFalse);
      expect(await h.storage.consumePendingRejoinRestrictionNotice(), isTrue);
      provider.dispose();
    });

    testWidgets('signed out outside the provider (revocation, rejoin '
        'restriction): state follows at once', (tester) async {
      SharedPreferences.setMockInitialValues({
        'onboarding_draft_u1': '{"nickname":"n"}',
      });
      final h = AuthHarness()..signedInAs('u1');
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isTrue);
      final before = h.notifications;

      h.session.signOut();
      await settleAsync(tester);

      expect(provider.isAuthenticated, isFalse);
      expect(provider.appUserId, isNull);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      expect(h.notifications, greaterThan(before));
      expect(await h.storage.getAppUserId(), isNull);
      expect(await h.storage.getOnboardingDraft('u1'), isEmpty);
      provider.dispose();
    });
  });

  group('account changes', () {
    testWidgets('another account attached without a logout: the previous '
        'identity is dropped, the new one is hydrated explicitly', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profiles['u2'] = verifiedProfile;
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.appUserId, 'u1');

      h.session.signIn('u2');
      await settleAsync(tester);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.appUserId, isNull);
      expect(h.auth.signOutCalls, 0);

      await provider.refreshAfterExternalSignIn();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u2');
      expect(await h.storage.getAppUserId(), 'u2');
      provider.dispose();
    });

    testWidgets('logout then immediate login: a resolution still in flight '
        'for the old account neither resurrects it nor signs the new one '
        'out', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profiles['u2'] = verifiedProfile;
      final oldProfileRead = Completer<void>();
      h.auth.profileGate = oldProfileRead;
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.initializing);
      expect(h.auth.profileReads, 1);

      await provider.logout();
      expect(h.auth.signOutCalls, 1);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);

      h.auth.profileGate = null;
      h.session.signIn('u2');
      await provider.refreshAfterExternalSignIn();
      await settleAsync(tester);
      expect(provider.appUserId, 'u2');

      // The old account's read finally returns.
      oldProfileRead.complete();
      await settleAsync(tester, const Duration(seconds: 5));

      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u2');
      expect(h.session.user?.uid, 'u2');
      expect(h.auth.signOutCalls, 1, reason: 'only the explicit logout');
      expect(await h.storage.getAppUserId(), 'u2');
      provider.dispose();
    });

    testWidgets('logout cancels a pending retry', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profileError = StateError('boom');
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.retryableError);
      final reads = h.auth.profileReads;

      await provider.logout();
      await settleAsync(tester, const Duration(minutes: 5));

      expect(h.auth.profileReads, reads);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.bootstrapPhase, AuthBootstrapPhase.ready);
      provider.dispose();
    });
  });

  group('subscriptions', () {
    testWidgets('exactly one of each, whatever happens afterwards', (
      tester,
    ) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profiles['u2'] = verifiedProfile;
      final provider = h.start();
      await settleAsync(tester);

      await provider.retryBootstrap();
      await provider.refreshAfterExternalSignIn();
      provider.handleAppResumed();
      await provider.logout();
      h.session.signIn('u2');
      await provider.refreshAfterExternalSignIn();
      await settleAsync(tester);

      expect(provider.appUserId, 'u2');
      expect(h.session.authStateListens, 1);
      expect(h.session.activeAuthStateListeners, 1);
      expect(h.appLinks.streamListens, 1);
      expect(h.kakaoListens, 1);

      provider.dispose();
      await settleAsync(tester);
      expect(h.session.activeAuthStateListeners, 0);
      expect(h.appLinks.links.hasListener, isFalse);
      expect(h.kakaoLinks.hasListener, isFalse);
    });

    testWidgets('dispose stops the retry', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.auth.profileError = StateError('boom');
      final provider = h.start();
      await settleAsync(tester);
      final reads = h.auth.profileReads;

      provider.dispose();
      await settleAsync(tester, const Duration(minutes: 5));
      expect(h.auth.profileReads, reads);
    });
  });

  group('app links (AUD-24)', () {
    const inviteToken =
        'a3f1c2d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90';
    final inviteLink = Uri.parse(
      'https://seolleyeon.com/invite/friend?token=$inviteToken',
    );
    final emailLink = Uri.parse(
      'https://seolleyeon-final.firebaseapp.com/__/auth/links'
      '?mode=signIn&oobCode=abc123',
    );

    testWidgets('a launch from an email link still starts the app-link '
        'listener, and leaves that one link to its owner', (tester) async {
      final h = AuthHarness();
      h.appLinks.initialLink = emailLink;
      final provider = h.start();
      await settleAsync(tester);

      expect(h.appLinks.streamListens, 1, reason: 'AUD-24');
      expect(provider.isAuthenticated, isFalse);

      // The platform replays the launch link on the stream: not consumed.
      h.appLinks.links.add(emailLink);
      await settleAsync(tester);
      expect(h.auth.emailLinkTokenLookups, 0);
      expect(h.auth.emailLinkCompletions, 0);

      // A friend invite tapped later in the same session IS delivered.
      h.appLinks.links.add(inviteLink);
      await settleAsync(tester);
      expect(h.invites.savedTokens, [inviteToken]);
      provider.dispose();
    });

    testWidgets('after an email-link launch a later re-check sees the '
        'session instead of resetting it again', (tester) async {
      final h = AuthHarness();
      h.appLinks.initialLink = emailLink;
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isFalse);

      h.signedInAs('u1');
      await provider.refreshAfterExternalSignIn();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isTrue);
      expect(provider.appUserId, 'u1');
      provider.dispose();
    });

    testWidgets('a cold-start invite delivered by both the initial link and '
        'the stream is handled once', (tester) async {
      final h = AuthHarness()..signedInAs('u1');
      h.appLinks.initialLink = inviteLink;
      final provider = h.start();
      await settleAsync(tester);

      h.appLinks.links.add(inviteLink);
      await settleAsync(tester);

      expect(h.appLinks.streamListens, 1);
      expect(h.invites.savedTokens, [inviteToken]);
      provider.dispose();
    });

    testWidgets('a link that arrives before login is kept for after it', (
      tester,
    ) async {
      final h = AuthHarness();
      final provider = h.start();
      await settleAsync(tester);
      expect(provider.isAuthenticated, isFalse);

      h.appLinks.links.add(inviteLink);
      await settleAsync(tester);
      expect(h.invites.savedTokens, [inviteToken]);
      provider.dispose();
    });
  });
}
