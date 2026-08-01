import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/avatar_lock_policy.dart';

void main() {
  test('approved avatar status locks even when display url is unsafe', () {
    final state = avatarLockStateFromUserProfile({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl': 'gs://private/users/u/source/src.jpg',
      },
    });

    expect(state.isLocked, isTrue);
    expect(state.approvedAvatarUrl, isEmpty);
  });

  test('approved avatar status keeps safe display url when present', () {
    final state = avatarLockStateFromUserProfile({
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl': 'https://cdn.example/avatar.png',
      },
    });

    expect(state.isLocked, isTrue);
    expect(state.approvedAvatarUrl, 'https://cdn.example/avatar.png');
  });

  test('generation statuses lock source changes before approval', () {
    for (final status in ['queued', 'preview_ready', 'failed']) {
      expect(
        avatarSourceLockedFromUserProfile({
          'avatar': {'status': status},
        }),
        isTrue,
        reason: status,
      );
    }
  });

  test('source lock can recover safe current avatar job id', () {
    final profile = {
      'avatar': {'status': 'queued'},
      'onboarding': {
        'avatarGenerationJobId': 'avatar_job_abc123DEF_456',
        'avatarSourceSelectionVersion': 3,
      },
    };

    expect(
      avatarSourceJobIdFromUserProfile(profile),
      'avatar_job_abc123DEF_456',
    );
    expect(avatarSourceSelectionVersionFromUserProfile(profile), 3);
  });

  test('source lock ignores unsafe or approved job recovery values', () {
    expect(
      avatarSourceJobIdFromUserProfile({
        'avatar': {'status': 'queued'},
        'onboarding': {'avatarGenerationJobId': 'avatar_job_bad/path'},
      }),
      isNull,
    );
    expect(
      avatarSourceJobIdFromUserProfile({
        'avatar': {
          'status': 'approved',
          'approvedAvatarUrl': 'https://cdn.example/avatar.png',
        },
        'onboarding': {'avatarGenerationJobId': 'avatar_job_abc123DEF_456'},
      }),
      isNull,
    );
  });
}
