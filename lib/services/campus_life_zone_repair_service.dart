import '../constants/campus_life_zones.dart';
import 'onboarding_save_helper.dart';
import 'storage_service.dart';
import 'user_service.dart';

/// 생활권 보충(repair) 필요 여부 판정과 저장 후 검증.
///
/// 추천·미팅은 `users/{uid}.onboarding.campusLifeZones` 를 hard eligibility 로
/// 쓰고, 값이 없으면 fail-closed 로 후보에서 제외한다. 기존 사용자 중 학년·
/// 학과를 저장한 적이 없는 계정은 생활권이 계산된 적이 없으므로 추천이 0명이
/// 된다. 이 서비스는 그 상태를 감지하고, 사용자가 부족한 값만 보충하면
/// 기존 [CampusLifeZoneResolver] 로 생활권이 생성되도록 돕는다.
///
/// 생활권 분류 로직은 여기서 재구현하지 않는다. 저장은 기존 온보딩 write
/// path 를 그대로 쓰고, 성공 판정은 Firestore 재조회 결과로만 한다.
class CampusLifeZoneRepairService {
  CampusLifeZoneRepairService({
    UserService? userService,
    StorageService? storageService,
  }) : _userService = userService ?? UserService(),
       _storageService = storageService ?? StorageService();

  final UserService _userService;
  final StorageService _storageService;

  /// 저장된 생활권을 읽는다. 값이 없으면 빈 집합.
  static Set<String> zonesFromProfile(Map<String, dynamic>? profile) {
    if (profile == null) return const <String>{};
    final onboarding = profile['onboarding'];
    final raw = onboarding is Map
        ? onboarding['campusLifeZones']
        : profile['campusLifeZones'];
    if (raw is! List) return const <String>{};
    return raw
        .map((zone) => zone?.toString().trim() ?? '')
        .where((zone) => zone.isNotEmpty)
        .toSet();
  }

  /// 이미 계산된 생활권이 있는지.
  static bool hasZones(Map<String, dynamic>? profile) =>
      zonesFromProfile(profile).isNotEmpty;

  static String? _text(Map<String, dynamic>? onboarding, String key) {
    final value = onboarding?[key];
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? null : text;
  }

  /// 보충 화면에 미리 채울 기존 값.
  static CampusLifeZoneRepairPrefill prefillFrom(Map<String, dynamic>? profile) {
    final onboarding = profile?['onboarding'];
    final map = onboarding is Map
        ? onboarding.map((k, v) => MapEntry(k.toString(), v))
        : <String, dynamic>{};
    return CampusLifeZoneRepairPrefill(
      grade: _text(map, 'grade'),
      major: _text(map, 'major'),
      department: _text(map, 'department'),
      isRa: map['isRa'] == true,
    );
  }

  /// 현재 로그인 사용자의 생활권 보충이 필요한지 확인한다.
  ///
  /// Firestore 를 직접 읽는다. 로그인 정보를 알 수 없으면 판단하지 않고
  /// `null` 을 돌려준다 (호출부가 별도의 로그인 안내를 하도록).
  Future<CampusLifeZoneStatus?> loadStatus() async {
    final uid = await _storageService.getKakaoUserId();
    if (uid == null || uid.isEmpty) return null;
    final profile = await _userService.getUserProfile(uid);
    if (profile == null) return null;
    return CampusLifeZoneStatus(
      zones: zonesFromProfile(profile),
      prefill: prefillFrom(profile),
    );
  }

  /// 부족한 값을 저장하고 Firestore 재조회로 생활권 생성을 확인한다.
  ///
  /// 저장 callback 성공만으로 완료 처리하지 않는다. 재조회 결과에
  /// canonical 생활권이 실제로 기록됐을 때만 [CampusLifeZoneRepairResult.saved].
  Future<CampusLifeZoneRepairResult> repair({
    String? grade,
    String? major,
    String? department,
    bool? isRa,
  }) async {
    final uid = await _storageService.getKakaoUserId();
    if (uid == null || uid.isEmpty) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.notSignedIn,
      );
    }

    final wrote = await OnboardingSaveHelper.saveCampusLifeZoneInputs(
      grade: grade,
      major: major,
      department: department,
      isRa: isRa,
    );
    if (!wrote) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.nothingToSave,
      );
    }

    // Firestore 가 source of truth. 저장 성공 callback 을 믿지 않는다.
    final profile = await _userService.getUserProfile(uid);
    final zones = zonesFromProfile(profile);
    if (zones.isEmpty) {
      // 입력이 부족하거나 분류 규칙에 해당하지 않아 생활권이 만들어지지 않았다.
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.unresolved,
      );
    }
    final unknown = zones.difference(_canonicalZones);
    if (unknown.isNotEmpty) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.unresolved,
      );
    }
    return CampusLifeZoneRepairResult.saved(zones);
  }

  static const Set<String> _canonicalZones = <String>{
    CampusLifeZones.sinchon,
    CampusLifeZones.songdo,
  };
}

/// 보충 화면 초기값.
class CampusLifeZoneRepairPrefill {
  final String? grade;
  final String? major;
  final String? department;
  final bool isRa;

  const CampusLifeZoneRepairPrefill({
    this.grade,
    this.major,
    this.department,
    this.isRa = false,
  });
}

/// 현재 사용자의 생활권 상태.
class CampusLifeZoneStatus {
  final Set<String> zones;
  final CampusLifeZoneRepairPrefill prefill;

  const CampusLifeZoneStatus({required this.zones, required this.prefill});

  bool get needsRepair => zones.isEmpty;
}

enum CampusLifeZoneRepairError {
  /// 로그인 정보를 확인할 수 없음.
  notSignedIn,

  /// 저장할 값이 하나도 없음.
  nothingToSave,

  /// 저장은 됐지만 생활권이 만들어지지 않음 (입력 부족/규칙 미해당).
  unresolved,
}

class CampusLifeZoneRepairResult {
  final Set<String> zones;
  final CampusLifeZoneRepairError? error;

  const CampusLifeZoneRepairResult.saved(this.zones) : error = null;

  const CampusLifeZoneRepairResult.failure(this.error)
    : zones = const <String>{};

  bool get isSuccess => error == null && zones.isNotEmpty;
}
