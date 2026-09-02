import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/models/terms_gate_failure.dart';

/// Cold-start Email Link recovery when the server rejects the terms proof.
///
/// BROKEN BEFORE: `signInWithEmailLink()` leaves a TEMPORARY Firebase session
/// attached. When `completePrimaryStudentEmailAuth()` then failed the terms
/// gate, the client navigated to `/terms` with that session still live. The
/// terms screen classifies by `FirebaseAuth.currentUser != null`, so it took
/// the POST-AUTH branch and called `recordTermsAcceptance`, which the server
/// rejects with `identity_conflict` because `users/{temporaryUid}` does not
/// exist — a dead end with no way back into the normal pre-auth flow.
///
/// FIXED AFTER: the temporary session is dropped before returning to terms, so
/// the screen takes its PRE-AUTH branch and the email flow is resumable. A
/// canonical session is unaffected and still re-consents post-auth.
String _read(String path) => File(path).readAsStringSync();

void main() {
  group('terms-gate recovery decision', () {
    test('a cleared temporary session returns the user to terms', () {
      expect(
        resolveTermsGateRecovery(temporarySessionCleared: true),
        TermsGateRecovery.returnToTerms,
      );
    });

    test('an uncleared session fails closed instead of reaching terms', () {
      // Handing the terms screen a live session it would read as canonical is
      // exactly the dead end this fix closes, so we stop rather than proceed.
      expect(
        resolveTermsGateRecovery(temporarySessionCleared: false),
        TermsGateRecovery.blockedSessionNotCleared,
      );
    });
  });

  group(
    'email-link screen drops the temporary session on a terms rejection',
    () {
      late String screen;

      setUp(() {
        screen = _read(
          'lib/features/auth/screens/student_verification_screen.dart',
        );
      });

      test('the failure handler clears the session before navigating', () {
        final handler = screen.substring(
          screen.indexOf('Future<void> _handleTermsGateFailure('),
        );
        final body = handler.substring(0, handler.indexOf('\n  Future<'));

        final clearIndex = body.indexOf('clearTemporaryEmailLinkSession');
        final navigateIndex = body.indexOf('RouteNames.terms');

        expect(
          clearIndex,
          greaterThanOrEqualTo(0),
          reason: 'the temporary email-link session must be dropped explicitly',
        );
        expect(navigateIndex, greaterThanOrEqualTo(0));
        expect(
          clearIndex,
          lessThan(navigateIndex),
          reason: 'clearing must happen before the terms screen is reached',
        );
      });

      test('a failed clear does not fall through to terms', () {
        final handler = screen.substring(
          screen.indexOf('Future<void> _handleTermsGateFailure('),
        );
        final body = handler.substring(0, handler.indexOf('\n  Future<'));

        expect(body, contains('TermsGateRecovery.blockedSessionNotCleared'));
      });
    },
  );

  test('AuthService confirms the session is gone rather than assuming it', () {
    final source = _read('lib/services/auth_service.dart');
    final method = source.substring(
      source.indexOf('Future<bool> clearTemporaryEmailLinkSession('),
    );
    final body = method.substring(0, method.indexOf('\n  /// '));

    expect(body, contains('signOut()'));
    // signOut can throw; the return value is derived from the observed session
    // so a swallowed error cannot report success.
    expect(body, contains('currentUser == null'));
  });

  group('recovery keeps both terms branches intact', () {
    late String terms;

    setUp(() {
      terms = _read('lib/features/onboarding/screens/terms_screen.dart');
    });

    test('pre-auth submit still stores the proof and resumes email auth', () {
      final submit = terms.substring(terms.indexOf('Future<void> _onSubmit('));
      final body = submit.substring(0, submit.indexOf('} catch'));

      expect(body, contains('savePendingLegalConsents'));
      expect(body, contains('RouteNames.studentVerification'));
    });

    test('a canonical session still re-consents through the callable', () {
      final submit = terms.substring(terms.indexOf('Future<void> _onSubmit('));
      final body = submit.substring(0, submit.indexOf('} catch'));

      expect(body, contains('_hasCanonicalSession'));
      expect(body, contains('recordTermsAcceptance'));
    });
  });

  test('the terms-gate failure copy stays user-facing only', () {
    // Regression guard for contract §9: no internal detail reaches the user.
    for (final failure in TermsGateFailure.values) {
      final message = TermsGateException(failure).userMessage;
      expect(message, isNotEmpty);
      expect(message, isNot(contains('_')));
    }
  });
}
