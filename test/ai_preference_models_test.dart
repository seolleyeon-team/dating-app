import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';

void main() {
  group('AI preference identity models', () {
    test('builds all three canonical paths for male_123', () {
      final identity = AiPreferenceIdentity.fromIdentityId('male_123');

      expect(identity.identityId, 'male_123');
      expect(
        identity.images.map((image) => image.storagePath),
        containsAll(<String>[
          'ai_profiles/male/123/face_card.png',
          'ai_profiles/male/123/vibe_card.png',
          'ai_profiles/male/123/silhouette_card.png',
        ]),
      );
    });

    test('builds all three canonical paths for female_207', () {
      final identity = AiPreferenceIdentity.fromIdentityId('female_207');

      expect(identity.identityId, 'female_207');
      expect(
        identity.images.map((image) => image.storagePath),
        containsAll(<String>[
          'ai_profiles/female/207/face_card.png',
          'ai_profiles/female/207/vibe_card.png',
          'ai_profiles/female/207/silhouette_card.png',
        ]),
      );
    });

    test('preserves zero-padded profile text exactly', () {
      final identity = AiPreferenceIdentity.fromIdentityId('male_007');

      expect(identity.profileId, '007');
      expect(identity.identityId, 'male_007');
      expect(
        identity.images.first.storagePath,
        'ai_profiles/male/007/face_card.png',
      );
      expect(
        identity.images,
        everyElement(
          predicate<AiPreferenceImage>(
            (image) => image.storagePath.contains('/007/'),
          ),
        ),
      );
    });

    test('contains exactly three unique shot types tied to one identity', () {
      final identity = AiPreferenceIdentity.fromIdentityId('female_207');

      expect(identity.images, hasLength(3));
      expect(
        identity.images.map((image) => image.shotType).toSet(),
        hasLength(3),
      );
      expect(
        identity.images.map((image) => image.identityId),
        everyElement('female_207'),
      );
    });

    test('orderedBy preserves the identity and selects each shot once', () {
      final identity = AiPreferenceIdentity.fromIdentityId('male_123');

      final ordered = identity.orderedBy(const <AiPreferenceShotType>[
        AiPreferenceShotType.silhouetteCard,
        AiPreferenceShotType.faceCard,
        AiPreferenceShotType.vibeCard,
      ]);

      expect(ordered.identityId, 'male_123');
      expect(
        ordered.images.map((image) => image.shotType),
        <AiPreferenceShotType>[
          AiPreferenceShotType.silhouetteCard,
          AiPreferenceShotType.faceCard,
          AiPreferenceShotType.vibeCard,
        ],
      );
      expect(ordered.images.map((image) => image.storagePath), <String>[
        'ai_profiles/male/123/silhouette_card.png',
        'ai_profiles/male/123/face_card.png',
        'ai_profiles/male/123/vibe_card.png',
      ]);
    });

    test('rejects malformed identity IDs without normalizing them', () {
      expect(
        () => AiPreferenceIdentity.fromIdentityId('male_7_extra'),
        throwsFormatException,
      );
      expect(
        () => AiPreferenceIdentity.fromIdentityId('male_'),
        throwsFormatException,
      );
    });
  });
}
