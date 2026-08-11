import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/firebase_options.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_profile_storage_service.dart';

void main() {
  group('AI profile Storage contract', () {
    test(
      'all configured platforms use the final Firebase project and bucket',
      () {
        final options = <FirebaseOptions>[
          DefaultFirebaseOptions.android,
          DefaultFirebaseOptions.ios,
          DefaultFirebaseOptions.web,
        ];

        for (final option in options) {
          expect(option.projectId, 'seolleyeon-final');
          expect(option.storageBucket, 'seolleyeon-final.firebasestorage.app');
        }
      },
    );

    test('resolver source has no old bucket fallback', () {
      final source = File(
        'lib/features/matching/services/ai_profile_storage_service.dart',
      ).readAsStringSync();

      expect(source, isNot(contains('seolleyeon.firebasestorage.app')));
    });

    test('resolves three paths independently and caches each path', () async {
      final requestedPaths = <String>[];
      final service = AiProfileStorageService(
        urlResolver: (path) async {
          requestedPaths.add(path);
          if (path.endsWith('vibe_card.png')) {
            throw FirebaseException(
              plugin: 'firebase_storage',
              code: 'object-not-found',
            );
          }
          return 'https://cdn.example/$path';
        },
      );

      final identity = service.buildIdentity(gender: 'male', profileId: '007');
      final resolved = await service.resolveIdentity(identity);

      expect(requestedPaths, hasLength(3));
      expect(
        resolved.images.map((image) => image.storagePath),
        containsAll(<String>[
          'ai_profiles/male/007/face_card.png',
          'ai_profiles/male/007/vibe_card.png',
          'ai_profiles/male/007/silhouette_card.png',
        ]),
      );
      expect(
        resolved.images
            .firstWhere(
              (image) => image.shotType == AiPreferenceShotType.faceCard,
            )
            .downloadUrl,
        'https://cdn.example/ai_profiles/male/007/face_card.png',
      );
      expect(
        resolved.images
            .firstWhere(
              (image) => image.shotType == AiPreferenceShotType.vibeCard,
            )
            .downloadUrl,
        isNull,
      );

      final secondResolution = await service.resolveIdentity(identity);

      expect(requestedPaths, hasLength(3));
      expect(secondResolution.images, hasLength(3));
      expect(
        secondResolution.images.map((image) => image.downloadUrl),
        contains('https://cdn.example/ai_profiles/male/007/face_card.png'),
      );
    });
  });
}
