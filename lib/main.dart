import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show debugPrint, kIsWeb, kReleaseMode;
import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'services/push_notification_service.dart';
import 'firebase_options.dart';
import 'app.dart';
import 'webview_web_stub.dart'
    if (dart.library.html) 'webview_web_impl.dart' as webview_web;

/// `true`이면 **release APK/AAB**에서도 Debug App Check provider 사용 (콘솔 디버그 토큰).
/// 로컬에 release 설치해 테스트할 때 Play Integrity 403 방지용.
/// 스토어 배포 빌드에서는 이 플래그를 켜지 말 것 (Play Integrity / App Attest 사용).
const bool _forceAppCheckDebugProvider =
    bool.fromEnvironment('FORCE_APP_CHECK_DEBUG', defaultValue: false);

void main() {
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();

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

      // App Check: Android/iOS 항상 활성화.
      // - 일반 debug/profile: Debug provider (!kReleaseMode)
      // - release: Play Integrity / App Attest — 로컬 release만 쓸 때는 403 나므로
      //   `flutter run --dart-define=FORCE_APP_CHECK_DEBUG=true` 또는 APK 빌드에 동일 define 추가
      if (!kIsWeb) {
        try {
          final useDebugAppCheck =
              !kReleaseMode || _forceAppCheckDebugProvider;
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
        } catch (e, st) {
          debugPrint('[AppCheck] activate failed: $e\n$st');
        }
      }

      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      runApp(const SeolleyeonApp());
    },
    (error, stack) {
      debugPrint('[GLOBAL] Uncaught error: $error\n$stack');
    },
  );
}
