// Pure App Check bootstrap policy (unit-testable, no FlutterFire imports).

enum AppCheckInitStatus {
  activated,
  skippedWebMissingKey,
  failed,
  unsupportedPlatform,
}

class AppCheckInitResult {
  const AppCheckInitResult({
    required this.status,
    required this.usedDebugProvider,
    this.platform = '',
    this.errorSummary,
  });

  final AppCheckInitStatus status;
  final bool usedDebugProvider;
  final String platform;
  final String? errorSummary;

  bool get isReady => status == AppCheckInitStatus.activated;

  /// Callables that enforce App Check will fail without a token.
  bool get callablesLikelyBlocked =>
      status == AppCheckInitStatus.failed ||
      status == AppCheckInitStatus.skippedWebMissingKey;
}

bool shouldUseDebugAppCheckProvider({
  required bool isWeb,
  required bool isReleaseMode,
  bool forceDebugProvider = false,
  bool isDebugSignedAndroid = false,
}) {
  if (isWeb) return false;
  // Store/release builds must never use debug providers unless an explicit
  // local-test dart-define is set (FORCE_APP_CHECK_DEBUG). Play/store pipelines
  // must not pass that define.
  if (forceDebugProvider) return true;
  if (!isReleaseMode) return true;
  return isDebugSignedAndroid;
}

/// reCAPTCHA v3 site key for Flutter web App Check.
///
/// Callable functions now set `enforceAppCheck: true`. Web builds must activate
/// App Check with this key or login/bootstrap callables will be rejected.
/// Pass via `--dart-define=APP_CHECK_WEB_RECAPTCHA_SITE_KEY=...`.
String? webAppCheckRecaptchaSiteKey({String? fromEnvironment}) {
  final key = (fromEnvironment ?? '').trim();
  return key.isEmpty ? null : key;
}

AppCheckInitResult evaluateWebAppCheckActivation({
  required String? siteKey,
  String? activateErrorSummary,
}) {
  if (siteKey == null) {
    return const AppCheckInitResult(
      status: AppCheckInitStatus.skippedWebMissingKey,
      usedDebugProvider: false,
      platform: 'web',
      errorSummary: 'APP_CHECK_WEB_RECAPTCHA_SITE_KEY unset',
    );
  }
  if (activateErrorSummary != null && activateErrorSummary.isNotEmpty) {
    return AppCheckInitResult(
      status: AppCheckInitStatus.failed,
      usedDebugProvider: false,
      platform: 'web',
      errorSummary: activateErrorSummary,
    );
  }
  return const AppCheckInitResult(
    status: AppCheckInitStatus.activated,
    usedDebugProvider: false,
    platform: 'web',
  );
}

AppCheckInitResult evaluateNativeAppCheckActivation({
  required bool usedDebugProvider,
  required String platform,
  String? activateErrorSummary,
}) {
  if (activateErrorSummary != null && activateErrorSummary.isNotEmpty) {
    return AppCheckInitResult(
      status: AppCheckInitStatus.failed,
      usedDebugProvider: usedDebugProvider,
      platform: platform,
      errorSummary: activateErrorSummary,
    );
  }
  return AppCheckInitResult(
    status: AppCheckInitStatus.activated,
    usedDebugProvider: usedDebugProvider,
    platform: platform,
  );
}
