import '../router/route_names.dart';
import '../shared/utils/avatar_lock_policy.dart';

/// Resolves the first incomplete onboarding step for a stored user profile.
///
/// The resolver is intentionally pure so login, splash recovery, and tests use
/// the same completion rules without reading local storage or Firestore.
String? resolveOnboardingNextRoute(Map<String, dynamic>? profile) {
  final onboarding = profile?['onboarding'];
  if (onboarding is! Map || onboarding.isEmpty) {
    return RouteNames.onboardingBasicInfo;
  }
  if (_isEmpty(onboarding['nickname']) && _isEmpty(onboarding['gender'])) {
    return RouteNames.onboardingBasicInfo;
  }

  final interests = onboarding['interests'];
  if (interests == null || (interests is List && interests.isEmpty)) {
    return RouteNames.onboardingInterestsSelection;
  }

  final lifestyle = onboarding['lifestyle'];
  if (lifestyle == null || (lifestyle is Map && lifestyle.isEmpty)) {
    return RouteNames.onboardingLifestyle;
  }
  if (_isEmpty(onboarding['major'])) {
    return RouteNames.onboardingMajor;
  }

  // 사진 단계는 승인된 아바타가 있어야만 완료된 것으로 본다. 업로드 카운터는
  // 클라이언트가 위조할 수 있고, 생성/승인 전 상태는 사진 화면에서 이어간다.
  if (!_hasApprovedAvatar(profile, onboarding)) {
    return RouteNames.onboardingPhoto;
  }
  if (_isEmpty(onboarding['selfIntroduction'])) {
    return RouteNames.onboardingSelfIntro;
  }

  final profileQa = onboarding['profileQa'];
  if (profileQa == null || (profileQa is List && profileQa.isEmpty)) {
    return RouteNames.onboardingProfileQa;
  }
  final keywords = onboarding['keywords'];
  if (keywords == null || (keywords is List && keywords.isEmpty)) {
    return RouteNames.onboardingKeywords;
  }

  final idealType = profile?['idealType'];
  if (idealType is! Map || idealType.isEmpty) {
    return RouteNames.onboardingIdealType;
  }
  if (idealType['preferredLifestyles'] == null) {
    return RouteNames.onboardingIdealLifestyle;
  }
  return null;
}

bool _isEmpty(dynamic value) {
  if (value == null) return true;
  if (value is String) return value.trim().isEmpty;
  return false;
}

bool _hasApprovedAvatar(Map<String, dynamic>? profile, Map onboarding) {
  final avatarRaw = profile?['avatar'];
  final avatar = avatarRaw is Map ? avatarRaw : const {};
  final status = avatar['status']?.toString().trim().toLowerCase() ?? '';
  if (status == 'approved') return true;

  final avatarUrlsRaw = onboarding['avatarUrls'];
  return avatarUrlsRaw is List &&
      avatarUrlsRaw.whereType<String>().any(isSafePublicApprovedAvatarUrl);
}
