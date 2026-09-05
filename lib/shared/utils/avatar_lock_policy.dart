class AvatarLockState {
  const AvatarLockState({
    required this.isLocked,
    required this.approvedAvatarUrl,
  });

  final bool isLocked;
  final String approvedAvatarUrl;
}

const String lockedAvatarMessage = '등록된 아바타는 삭제하거나 변경할 수 없어요.';
const String lockedAvatarNotice = '아바타가 등록되어 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.';
const String sourceLockedAvatarMessage = '아바타 생성이 시작되어 사진을 변경할 수 없어요.';
const String sourceLockedAvatarFailureMessage =
    '아바타 생성에 실패했어요. 같은 사진으로 다시 시도해주세요.';

const Set<String> sourceLockedAvatarStatuses = {
  'queued',
  'source_selecting',
  'generating',
  'running',
  'qa_pending',
  'preview_ready',
  'needs_review',
  'no_previewable_candidates',
  'failed',
  // 서버가 실제로 기록하는 종료 상태. 빠지면 jobId 가 버려져 복구가 끊긴다.
  'retryable_failed',
  'terminal_failed',
  'reconciliation_required',
};

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

bool avatarSourceLockedFromUserProfile(Map<String, dynamic>? data) {
  if (data == null) return false;
  final avatarRaw = data['avatar'];
  final avatar = avatarRaw is Map ? avatarRaw : const {};
  final status = avatar['status']?.toString().trim().toLowerCase() ?? '';
  return sourceLockedAvatarStatuses.contains(status);
}

String? avatarSourceJobIdFromUserProfile(Map<String, dynamic>? data) {
  if (data == null || avatarLockStateFromUserProfile(data).isLocked) {
    return null;
  }
  if (!avatarSourceLockedFromUserProfile(data)) return null;
  final onboardingRaw = data['onboarding'];
  final onboarding = onboardingRaw is Map ? onboardingRaw : const {};
  final jobId = onboarding['avatarGenerationJobId']?.toString().trim() ?? '';
  if (!_isSafeAvatarJobId(jobId)) return null;
  return jobId;
}

int? avatarSourceSelectionVersionFromUserProfile(Map<String, dynamic>? data) {
  if (data == null || avatarLockStateFromUserProfile(data).isLocked) {
    return null;
  }
  final onboardingRaw = data['onboarding'];
  final onboarding = onboardingRaw is Map ? onboardingRaw : const {};
  return int.tryParse(
    onboarding['avatarSourceSelectionVersion']?.toString() ?? '',
  );
}

bool _isSafeAvatarJobId(String value) {
  return RegExp(r'^avatar_job_[A-Za-z0-9_-]{8,80}$').hasMatch(value);
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
