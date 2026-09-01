import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/legal_texts.dart';
import 'package:seolleyeon/models/account_setup_state.dart';
import 'package:seolleyeon/models/terms_acceptance.dart';
import 'package:seolleyeon/models/terms_gate_failure.dart';
import 'package:seolleyeon/router/route_names.dart';

/// Source-contract audit of the terms gate (`docs/auth-rearchitecture/
/// terms-gate-contract.md`). Closes findings F1-F4, F7 and F11: the terms
/// screen must be a real gate whose acceptance is recorded server-side, not a
/// decorative screen whose checkbox state is thrown away.
void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  String section(String source, String start, String end) {
    final startIndex = source.indexOf(start);
    expect(startIndex, isNonNegative, reason: 'missing anchor: $start');
    final endIndex = source.indexOf(end, startIndex);
    return source.substring(
      startIndex,
      endIndex == -1 ? source.length : endIndex,
    );
  }

  group('F2/F3: the pending acceptance carries the REAL selections', () {
    test('savePendingLegalConsents takes the actual values and fabricates '
        'nothing', () {
      final source = read('lib/services/storage_service.dart');
      final body = section(
        source,
        'Future<void> savePendingLegalConsents(',
        'Future<Map<String, dynamic>?> getPendingLegalConsents(',
      );

      expect(body, contains('required List<String> acceptedDocumentIds'));
      expect(body, contains('required Map<String, bool> optionalConsents'));
      expect(body, contains('required String version'));
      // Contract §2: `ageOver18` is not a UI item and must never be recorded.
      expect(body, isNot(contains('ageOver18')));
      // Contract §0 F2: no hardcoded consent booleans at all.
      expect(body, isNot(contains("'termsOfService': true")));
      expect(body, isNot(contains("'privacyPolicy': true")));
      expect(body, isNot(contains("'kakaoNamePhone': true")));
      expect(body, isNot(contains("'ageOver20': true")));
    });

    test('the pending key is cleared with the user-scoped session', () {
      final source = read('lib/services/storage_service.dart');
      final body = section(
        source,
        'Future<void> clearUserScopedSession(',
        '\n}\n',
      );
      expect(body, contains('clearPendingLegalConsents()'));
    });

    test('the legacy legalConsents receipt no longer defaults to true', () {
      final source = read('lib/services/user_service.dart');
      final body = section(
        source,
        'Future<void> saveLegalConsents(',
        'Future<bool> isInitialSetupComplete(',
      );
      expect(body, contains('required PendingTermsAcceptance acceptance'));
      expect(body, isNot(contains('fallback: true')));
      expect(body, contains("'version': acceptance.version"));
    });

    test('terms screen submits the real checkbox state', () {
      final source = read('lib/features/onboarding/screens/terms_screen.dart');
      final body = section(source, 'Future<void> _onSubmit(', '\n  @override');

      expect(body, contains('acceptedDocumentIds:'));
      expect(body, contains('optionalConsents:'));
      expect(body, contains("'marketing': _marketingChecked"));
      expect(body, contains("'push': _pushEnabled"));
      expect(body, contains("'email': _emailEnabled"));
      expect(body, contains('LegalTexts.version'));
      // Pre-auth progression goes to Yonsei email auth — adult/real-name
      // verification is a post-auth gate. /main is never a submit target.
      expect(body, contains('RouteNames.studentVerification'));
      expect(body, isNot(contains('RouteNames.adultVerification')));
      expect(body, isNot(contains('RouteNames.main')));
    });

    test('F4: 전체 동의 clears the push/email switches symmetrically', () {
      final source = read('lib/features/onboarding/screens/terms_screen.dart');
      final body = section(source, 'void _toggleAll(', 'void _toggleItem(');

      expect(body, contains('_pushEnabled = value'));
      expect(body, contains('_emailEnabled = value'));
      expect(body, isNot(contains('if (value)')));
    });
  });

  group('F7: server-verifiable acceptance wiring', () {
    test('sendPrimaryStudentEmailLink carries the termsAcceptance payload and '
        'refuses to send without one', () {
      final source = read('lib/services/auth_service.dart');
      final body = section(
        source,
        'Future<void> sendPrimaryStudentEmailLink(',
        'Future<PrimaryStudentEmailAuthCompletion>',
      );

      expect(body, contains("'termsAcceptance'"));
      expect(body, contains('getPendingLegalConsents()'));
      expect(body, contains('TermsGateFailure.acceptanceRequired'));
      // The refusal precedes the callable invocation (fail closed).
      expect(
        body.indexOf('TermsGateFailure.acceptanceRequired'),
        lessThan(body.indexOf("httpsCallable('sendPrimaryStudentEmailLink')")),
      );
    });

    test('recordTermsAcceptance exists as a canonical-session callable', () {
      final source = read('lib/services/auth_service.dart');
      final body = section(
        source,
        'Future<void> recordTermsAcceptance(',
        '\n  Future<',
      );

      expect(body, contains("httpsCallable('recordTermsAcceptance')"));
      expect(body, contains('_firebaseAuth.currentUser == null'));
      expect(body, contains('acceptedDocumentIds'));
      expect(body, contains('optionalConsents'));
    });

    test('both callables map the server terms errors to a typed failure', () {
      final source = read('lib/services/auth_service.dart');
      expect(
        RegExp('TermsGateException.fromFunctionsException').allMatches(source),
        hasLength(greaterThanOrEqualTo(3)),
        reason: 'send / complete / record must all translate the terms errors.',
      );

      final failure = read('lib/models/terms_gate_failure.dart');
      expect(failure, contains("'terms_acceptance_required'"));
      expect(failure, contains("'terms_version_outdated'"));
      expect(failure, contains("details['detail']"));
    });

    test('the typed failure maps both machine-readable details', () {
      expect(
        const TermsGateException(TermsGateFailure.acceptanceRequired).detail,
        'terms_acceptance_required',
      );
      expect(
        const TermsGateException(TermsGateFailure.versionOutdated).detail,
        'terms_version_outdated',
      );
      // Contract §9: user-facing copy never leaks server internals.
      for (final failure in TermsGateFailure.values) {
        final message = TermsGateException(failure).userMessage;
        expect(message, isNot(contains('terms_')));
        expect(message, contains('약관'));
      }
    });

    test('the email login screen turns the terms failure into a /terms '
        'redirect', () {
      final source = read(
        'lib/features/auth/screens/student_verification_screen.dart',
      );
      expect(source, contains('on TermsGateException'));
      expect(source, contains('pushNamedAndRemoveUntil(RouteNames.terms'));
      expect(source, contains('failure.userMessage'));
      // The bypass target stays unreachable from this screen.
      expect(
        source,
        isNot(contains('pushNamedAndRemoveUntil(RouteNames.main')),
      );
    });

    test('no acceptance payload, token or email is ever logged', () {
      for (final path in [
        'lib/services/auth_service.dart',
        'lib/features/onboarding/screens/terms_screen.dart',
      ]) {
        final source = read(path);
        expect(source, isNot(contains(r'debugPrint(acceptance')));
        expect(source, isNot(contains(r'$acceptance')));
        expect(source, isNot(contains(r'$normalizedEmail')));
        expect(source, isNot(contains(r'$customToken')));
      }
    });
  });

  group('§7: the resolver rung', () {
    test('the state exists and routes to /terms', () {
      expect(
        AccountSetupState.values,
        contains(AccountSetupState.termsAcceptanceRequired),
      );

      final flow = read('lib/services/account_setup_flow.dart');
      final body = section(
        flow,
        'case AccountSetupState.termsAcceptanceRequired:',
        'case AccountSetupState.adultVerificationRequired:',
      );
      expect(body, contains('return RouteNames.terms;'));
      expect(RouteNames.terms, '/terms');
    });

    test('the rung uses ONLY server fields and documents the grandfather', () {
      final source = read('lib/models/account_setup_state.dart');
      expect(source, contains('termsAcceptance'));
      expect(source, contains('legalConsents'));
      expect(source, contains('LegalTexts.version'));
      // Contract §7 demands the grandfather be documented prominently.
      expect(source, contains('GRANDFATHER'));
      expect(source, contains('terms-gate contract §7'));
      // Inserted after the student-verification rung, before adult.
      // The signature spans lines, so the close anchor must be a
      // column-zero brace followed by a newline.
      final resolver = section(
        source,
        'AccountSetupState resolveAccountSetupState(',
        '\n}\n',
      );
      expect(
        resolver.indexOf("userDoc['isStudentVerified']"),
        lessThan(resolver.indexOf('termsAcceptanceRequired')),
      );
      expect(
        resolver.indexOf('termsAcceptanceRequired'),
        lessThan(resolver.indexOf('adultVerificationRequired')),
      );
    });

    test('the terms screen is dual-mode and never pushes /main', () {
      final source = read('lib/features/onboarding/screens/terms_screen.dart');
      final body = section(source, 'Future<void> _onSubmit(', '\n  @override');

      expect(body, contains('recordTermsAcceptance'));
      expect(body, contains('resolveNextRoute()'));
      expect(body, isNot(contains('RouteNames.main')));
    });
  });

  group('F11: push taps route through the setup ladder', () {
    test('notification navigation resolves the gate before deep linking', () {
      final source = read('lib/services/push_notification_service.dart');

      expect(source, contains('AccountSetupFlow'));
      expect(source, contains('resolveNextRoute()'));
      final guard = section(
        source,
        'Future<void> _navigateFromDataGuarded(',
        'void _routeNotificationTarget(',
      );
      expect(guard, contains('_resolveSetupGateRoute()'));
      expect(
        guard.indexOf('_resolveSetupGateRoute()'),
        lessThan(guard.indexOf('_routeNotificationTarget(')),
        reason: 'The ladder must be consulted before any deep-link target.',
      );
      // A `complete` user still reaches the in-app target.
      final gate = section(
        source,
        'Future<String?> _resolveSetupGateRoute(',
        '\n  void ',
      );
      expect(gate, contains('RouteNames.main'));
      expect(gate, contains('null'));
    });
  });

  group('§3-§6: server identifiers the client contract depends on', () {
    // These identifiers are pinned by the contract; the functions files are
    // owned by other agents. A miss here is a cross-agent integration gap.
    test('functions expose termsAcceptance and recordTermsAcceptance', () {
      final primaryAuth = read('functions/src/primaryEmailAuth.ts');
      expect(primaryAuth, contains('termsAcceptance'));
      expect(primaryAuth, contains('terms_acceptance_required'));
      expect(primaryAuth, contains('terms_version_outdated'));

      final index = read('functions/src/index.ts');
      expect(index, contains('recordTermsAcceptance'));
    });
  });

  group('document authority', () {
    test(
      'the required ids match legal_texts, and the version is repo-wide',
      () {
        expect(PendingTermsAcceptance.requiredDocumentIds, [
          LegalTexts.serviceTerms.id,
          LegalTexts.privacyPolicy.id,
          LegalTexts.kakaoNamePhoneConsent.id,
          LegalTexts.ageOver20Consent.id,
        ]);
        expect(LegalTexts.version, '2026-05-16');
      },
    );

    test('a partial acceptance never satisfies the required set', () {
      const partial = PendingTermsAcceptance(
        version: '2026-05-16',
        acceptedDocumentIds: ['termsOfService', 'privacyPolicy'],
        optionalConsents: {},
      );
      expect(partial.coversRequiredDocuments, isFalse);

      final full = PendingTermsAcceptance(
        version: LegalTexts.version,
        acceptedDocumentIds: PendingTermsAcceptance.requiredDocumentIds,
        optionalConsents: const {'marketing': false},
      );
      expect(full.coversRequiredDocuments, isTrue);
      expect(full.toCallablePayload()['version'], LegalTexts.version);
      expect(full.toCallablePayload()['optionalConsents'], {
        'marketing': false,
        'push': false,
        'email': false,
      });
    });

    test('a malformed stored blob resolves to no acceptance (fail closed)', () {
      expect(PendingTermsAcceptance.fromStorageMap(null), isNull);
      expect(PendingTermsAcceptance.fromStorageMap({}), isNull);
      expect(
        PendingTermsAcceptance.fromStorageMap({'version': '', 'x': 1}),
        isNull,
      );
      expect(
        PendingTermsAcceptance.fromStorageMap({
          'version': '2026-05-16',
          'acceptedDocumentIds': 'termsOfService',
        }),
        isNull,
      );
    });
  });
}
