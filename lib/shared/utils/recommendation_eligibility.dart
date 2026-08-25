import 'campus_life_zone_values.dart';
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

  /// `users/{uid}.onboarding.campusLifeZones` 를 읽는다.
  ///
  /// 분류는 온보딩의 [CampusLifeZoneResolver] 가 이미 끝냈다. 여기서
  /// grade/department/RA 로 재계산하지 않으며, 값이 없으면 빈 집합이다.
  static Set<String> campusLifeZonesOf(Map<String, dynamic>? profile) {
    if (profile == null) return const <String>{};
    final onboarding = profile['onboarding'];
    final raw = onboarding is Map
        ? onboarding['campusLifeZones']
        : profile['campusLifeZones'];
    // canonical(sinchon/songdo) 이 아닌 값은 생활권으로 인정하지 않는다.
    return CampusLifeZoneValues.readPersisted(raw);
  }

  /// 생활권이 겹치는지. 복수 생활권 사용자를 위해 equality가 아닌 교집합이다.
  ///
  /// 생활권은 랭킹 점수가 아니라 hard eligibility이며, 어느 한쪽이라도
  /// 값이 없으면 추천하지 않는다 (fail-closed).
  /// serving 단계의 생활권 게이트.
  ///
  /// [enforced] 는 서버가 정한 rollout activation 상태다. 적용 전(OFF)에는
  /// 생활권으로 후보를 거르지 않는다. 적용 후(ON)에는 값이 없으면
  /// fail-closed 로 제외한다 (교집합이 없으면 실제로 만날 수 없으므로).
  static bool passesCampusLifeZoneGate({
    required bool enforced,
    required Set<String> viewerZones,
    required Set<String> candidateZones,
  }) {
    if (!enforced) return true;
    return hasCompatibleCampusLifeZone(viewerZones, candidateZones);
  }

  static bool hasCompatibleCampusLifeZone(
    Set<String> viewerZones,
    Set<String> candidateZones,
  ) {
    if (viewerZones.isEmpty || candidateZones.isEmpty) return false;
    return viewerZones.intersection(candidateZones).isNotEmpty;
  }

  /// 뷰어와 후보 프로필 문서로 바로 판정한다.
  static bool isCampusLifeZoneCompatible(
    Map<String, dynamic>? viewerProfile,
    Map<String, dynamic>? candidateProfile,
  ) {
    return hasCompatibleCampusLifeZone(
      campusLifeZonesOf(viewerProfile),
      campusLifeZonesOf(candidateProfile),
    );
  }

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
