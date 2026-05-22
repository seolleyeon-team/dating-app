class AvatarLockState {
  const AvatarLockState({
    required this.isLocked,
    required this.approvedAvatarUrl,
  });

  final bool isLocked;
  final String approvedAvatarUrl;
}

const String lockedAvatarMessage = '등록된 아바타는 삭제하거나 변경할 수 없어요.';
const String lockedAvatarNotice = '아바타가 등록되어 있어요. 프로필 이미지는 삭제할 수 없어요.';

AvatarLockState avatarLockStateFromUserProfile(Map<String, dynamic>? data) {
  if (data == null) {
    return const AvatarLockState(isLocked: false, approvedAvatarUrl: '');
  }

  final avatarRaw = data['avatar'];
  final avatar = avatarRaw is Map ? avatarRaw : const {};
  final status = avatar['status']?.toString().trim().toLowerCase() ?? '';
  final approvedUrl = avatar['approvedAvatarUrl']?.toString().trim() ?? '';

  if (status == 'approved') {
    return AvatarLockState(
      isLocked: true,
      approvedAvatarUrl: isSafePublicApprovedAvatarUrl(approvedUrl)
          ? approvedUrl
          : '',
    );
  }

  return const AvatarLockState(isLocked: false, approvedAvatarUrl: '');
}

bool isSafePublicApprovedAvatarUrl(String value) {
  final url = value.trim();
  if (url.isEmpty) return false;

  final lower = url.toLowerCase();
  if (lower.startsWith('gs://') || lower.startsWith('gcs://')) return false;

  const forbiddenMarkers = [
    'private-source-photos',
    'avatar-temp',
    'chat-profile-photos',
    '/source/',
    '%2fsource%2f',
    'x-goog-',
    'x-amz-',
    'googleaccessid',
    'signature=',
    'expires=',
    'awsaccesskeyid',
    'signedurl',
  ];

  return !forbiddenMarkers.any(lower.contains);
}
