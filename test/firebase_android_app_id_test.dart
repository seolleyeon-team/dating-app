import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Android production/staging flavor는 같은 운영 패키지와 Firebase 앱을 사용한다.
///
///   production : com.seolleyeon.app  — Google Play/TestFlight 운영 앱
///   staging    : com.seolleyeon.app  — 기존 개발 명령 호환용 flavor
///
/// 두 flavor를 서로 다른 Firebase 앱으로 연결하면 로그인·FCM·App Check가
/// 잘못된 앱 신원으로 동작한다. 이 테스트는 운영 앱 하나만 쓰는지 확인한다.
void main() {
  final buildGradle = File('android/app/build.gradle.kts').readAsStringSync();
  final googleServices =
      jsonDecode(File('android/app/google-services.json').readAsStringSync())
          as Map<String, dynamic>;
  final clients = (googleServices['client'] as List<dynamic>)
      .cast<Map<String, dynamic>>();

  String? appIdFor(String packageName) {
    for (final client in clients) {
      final info = client['client_info'] as Map<String, dynamic>;
      final android = info['android_client_info'] as Map<String, dynamic>;
      if (android['package_name'] == packageName) {
        return info['mobilesdk_app_id'] as String;
      }
    }
    return null;
  }

  String? flavorApplicationId(String flavor) {
    final block = RegExp(
      'create\\("$flavor"\\)\\s*\\{(.*?)\\n        \\}',
      dotAll: true,
    ).firstMatch(buildGradle)?.group(1);
    if (block == null) return null;
    return RegExp(r'applicationId\s*=\s*"([^"]+)"').firstMatch(block)?.group(1);
  }

  test('production flavor targets the Play package', () {
    expect(flavorApplicationId('production'), 'com.seolleyeon.app');
  });

  test('staging flavor shares the production package', () {
    expect(flavorApplicationId('staging'), 'com.seolleyeon.app');
    expect(flavorApplicationId('staging'), flavorApplicationId('production'));
  });

  test('a build without a flavor cannot inherit a package', () {
    // defaultConfig 에 applicationId 가 남아 있으면 flavor 를 빼먹은 빌드가
    // 조용히 그 패키지로 나간다.
    final defaultConfig = RegExp(
      r'defaultConfig\s*\{(.*?)\n    \}',
      dotAll: true,
    ).firstMatch(buildGradle)?.group(1);
    expect(defaultConfig, isNotNull);
    final withoutComments = defaultConfig!.replaceAll(RegExp(r'//[^\n]*'), '');
    expect(withoutComments, isNot(contains('applicationId')));
  });

  test('google-services.json carries only the production package', () {
    expect(appIdFor('com.seolleyeon.app'), isNotNull);
    expect(
      clients
          .map(
            (client) =>
                (client['client_info']
                        as Map<String, dynamic>)['android_client_info']
                    as Map<String, dynamic>,
          )
          .map((info) => info['package_name'])
          .toSet(),
      {'com.seolleyeon.app'},
    );
  });

  test('FlutterFire options use the shared production Firebase app', () {
    final firebaseOptions = File(
      'lib/firebase_options.dart',
    ).readAsStringSync();

    final productionAppId = appIdFor('com.seolleyeon.app')!;
    expect(firebaseOptions, contains("appId: '$productionAppId'"));
    expect(firebaseOptions, contains('androidProduction'));
    expect(firebaseOptions, isNot(contains('androidStaging')));
  });

  test('FlutterFire config defaults to the production Android app', () {
    final firebaseJson = File('firebase.json').readAsStringSync();
    final productionAppId = appIdFor('com.seolleyeon.app')!;

    // 여기가 staging 을 가리키면 flutterfire configure 를 다시 돌렸을 때
    // production 설정이 조용히 staging 으로 되돌아간다.
    expect(firebaseJson, contains('"appId": "$productionAppId"'));
  });
}
