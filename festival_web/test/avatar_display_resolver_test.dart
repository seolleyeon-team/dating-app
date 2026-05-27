import 'package:festival_web/avatar/avatar_display_resolver.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('returns only approved avatar url and ignores fallback photos', () {
    final url = FestivalAvatarDisplayResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl': 'https://cdn.example/avatar.png',
      },
      'onboarding': {
        'photoUrls': ['https://cdn.example/source-photo.png'],
        'avatarUrls': ['https://cdn.example/avatar-fallback.png'],
      },
      'photoMode': 'avatar',
      'photoUrl': 'https://cdn.example/direct-avatar.png',
    });

    expect(url, 'https://cdn.example/avatar.png');

    expect(
      FestivalAvatarDisplayResolver.resolve({
        'avatar': {'status': 'queued'},
        'onboarding': {
          'photoUrls': ['https://cdn.example/legacy-source.png'],
          'avatarUrls': ['https://cdn.example/avatar-fallback.png'],
        },
        'photoMode': 'avatar',
        'photoUrl': 'https://cdn.example/direct-avatar.png',
      }),
      isEmpty,
    );
  });

  test('rejects signed, private, and temp candidate urls', () {
    expect(
      FestivalAvatarDisplayResolver.isSafeDisplayUrl(
        'https://storage.googleapis.com/seolleyeon-private-source-photos/users/u/source/a.jpg',
      ),
      isFalse,
    );
    expect(
      FestivalAvatarDisplayResolver.isSafeDisplayUrl(
        'https://cdn.example/avatar.png?X-Goog-Signature=abc',
      ),
      isFalse,
    );
    expect(
      FestivalAvatarDisplayResolver.isSafeDisplayUrl(
        'https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/jobs/j/candidates/c.png',
      ),
      isFalse,
    );
    expect(
      FestivalAvatarDisplayResolver.isSafeDisplayUrl(
        'data:image/png;base64,abc',
      ),
      isFalse,
    );
    expect(
      FestivalAvatarDisplayResolver.isSafeDisplayUrl('javascript:alert(1)'),
      isFalse,
    );
    expect(
      FestivalAvatarDisplayResolver.resolve({
        'avatar': {'status': 'approved'},
        'onboarding': {
          'photoUrls': ['https://cdn.example/legacy-source.png'],
          'avatarUrls': ['https://cdn.example/avatar-fallback.png'],
        },
      }),
      isEmpty,
    );
  });
}
