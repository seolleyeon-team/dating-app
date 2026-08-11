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
  // Kept as a source-compatible parameter for existing callers. A release
  // signing certificate must never implicitly select the debug provider.
  bool isDebugSignedAndroid = false,
}) {
  if (isWeb) return false;
  // Store/release builds must never use debug providers unless an explicit
  // local-test dart-define is set (FORCE_APP_CHECK_DEBUG). Play/store pipelines
  // must not pass that define.
  if (forceDebugProvider) return true;
  return !isReleaseMode;
}

/// Resolves the optional local Android debug token without ever providing a
/// value to a release provider branch.
String? androidAppCheckDebugToken({String? fromEnvironment}) {
  final token = (fromEnvironment ?? '').trim();
  return token.isEmpty ? null : token;
}

/// Web debug builds running on a loopback host use Firebase's Debug Provider.
/// This keeps callable App Check enforcement on while avoiding reCAPTCHA in
/// local development. Deployed web builds always use the configured provider.
bool shouldUseWebDebugAppCheckProvider({
  required bool isDebugMode,
  required String host,
}) {
  if (!isDebugMode) return false;

  final normalizedHost = host.trim().toLowerCase();
  return normalizedHost == 'localhost' ||
      normalizedHost == '127.0.0.1' ||
      normalizedHost == '::1';
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
