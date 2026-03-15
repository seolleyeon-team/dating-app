import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:firebase_core/firebase_core.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'services/push_notification_service.dart';
import 'firebase_options.dart';
import 'app.dart';

void main() {
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();

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
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      runApp(const SeolleyeonApp());
    },
    (error, stack) {
      print('[GLOBAL] Uncaught error: $error\n$stack');
    },
  );
}
