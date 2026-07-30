import 'package:flutter/foundation.dart';

/// Guards accidental use of legacy Material stub screens under `lib/screens/*`
/// and the unused GoRouter in `lib/routes/app_router.dart`.
///
/// The production navigator is `lib/router/app_router.dart` (named routes).
class LegacyStubPolicy {
  const LegacyStubPolicy._();

  /// True when a legacy stub screen may be shown (debug / tests only).
  static bool get allowLegacyStubScreens => kDebugMode;

  static Never denyInRelease(String screenName) {
    throw UnsupportedError(
      'Legacy stub screen "$screenName" is not available in release builds. '
      'Use lib/features/* via lib/router/app_router.dart instead.',
    );
  }
}
