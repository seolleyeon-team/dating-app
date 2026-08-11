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
import 'services/firebase_diagnostics.dart';
import 'services/push_notification_service.dart';
import 'services/app_check_bootstrap.dart';
import 'shared/utils/app_check_provider_policy.dart';
import 'services/windows_protocol_registration_stub.dart'
    if (dart.library.io) 'services/windows_protocol_registration_io.dart';
import 'services/app_check_web_storage_stub.dart'
    if (dart.library.html) 'services/app_check_web_storage_impl.dart';
import 'firebase_options.dart';
import 'app.dart';
import 'webview_web_stub.dart'
    if (dart.library.html) 'webview_web_impl.dart'
    as webview_web;

/// `true`이면 **release APK/AAB**에서도 Debug App Check provider 사용 (콘솔 디버그 토큰).
/// 로컬에 release 설치해 테스트할 때 Play Integrity 403 방지용.
/// 스토어 배포 빌드에서는 이 플래그를 켜지 말 것 (Play Integrity / App Attest 사용).
const bool _forceAppCheckDebugProvider = bool.fromEnvironment(
  'FORCE_APP_CHECK_DEBUG',
  defaultValue: false,
);
const String _webAppCheckRecaptchaSiteKey = String.fromEnvironment(
  'APP_CHECK_WEB_RECAPTCHA_SITE_KEY',
  defaultValue: '',
);
const String _webAppCheckDebugToken = String.fromEnvironment(
  'APP_CHECK_WEB_DEBUG_TOKEN',
  defaultValue: '',
);
const String _androidAppCheckDebugToken = String.fromEnvironment(
  'APP_CHECK_ANDROID_DEBUG_TOKEN',
  defaultValue: '',
);

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

      if (kIsWeb) {
        clearStoredWebAppCheckProvider();
      }

      // ✅ Firebase init
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      FirebaseDiagnostics.logCurrentFirebaseApp('firebase_initialize_success');

      // App Check: Android/iOS always. Web uses reCAPTCHA v3 normally, with
      // an explicit debug-provider escape hatch for local Chrome testing.
      // Callable functions enforce App Check, so either provider must be
      // registered in Firebase Console before login can succeed.
      var usedDebugAppCheckProvider = false;
      try {
        if (kIsWeb) {
          if (_forceAppCheckDebugProvider) {
            usedDebugAppCheckProvider = true;
            final debugToken = _webAppCheckDebugToken.trim();
            await FirebaseAppCheck.instance.activate(
              providerWeb: WebDebugProvider(
                debugToken: debugToken.isEmpty ? null : debugToken,
              ),
            );
            await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
            debugPrint(
              '[AppCheck] web debug provider activated; '
              'register the browser debug token in Firebase Console',
            );
            recordAppCheckInitResult(
              const AppCheckInitResult(
                status: AppCheckInitStatus.activated,
                usedDebugProvider: true,
                platform: 'web',
              ),
            );
          } else {
            final siteKey = webAppCheckRecaptchaSiteKey(
              fromEnvironment: _webAppCheckRecaptchaSiteKey,
            );
            if (siteKey != null) {
              await FirebaseAppCheck.instance.activate(
                providerWeb: ReCaptchaV3Provider(siteKey),
              );
              await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
              debugPrint('[AppCheck] web reCAPTCHA v3 provider activated');
              recordAppCheckInitResult(
                evaluateWebAppCheckActivation(siteKey: siteKey),
              );
            } else {
              debugPrint(
                '[AppCheck] web skipped: APP_CHECK_WEB_RECAPTCHA_SITE_KEY unset',
              );
              recordAppCheckInitResult(
                evaluateWebAppCheckActivation(siteKey: null),
              );
            }
          }
        } else {
          final useDebugAppCheck = shouldUseDebugAppCheckProvider(
            isWeb: false,
            isReleaseMode: kReleaseMode,
            forceDebugProvider: _forceAppCheckDebugProvider,
          );
          usedDebugAppCheckProvider = useDebugAppCheck;
          final androidDebugToken = androidAppCheckDebugToken(
            fromEnvironment: _androidAppCheckDebugToken,
          );
          await FirebaseAppCheck.instance.activate(
            providerAndroid: useDebugAppCheck
                ? AndroidDebugProvider(debugToken: androidDebugToken)
                : const AndroidPlayIntegrityProvider(),
            providerApple: useDebugAppCheck
                ? const AppleDebugProvider()
                : const AppleAppAttestProvider(),
          );
          await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
          debugPrint(
            '[AppCheck] debugProviders=$useDebugAppCheck '
            'kReleaseMode=$kReleaseMode forceDebug=$_forceAppCheckDebugProvider',
          );
          recordAppCheckInitResult(
            evaluateNativeAppCheckActivation(
              usedDebugProvider: useDebugAppCheck,
              platform: defaultTargetPlatform == TargetPlatform.iOS
                  ? 'ios'
                  : 'android',
            ),
          );
        }
      } catch (e) {
        recordAppCheckInitResult(
          AppCheckInitResult(
            status: AppCheckInitStatus.failed,
            usedDebugProvider: usedDebugAppCheckProvider,
            platform: kIsWeb
                ? 'web'
                : defaultTargetPlatform == TargetPlatform.iOS
                ? 'ios'
                : 'android',
            errorSummary: summarizeAppCheckError(e),
          ),
        );
        debugPrint(
          '[AppCheck] activate failed: ${PrivacyLogUtils.errorSummary(e)}',
        );
      }

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
