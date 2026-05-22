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

  // Note: Web configuration is incomplete (appId is placeholder)

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyDWzBTro7NNlvq4ufdvQm6hDwxrBX_Dc_I',
    appId: '1:623093454373:web:57be6c4135b9027b0251cc',
    messagingSenderId: '623093454373',
    projectId: 'seolleyeon',
    authDomain: 'seolleyeon.firebaseapp.com',
    storageBucket: 'seolleyeon.firebasestorage.app',
    measurementId: 'G-ZFTMMQTHQP',
  );

  // To use Web, configure Firebase Web app in Firebase Console and update this

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