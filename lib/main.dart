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
import 'package:firebase_core/firebase_core.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'core/error/crash_reporting.dart';
import 'services/firebase_diagnostics.dart';
import 'services/firebase_emulator_config.dart';
import 'services/push_notification_service.dart';
import 'services/app_check_bootstrap.dart';
import 'features/shop/services/iap_service.dart';
import 'shared/utils/app_check_provider_policy.dart';
import 'shared/utils/release_build_guards.dart';
import 'services/windows_protocol_registration_stub.dart'
    if (dart.library.io) 'services/windows_protocol_registration_io.dart';
import 'services/app_check_web_storage_stub.dart'
    if (dart.library.html) 'services/app_check_web_storage_impl.dart';
import 'services/web_app_check_bootstrap_stub.dart'
    if (dart.library.html) 'services/web_app_check_bootstrap_web.dart'
    as web_app_check_bootstrap;
import 'firebase_options.dart';
import 'app.dart';
import 'webview_web_stub.dart'
    if (dart.library.html) 'webview_web_impl.dart'
    as webview_web;

// Debug / QA dart-defines (FORCE_APP_CHECK_DEBUG, APP_CHECK_DIAGNOSTIC_MODE,
// the App Check debug tokens) are read ONLY through ReleaseBuildGuards: a
// release build ignores them, so a store-signed binary always uses Play
// Integrity / App Attest and never carries a debug token.
const bool _forceAppCheckDebugProvider =
    ReleaseBuildGuards.forceAppCheckDebugProvider;
const String _webAppCheckRecaptchaSiteKey = String.fromEnvironment(
  'APP_CHECK_WEB_RECAPTCHA_SITE_KEY',
  defaultValue: '',
);
const String _webAppCheckDebugToken = ReleaseBuildGuards.webAppCheckDebugToken;
const String _androidAppCheckDebugToken =
    ReleaseBuildGuards.androidAppCheckDebugToken;

/// Debug/profile-only switch for isolating a single App Check token request.
const bool _appCheckDiagnosticMode = ReleaseBuildGuards.appCheckDiagnosticMode;

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
      if (kIsWeb) {
        clearStoredWebAppCheckProvider();
      }
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
      // StoreKit Local Testing receipt은 운영 Apple 서버에서 검증할 수 없으므로,
      // emulator + IAP_VERIFICATION_MODE=storekit_local 조합만 허용한다.
      // Auth, Firestore, Functions and Storage are routed together or not at
      // all, and never in a release build. A partial routing throws, which
      // stops start-up instead of running half against production.
      await configureFirebaseEmulators(
        requested: _useFirebaseEmulators,
        isReleaseBuild: kReleaseMode,
        host: _firebaseEmulatorHost,
      );
      FirebaseDiagnostics.logCurrentFirebaseApp('firebase_initialize_success');

      // P1-6: crash reporting — FlutterError.onError, PlatformDispatcher
      // onError and the root zone below all report through one facade that
      // strips raw messages (privacy) and deduplicates. Collection is on for
      // release builds on Android/iOS only.
      await CrashReporting.instance.install();

      // App Check: Android/iOS always. Web uses reCAPTCHA v3 normally, with
      // an explicit debug-provider escape hatch for local Chrome testing.
      // Callable functions enforce App Check, so either provider must be
      // registered in Firebase Console before login can succeed.
      var usedDebugAppCheckProvider = false;
      try {
        if (kIsWeb) {
          final useWebDebugProvider =
              useLocalWebDebugProvider ||
              (_forceAppCheckDebugProvider &&
                  shouldUseWebDebugAppCheckProvider(
                    isDebugMode: !kReleaseMode,
                    host: Uri.base.host,
                  ));
          if (useWebDebugProvider) {
            usedDebugAppCheckProvider = true;
            await FirebaseAppCheck.instance.activate(
              providerWeb: WebDebugProvider(
                debugToken: webDebugToken.isEmpty ? null : webDebugToken,
              ),
            );
            await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(true);
            debugPrint(
              '[AppCheck] web debug provider activated for localhost; '
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
          await FirebaseAppCheck.instance.setTokenAutoRefreshEnabled(
            !_appCheckDiagnosticMode,
          );
          debugPrint(
            '[AppCheck] debugProviders=$useDebugAppCheck '
            'kReleaseMode=$kReleaseMode forceDebug=$_forceAppCheckDebugProvider '
            'diagnostic=$_appCheckDiagnosticMode',
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

      // Subscribe only after App Check activation so unfinished purchases can
      // reach the protected grant callable on their first redelivery.
      unawaited(IapService.instance.initialize());

      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      runApp(const SeolleyeonApp());
    },
    (error, stack) {
      debugPrint(
        '[GLOBAL] Uncaught error: ${PrivacyLogUtils.errorSummary(error)}',
      );
      // Before Firebase is initialised this only prints; afterwards it is
      // uploaded once as a fatal error.
      CrashReporting.instance.recordZoneError(error, stack);
    },
  );
}
