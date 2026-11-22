import 'package:flutter/foundation.dart' show kReleaseMode;

/// Compile-time debug / QA switches that must be inert in a release artifact.
///
/// Each of these is requested with `--dart-define=<NAME>=true`. A define is
/// only a request: the value the app acts on is `!kReleaseMode && requested`,
/// so a release binary (the only kind that is store-signed and reaches real
/// users) cannot turn any of them on, even when the define is passed by a
/// script, a CI job or by hand. Because the guarded values are compile-time
/// constants, the bypassed branches are also removed from release code.
///
/// Local testing of these switches uses a debug or profile build.
///
/// Read these switches ONLY through this class.
/// test/release_build_guards_contract_test.dart pins that.
class ReleaseBuildGuards {
  const ReleaseBuildGuards._();

  /// Pure decision, so the release matrix is unit-testable.
  static bool resolve({required bool isReleaseBuild, required bool requested}) {
    return !isReleaseBuild && requested;
  }

  static const bool _forceAppCheckDebugRequested = bool.fromEnvironment(
    'FORCE_APP_CHECK_DEBUG',
    defaultValue: false,
  );

  /// Forces the App Check debug provider. Non-release builds already default
  /// to the debug provider on Android/iOS; on the web this additionally needs
  /// a loopback host.
  static const bool forceAppCheckDebugProvider =
      !kReleaseMode && _forceAppCheckDebugRequested;

  static const bool _appCheckDiagnosticRequested = bool.fromEnvironment(
    'APP_CHECK_DIAGNOSTIC_MODE',
    defaultValue: false,
  );

  /// Turns App Check token auto-refresh off to isolate a single token
  /// request while diagnosing a provider failure.
  static const bool appCheckDiagnosticMode =
      !kReleaseMode && _appCheckDiagnosticRequested;

  static const bool _qaScreenCaptureRequested = bool.fromEnvironment(
    'SEOLLEYEON_QA_ALLOW_SCREEN_CAPTURE',
    defaultValue: false,
  );

  /// Lifts screenshot / recording protection (FLAG_SECURE, the background
  /// privacy cover and the iOS secure image layer) for a QA recording.
  static const bool allowQaScreenCapture =
      !kReleaseMode && _qaScreenCaptureRequested;

  static const String _androidAppCheckDebugTokenRaw = String.fromEnvironment(
    'APP_CHECK_ANDROID_DEBUG_TOKEN',
    defaultValue: '',
  );

  /// A registered App Check debug token is a credential: anyone who extracts
  /// it can mint App Check tokens for the project. It is never compiled into
  /// a release binary.
  static const String androidAppCheckDebugToken = kReleaseMode
      ? ''
      : _androidAppCheckDebugTokenRaw;

  static const String _webAppCheckDebugTokenRaw = String.fromEnvironment(
    'APP_CHECK_WEB_DEBUG_TOKEN',
    defaultValue: '',
  );

  /// See [androidAppCheckDebugToken].
  static const String webAppCheckDebugToken = kReleaseMode
      ? ''
      : _webAppCheckDebugTokenRaw;
}
