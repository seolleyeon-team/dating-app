/// 앱 호환성 게이트의 판정 로직.
///
/// **이것은 UX 장치이지 보안 경계가 아니다.** 수정된 클라이언트는 업데이트
/// 화면을 우회할 수 있고, 그래도 문제가 되면 안 된다 — legacy write 를 실제로
/// 거부하는 것은 Firestore Rules 다. 여기서 클라이언트 버전을 신뢰하는 구조를
/// 만들면 안 되고, 서버 보안이 이 판정에 의존해서도 안 된다.
///
/// 이 파일이 실제로 책임지는 것은 하나다: **멀쩡한 사용자를 잠그지 않는 것.**
/// 원격 정책을 못 읽었다는 이유로 앱을 막으면 백엔드 장애 한 번이 전체 사용자
/// lockout 이 된다. 그래서 모르는 값·깨진 값·읽기 실패는 전부 "통과" 쪽으로
/// 떨어진다.
library;

/// 이 빌드가 실제로 할 수 있는 일.
///
/// 버전 번호 대신 이걸 요구하면 정책이 "몇 번 빌드 이상" 이 아니라 "이 기능을
/// 가진 빌드" 를 말할 수 있다. SEC-04 하나에 게이트를 하드코딩하지 않으려는
/// 이유이기도 하다.
///
/// `bambooPrivateOwnershipV1`: 대나무숲 글/댓글을 쓸 때 비공개 소유권 매핑을
/// 함께 기록한다. Phase C 에서 public `authorId` 가 사라져도 "내가 쓴 글" 을
/// 찾을 수 있는 빌드라는 뜻이다.
const Set<String> kAppCapabilities = {'bambooPrivateOwnershipV1'};

/// pubspec 의 현재 build number. 기본 정책이 현재 출시본을 스스로 막지 않는지
/// 테스트에서 확인하는 용도다. 런타임 판정은 실제 패키지 정보를 쓴다.
const int currentKnownReleaseBuild = 21;

/// bridge 게이트가 들어가기 **전** 마지막 build number.
///
/// 이 값과 [currentKnownReleaseBuild] 가 같으면 정책이 두 빌드를 구분할 수
/// 없다. 그러면 "bridge 이상만 지원" 이라는 정책 자체를 쓸 수 없으므로 bridge
/// 릴리스는 반드시 이보다 큰 build number 를 달아야 한다.
///
/// 주의: 실제 설치된 pre-bridge 빌드에는 게이트 코드가 없어서 이 정책을 읽지
/// 않는다. 여기서 구분되는 것은 bridge 이후 빌드끼리다.
const int preBridgeReleaseBuild = 14;

enum CompatibilityPlatform { android, ios }

enum CompatibilityStatus {
  supported,

  /// 앱은 그대로 쓸 수 있고 업데이트를 안내만 한다.
  updateRecommended,

  /// 본 화면 진입을 막고 업데이트 화면만 보여준다.
  updateRequired,
}

/// 스토어에 나가는 빌드별로 정책 문서를 나눈다.
///
/// production 과 staging 이 같은 Firebase 프로젝트를 쓰기 때문에 프로젝트로
/// 분리할 수 없다. production 최소 빌드가 개발자 staging 빌드를 잠그면 개발이
/// 멈추므로 문서 자체를 분리한다.
///
/// Android 는 flavor 가 applicationId 를 정하므로 flavor 가 곧 정체성이다.
/// flavor 를 모르는 Android 빌드는 스토어 배포 대상이 아니라서 게이트를
/// 적용하지 않는다.
///
/// iOS 는 사정이 다르다. Xcode 프로젝트에 flavor scheme 이 없어서 — Runner
/// 하나뿐이고 번들 id 도 `com.seolleyeon.app` 하나다 — 릴리스가 `--flavor`
/// 없이 빌드되고 `appFlavor` 가 null 로 들어온다. 그것을 Android 와 똑같이
/// "게이트 미적용" 으로 처리하면 iOS 에서는 업데이트 게이트가 영원히 동작하지
/// 않는다. iOS 빌드는 곧 production 이므로 flavor 가 없으면 production 으로
/// 본다. 나중에 scheme 이 추가되면 flavor 가 채워져 자동으로 그쪽을 탄다.
///
/// 웹은 언제나 마지막으로 배포된 코드가 뜨므로 낡은 클라이언트가 남지 않는다.
/// 그래서 [platform] 이 null 인 호출부(웹/데스크톱)는 애초에 여기까지 오지
/// 않는다.
String? compatibilityPolicyDocIdFor(
  String? flavor, {
  required CompatibilityPlatform platform,
}) {
  switch (flavor) {
    case 'production':
      return 'production';
    case 'staging':
      return 'staging';
  }
  return platform == CompatibilityPlatform.ios ? 'production' : null;
}

class AppCompatibilityPolicy {
  const AppCompatibilityPolicy({
    required this.policyVersion,
    required this.minimumSupportedBuild,
    required this.recommendedBuild,
    required this.storeUrl,
    required this.requiredCapabilities,
    required this.messageVersion,
  });

  final int policyVersion;
  final int minimumSupportedBuild;
  final int recommendedBuild;
  final String? storeUrl;
  final Set<String> requiredCapabilities;
  final int messageVersion;

  /// 원격 문서를 아직 못 읽었을 때 쓰는 값. **누구도 잠그지 않아야 한다.**
  /// 정책 문서를 만들기 전에 앱이 먼저 배포되는 순간이 반드시 있고, 그때
  /// 이 값이 잘못되어 있으면 전체 사용자가 잠긴다.
  static const AppCompatibilityPolicy safeDefault = AppCompatibilityPolicy(
    policyVersion: 0,
    minimumSupportedBuild: 0,
    recommendedBuild: 0,
    storeUrl: null,
    requiredCapabilities: <String>{},
    messageVersion: 0,
  );

  /// 공개 정책 문서를 읽는다. 문서가 없으면 `null` 을 돌려 호출부가 캐시나
  /// 기본값을 쓰게 한다.
  ///
  /// 값 하나가 깨져 있다고 문서 전체를 버리지는 않는다. 대신 읽을 수 없는
  /// 필드만 "없음" 으로 떨어뜨린다 — 운영자가 오타를 내도 전체 사용자가
  /// 잠기지 않아야 하기 때문이다.
  static AppCompatibilityPolicy? fromRemote(
    Map<String, dynamic>? raw, {
    required CompatibilityPlatform platform,
  }) {
    if (raw == null) return null;

    final section =
        raw[platform == CompatibilityPlatform.android ? 'android' : 'ios'];
    final platformPolicy = section is Map
        ? section
        : const <dynamic, dynamic>{};

    return AppCompatibilityPolicy(
      policyVersion: _readBuild(raw['policyVersion']),
      minimumSupportedBuild: _readBuild(
        platformPolicy['minimumSupportedBuild'],
      ),
      recommendedBuild: _readBuild(platformPolicy['recommendedBuild']),
      storeUrl: _readStoreUrl(platformPolicy['storeUrl']),
      requiredCapabilities: _readCapabilities(raw['requiredCapabilities']),
      messageVersion: _readBuild(raw['messageVersion']),
    );
  }

  /// 빌드 번호는 monotonically increasing 정수다. semver 문자열 비교는
  /// `1.0.10 < 1.0.9` 같은 결과를 내므로 hard gate 근거로 쓰지 않는다.
  static int _readBuild(Object? value) {
    final number = value is num ? value : null;
    if (number == null || !number.isFinite) return 0;
    final floored = number.floor();
    // 음수 최소 빌드는 의미가 없다. 0 이면 아무도 막지 않는다.
    return floored < 0 ? 0 : floored;
  }

  static String? _readStoreUrl(Object? value) {
    if (value is! String) return null;
    final trimmed = value.trim();
    if (trimmed.isEmpty) return null;
    final uri = Uri.tryParse(trimmed);
    // 정책 문서는 공개 정보이고 이 값은 그대로 열린다. 스토어로 가는
    // http(s) 만 받는다.
    if (uri == null || (uri.scheme != 'https' && uri.scheme != 'http')) {
      return null;
    }
    return trimmed;
  }

  static Set<String> _readCapabilities(Object? value) {
    if (value is! List) return const <String>{};
    return value
        .whereType<String>()
        .map((entry) => entry.trim())
        .where((entry) => entry.isNotEmpty)
        .toSet();
  }
}

class CompatibilityDecision {
  const CompatibilityDecision({required this.status, required this.storeUrl});

  final CompatibilityStatus status;
  final String? storeUrl;

  bool get blocksApp => status == CompatibilityStatus.updateRequired;
}

/// 정책과 이 빌드의 사실을 놓고 상태를 정한다.
///
/// [buildNumber] 가 `null` 이면 자기 빌드 번호를 읽지 못한 것이다. 그 상태에서
/// "너무 낡았다" 고 단정할 근거가 없으므로 빌드 기반 판정은 건너뛴다.
/// capability 는 컴파일 타임 상수라 그때도 확인할 수 있다.
CompatibilityDecision evaluateCompatibility({
  required int? buildNumber,
  required Set<String> capabilities,
  required AppCompatibilityPolicy policy,
}) {
  final missingCapability = policy.requiredCapabilities.any(
    (capability) => !capabilities.contains(capability),
  );
  if (missingCapability) {
    return CompatibilityDecision(
      status: CompatibilityStatus.updateRequired,
      storeUrl: policy.storeUrl,
    );
  }

  if (buildNumber != null && buildNumber < policy.minimumSupportedBuild) {
    return CompatibilityDecision(
      status: CompatibilityStatus.updateRequired,
      storeUrl: policy.storeUrl,
    );
  }

  if (buildNumber != null && buildNumber < policy.recommendedBuild) {
    return CompatibilityDecision(
      status: CompatibilityStatus.updateRecommended,
      storeUrl: policy.storeUrl,
    );
  }

  return CompatibilityDecision(
    status: CompatibilityStatus.supported,
    storeUrl: policy.storeUrl,
  );
}
