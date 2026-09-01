import 'package:flutter/foundation.dart';

/// Controls entry points that skip the onboarding gates (terms, Yonsei email
/// verification, adult/real-name verification, Kakao friend connection, the
/// one-time friend snapshot, and profile onboarding).
///
/// Student verification is the product's trust boundary. Everything downstream
/// of it — recommendations, chat, 무물, community — assumes the account behind
/// the session belongs to a verified student. Any shipped path around it puts
/// unverified accounts into all of those surfaces at once.
///
/// DEV/QA ONLY — NEVER RELEASE. Two independent conditions must both hold:
///   1. the artifact is a debug build, and
///   2. the operator opted in explicitly at compile time.
///
/// A flavor name is deliberately NOT part of this decision. `staging` is a
/// release artifact that real testers install, so treating the flavor as an
/// authorization shipped a full gate bypass inside a signed build.
///
/// Opt in for local QA with:
///   flutter run --dart-define=ALLOW_TEST_ACCOUNT_ENTRY=true
class DevEntryPolicy {
  const DevEntryPolicy._();

  /// Compile-time QA opt-in. Absent from every build that does not pass the
  /// define, which includes all release and profile artifacts.
  static const bool explicitQaEntryEnabled = bool.fromEnvironment(
    'ALLOW_TEST_ACCOUNT_ENTRY',
    defaultValue: false,
  );

  static bool? _testOverride;

  /// Pure decision, so the whole release matrix is unit-testable without
  /// building each flavor.
  static bool resolveTestAccountEntry({
    required bool isDebugBuild,
    required bool explicitQaEntryEnabled,
  }) {
    return isDebugBuild && explicitQaEntryEnabled;
  }

  /// Runtime answer for the current artifact.
  static bool get allowTestAccountEntry =>
      _testOverride ??
      resolveTestAccountEntry(
        isDebugBuild: kDebugMode,
        explicitQaEntryEnabled: explicitQaEntryEnabled,
      );

  @visibleForTesting
  static void debugSetTestAccountEntry(bool? value) {
    _testOverride = value;
  }
}
