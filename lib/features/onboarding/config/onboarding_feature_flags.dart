/// Temporary onboarding feature switches.
///
/// Avatar generation is disabled by default while the onboarding flow is
/// being verified independently from the generation pipeline. Re-enable it
/// for a build with:
/// `--dart-define=ENABLE_ONBOARDING_AVATAR_GENERATION=true`
const bool kEnableOnboardingAvatarGeneration = bool.fromEnvironment(
  'ENABLE_ONBOARDING_AVATAR_GENERATION',
  defaultValue: false,
);
