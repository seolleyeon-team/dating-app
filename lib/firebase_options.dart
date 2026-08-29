// File generated using Firebase configuration from google-services.json

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Default [FirebaseOptions] for use with your Firebase apps.
///
/// Example:
/// ```dart
/// import 'firebase_options.dart';
/// // ...
/// await Firebase.initializeApp(
///   options: DefaultFirebaseOptions.currentPlatform,
/// );
/// ```
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for macos - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      case TargetPlatform.windows:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for windows - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      case TargetPlatform.linux:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for linux - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyAQseKwnuvNvx7gSyfdw-SgAAYDHcClJL8',
    appId: '1:810450765203:web:70f46fa58d6133f35c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    authDomain: 'seolleyeon-final.firebaseapp.com',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
    measurementId: 'G-17X0QMS7ZH',
  );

  /// 빌드된 flavor 이름. `--flavor` 를 주면 Flutter 가 자동으로 넣어준다.
  ///
  /// Android 는 flavor 마다 applicationId 가 다르고, 패키지마다 별도의 Firebase
  /// 앱이 등록돼 있다. 여기서 flavor 를 보지 않으면 production 번들이 staging
  /// Firebase 앱으로 초기화된다.
  static const String appFlavor = String.fromEnvironment('FLUTTER_APP_FLAVOR');

  /// Android 는 flavor 에 따라 서로 다른 Firebase 앱을 쓴다.
  static FirebaseOptions get android =>
      appFlavor == 'staging' ? androidStaging : androidProduction;

  /// Google Play 에 등록된 실제 앱 (com.seolleyeon.app).
  static const FirebaseOptions androidProduction = FirebaseOptions(
    apiKey: 'AIzaSyCXdft1O8zRTn48Jkwzl9PBN7Xb0pcsScs',
    appId: '1:810450765203:android:685c8e050fcac6b55c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
  );

  /// 개발/검증용 (com.yonsei.dating). Play 에 올리지 않는다.
  static const FirebaseOptions androidStaging = FirebaseOptions(
    apiKey: 'AIzaSyCXdft1O8zRTn48Jkwzl9PBN7Xb0pcsScs',
    appId: '1:810450765203:android:81ca13cb23027d875c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyDSBDbN6inF09enjKz946oZOX3rJ0tdAW0',
    appId: '1:810450765203:ios:fddeea51ac71dc4e5c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
    iosBundleId: 'com.seolleyeon.app',
  );
}
