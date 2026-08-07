import '../router/route_names.dart';

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

  final uploadedPhotoCount = onboarding['sourcePhotoUploadCount'];
  if (uploadedPhotoCount is! num || uploadedPhotoCount <= 0) {
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
