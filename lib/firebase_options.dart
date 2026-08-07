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

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyCXdft1O8zRTn48Jkwzl9PBN7Xb0pcsScs',
    appId: '1:810450765203:android:81ca13cb23027d875c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyDSBDbN6inF09enjKz946oZOX3rJ0tdAW0',
    appId: '1:810450765203:ios:7e51bb82970a77145c9466',
    messagingSenderId: '810450765203',
    projectId: 'seolleyeon-final',
    storageBucket: 'seolleyeon-final.firebasestorage.app',
    iosBundleId: 'com.yonsei.dating',
  );
}
