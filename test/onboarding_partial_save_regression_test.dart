import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/services/onboarding_write_payload.dart';

void main() {
  test('keyword save must not write or require interests', () {
    final helperSource = File(
      'lib/services/onboarding_save_helper.dart',
    ).readAsStringSync();
    final userServiceSource = File(
      'lib/services/user_service.dart',
    ).readAsStringSync();

    expect(helperSource, isNot(contains('interests: []')));
    final keywordMethod = RegExp(
      r'Future<void> saveOnboardingKeywords\(\{.*?\n  \}',
      dotAll: true,
    ).firstMatch(userServiceSource)?.group(0);
    expect(keywordMethod, isNotNull);
    expect(keywordMethod, isNot(contains('interests')));
    expect(userServiceSource, contains('buildOnboardingFieldUpdate'));
  });

  test('keyword field update preserves sibling onboarding fields', () {
    final document = <String, dynamic>{
      'onboarding': <String, dynamic>{
        'interests': ['movie', 'travel'],
        'keywords': <String>[],
        'selfIntroduction': 'existing intro',
      },
    };

    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(
        fieldName: 'keywords',
        value: ['calm', 'humor'],
      ),
    );

    expect(document['onboarding'], {
      'interests': ['movie', 'travel'],
      'keywords': ['calm', 'humor'],
      'selfIntroduction': 'existing intro',
    });
  });

  test('interest and keyword saves are independent in either order', () {
    final document = <String, dynamic>{
      'onboarding': <String, dynamic>{
        'interests': ['movie', 'travel'],
        'keywords': ['calm'],
        'lifestyle': <String, dynamic>{'drinking': 'none'},
      },
    };

    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(
        fieldName: 'interests',
        value: ['exhibition', 'walk'],
      ),
    );
    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(fieldName: 'keywords', value: <String>[]),
    );
    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(fieldName: 'keywords', value: ['saved again']),
    );

    expect(document['onboarding'], {
      'interests': ['exhibition', 'walk'],
      'keywords': ['saved again'],
      'lifestyle': {'drinking': 'none'},
    });
  });

  test(
    'interest field update preserves existing keywords and nested fields',
    () {
      final document = <String, dynamic>{
        'onboarding': <String, dynamic>{
          'interests': ['movie'],
          'keywords': ['calm', 'honest'],
          'lifestyle': <String, dynamic>{
            'drinking': 'none',
            'smoking': 'never',
          },
        },
      };

      _applyFieldUpdates(
        document,
        buildOnboardingFieldUpdates({
          'interests': ['exhibition', 'walk'],
          'lifestyle': {'drinking': 'social'},
        }),
      );

      expect(document['onboarding'], {
        'interests': ['exhibition', 'walk'],
        'keywords': ['calm', 'honest'],
        'lifestyle': {'drinking': 'social', 'smoking': 'never'},
      });
    },
  );

  test('keyword payload only contains the keyword field and timestamp', () {
    final payload = buildOnboardingFieldUpdate(
      fieldName: 'keywords',
      value: <String>[],
    );

    expect(
      payload.keys,
      containsAll(<String>['onboarding.keywords', 'onboardingUpdatedAt']),
    );
    expect(payload.keys, isNot(contains('onboarding')));
    expect(payload.keys, isNot(contains('onboarding.interests')));
    expect(payload['onboardingUpdatedAt'], isA<FieldValue>());
  });

  test('all partial onboarding paths preserve siblings', () {
    final document = <String, dynamic>{
      'onboarding': <String, dynamic>{
        'interests': ['movie'],
        'keywords': ['calm'],
        'photoUrls': ['old-photo'],
        'profileQa': [
          {'question': 'old', 'answer': 'old'},
        ],
        'selfIntroduction': 'old intro',
        'lifestyle': <String, dynamic>{
          'drinking': 'none',
          'smoking': 'never',
          'exercise': 'often',
          'religion': 'none',
        },
      },
      'privacySettings': <String, dynamic>{'avoidSameDepartment': false},
      'idealType': <String, dynamic>{
        'minAge': 20,
        'maxAge': 30,
        'preferredLifestyles': <String, dynamic>{
          'drinking': 'none',
          'smoking': 'never',
        },
      },
    };

    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(fieldName: 'photoUrls', value: ['new-photo']),
    );
    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdate(
        fieldName: 'profileQa',
        value: [
          {'question': 'new', 'answer': 'new'},
        ],
      ),
    );
    _applyFieldUpdates(
      document,
      buildPrivacyFieldUpdates({'avoidSameDepartment': true}),
    );
    _applyFieldUpdates(
      document,
      buildIdealTypeFieldUpdate(
        fieldName: 'preferredPersonalities',
        value: ['kind'],
      ),
    );

    expect(document['onboarding']['interests'], ['movie']);
    expect(document['onboarding']['keywords'], ['calm']);
    expect(document['onboarding']['photoUrls'], ['new-photo']);
    expect(document['onboarding']['profileQa'], [
      {'question': 'new', 'answer': 'new'},
    ]);
    expect(document['onboarding']['lifestyle'], {
      'drinking': 'none',
      'smoking': 'never',
      'exercise': 'often',
      'religion': 'none',
    });
    expect(document['privacySettings'], {'avoidSameDepartment': true});
    expect(document['idealType']['minAge'], 20);
    expect(document['idealType']['maxAge'], 30);
    expect(document['idealType']['preferredLifestyles'], {
      'drinking': 'none',
      'smoking': 'never',
    });
    expect(document['idealType']['preferredPersonalities'], ['kind']);
  });

  test('concurrent leaf saves are order-independent', () {
    Map<String, dynamic> seed() => <String, dynamic>{
      'onboarding': <String, dynamic>{
        'interests': ['old-interest'],
        'keywords': ['old-keyword'],
        'lifestyle': <String, dynamic>{'smoking': 'never'},
      },
    };

    final interestUpdate = buildOnboardingFieldUpdate(
      fieldName: 'interests',
      value: ['new-interest'],
    );
    final keywordUpdate = buildOnboardingFieldUpdate(
      fieldName: 'keywords',
      value: ['new-keyword'],
    );

    final firstOrder = seed();
    _applyFieldUpdates(firstOrder, interestUpdate);
    _applyFieldUpdates(firstOrder, keywordUpdate);

    final secondOrder = seed();
    _applyFieldUpdates(secondOrder, keywordUpdate);
    _applyFieldUpdates(secondOrder, interestUpdate);

    expect(firstOrder, secondOrder);
    expect(firstOrder['onboarding']['lifestyle'], {'smoking': 'never'});
  });

  test('explicit clears stay scoped to a leaf field', () {
    final document = <String, dynamic>{
      'onboarding': <String, dynamic>{
        'interests': ['movie'],
        'keywords': ['calm'],
        'selfIntroduction': 'existing',
        'lifestyle': <String, dynamic>{
          'drinking': 'social',
          'smoking': 'never',
        },
      },
    };

    _applyFieldUpdates(
      document,
      buildOnboardingFieldUpdates({
        'interests': <String>[],
        'selfIntroduction': null,
        'keywords': FieldValue.delete(),
        'lifestyle': {'drinking': null, 'smoking': FieldValue.delete()},
      }),
    );

    expect(document['onboarding']['interests'], isEmpty);
    expect(document['onboarding']['selfIntroduction'], isNull);
    expect(document['onboarding']['keywords'], isA<FieldValue>());
    expect(document['onboarding']['lifestyle']['drinking'], isNull);
    expect(document['onboarding']['lifestyle']['smoking'], isA<FieldValue>());
  });

  test('unsafe or unsupported field paths are rejected', () {
    expect(
      () => buildOnboardingFieldUpdate(
        fieldName: 'interests.someSibling',
        value: ['bad'],
      ),
      throwsArgumentError,
    );
    expect(
      () => buildOnboardingFieldUpdates({'unexpectedField': true}),
      throwsArgumentError,
    );
    expect(
      () => buildOnboardingFieldUpdates({
        'lifestyle': {'drinking.someSibling': 'bad'},
      }),
      throwsArgumentError,
    );
    expect(
      () => buildOnboardingFieldUpdates({'lifestyle': null}),
      throwsArgumentError,
    );
    expect(
      () => buildIdealTypeFieldUpdate(
        fieldName: 'preferredLifestyles',
        value: {'unexpected': 'bad'},
      ),
      throwsArgumentError,
    );
    expect(
      () => buildPrivacyFieldUpdates({'unexpected': true}),
      throwsArgumentError,
    );
  });

  test('empty nested maps never replace the nested object', () {
    final payload = buildOnboardingFieldUpdates({
      'lifestyle': <String, dynamic>{},
    });

    expect(payload.keys, contains('onboardingUpdatedAt'));
    expect(payload.keys, isNot(contains('onboarding.lifestyle')));
  });

  test('ideal type field saves do not replace sibling fields', () {
    final document = <String, dynamic>{
      'idealType': <String, dynamic>{'minAge': 20, 'maxAge': 30},
    };

    _applyFieldUpdates(
      document,
      buildIdealTypeFieldUpdate(fieldName: 'preferredMbti', value: ['ENFP']),
    );

    expect(document['idealType'], {
      'minAge': 20,
      'maxAge': 30,
      'preferredMbti': ['ENFP'],
    });
  });

  test('school verification and interest gates are fail-closed', () {
    for (final value in <Object?>[true, false, 'true', 1, null]) {
      final profile = BlindMeetingProfileSnapshot.fromUserDoc('user-1', {
        'isStudentVerified': value,
        'onboarding': <String, dynamic>{
          'interests': ['movie'],
        },
      });
      expect(profile.schoolVerified, value == true);
    }

    final missingInterests = BlindMeetingProfileSnapshot.fromUserDoc('user-1', {
      'isStudentVerified': true,
      'onboarding': <String, dynamic>{'interests': <String>[]},
    });
    expect(missingInterests.needsInterests, isTrue);
  });
}

void _applyFieldUpdates(
  Map<String, dynamic> document,
  Map<String, dynamic> updates,
) {
  for (final entry in updates.entries) {
    if (!entry.key.contains('.')) continue;
    final segments = entry.key.split('.');
    var current = document;
    for (final segment in segments.take(segments.length - 1)) {
      final value = current[segment];
      if (value is Map<String, dynamic>) {
        current = value;
      } else if (value is Map) {
        current = value.cast<String, dynamic>();
      } else {
        current[segment] = <String, dynamic>{};
        current = current[segment] as Map<String, dynamic>;
      }
    }
    current[segments.last] = entry.value;
  }
}
