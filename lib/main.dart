import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart'
    show
        TargetPlatform,
        debugPrint,
        defaultTargetPlatform,
        kIsWeb,
        kReleaseMode;
import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';
import 'services/firebase_diagnostics.dart';
import 'services/push_notification_service.dart';
import 'services/app_check_bootstrap.dart';
import 'shared/utils/app_check_provider_policy.dart';
import 'services/windows_protocol_registration_stub.dart'
    if (dart.library.io) 'services/windows_protocol_registration_io.dart';
import 'firebase_options.dart';
import 'app.dart';
import 'webview_web_stub.dart'
    if (dart.library.html) 'webview_web_impl.dart'
    as webview_web;

/// `true`이면 **local release APK/AAB**에서도 Debug App Check provider 사용.
/// 스토어 배포 빌드에서는 이 플래그를 켜지 말 것.
const bool _forceAppCheckDebugProvider = bool.fromEnvironment(
  'FORCE_APP_CHECK_DEBUG',
  defaultValue: false,
);
const String _webAppCheckRecaptchaSiteKey = String.fromEnvironment(
  'APP_CHECK_WEB_RECAPTCHA_SITE_KEY',
  defaultValue: '',
);
const MethodChannel _kakaoUtilChannel = MethodChannel(
  'com.yonsei.dating/kakao_util',
);

Future<bool> _shouldUseDebugAppCheckProvider() async {
  if (kIsWeb) return false;
  if (_forceAppCheckDebugProvider) return true;
  if (!kReleaseMode) return true;
  if (defaultTargetPlatform != TargetPlatform.android) return false;

  try {
    final isDebugSigned =
        await _kakaoUtilChannel.invokeMethod<bool>('isDebugSigned') ?? false;
    if (isDebugSigned) {
      debugPrint(
        '[AppCheck] Android app is signed with the debug certificate; '
        'using debug provider.',
      );
    }
    return shouldUseDebugAppCheckProvider(
      isWeb: false,
      isReleaseMode: true,
      isDebugSignedAndroid: isDebugSigned,
    );
  } catch (e) {
    debugPrint(
      '[AppCheck] debug-signing check failed: ${PrivacyLogUtils.errorSummary(e)}',
    );
    return false;
  }
}

Future<void> _activateAppCheck() async {
  if (kIsWeb) {
    final siteKey = webAppCheckRecaptchaSiteKey(
      fromEnvironment: _webAppCheckRecaptchaSiteKey,
    );
    if (siteKey == null) {
      final result = evaluateWebAppCheckActivation(siteKey: null);
      recordAppCheckInitResult(result);
      debugPrint(
        '[AppCheck] web skipped: APP_CHECK_WEB_RECAPTCHA_SITE_KEY unset',
      );
      return;
    }
    try {
      await FirebaseAppCheck.instance.activate(
        providerWeb: ReCaptchaV3Provider(siteKey),
      );
      await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
      recordAppCheckInitResult(evaluateWebAppCheckActivation(siteKey: siteKey));
      debugPrint('[AppCheck] web reCAPTCHA v3 provider activated');
    } catch (e) {
      final summary = summarizeAppCheckError(e);
      recordAppCheckInitResult(
        evaluateWebAppCheckActivation(
          siteKey: siteKey,
          activateErrorSummary: summary,
        ),
      );
      debugPrint('[AppCheck] activate failed: $summary');
      // Keep running so UI can surface a recoverable App Check error.
    }
    return;
  }

  final useDebugAppCheck = await _shouldUseDebugAppCheckProvider();
  final platform = defaultTargetPlatform.name;
  try {
    await FirebaseAppCheck.instance.activate(
      providerAndroid: useDebugAppCheck
          ? const AndroidDebugProvider()
          : const AndroidPlayIntegrityProvider(),
      providerApple: useDebugAppCheck
          ? const AppleDebugProvider()
          : const AppleAppAttestProvider(),
    );
    await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
    recordAppCheckInitResult(
      evaluateNativeAppCheckActivation(
        usedDebugProvider: useDebugAppCheck,
        platform: platform,
      ),
    );
    debugPrint(
      '[AppCheck] debugProviders=$useDebugAppCheck '
      'kReleaseMode=$kReleaseMode forceDebug=$_forceAppCheckDebugProvider',
    );
  } catch (e) {
    final summary = summarizeAppCheckError(e);
    recordAppCheckInitResult(
      evaluateNativeAppCheckActivation(
        usedDebugProvider: useDebugAppCheck,
        platform: platform,
        activateErrorSummary: summary,
      ),
    );
    debugPrint('[AppCheck] activate failed: $summary');
    // Do not swallow: callable Auth/bootstrap will fail closed with App Check.
    // Keep the app running so UI can show a recoverable error state.
  }
}

void main() {
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();
      await ensureWindowsProtocolRegistration();

      // ✅ WebView 웹 플랫폼 등록 (웹 빌드 시에만)
      webview_web.registerWebViewWebPlatform();

      // ✅ Kakao init
      const kakaoNativeAppKey = 'cb08e2aea50a58b7d0c5e610e0c5a644';
      const kakaoJavaScriptKey = 'bff1db6356fcd7aaf5dc466080359ce0';

      KakaoSdk.init(
        nativeAppKey: kIsWeb ? null : kakaoNativeAppKey,
        javaScriptAppKey: kIsWeb ? kakaoJavaScriptKey : null,
      );

      // ✅ Firebase init
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      FirebaseDiagnostics.logCurrentFirebaseApp('firebase_initialize_success');

      // App Check: Android/iOS always; web when a reCAPTCHA v3 site key is
      // supplied. Callable functions enforce App Check, so web login requires
      // `--dart-define=APP_CHECK_WEB_RECAPTCHA_SITE_KEY=...`.
      await _activateAppCheck();

      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      runApp(const SeolleyeonApp());
    },
    (error, stack) {
      debugPrint(
        '[GLOBAL] Uncaught error: ${PrivacyLogUtils.errorSummary(error)}',
      );
    },
  );
}
