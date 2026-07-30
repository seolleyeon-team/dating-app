import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('FlutterFire Android app id matches the Android application id', () {
    final buildGradle = File('android/app/build.gradle.kts').readAsStringSync();
    final applicationId = RegExp(
      r'applicationId\s*=\s*"([^"]+)"',
    ).firstMatch(buildGradle)?.group(1);
    expect(applicationId, isNotNull);

    final googleServices =
        jsonDecode(File('android/app/google-services.json').readAsStringSync())
            as Map<String, dynamic>;
    final clients = googleServices['client'] as List<dynamic>;
    final matchingClient = clients.cast<Map<String, dynamic>>().firstWhere(
      (client) =>
          ((client['client_info']
                  as Map<String, dynamic>)['android_client_info']
              as Map<String, dynamic>)['package_name'] ==
          applicationId,
    );
    final expectedAppId =
        (matchingClient['client_info']
                as Map<String, dynamic>)['mobilesdk_app_id']
            as String;

    final firebaseOptions = File(
      'lib/firebase_options.dart',
    ).readAsStringSync();
    final firebaseJson = File('firebase.json').readAsStringSync();

    expect(firebaseOptions, contains("appId: '$expectedAppId'"));
    expect(firebaseJson, contains('"appId": "$expectedAppId"'));
  });
}
