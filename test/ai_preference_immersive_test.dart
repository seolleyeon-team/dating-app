import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_identity_session.dart';
import 'package:seolleyeon/features/matching/services/ai_profile_storage_service.dart';

void main() {
  test('AI preference identity keeps canonical target and zero-padded profile ID', () {
    final identity = AiPreferenceIdentity.fromIdentityId('male_007');

    expect(identity.identityId, 'male_007');
    expect(identity.profileId, '007');
    expect(
      identity.images.map((image) => image.storagePath),
      containsAll(<String>[
        'ai_profiles/male/007/face_card.png',
        'ai_profiles/male/007/vibe_card.png',
        'ai_profiles/male/007/silhouette_card.png',
      ]),
    );
    expect(identity.identityId.contains('face_card'), isFalse);
  });

  test('browsing all evidence shots does not write an event', () {
    var writeCount = 0;
    final session = AiPreferenceIdentitySessionController(
      identities: [AiPreferenceIdentity.fromIdentityId('female_123')],
      onDecision: (_) async => writeCount++,
    );

    session.browseNextShot();
    session.browseNextShot();
    session.browsePreviousShot();
    session.browsePreviousShot();

    expect(session.currentShotIndex, 0);
    expect(writeCount, 0);
  });

  test('missing Storage evidence is not represented as a complete identity', () async {
    final service = AiProfileStorageService(
      urlResolver: (path) async =>
          path.endsWith('face_card.png') ? 'https://example.com/$path' : null,
    );
    final resolved = await service.resolveIdentity(
      service.buildIdentity(gender: 'female', profileId: '123'),
    );

    expect(
      resolved.images.where((image) => image.downloadUrl != null),
      hasLength(1),
    );
    expect(
      resolved.images.every((image) => image.downloadUrl != null),
      isFalse,
    );
  });
}
