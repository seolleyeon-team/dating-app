import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/chat_profile_photo_service.dart';

void main() {
  test('chat real photo result parses runtime url without private refs', () {
    final result = ChatProfilePhotoResult.fromMap({
      'displayMode': 'real_photo',
      'imageUrl':
          'https://storage.googleapis.com/runtime-chat-photo.jpg?X-Goog-Signature=runtime',
      'approvedAvatarUrl': 'https://cdn.example/avatar.png',
      'expiresAt': '2026-05-18T12:00:00.000Z',
    });

    expect(result.isRealPhoto, isTrue);
    expect(result.approvedAvatarUrl, 'https://cdn.example/avatar.png');
    expect(result.expiresAt, isNotNull);
  });

  test(
    'avatar fallback uses approved avatar when real photo is unavailable',
    () {
      final result = ChatProfilePhotoResult.fromMap({
        'displayMode': 'avatar',
        'approvedAvatarUrl': 'https://cdn.example/avatar.png',
        'reason': 'no_chat_real_photo_consent',
      }, fallbackAvatarUrl: 'https://cdn.example/fallback.png');

      expect(result.isRealPhoto, isFalse);
      expect(result.imageUrl, 'https://cdn.example/avatar.png');
      expect(result.reason, 'no_chat_real_photo_consent');
    },
  );

  test('empty backend response keeps caller fallback avatar', () {
    final result = ChatProfilePhotoResult.fromMap(
      const {},
      fallbackAvatarUrl: 'https://cdn.example/fallback.png',
    );

    expect(result.displayMode, 'avatar');
    expect(result.imageUrl, 'https://cdn.example/fallback.png');
  });

  test('chat result ignores photoUrls and uses chat-specific image fields', () {
    final result = ChatProfilePhotoResult.fromMap({
      'displayMode': 'avatar',
      'photoUrls': ['https://example.com/legacy-source.jpg'],
      'approvedAvatarUrl': 'https://cdn.example/avatar.png',
    });

    expect(result.isRealPhoto, isFalse);
    expect(result.imageUrl, 'https://cdn.example/avatar.png');
  });
}
