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
}
