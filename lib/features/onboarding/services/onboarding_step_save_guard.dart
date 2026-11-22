import 'dart:async';

import '../../../shared/utils/safe_catch.dart';

enum OnboardingStepSaveOutcome {
  /// The save finished; the caller may leave the step.
  saved,

  /// The save threw or did not finish in time; the caller stays on the step.
  failed,

  /// Another save of this step is still running. The call that started it owns
  /// the navigation, so this caller must do nothing.
  alreadyRunning,
}

/// Runs one save of an onboarding step at a time.
///
/// The step screens used to guard the save with a flag whose second caller
/// simply returned, and then navigated as if it had saved. A second tap during
/// a slow save therefore pushed the next screen before the write finished, and
/// the first tap pushed it again. A thrown save escaped as an unhandled error
/// with no feedback.
///
/// A Firestore write made while offline does not fail: its future stays
/// pending until the device is back online. [timeout] turns that into a
/// reported failure so the button cannot stay dead for the rest of the
/// session.
class OnboardingStepSaveGuard {
  OnboardingStepSaveGuard({this.timeout = const Duration(seconds: 15)});

  final Duration timeout;
  bool _inFlight = false;

  bool get inFlight => _inFlight;

  Future<OnboardingStepSaveOutcome> run(
    Future<void> Function() save, {
    required String tag,
  }) async {
    if (_inFlight) return OnboardingStepSaveOutcome.alreadyRunning;
    _inFlight = true;
    try {
      await save().timeout(timeout);
      return OnboardingStepSaveOutcome.saved;
    } catch (error, stackTrace) {
      logCaughtError(tag, error, stackTrace);
      return OnboardingStepSaveOutcome.failed;
    } finally {
      _inFlight = false;
    }
  }
}
