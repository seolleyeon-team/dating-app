import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/core/compatibility/app_compatibility.dart';
import 'package:seolleyeon/core/compatibility/app_compatibility_service.dart';

/// 정책 소스가 실패했을 때의 동작.
///
/// 여기서 잘못 판정하면 백엔드 장애 한 번이 전체 사용자 lockout 이 된다.
/// 실패는 전부 통과 쪽으로 떨어져야 한다 — 보안은 Firestore Rules 가 맡고,
/// 이 게이트는 UX 다.
void main() {
  const productionPolicy = {
    'policyVersion': 1,
    'android': {
      'minimumSupportedBuild': 20,
      'recommendedBuild': 30,
      'storeUrl': 'https://play.google.com/store/apps/details?id=x',
    },
  };

  AppCompatibilityService service({
    CompatibilityPolicyFetcher? fetch,
    Future<int?> Function()? build,
    String? flavor = 'production',
    Duration timeout = const Duration(milliseconds: 200),
  }) {
    return AppCompatibilityService(
      fetchPolicy: fetch ?? (_) async => productionPolicy,
      readBuildNumber: build ?? () async => 14,
      flavor: flavor,
      platform: CompatibilityPlatform.android,
      timeout: timeout,
    );
  }

  group('정상 경로', () {
    test('정책을 읽어 낡은 빌드를 막는다', () async {
      final decision = await service().evaluate();
      expect(decision.status, CompatibilityStatus.updateRequired);
      expect(decision.storeUrl, startsWith('https://'));
    });

    test('요청하는 문서 id 는 flavor 를 따른다', () async {
      final requested = <String>[];
      await service(
        fetch: (docId) async {
          requested.add(docId);
          return productionPolicy;
        },
      ).evaluate();
      expect(requested, ['production']);
    });

    test('staging 빌드는 staging 문서를 읽는다', () async {
      // production 최소 빌드가 개발자 staging 빌드를 잠그면 안 된다.
      final requested = <String>[];
      await service(
        flavor: 'staging',
        fetch: (docId) async {
          requested.add(docId);
          return null;
        },
      ).evaluate();
      expect(requested, ['staging']);
    });

    test('flavor 없는 빌드는 정책을 아예 읽지 않는다', () async {
      var called = false;
      final decision = await service(
        flavor: null,
        fetch: (_) async {
          called = true;
          return productionPolicy;
        },
      ).evaluate();
      expect(called, isFalse);
      expect(decision.status, CompatibilityStatus.supported);
    });
  });

  group('정책 소스 실패', () {
    test('첫 실행에 오프라인이면 막지 않는다', () async {
      final decision = await service(
        fetch: (_) async => throw StateError('offline'),
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('타임아웃도 막지 않는다', () async {
      final decision = await service(
        fetch: (_) =>
            Future.delayed(const Duration(seconds: 5), () => productionPolicy),
        timeout: const Duration(milliseconds: 50),
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('문서가 없어도 막지 않는다', () async {
      final decision = await service(fetch: (_) async => null).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('권한 오류도 막지 않는다', () async {
      final decision = await service(
        fetch: (_) async => throw Exception('PERMISSION_DENIED'),
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('한 번 읽은 정책은 이후 실패에도 유지된다', () async {
      var attempt = 0;
      final gate = service(
        fetch: (_) async {
          attempt += 1;
          if (attempt == 1) return productionPolicy;
          throw StateError('backend down');
        },
      );

      expect(
        (await gate.evaluate()).status,
        CompatibilityStatus.updateRequired,
      );
      // 백엔드가 죽었다고 방금까지 유효하던 정책을 버리지 않는다.
      expect(
        (await gate.evaluate()).status,
        CompatibilityStatus.updateRequired,
      );
      expect(gate.cachedPolicy?.minimumSupportedBuild, 20);
    });

    test('깨진 값이 섞여 있어도 잠그지 않는다', () async {
      final decision = await service(
        fetch: (_) async => const {
          'android': {'minimumSupportedBuild': 'twenty'},
        },
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });
  });

  group('빌드 번호를 읽지 못할 때', () {
    test('패키지 정보 실패는 막지 않는다', () async {
      final decision = await service(
        build: () async => throw MissingPluginException('no platform'),
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('빌드 번호를 몰라도 capability 요구는 유효하다', () async {
      final decision = await AppCompatibilityService(
        fetchPolicy: (_) async => const {
          'requiredCapabilities': ['somethingThisBuildLacks'],
        },
        readBuildNumber: () async => null,
        flavor: 'production',
        platform: CompatibilityPlatform.android,
      ).evaluate();
      expect(decision.status, CompatibilityStatus.updateRequired);
    });
  });

  group('현재 출시본 보호', () {
    test('정책이 비어 있으면 현재 빌드가 잠기지 않는다', () async {
      // 앱이 먼저 배포되고 정책 문서를 나중에 만드는 순간이 반드시 있다.
      final decision = await service(
        fetch: (_) async => const <String, dynamic>{},
        build: () async => currentKnownReleaseBuild,
      ).evaluate();
      expect(decision.status, CompatibilityStatus.supported);
    });
  });
}
