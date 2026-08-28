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

/// Temporarily lets new users continue onboarding before adding profile photos.
/// Restore the two-photo gate for a release with:
/// `--dart-define=REQUIRE_ONBOARDING_PHOTOS=true`
const bool kRequireOnboardingPhotos = bool.fromEnvironment(
  'REQUIRE_ONBOARDING_PHOTOS',
  defaultValue: false,
);
