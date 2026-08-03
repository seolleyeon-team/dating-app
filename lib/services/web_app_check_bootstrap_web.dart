import 'dart:js_interop';
import 'dart:js_interop_unsafe';

const _recaptchaTypeKey = 'FlutterFire-[DEFAULT]-recaptchaType';
const _recaptchaSiteKey = 'FlutterFire-[DEFAULT]-recaptchaSiteKey';

bool primeWebAppCheckDebugProvider(String debugToken) {
  final normalizedToken = debugToken.trim();
  if (normalizedToken.isEmpty) return false;

  try {
    globalContext.setProperty(
      'FIREBASE_APPCHECK_DEBUG_TOKEN'.toJS,
      normalizedToken.toJS,
    );
    _setStorageValue('localStorage', _recaptchaTypeKey, 'debug');
    _setStorageValue('localStorage', _recaptchaSiteKey, normalizedToken);
    _setStorageValue('sessionStorage', _recaptchaTypeKey, 'debug');
    _setStorageValue('sessionStorage', _recaptchaSiteKey, normalizedToken);
    return true;
  } catch (_) {
    return false;
  }
}

void _setStorageValue(String storageName, String key, String value) {
  final storage = globalContext.getProperty<JSObject>(storageName.toJS);
  storage.callMethod<JSAny?>('setItem'.toJS, key.toJS, value.toJS);
}
