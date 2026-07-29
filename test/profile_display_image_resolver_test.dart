import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/profile_display_image_resolver.dart';

void main() {
  test('approved avatar returns approvedAvatarUrl', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl': 'https://cdn.example/avatar.png',
      },
      'onboarding': {
        'avatarUrls': ['https://cdn.example/fallback.png'],
        'photoUrls': ['https://example.com/source.jpg'],
      },
    });

    expect(url, 'https://cdn.example/avatar.png');
  });

  test('onboarding avatarUrls fallback returns first avatar URL', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {'status': 'none'},
      'onboarding': {
        'avatarUrls': ['https://cdn.example/avatar-fallback.png'],
        'photoUrls': ['https://example.com/source.jpg'],
      },
    });

    expect(url, 'https://cdn.example/avatar-fallback.png');
  });

  test('unsafe onboarding avatarUrls fallback is rejected', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {'status': 'none'},
      'onboarding': {
        'avatarUrls': [
          'https://storage.googleapis.com/public-bucket/users/u/candidates/c.png',
        ],
      },
    });

    expect(url, '');
  });

  test('photoUrls alone returns empty string', () {
    final url = ProfileDisplayImageResolver.resolve({
      'onboarding': {
        'photoUrls': ['https://example.com/source.jpg'],
      },
    });

    expect(url, '');
  });

  test('top-level photoUrls alone returns empty string', () {
    final url = ProfileDisplayImageResolver.resolve({
      'photoUrls': ['https://example.com/source.jpg'],
    });

    expect(url, '');
  });

  test('photoUrls never becomes display fallback for unsafe refs', () {
    const unsafePhotoUrls = [
      'gs://seolleyeon-private-source-photos/users/u/source/src_001.jpg',
      'gcs://seolleyeon-private-source-photos/users/u/source/src_002.jpg',
      'https://cdn.example/source.jpg?X-Goog-Signature=secret',
      'https://cdn.example/source.jpg?GoogleAccessId=svc@example&Signature=abc&Expires=9999999999',
      'https://storage.googleapis.com/public-bucket/users/u/source/src.jpg',
      'https://storage.googleapis.com/public-bucket/users/u/jobs/job_1/c.png',
      'https://storage.googleapis.com/public-bucket/users/u/candidates/c_1.png',
    ];

    for (final value in unsafePhotoUrls) {
      expect(
        ProfileDisplayImageResolver.resolve({
          'photoUrls': [value],
          'onboarding': {
            'photoUrls': [value],
          },
        }),
        '',
        reason: value,
      );
    }
  });

  test('profileImageUrl alone returns empty string', () {
    final url = ProfileDisplayImageResolver.resolve({
      'profileImageMode': 'avatar',
      'profileImageUrl': 'https://example.com/legacy-source.jpg',
    });

    expect(url, '');
  });

  test('private source GCS path never returns as display image', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl':
            'gs://seolleyeon-private-source-photos/users/u/source/src_001.jpg',
      },
      'onboarding': {
        'avatarUrls': [
          'gs://seolleyeon-private-source-photos/users/u/source/src_002.jpg',
        ],
      },
    });

    expect(url, '');
  });

  test('private source bucket URL never returns as display image', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl':
            'https://storage.googleapis.com/seolleyeon-private-source-photos/users/u/source/src_001.jpg',
      },
      'onboarding': {
        'avatarUrls': [
          'https://firebasestorage.googleapis.com/v0/b/seolleyeon-private-source-photos/o/users%2Fu%2Fsource%2Fsrc_002.jpg?alt=media',
        ],
      },
    });

    expect(url, '');
  });

  test('avatar temp bucket URL never returns as display image', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl':
            'https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/jobs/j/candidates/c.png',
      },
    });

    expect(url, '');
  });

  test('virtual-hosted private buckets never return as display image', () {
    const unsafeUrls = [
      'https://seolleyeon-final-private-source-photos.storage.googleapis.com/users/u/source/src.jpg',
      'https://seolleyeon-private-source-photos.storage.googleapis.com/users/u/source/src.jpg',
      'https://seolleyeon-final-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png',
      'https://seolleyeon-final-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg',
      'https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg',
      'https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png',
      'https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg',
    ];

    for (final value in unsafeUrls) {
      expect(
        ProfileDisplayImageResolver.resolve({
          'avatar': {'status': 'approved', 'approvedAvatarUrl': value},
          'onboarding': {
            'avatarUrls': [value],
          },
        }),
        '',
        reason: value,
      );
    }
  });

  test('lower-case signed storage URLs never return as display image', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl':
            'https://storage.googleapis.com/public-bucket/avatar.png?x-goog-signature=secret',
      },
      'onboarding': {
        'avatarUrls': [
          'https://cdn.example/avatar.png?googleaccessid=svc@example&signature=abc&expires=9999999999',
        ],
      },
    });

    expect(url, '');
  });

  test('storage source paths never return as display image', () {
    final url = ProfileDisplayImageResolver.resolve({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl':
            'https://storage.googleapis.com/public-bucket/users/u/source/src.jpg',
      },
      'onboarding': {
        'avatarUrls': [
          'https://firebasestorage.googleapis.com/v0/b/public-bucket/o/users%2Fu%2Fsource%2Fsrc.jpg?alt=media',
        ],
      },
    });

    expect(url, '');
  });
}
