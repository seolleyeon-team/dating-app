import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/core/compatibility/app_compatibility.dart';

/// 앱 호환성 게이트의 판정 로직.
///
/// 이 게이트는 **UX 장치이지 보안 경계가 아니다**. 수정된 클라이언트는 이
/// 화면을 우회할 수 있고, 그래도 상관없다 — legacy write 차단은 Firestore
/// Rules 가 한다. 여기서 지켜야 하는 것은 하나다: 멀쩡한 사용자를 잠그지
/// 않는 것. 정책을 못 읽었다는 이유로 앱을 막으면 백엔드 장애 한 번이
/// 전체 사용자 lockout 이 된다.
void main() {
  const capabilities = {'bambooPrivateOwnershipV1'};

  AppCompatibilityPolicy policy({
    int minimum = 10,
    int recommended = 20,
    Set<String> required = const {},
  }) {
    return AppCompatibilityPolicy(
      policyVersion: 1,
      minimumSupportedBuild: minimum,
      recommendedBuild: recommended,
      storeUrl:
          'https://play.google.com/store/apps/details?id=com.seolleyeon.app',
      requiredCapabilities: required,
      messageVersion: 1,
    );
  }

  CompatibilityDecision decide({
    required int? build,
    Set<String> caps = capabilities,
    AppCompatibilityPolicy? p,
  }) {
    return evaluateCompatibility(
      buildNumber: build,
      capabilities: caps,
      policy: p ?? policy(),
    );
  }

  group('빌드 번호 판정', () {
    test('최소 미만은 필수 업데이트', () {
      expect(decide(build: 9).status, CompatibilityStatus.updateRequired);
    });

    test('최소와 같으면 통과 — 경계에서 잠그지 않는다', () {
      // 여기서 어긋나면 최소 지원 버전을 막 설치한 사용자가 잠긴다.
      expect(decide(build: 10).status, CompatibilityStatus.updateRecommended);
    });

    test('권장 이상은 정상', () {
      expect(decide(build: 20).status, CompatibilityStatus.supported);
      expect(decide(build: 999).status, CompatibilityStatus.supported);
    });

    test('최소 이상 권장 미만은 안내만', () {
      final decision = decide(build: 15);
      expect(decision.status, CompatibilityStatus.updateRecommended);
      expect(decision.blocksApp, isFalse);
    });

    test('필수 상태만 앱을 막는다', () {
      expect(decide(build: 9).blocksApp, isTrue);
      expect(decide(build: 20).blocksApp, isFalse);
    });
  });

  group('capability 판정', () {
    test('정책이 요구하는 capability 가 없으면 필수 업데이트', () {
      // 버전 번호를 하드코딩하지 않고도 "이 기능을 가진 빌드" 를 요구할 수 있다.
      final decision = decide(
        build: 999,
        p: policy(required: {'bambooPrivateOwnershipV1'}),
        caps: const {},
      );
      expect(decision.status, CompatibilityStatus.updateRequired);
    });

    test('capability 를 갖추면 빌드가 최신이 아니어도 막지 않는다', () {
      final decision = decide(
        build: 999,
        p: policy(required: {'bambooPrivateOwnershipV1'}),
      );
      expect(decision.status, CompatibilityStatus.supported);
    });

    test('알 수 없는 capability 를 요구하면 필수 업데이트', () {
      final decision = decide(
        build: 999,
        p: policy(required: {'someFutureThing'}),
      );
      expect(decision.status, CompatibilityStatus.updateRequired);
    });
  });

  group('자기 빌드 번호를 모를 때', () {
    test('빌드 번호를 읽지 못하면 막지 않는다', () {
      // 우리가 몇 번째 빌드인지도 모르면서 "너무 낡았다" 고 단정할 수 없다.
      expect(decide(build: null).status, CompatibilityStatus.supported);
    });

    test('빌드 번호를 몰라도 없는 capability 는 여전히 걸린다', () {
      final decision = decide(
        build: null,
        p: policy(required: {'bambooPrivateOwnershipV1'}),
        caps: const {},
      );
      expect(decision.status, CompatibilityStatus.updateRequired);
    });
  });

  group('안전 기본 정책', () {
    test('내장 기본값은 누구도 잠그지 않는다', () {
      // 원격 문서가 아직 없을 때 쓰이는 값이다. 여기가 틀리면 배포 직후
      // 전체 사용자가 잠긴다.
      const fallback = AppCompatibilityPolicy.safeDefault;
      expect(fallback.minimumSupportedBuild, 0);
      expect(fallback.requiredCapabilities, isEmpty);
      expect(
        evaluateCompatibility(
          buildNumber: 1,
          capabilities: const {},
          policy: fallback,
        ).status,
        CompatibilityStatus.supported,
      );
    });

    test('현재 출시 빌드가 기본 정책에 걸리지 않는다', () {
      expect(
        evaluateCompatibility(
          buildNumber: currentKnownReleaseBuild,
          capabilities: kAppCapabilities,
          policy: AppCompatibilityPolicy.safeDefault,
        ).status,
        CompatibilityStatus.supported,
      );
    });
  });

  group('원격 문서 파싱', () {
    test('정상 문서를 읽는다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'policyVersion': 2,
        'messageVersion': 3,
        'android': {
          'minimumSupportedBuild': 14,
          'recommendedBuild': 20,
          'storeUrl': 'https://play.google.com/store/apps/details?id=x',
        },
        'ios': {'minimumSupportedBuild': 99},
        'requiredCapabilities': ['bambooPrivateOwnershipV1'],
      }, platform: CompatibilityPlatform.android);

      expect(parsed, isNotNull);
      expect(parsed!.minimumSupportedBuild, 14);
      expect(parsed.recommendedBuild, 20);
      expect(parsed.policyVersion, 2);
      expect(parsed.messageVersion, 3);
      expect(parsed.requiredCapabilities, {'bambooPrivateOwnershipV1'});
    });

    test('플랫폼별로 다른 값을 읽는다', () {
      const raw = {
        'android': {'minimumSupportedBuild': 14},
        'ios': {'minimumSupportedBuild': 99},
      };
      expect(
        AppCompatibilityPolicy.fromRemote(
          raw,
          platform: CompatibilityPlatform.ios,
        )!.minimumSupportedBuild,
        99,
      );
    });

    test('내 플랫폼 정책이 없으면 잠그지 않는다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {'minimumSupportedBuild': 14},
      }, platform: CompatibilityPlatform.ios);
      expect(parsed, isNotNull);
      expect(parsed!.minimumSupportedBuild, 0);
    });

    test('문서가 없으면 null 을 돌려 호출부가 기본값을 쓰게 한다', () {
      expect(
        AppCompatibilityPolicy.fromRemote(
          null,
          platform: CompatibilityPlatform.android,
        ),
        isNull,
      );
    });

    test('숫자가 아닌 값은 없는 것으로 본다', () {
      // 운영자가 오타를 내도 전체 사용자가 잠기면 안 된다.
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {
          'minimumSupportedBuild': 'twenty',
          'recommendedBuild': null,
        },
      }, platform: CompatibilityPlatform.android);
      expect(parsed!.minimumSupportedBuild, 0);
      expect(parsed.recommendedBuild, 0);
    });

    test('음수는 0 으로 본다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {'minimumSupportedBuild': -5},
      }, platform: CompatibilityPlatform.android);
      expect(parsed!.minimumSupportedBuild, 0);
    });

    test('소수점 값은 버림 처리한다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {'minimumSupportedBuild': 14.9},
      }, platform: CompatibilityPlatform.android);
      expect(parsed!.minimumSupportedBuild, 14);
    });

    test('터무니없이 큰 값도 터지지 않는다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {'minimumSupportedBuild': 9007199254740991},
      }, platform: CompatibilityPlatform.android);
      expect(
        evaluateCompatibility(
          buildNumber: 14,
          capabilities: kAppCapabilities,
          policy: parsed!,
        ).status,
        CompatibilityStatus.updateRequired,
      );
    });

    test('capability 목록이 문자열이 아니면 무시한다', () {
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'requiredCapabilities': [1, null, 'bambooPrivateOwnershipV1', ''],
      }, platform: CompatibilityPlatform.android);
      expect(parsed!.requiredCapabilities, {'bambooPrivateOwnershipV1'});
    });

    test('store url 이 http(s) 가 아니면 버린다', () {
      // 정책 문서는 공개 정보다. 이상한 스킴을 그대로 열지 않는다.
      final parsed = AppCompatibilityPolicy.fromRemote(const {
        'android': {'storeUrl': 'javascript:alert(1)'},
      }, platform: CompatibilityPlatform.android);
      expect(parsed!.storeUrl, isNull);
    });
  });

  group('flavor 분리', () {
    test('production 빌드만 production 정책을 읽는다', () {
      expect(
        compatibilityPolicyDocIdFor(
          'production',
          platform: CompatibilityPlatform.android,
        ),
        'production',
      );
    });

    test('staging 빌드는 staging 정책을 읽는다', () {
      // production 최소 빌드가 개발자 staging 빌드를 막으면 안 된다.
      expect(
        compatibilityPolicyDocIdFor(
          'staging',
          platform: CompatibilityPlatform.android,
        ),
        'staging',
      );
    });

    test('Android 는 flavor 를 모르면 게이트를 적용하지 않는다', () {
      // Android 는 flavor 가 applicationId 를 정한다. 그것을 모르는 빌드는
      // 스토어 배포 대상이 아니다.
      for (final flavor in [null, '', 'someOtherFlavor']) {
        expect(
          compatibilityPolicyDocIdFor(
            flavor,
            platform: CompatibilityPlatform.android,
          ),
          isNull,
        );
      }
    });

    test('iOS 는 flavor 가 없어도 production 정책을 읽는다', () {
      // iOS 프로젝트에는 flavor scheme 이 없다 — Runner 하나뿐이고 번들 id 는
      // com.seolleyeon.app 하나다. 그래서 iOS 릴리스는 --flavor 없이 빌드되고
      // appFlavor 가 null 이 된다. 이걸 "게이트 미적용" 으로 두면 iOS 에서는
      // 업데이트 게이트가 영원히 동작하지 않는다.
      expect(
        compatibilityPolicyDocIdFor(null, platform: CompatibilityPlatform.ios),
        'production',
      );
    });

    test('iOS 에 flavor 가 생기면 그쪽이 우선한다', () {
      // 나중에 Xcode scheme 이 추가되면 자동으로 flavor 경로를 탄다.
      expect(
        compatibilityPolicyDocIdFor(
          'staging',
          platform: CompatibilityPlatform.ios,
        ),
        'staging',
      );
    });
  });

  group('bridge 릴리스 식별', () {
    test('상수가 pubspec 의 실제 build number 와 일치한다', () {
      // 이 상수가 pubspec 과 어긋나면 위아래 테스트가 전부 거짓말이 된다.
      // 릴리스 때 pubspec 만 올리고 상수를 잊는 실수를 여기서 잡는다.
      final pubspec = File('pubspec.yaml').readAsStringSync();
      final match = RegExp(
        r'^version:\s*\d+\.\d+\.\d+\+(\d+)\s*$',
        multiLine: true,
      ).firstMatch(pubspec);
      expect(match, isNotNull, reason: 'pubspec version could not be read');
      expect(int.parse(match!.group(1)!), currentKnownReleaseBuild);
    });

    test('bridge 빌드는 pre-bridge 빌드보다 큰 번호를 단다', () {
      // 두 값이 같으면 "bridge 이상만 지원" 이라는 정책을 아예 표현할 수 없다.
      // 릴리스 때 build number 를 올리지 않으면 여기서 걸린다.
      expect(currentKnownReleaseBuild, greaterThan(preBridgeReleaseBuild));
    });

    test('bridge 를 최소 지원 빌드로 세우면 pre-bridge 는 필수 업데이트가 된다', () {
      // 운영자가 cutover 때 실제로 세울 정책이다. 정책이 두 빌드를 구분하지
      // 못하면 여기서 드러난다.
      final policy = AppCompatibilityPolicy(
        policyVersion: 1,
        minimumSupportedBuild: currentKnownReleaseBuild,
        recommendedBuild: currentKnownReleaseBuild,
        storeUrl: null,
        requiredCapabilities: const {},
        messageVersion: 1,
      );

      expect(
        evaluateCompatibility(
          buildNumber: preBridgeReleaseBuild,
          capabilities: kAppCapabilities,
          policy: policy,
        ).status,
        CompatibilityStatus.updateRequired,
      );
      expect(
        evaluateCompatibility(
          buildNumber: currentKnownReleaseBuild,
          capabilities: kAppCapabilities,
          policy: policy,
        ).status,
        CompatibilityStatus.supported,
      );
    });

    test('이 정책은 bridge 이후 빌드끼리만 유효하다', () {
      // 실제로 설치돼 있는 pre-bridge 빌드에는 게이트 코드가 없어서 이 정책을
      // 읽지도 않는다. 위 테스트가 통과한다고 구버전이 차단되는 것이 아니다.
      // 그 사실은 docs/security/sec04-bridge-cutover.md 에 적혀 있다.
      final doc = File(
        'docs/security/sec04-bridge-cutover.md',
      ).readAsStringSync();
      expect(doc.contains('OLD_CLIENTS_FORCED_TO_UPDATE = NO'), isTrue);
      expect(doc.contains('PRE_BRIDGE_CLIENTS_DO_NOT_KNOW_THIS_GATE'), isTrue);
    });
  });

  group('이 빌드가 선언하는 capability', () {
    test('Phase A dual-write 능력을 선언한다', () {
      // 이 빌드의 저장소는 글/댓글과 소유권 매핑을 함께 쓴다.
      expect(kAppCapabilities, contains('bambooPrivateOwnershipV1'));
    });
  });
}
