bool shouldUseDebugAppCheckProvider({
  required bool isWeb,
  required bool isReleaseMode,
}) {
  if (isWeb) return false;
  return !isReleaseMode;
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
