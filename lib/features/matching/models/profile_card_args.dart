import '../../../services/ai_recommendation_service.dart';

class ProfileCardArgs {
  final String userId;
  final AiRecommendedProfile? aiProfile;
  final bool showActions;
  final bool isPreview;
  final Map<String, dynamic>? onboardingOverride;

  const ProfileCardArgs({
    required this.userId,
    this.aiProfile,
    this.showActions = true,
    this.isPreview = false,
    this.onboardingOverride,
  });

  factory ProfileCardArgs.fromAi(AiRecommendedProfile profile) {
    return ProfileCardArgs(
      userId: profile.candidateUid,
      aiProfile: profile,
      showActions: true,
      isPreview: false,
    );
  }

  factory ProfileCardArgs.fromChat({required String userId}) {
    return ProfileCardArgs(
      userId: userId,
      showActions: false,
      isPreview: false,
    );
  }

  factory ProfileCardArgs.preview({
    required String userId,
    required Map<String, dynamic> onboardingOverride,
  }) {
    return ProfileCardArgs(
      userId: userId,
      showActions: false,
      isPreview: true,
      onboardingOverride: onboardingOverride,
    );
  }
}
