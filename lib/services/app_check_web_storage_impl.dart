// The package is supplied transitively by the Flutter web plugin stack.
// ignore: depend_on_referenced_packages
import 'package:web/web.dart' as web;

const _appCheckProviderStorageKeys = <String>[
  'FlutterFire-[DEFAULT]-recaptchaType',
  'FlutterFire-[DEFAULT]-recaptchaSiteKey',
];

/// Removes FlutterFire's persisted web provider selection.
///
/// firebase_app_check_web restores the last provider before the app can select
/// a new one. Clearing these two keys lets local debug and reCAPTCHA providers
/// be switched deterministically between full app launches.
void clearStoredWebAppCheckProvider() {
  for (final key in _appCheckProviderStorageKeys) {
    try {
      web.window.localStorage.removeItem(key);
    } catch (_) {
      // Storage may be unavailable in privacy-restricted browser contexts.
    }
    try {
      web.window.sessionStorage.removeItem(key);
    } catch (_) {
      // Storage may be unavailable in privacy-restricted browser contexts.
    }
  }
}
