import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show appFlavor;
import 'package:package_info_plus/package_info_plus.dart';

import 'app_compatibility.dart';

/// 정책 문서를 가져오는 방법. 테스트가 Firestore 없이 실패 경로를 재현할 수
/// 있도록 주입 가능하게 둔다.
typedef CompatibilityPolicyFetcher =
    Future<Map<String, dynamic>?> Function(String docId);

/// 앱 호환성 정책을 읽고 현재 빌드의 상태를 판정한다.
///
/// 정책은 Firebase Remote Config 가 아니라 공개 읽기 전용 Firestore 문서에
/// 둔다. 이 저장소에는 이미 `blindMeetingConfig` / `meetingIcebreakerConfig`
/// 같은 운영 설정 문서 관례가 있고, `cloud_firestore` 는 이미 의존성에
/// 들어 있다. 네이티브 플러그인을 하나 더 들이지 않으면서 오프라인 캐시를
/// 그대로 얻고, 문서가 공개 읽기이며 클라이언트가 쓸 수 없다는 사실을
/// rules 테스트로 CI 에서 증명할 수 있다.
///
/// **이 서비스는 보안 판정을 하지 않는다.** 실패하면 언제나 통과 쪽으로
/// 떨어진다. legacy write 차단은 Firestore Rules 의 몫이다.
class AppCompatibilityService {
  AppCompatibilityService({
    CompatibilityPolicyFetcher? fetchPolicy,
    Future<int?> Function()? readBuildNumber,
    String? flavor,
    CompatibilityPlatform? platform,
    Set<String> capabilities = kAppCapabilities,
    this.timeout = const Duration(seconds: 5),
  }) : _fetchPolicy = fetchPolicy ?? _fetchFromFirestore,
       _readBuildNumber = readBuildNumber ?? _readPlatformBuildNumber,
       _flavor = flavor ?? appFlavor,
       _platform = platform ?? _currentPlatform(),
       _capabilities = capabilities;

  static const String collection = 'appCompatibilityConfig';

  final CompatibilityPolicyFetcher _fetchPolicy;
  final Future<int?> Function() _readBuildNumber;
  final String? _flavor;
  final CompatibilityPlatform? _platform;
  final Set<String> _capabilities;
  final Duration timeout;

  AppCompatibilityPolicy? _cachedPolicy;

  /// 마지막으로 성공한 정책. 원격을 못 읽었을 때 이 값을 다시 쓴다.
  @visibleForTesting
  AppCompatibilityPolicy? get cachedPolicy => _cachedPolicy;

  static const CompatibilityDecision _pass = CompatibilityDecision(
    status: CompatibilityStatus.supported,
    storeUrl: null,
  );

  Future<CompatibilityDecision> evaluate() async {
    final platform = _platform;
    // 웹/데스크톱은 게이트 대상이 아니다. 웹은 언제나 마지막 배포본이 뜨므로
    // 낡은 클라이언트가 남지 않는다.
    if (platform == null) return _pass;

    final docId = compatibilityPolicyDocIdFor(_flavor, platform: platform);
    // flavor 를 모르는 Android 빌드(테스트 등)는 스토어 배포 대상이 아니다.
    if (docId == null) return _pass;

    final policy = await _loadPolicy(docId);
    final buildNumber = await _loadBuildNumber();

    return evaluateCompatibility(
      buildNumber: buildNumber,
      capabilities: _capabilities,
      policy: policy,
    );
  }

  Future<AppCompatibilityPolicy> _loadPolicy(String docId) async {
    try {
      final raw = await _fetchPolicy(docId).timeout(timeout);
      final parsed = AppCompatibilityPolicy.fromRemote(
        raw,
        platform: _platform!,
      );
      if (parsed != null) {
        _cachedPolicy = parsed;
        return parsed;
      }
    } catch (error) {
      // 네트워크 없음, 타임아웃, 백엔드 장애, 권한 오류 — 전부 여기로 온다.
      // 정책을 못 읽은 것을 "너무 낡은 앱" 으로 오인하면 백엔드 장애 한 번이
      // 전체 사용자 lockout 이 된다.
      debugPrint('[Compatibility] policy fetch failed: ${error.runtimeType}');
    }
    return _cachedPolicy ?? AppCompatibilityPolicy.safeDefault;
  }

  // 값을 들고 있지 않는다. 플러그인이 이미 자체 캐시를 하고, 여기서 또
  // 붙잡으면 업데이트 후 복귀했을 때 옛날 빌드 번호로 계속 판정한다.
  Future<int?> _loadBuildNumber() async {
    try {
      return await _readBuildNumber().timeout(timeout);
    } catch (error) {
      debugPrint('[Compatibility] build number unavailable');
      return null;
    }
  }

  static CompatibilityPlatform? _currentPlatform() {
    if (kIsWeb) return null;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return CompatibilityPlatform.android;
      case TargetPlatform.iOS:
        return CompatibilityPlatform.ios;
      default:
        return null;
    }
  }

  static Future<Map<String, dynamic>?> _fetchFromFirestore(String docId) async {
    final snapshot = await FirebaseFirestore.instance
        .collection(collection)
        .doc(docId)
        .get();
    return snapshot.data();
  }

  /// Android `versionCode` 와 iOS `CFBundleVersion` 은 둘 다 Flutter build
  /// number 에서 나온다. semver 문자열이 아니라 이 정수를 쓴다 — 문자열
  /// 비교는 `1.0.10 < 1.0.9` 같은 결과를 낸다.
  static Future<int?> _readPlatformBuildNumber() async {
    final info = await PackageInfo.fromPlatform();
    return int.tryParse(info.buildNumber.trim());
  }
}
