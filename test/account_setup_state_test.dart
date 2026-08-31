import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/models/account_setup_state.dart';
import 'package:seolleyeon/router/route_names.dart';

/// The setup-state resolver is the single routing authority of the
/// Yonsei-email-primary architecture. Restarting the app at any state must
/// resolve to the SAME gate (restart-at-each-state semantics), driven purely
/// by server-truth fields.
void main() {
  Map<String, dynamic> completeDoc({
    Map<String, dynamic>? overrides,
    bool withConnection = true,
  }) {
    final doc = <String, dynamic>{
      'isStudentVerified': true,
      'adultVerified': true,
      'realNameVerified': true,
      'recommendationPrivacyReady': true,
      if (withConnection)
        'kakaoFriendConnection': <String, dynamic>{
          'connected': true,
          'initialSyncComplete': true,
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
    test('missing connection and not privacy-ready requires connection', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            withConnection: false,
            overrides: {'recommendationPrivacyReady': false},
          ),
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('GRANDFATHER: legacy doc without connection field but privacy-ready '
        'passes the connection gate without a forced re-link', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(withConnection: false),
        ),
        AccountSetupState.complete,
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

    test('connected but initial sync incomplete requires the sync gate', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {
              'kakaoFriendConnection': {
                'connected': true,
                'initialSyncComplete': false,
              },
            },
          ),
        ),
        AccountSetupState.initialFriendSyncRequired,
      );
    });

    test('connected + synced but recommendationPrivacyReady false stays gated '
        '(fail-closed readiness flag is the authority)', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {'recommendationPrivacyReady': false},
          ),
        ),
        AccountSetupState.initialFriendSyncRequired,
      );
    });
  });

  group('onboarding and tutorial gates', () {
    test('connected account with empty profile resumes onboarding', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: completeDoc(
            overrides: {'initialSetupComplete': false, 'onboarding': {}},
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
  });

  group('gate ordering (restart at each state)', () {
    test('email gate outranks adult, connection, onboarding and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': false,
            'adultVerified': false,
            'recommendationPrivacyReady': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.emailVerificationPending,
      );
    });

    test('adult gate outranks connection, onboarding and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'adultVerified': false,
            'recommendationPrivacyReady': false,
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });

    test('connection gate outranks onboarding and tutorial', () {
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'adultVerified': true,
            'realNameVerified': true,
            'recommendationPrivacyReady': false,
            'onboarding': {},
            'hasSeenTutorial': false,
          },
        ),
        AccountSetupState.kakaoConnectionRequired,
      );
    });

    test('new-user shell doc (fail-closed defaults) routes to adult gate', () {
      // Shell created by completePrimaryStudentEmailAuth for a NEW user:
      // isStudentVerified true, recommendationPrivacyReady false, no adult
      // verification yet (contract §4.2 step 2).
      expect(
        resolveAccountSetupState(
          hasFirebaseSession: true,
          userDoc: {
            'isStudentVerified': true,
            'recommendationPrivacyReady': false,
            'kakaoFriendAvoidanceEnabled': false,
          },
        ),
        AccountSetupState.adultVerificationRequired,
      );
    });
  });

  group('enum surface', () {
    test('screen-internal consent/verify sub-states remain declared', () {
      // The resolver collapses them into the connection gate, but the enum
      // values stay part of the public state machine.
      expect(
        AccountSetupState.values,
        containsAll(<AccountSetupState>[
          AccountSetupState.kakaoFriendsConsentRequired,
          AccountSetupState.kakaoFriendsVerificationRequired,
        ]),
      );
    });

    test('route constant for the connection screen exists', () {
      expect(RouteNames.kakaoFriendConnect, '/kakao-friend-connect');
    });
  });
}
