import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/legal_texts.dart';
import 'package:seolleyeon/models/account_setup_state.dart';
import 'package:seolleyeon/router/route_names.dart';

/// The setup-state resolver is the single routing authority of the
/// Yonsei-email-primary architecture. Restarting the app at any state must
/// resolve to the SAME gate (restart-at-each-state semantics, spec §29),
/// driven purely by server-truth fields.
///
/// Ladder (kakao-friend-pairs contract §8 + terms-gate contract §7):
/// session → studentVerified → TERMS ACCEPTANCE → adult →
/// kakaoFriendConnection.connected → kakaoFriendSnapshot.status ==
/// "completed" → onboarding → tutorial.
void main() {
  /// The server-owned acceptance record (terms-gate contract §3). Every
  /// account created by `completePrimaryStudentEmailAuth` carries it.
  Map<String, dynamic> termsAcceptance({String? version}) => <String, dynamic>{
    'schemaVersion': 1,
    'version': version ?? LegalTexts.version,
    'requiredDocumentIds': const [
      'termsOfService',
      'privacyPolicy',
      'kakaoNamePhone',
      'ageOver20',
    ],
    'source': 'primary_auth_token',
  };

  Map<String, dynamic> completeDoc({
    Map<String, dynamic>? overrides,
    bool withConnection = true,
    bool withSnapshot = true,
    bool withTerms = true,
  }) {
    final doc = <String, dynamic>{
      'isStudentVerified': true,
      if (withTerms) 'termsAcceptance': termsAcceptance(),
      'adultVerified': true,
      'realNameVerified': true,
      if (withConnection)
        'kakaoFriendConnection': <String, dynamic>{'connected': true},
      if (withSnapshot)
        'kakaoFriendSnapshot': <String, dynamic>{
          'status': 'completed',
          'pairCount': 3,
          'schemaVersion': 1,
        },
      'initialSetupComplete': true,
      'hasSeenTutorial': true,
    };
    if (overrides != null) doc.addAll(overrides);
    return doc;
  }

  group('session gate', () {
    test('no Firebase session resolves to unauthenticated', () {
      expect(
        resolveAccountSetupState(hasFirebaseSession: false, userDoc: null),
        AccountSetupState.unauthenticated,
      );
    });

    test('pending email link without session stays on email verification', () {
      // Single-consumer race guard: the action link owns the flow.
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: false,
          userDoc: null,
          emailLinkPending: true,
        ),
        AccountSetupState.emailVerificationPending,
      );
    });

    test('session without a users doc fails closed to email verification', () {
      expect(
        resolveAccountSetupState(hasFirebaseSession: true, userDoc: null),
        AccountSetupState.emailVerificationPending,
      );
    });

    test('a cached local id alone never authenticates (server flag rules)', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {'isStudentVerified': false},
        ),
        AccountSetupState.emailVerificationPending,
      );
    });
  });

  group('adult verification gate', () {
    test('student verified but no adult verification gates on PortOne', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {'adultVerified': false, 'realNameVerified': false},
          ),
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });

    test('adultVerified without realNameVerified is not enough', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(overrides: {'realNameVerified': false}),
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });

    test('explicit debug bypass skips the adult gate only', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {'adultVerified': false, 'realNameVerified': false},
          ),
          adultVerificationDisabled: true,
        ),
        AccountSetupState.complete,
      );
    });
  });

  group('kakao friend connection gate', () {
    test('missing connection map requires connection', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(withConnection: false),
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('connection field present but not connected requires connection', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {
              'kakaoFriendConnection': {'connected': false},
            },
          ),
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('MIGRATION (spec §30): legacy doc without connection or snapshot '
        'goes through the connection gate ONCE even when the legacy '
        'recommendationPrivacyReady flag is true', () {
      // recommendationPrivacyReady is no longer consulted: the one-time
      // snapshot is the only Kakao readiness authority.
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            withConnection: false,
            withSnapshot: false,
            overrides: {'recommendationPrivacyReady': true},
          ),
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('MIGRATION: connected legacy doc without a snapshot field resolves '
        'to the snapshot gate regardless of recommendationPrivacyReady', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            withSnapshot: false,
            overrides: {'recommendationPrivacyReady': true},
          ),
        ),
        AccountSetupState.kakaoFriendSnapshotRequired,
      );
    });
  });

  group('kakao friend snapshot gate (one-time)', () {
    for (final status in ['not_started', 'in_progress', 'failed']) {
      test('snapshot status "$status" stays gated at the snapshot step', () {
        expect(
          resolveAccountSetupState(
            hasFirebaseSession: true,
            userDoc: completeDoc(
              overrides: {
                'kakaoFriendSnapshot': {'status': status},
              },
            ),
          ),
          AccountSetupState.kakaoFriendSnapshotRequired,
        );
      });
    }

    test('restart case (spec §29 E): completed snapshot never resolves to any '
        'kakao gate again', () {
      final state = resolveAccountSetupState(
        hasFirebaseSession: true,
        userDoc: completeDoc(),
      );
      expect(state, AccountSetupState.complete);
      expect(
        state,
        isNot(
          anyOf(
            AccountSetupState.kakaoConnectionRequired,
            AccountSetupState.kakaoFriendsConsentRequired,
            AccountSetupState.kakaoFriendSnapshotRequired,
          ),
        ),
      );
    });

    test('completed snapshot passes even when the legacy readiness flag is '
        'absent or false (flag removed from the ladder)', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {'recommendationPrivacyReady': false},
          ),
        ),
        AccountSetupState.complete,
      );
    });
  });

  group('onboarding and tutorial gates', () {
    test('snapshot-complete account with empty profile resumes onboarding '
        '(snapshot precedes onboarding, never re-requests it)', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {
              'initialSetupComplete': false,
              'hasSeenTutorial': false,
              'onboarding': {},
            },
          ),
        ),
        AccountSetupState.onboardingRequired,
      );
    });

    test('legacy complete profile without the marker passes onboarding', () {
      // resolveOnboardingNextRoute == null means every required field exists.
      final doc = completeDoc(
        overrides: {
          'initialSetupComplete': false,
          'hasSeenTutorial': false,
          'onboarding': {
            'nickname': 'n',
            'gender': 'f',
            'interests': ['a'],
            'lifestyle': {'x': 1},
            'major': 'CS',
            'selfIntroduction': 'hi',
            'profileQa': ['q'],
            'keywords': ['k'],
          },
          'avatar': {'status': 'approved'},
          'idealType': {
            'preferredLifestyles': ['x'],
          },
        },
      );
      expect(
        resolveAccountSetupState(hasFirebaseSession: true, userDoc: doc),
        AccountSetupState.tutorialRequired,
      );
    });

    test('everything but the tutorial resolves to tutorialRequired', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(overrides: {'hasSeenTutorial': false}),
        ),
        AccountSetupState.tutorialRequired,
      );
    });

    test('fully set up account resolves to complete', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(),
        ),
        AccountSetupState.complete,
      );
    });

    test(
      'completed tutorial never falls back to the photo step when the legacy '
      'onboarding marker or approved avatar is missing',
      () {
        final doc = completeDoc(
          overrides: {
            'initialSetupComplete': false,
            'hasSeenTutorial': true,
            'onboarding': {
              'nickname': 'n',
              'gender': 'f',
              'interests': ['a'],
              'lifestyle': {'x': 1},
              'major': 'CS',
            },
          },
        );
        doc.remove('avatar');

        expect(
          resolveAccountSetupState(hasFirebaseSession: true, userDoc: doc),
          AccountSetupState.complete,
        );
      },
    );
  });

  group('gate ordering (restart at each state)', () {
    test('email gate outranks adult, connection, snapshot and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': false,
            'adultVerified': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.emailVerificationPending,
      );
    });

    test('email gate outranks the terms gate (a user failing BOTH resolves to '
        'email verification first)', () {
      // Terms-gate contract §7 rung order: the terms rung is inserted AFTER
      // student verification, so an unverified account never sees it.
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': false,
            'adultVerified': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.emailVerificationPending,
      );
    });

    test('terms gate outranks adult, connection, snapshot and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'adultVerified': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });

    test('adult gate outranks connection, snapshot and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'termsAcceptance': termsAcceptance(),
            'adultVerified': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });

    test('connection gate outranks snapshot, onboarding and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'termsAcceptance': termsAcceptance(),
            'adultVerified': true,
            'realNameVerified': true,
            'kakaoFriendSnapshot': {'status': 'not_started'},
            'onboarding': {},
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('snapshot gate outranks onboarding and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'termsAcceptance': termsAcceptance(),
            'adultVerified': true,
            'realNameVerified': true,
            'kakaoFriendConnection': {'connected': true},
            'onboarding': {},
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.kakaoFriendSnapshotRequired,
      );
    });

    test('new-user shell doc (fail-closed defaults) routes to adult gate', () {
      // Shell created by completePrimaryStudentEmailAuth for a NEW user:
      // isStudentVerified true, termsAcceptance written from the validated
      // email-link token proof (terms-gate contract §5), kakaoFriendSnapshot
      // not_started (kakao contract §7), no adult verification yet.
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'termsAcceptance': termsAcceptance(),
            'kakaoFriendSnapshot': {'status': 'not_started'},
            'kakaoFriendAvoidanceEnabled': false,
          },
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });
  });

  group('terms acceptance gate (terms-gate contract §7)', () {
    test('a verified account with NEITHER record is gated on terms', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(withTerms: false),
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });

    test('a stale accepted version is gated on terms', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {
              'termsAcceptance': termsAcceptance(version: '2024-01-01'),
            },
          ),
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });

    test('a malformed termsAcceptance value fails closed', () {
      for (final malformed in <Object?>[
        'yes',
        42,
        <String, dynamic>{},
        <String, dynamic>{'version': ''},
        <String, dynamic>{'schemaVersion': 1},
      ]) {
        expect(
          resolveAccountSetupState(
            hasFirebaseSession: true,
            userDoc: completeDoc(overrides: {'termsAcceptance': malformed}),
          ),
          AccountSetupState.termsAcceptanceRequired,
          reason: 'malformed: $malformed',
        );
      }
    });

    test('the current server-recorded version passes the gate', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(),
        ),
        AccountSetupState.complete,
      );
    });

    test(
      'a legacy account carrying only the client legalConsents receipt '
      'must re-consent (the receipt is client-writable, never gate truth)',
      () {
        expect(
          resolveAccountSetupState(
            hasFirebaseSession: true,
            userDoc: completeDoc(
              withTerms: false,
              overrides: {
                'legalConsents': {
                  'termsOfService': true,
                  'privacyPolicy': true,
                  'version': LegalTexts.version,
                },
              },
            ),
          ),
          AccountSetupState.termsAcceptanceRequired,
        );
      },
    );

    test('the grandfather does NOT extend to a stale legacy receipt', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            withTerms: false,
            overrides: {
              'legalConsents': {'version': '2024-01-01'},
            },
          ),
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });

    test('a current server record wins over a stale legacy receipt', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {
              'legalConsents': {'version': '2024-01-01'},
            },
          ),
        ),
        AccountSetupState.complete,
      );
    });

    test('the gate reads ONLY server fields — no local pending blob can open '
        'it', () {
      // The pre-auth pending acceptance lives in SharedPreferences and is
      // deliberately not an input to this pure resolver.
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            withTerms: false,
            overrides: {
              'pendingLegalConsents': {'version': LegalTexts.version},
            },
          ),
        ),
        AccountSetupState.termsAcceptanceRequired,
      );
    });
  });

  group('enum surface', () {
    test('screen-internal consent sub-state remains declared and the legacy '
        'repeated-sync states are gone', () {
      expect(
        AccountSetupState.values,
        contains(AccountSetupState.kakaoFriendsConsentRequired),
      );
      expect(
        AccountSetupState.values,
        contains(AccountSetupState.kakaoFriendSnapshotRequired),
      );
      expect(
        AccountSetupState.values,
        contains(AccountSetupState.termsAcceptanceRequired),
      );
      final names = AccountSetupState.values.map((v) => v.name).toList();
      expect(names, isNot(contains('initialFriendSyncRequired')));
      expect(names, isNot(contains('kakaoFriendsVerificationRequired')));
    });

    test('the terms rung sits between the email and adult rungs', () {
      final values = AccountSetupState.values;
      expect(
        values.indexOf(AccountSetupState.emailVerificationPending),
        lessThan(values.indexOf(AccountSetupState.termsAcceptanceRequired)),
      );
      expect(
        values.indexOf(AccountSetupState.termsAcceptanceRequired),
        lessThan(values.indexOf(AccountSetupState.adultVerificationRequired)),
      );
    });

    test('route constant for the connection screen exists', () {
      expect(RouteNames.kakaoFriendConnect, '/kakao-friend-connect');
    });
  });
}
