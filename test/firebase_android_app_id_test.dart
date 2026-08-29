import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Android 는 flavor 마다 applicationId 가 다르고, 패키지마다 별도의 Firebase
/// 앱이 등록돼 있다.
///
///   production : com.seolleyeon.app  — Google Play 에 등록된 실제 앱
///   staging    : com.yonsei.dating   — 개발/검증용
///
/// 두 축이 어긋나면 production 번들이 staging Firebase 앱으로 초기화되고,
/// 로그인·FCM·App Check 가 잘못된 앱 신원으로 동작한다. 빌드는 그대로
/// 성공하기 때문에 배포 전에는 드러나지 않는다.
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

  test('staging flavor keeps its own package', () {
    expect(flavorApplicationId('staging'), 'com.yonsei.dating');
    expect(
      flavorApplicationId('staging'),
      isNot(flavorApplicationId('production')),
    );
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

  test('google-services.json carries both packages', () {
    expect(appIdFor('com.seolleyeon.app'), isNotNull);
    expect(appIdFor('com.yonsei.dating'), isNotNull);
  });

  test('FlutterFire options map each flavor to its own Firebase app', () {
    final firebaseOptions = File(
      'lib/firebase_options.dart',
    ).readAsStringSync();

    final productionAppId = appIdFor('com.seolleyeon.app')!;
    final stagingAppId = appIdFor('com.yonsei.dating')!;

    expect(firebaseOptions, contains("appId: '$productionAppId'"));
    expect(firebaseOptions, contains("appId: '$stagingAppId'"));
    // flavor 를 실제로 읽어서 고르는지 (상수 하나로 고정돼 있으면 안 된다).
    expect(firebaseOptions, contains('FLUTTER_APP_FLAVOR'));
    expect(firebaseOptions, contains('androidProduction'));
    expect(firebaseOptions, contains('androidStaging'));
  });

  test('FlutterFire config defaults to the production Android app', () {
    final firebaseJson = File('firebase.json').readAsStringSync();
    final productionAppId = appIdFor('com.seolleyeon.app')!;

    // 여기가 staging 을 가리키면 flutterfire configure 를 다시 돌렸을 때
    // production 설정이 조용히 staging 으로 되돌아간다.
    expect(firebaseJson, contains('"appId": "$productionAppId"'));
  });
}
