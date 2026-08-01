import 'profile_display_image_resolver.dart';

/// 추천 후보로 노출해도 되는지 판정한다.
///
/// 파이썬 배치 파이프라인의 `load_avatar_display_status_from_docs` +
/// 동성 제외 규칙과 같은 기준을 클라이언트에서도 적용하기 위한 것이다.
/// 배치가 만든 `modelRecs`는 하루 전 스냅샷일 수 있고, `users` 폴백 피드는
/// 애초에 배치를 거치지 않으므로 노출 직전에 한 번 더 확인해야 한다.
class RecommendationEligibility {
  const RecommendationEligibility._();

  static const Set<String> _blockedAccountStatuses = {
    'blocked',
    'deleted',
    'suspended',
  };

  /// 후보 계정 자체가 노출 가능한 상태인지.
  static bool isCandidateDisplayable(Map<String, dynamic>? profile) {
    if (profile == null) return false;
    if (!isAccountActive(profile)) return false;
    if (profile['isStudentVerified'] != true) return false;
    if (!isProfileComplete(profile)) return false;
    return ProfileDisplayImageResolver.resolve(profile).isNotEmpty;
  }

  static bool isAccountActive(Map<String, dynamic> profile) {
    final status = (profile['status'] ?? profile['accountStatus'])
        ?.toString()
        .toLowerCase();
    if (status != null && _blockedAccountStatuses.contains(status)) {
      return false;
    }
    if (profile['isDeleted'] == true) return false;
    if (profile['isSuspended'] == true) return false;
    return profile['isActive'] != false;
  }

  static bool isProfileComplete(Map<String, dynamic> profile) {
    final explicit = profile['isProfileComplete'];
    if (explicit is bool) return explicit;
    return profile['initialSetupComplete'] == true;
  }

  /// `users/{uid}.onboarding.gender` 또는 최상위 `gender`를 정규화해서 읽는다.
  static String? genderOf(Map<String, dynamic>? profile) {
    if (profile == null) return null;
    final onboarding = profile['onboarding'];
    final raw =
        (onboarding is Map ? onboarding['gender'] : null) ?? profile['gender'];
    final text = raw?.toString().trim().toLowerCase();
    return (text == null || text.isEmpty) ? null : text;
  }

  /// 성별을 양쪽 다 아는 경우에만 동성을 제외한다.
  /// 한쪽이라도 모르면 제외하지 않아 신규 가입자가 사라지지 않도록 한다.
  static bool isOppositeGender({
    required Map<String, dynamic>? viewer,
    required Map<String, dynamic>? candidate,
  }) {
    final viewerGender = genderOf(viewer);
    final candidateGender = genderOf(candidate);
    if (viewerGender == null || candidateGender == null) return true;
    return viewerGender != candidateGender;
  }

  /// 특정 조회자에게 이 후보를 보여줘도 되는지.
  static bool isRecommendableTo({
    required String viewerUid,
    required Map<String, dynamic>? viewer,
    required String candidateUid,
    required Map<String, dynamic>? candidate,
    Set<String> blockedUids = const {},
  }) {
    if (candidateUid.isEmpty || candidateUid == viewerUid) return false;
    if (blockedUids.contains(candidateUid)) return false;
    if (!isCandidateDisplayable(candidate)) return false;
    return isOppositeGender(viewer: viewer, candidate: candidate);
  }
}
