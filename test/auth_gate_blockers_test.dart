import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/legal_texts.dart';
import 'package:seolleyeon/models/account_setup_state.dart';
import 'package:seolleyeon/shared/utils/dev_entry_policy.dart';

/// Release blockers closed in this change set. Each group starts from the
/// exact defect the audit reproduced in source, so a regression flips the test
/// back to red rather than silently re-opening the gate.
///
/// Flow authority (docs/auth-rearchitecture/onboarding-flow.md):
///   TERMS → YONSEI EMAIL AUTH → canonical appUserId → PORTONE ADULT/REAL-NAME
///   → KAKAO → SNAPSHOT → ONBOARDING → TUTORIAL → HOME
String _read(String path) => File(path).readAsStringSync();

Map<String, dynamic> _verifiedUser({
  Map<String, dynamic>? termsAcceptance,
  Map<String, dynamic>? legalConsents,
  bool adultVerified = true,
  bool realNameVerified = true,
  bool kakaoConnected = true,
  String snapshotStatus = 'completed',
  bool initialSetupComplete = true,
  bool hasSeenTutorial = true,
}) {
  return <String, dynamic>{
    'isStudentVerified': true,
    if (termsAcceptance != null) 'termsAcceptance': termsAcceptance,
    if (legalConsents != null) 'legalConsents': legalConsents,
    'adultVerified': adultVerified,
    'realNameVerified': realNameVerified,
    'kakaoFriendConnection': <String, dynamic>{'connected': kakaoConnected},
    'kakaoFriendSnapshot': <String, dynamic>{'status': snapshotStatus},
    'initialSetupComplete': initialSetupComplete,
    'hasSeenTutorial': hasSeenTutorial,
  };
}

AccountSetupState _resolve(Map<String, dynamic>? userDoc) {
  return resolveAccountSetupState(hasFirebaseSession: true, userDoc: userDoc);
}

void main() {
  group('BLOCKER 1 — PortOne runs after canonical auth, never before', () {
    test('pre-auth terms submit continues to Yonsei email auth', () {
      final source = _read('lib/features/onboarding/screens/terms_screen.dart');
      final preAuthBranch = source.substring(
        source.indexOf('await _storageService.savePendingLegalConsents('),
      );
      final nextRoute = preAuthBranch.substring(
        0,
        preAuthBranch.indexOf('} catch'),
      );

      // The PortOne callable requires request.auth.uid, so a pre-auth
      // verification result has no canonical account to attach to.
      expect(
        nextRoute,
        isNot(contains('RouteNames.adultVerification')),
        reason: 'terms must not hand a pre-auth user to PortOne',
      );
      expect(
        nextRoute,
        anyOf(
          contains('RouteNames.studentVerification'),
          contains('RouteNames.login'),
        ),
        reason: 'terms must continue to the Yonsei email entry route',
      );
    });

    test(
      'the adult gate returns to the resolver, not to a hardcoded route',
      () {
        final source = _read(
          'lib/features/auth/screens/adult_verification_gate_screen.dart',
        );
        expect(
          source,
          contains('resolveNextRoute'),
          reason:
              'adult verification is post-auth; the resolver picks what '
              'comes next (Kakao connection for a fresh account)',
        );
        expect(
          source,
          isNot(contains('pushReplacementNamed(RouteNames.login)')),
          reason: 'a canonical session must never be sent back to email login',
        );
      },
    );

    test('the PortOne callable requires an authenticated caller', () {
      final source = _read('functions/src/index.ts');
      final callable = source.substring(
        source.indexOf('export const verifyAdultIdentityAfterLogin'),
      );
      final body = callable.substring(0, callable.indexOf('\nexport const '));
      expect(body, contains('request.auth?.uid'));
      expect(body, contains('unauthenticated'));
    });

    test('canonical user with adult verification pending stops at PortOne', () {
      expect(
        _resolve(
          _verifiedUser(
            termsAcceptance: {'version': LegalTexts.version},
            adultVerified: false,
            realNameVerified: false,
          ),
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });

    test('adult verification complete advances to the Kakao connection', () {
      expect(
        _resolve(
          _verifiedUser(
            termsAcceptance: {'version': LegalTexts.version},
            kakaoConnected: false,
          ),
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('adult verification is never skipped on the way to Kakao', () {
      // adultVerified alone is not enough — real-name verification is part of
      // the same PortOne result.
      expect(
        _resolve(
          _verifiedUser(
            termsAcceptance: {'version': LegalTexts.version},
            realNameVerified: false,
            kakaoConnected: false,
          ),
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });
  });

  group('BLOCKER 2 — termsAcceptance is the only gate authority', () {
    test('a client-written legalConsents receipt cannot open the gate', () {
      expect(
        _resolve(_verifiedUser(legalConsents: {'version': LegalTexts.version})),
        AccountSetupState.termsAcceptanceRequired,
        reason:
            'legalConsents is client-writable and must never satisfy a '
            'security gate',
      );
    });

    test('a stale server record is not rescued by a current receipt', () {
      expect(
        _resolve(
          _verifiedUser(
            termsAcceptance: {'version': 'stale-version'},
            legalConsents: {'version': LegalTexts.version},
          ),
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });

    test('the server record alone satisfies the gate', () {
      expect(
        _resolve(
          _verifiedUser(termsAcceptance: {'version': LegalTexts.version}),
        ),
        AccountSetupState.complete,
      );
    });

    test(
      'a legacy account re-consents without losing any downstream state',
      () {
        final legacy = _verifiedUser(
          legalConsents: {'version': LegalTexts.version},
        );
        expect(_resolve(legacy), AccountSetupState.termsAcceptanceRequired);

        // recordTermsAcceptance writes only termsAcceptance; every other field
        // is untouched, so the ladder resumes exactly where it left off.
        final afterReconsent = Map<String, dynamic>.from(legacy)
          ..['termsAcceptance'] = {'version': LegalTexts.version};
        expect(_resolve(afterReconsent), AccountSetupState.complete);
        expect(
          afterReconsent['kakaoFriendSnapshot'],
          legacy['kakaoFriendSnapshot'],
        );
        expect(afterReconsent['initialSetupComplete'], isTrue);
      },
    );

    test('the resolver never reads legalConsents at all', () {
      final source = _read('lib/models/account_setup_state.dart');
      expect(
        source,
        isNot(contains("userDoc['legalConsents']")),
        reason: 'the client receipt must not appear in gate logic',
      );
    });
  });

  group('BLOCKER 3 — the QA shortcut cannot ship in a release build', () {
    tearDown(() => DevEntryPolicy.debugSetTestAccountEntry(null));

    test('debug + explicit opt-in is the only allowed combination', () {
      expect(
        DevEntryPolicy.resolveTestAccountEntry(
          isDebugBuild: true,
          explicitQaEntryEnabled: true,
        ),
        isTrue,
      );
    });

    test('debug without the explicit flag stays disabled', () {
      expect(
        DevEntryPolicy.resolveTestAccountEntry(
          isDebugBuild: true,
          explicitQaEntryEnabled: false,
        ),
        isFalse,
      );
    });

    test('a release build is disabled even with the flag set', () {
      expect(
        DevEntryPolicy.resolveTestAccountEntry(
          isDebugBuild: false,
          explicitQaEntryEnabled: true,
        ),
        isFalse,
        reason:
            'staging and production release artifacts must never carry a '
            'gate bypass',
      );
    });

    test('a release build without the flag is disabled', () {
      expect(
        DevEntryPolicy.resolveTestAccountEntry(
          isDebugBuild: false,
          explicitQaEntryEnabled: false,
        ),
        isFalse,
      );
    });

    test('the flavor name grants no privilege of its own', () {
      final source = _read('lib/shared/utils/dev_entry_policy.dart');
      expect(
        source,
        isNot(contains("appFlavor == 'staging'")),
        reason: 'a flavor name is not an authorization',
      );
      expect(source, isNot(contains('appFlavor')));
    });

    test('the runtime getter is debug-gated and opt-in', () {
      // In the test harness kDebugMode is true, so the getter is decided by the
      // compile-time QA flag, which defaults to false.
      DevEntryPolicy.debugSetTestAccountEntry(null);
      expect(
        DevEntryPolicy.allowTestAccountEntry,
        DevEntryPolicy.resolveTestAccountEntry(
          isDebugBuild: kDebugMode,
          explicitQaEntryEnabled: DevEntryPolicy.explicitQaEntryEnabled,
        ),
      );
      expect(DevEntryPolicy.explicitQaEntryEnabled, isFalse);
    });
  });
}
