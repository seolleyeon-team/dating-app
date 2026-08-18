import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart'
    show
        TargetPlatform,
        debugPrint,
        defaultTargetPlatform,
        kDebugMode,
        kIsWeb,
        kReleaseMode;
import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';
import 'services/firebase_diagnostics.dart';
import 'services/firebase_runtime.dart';
import 'services/push_notification_service.dart';
import 'features/shop/services/iap_service.dart';
import 'shared/utils/app_check_provider_policy.dart';
import 'services/web_app_check_bootstrap_stub.dart'
    if (dart.library.html) 'services/web_app_check_bootstrap_web.dart'
    as web_app_check_bootstrap;
import 'services/windows_protocol_registration_stub.dart'
    if (dart.library.io) 'services/windows_protocol_registration_io.dart';
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
const bool _useFirebaseEmulators = bool.fromEnvironment(
  'USE_FIREBASE_EMULATORS',
  defaultValue: false,
);

// Simulator는 기본값(127.0.0.1)을 쓰고, USB/Wi-Fi 실기기 테스트에서는
// Mac의 LAN IP를 --dart-define=FIREBASE_EMULATOR_HOST=... 로 넘긴다.
const String _firebaseEmulatorHost = String.fromEnvironment(
  'FIREBASE_EMULATOR_HOST',
  defaultValue: '127.0.0.1',
);
const MethodChannel _kakaoUtilChannel = MethodChannel(
  'com.seolleyeon.app/kakao_util',
);

Future<bool> _shouldUseDebugAppCheckProvider() async {
  if (kIsWeb) return false;
  if (!kReleaseMode || _forceAppCheckDebugProvider) return true;
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
    return isDebugSigned;
  } catch (e) {
    debugPrint(
      '[AppCheck] debug-signing check failed: ${PrivacyLogUtils.errorSummary(e)}',
    );
    return false;
  }
}

Future<void> _configureFirebaseEmulators() async {
  // StoreKit Local Testing receipt은 운영 Apple 서버에서 검증할 수 없으므로,
  // emulator + IAP_VERIFICATION_MODE=storekit_local 조합만 허용한다.
  if (!_useFirebaseEmulators || kReleaseMode) return;

  FirebaseAuth.instance.useAuthEmulator(_firebaseEmulatorHost, 9099);
  FirebaseFirestore.instance.useFirestoreEmulator(_firebaseEmulatorHost, 8080);
  FirebaseFunctions.instance.useFunctionsEmulator(_firebaseEmulatorHost, 5001);
  FirebaseFunctions.instanceFor(
    region: firebaseFunctionsRegion,
  ).useFunctionsEmulator(_firebaseEmulatorHost, 5001);
  debugPrint(
    '[Firebase] Using local Auth/Firestore/Functions emulators '
    'host=$_firebaseEmulatorHost',
  );
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

      final useLocalWebDebugProvider =
          kIsWeb &&
          shouldUseWebDebugAppCheckProvider(
            isDebugMode: kDebugMode,
            host: Uri.base.host,
          );
      final webDebugToken = _webAppCheckDebugToken.trim();
      if (useLocalWebDebugProvider && webDebugToken.isNotEmpty) {
        final primed = web_app_check_bootstrap.primeWebAppCheckDebugProvider(
          webDebugToken,
        );
        debugPrint(
          '[AppCheck] web debug provider primed before Firebase init: '
          'success=$primed.',
        );
      }

      // ✅ Firebase init
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      await _configureFirebaseEmulators();
      FirebaseDiagnostics.logCurrentFirebaseApp('firebase_initialize_success');

      // 화면 수명과 분리해 앱 재실행 때 StoreKit의 미완료 transaction도 처리한다.
      // 서비스 내부에서 iOS가 아닌 플랫폼은 아무 StoreKit 호출도 하지 않는다.
      unawaited(IapService.instance.initialize());

      // App Check: local web debug builds use a console-registered debug token;
      // deployed web builds require the configured reCAPTCHA v3 provider.
      try {
        if (kIsWeb) {
          if (useLocalWebDebugProvider) {
            await FirebaseAppCheck.instance.activate(
              providerWeb: webDebugToken.isEmpty
                  ? WebDebugProvider()
                  : WebDebugProvider(debugToken: webDebugToken),
            );
            await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
            debugPrint(
              '[AppCheck] web debug provider activated for localhost; '
              'stableTokenConfigured=${webDebugToken.isNotEmpty}.',
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
            } else {
              debugPrint(
                '[AppCheck] web skipped: '
                'APP_CHECK_WEB_RECAPTCHA_SITE_KEY unset',
              );
            }
          }
        } else {
          final useDebugAppCheck = await _shouldUseDebugAppCheckProvider();
          await FirebaseAppCheck.instance.activate(
            providerAndroid: useDebugAppCheck
                ? const AndroidDebugProvider()
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
        }
      } catch (e) {
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
