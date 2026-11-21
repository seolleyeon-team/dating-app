import '../services/user_service.dart';
import '../services/storage_service.dart';

/// 온보딩 각 화면에서 Firebase 저장을 호출하는 헬퍼.
/// kakaoUserId를 SharedPreferences에서 가져오고, UserService로 Firestore에 저장.
class OnboardingSaveHelper {
  static final UserService _userService = UserService();
  static final StorageService _storageService = StorageService();

  static Future<String?> _getUserId() async {
    return await _storageService.getKakaoUserId();
  }

  static Future<void> _completeOnboarding(String uid) async {
    // One-time-snapshot architecture: the Kakao friend snapshot already ran
    // BEFORE onboarding (setup ladder gate), so completing onboarding needs
    // no friend sync. Pair exclusions are server-maintained from
    // kakaoFriendPairs.
    await _userService.completeOnboarding(uid);
  }

  /// 온보딩 완료 기록. 아바타 선택 화면이 승인 뒤에만 호출한다.
  ///
  /// 이상형 단계의 저장/건너뛰기는 더 이상 완료를 기록하지 않는다. 그렇게 하면
  /// 아바타 승인 전에 `initialSetupComplete` 가 서서 재진입 resolver 가 마지막
  /// 단계를 건너뛴다.
  static Future<void> completeOnboarding() async {
    final uid = await _getUserId();
    if (uid == null || uid.isEmpty) return;
    await _completeOnboarding(uid);
  }

  /// Step 1: 기본 정보
  static Future<void> saveBasicInfo({
    required String nickname,
    required String gender,
    required String region,
    required String education,
    required int height,
    required int age,
    required String grade,
    required bool isRa,
    required String mbti,
    required List<String> loveLanguages,
    required String relationship,
  }) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {
        'nickname': nickname,
        'gender': gender,
        'region': region,
        'education': education,
        'height': height,
        'age': age,
        'grade': grade,
        'isRa': isRa,
        'mbti': mbti,
        'loveLanguages': loveLanguages,
        'relationship': relationship,
      },
    );
  }

  /// Step 2: 관심사
  static Future<bool> saveInterests(List<String> interests) async {
    final uid = await _getUserId();
    if (uid == null || uid.isEmpty) return false;
    await _userService.saveOnboardingInterests(
      kakaoUserId: uid,
      interests: interests,
    );
    return true;
  }

  /// Step 3: 라이프스타일
  static Future<void> saveLifestyle({
    required String? drinking,
    required String? smoking,
    required String? exercise,
    required String? religion,
  }) async {
    final lifestyle = selectedLifestyleFields(
      drinking: drinking,
      smoking: smoking,
      exercise: exercise,
      religion: religion,
    );
    if (lifestyle.isEmpty) return;
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'lifestyle': lifestyle},
    );
  }

  /// 선택된 항목만 담는다. 선택하지 않은 항목은 쓰지 않는다.
  ///
  /// 라이프스타일 화면에서는 한 번 고른 값을 비울 수 없으므로 null 은 "지움"이
  /// 아니라 "이번에 고르지 않음"이다. 그것을 그대로 저장하면, 화면이 기존 값을
  /// 복원하지 않은 채(로드 전, 또는 예전 자동 기본값 조합이라 다시 고르게 한
  /// 경우) 뒤로/다음을 누르는 것만으로 저장돼 있던 음주·흡연 값이 null 로
  /// 덮인다. 그 두 값이 없으면 블라인드 미팅 신청이 서버에서 거부된다.
  static Map<String, String> selectedLifestyleFields({
    required String? drinking,
    required String? smoking,
    required String? exercise,
    required String? religion,
  }) {
    return {
      if (drinking != null && drinking.isNotEmpty) 'drinking': drinking,
      if (smoking != null && smoking.isNotEmpty) 'smoking': smoking,
      if (exercise != null && exercise.isNotEmpty) 'exercise': exercise,
      if (religion != null && religion.isNotEmpty) 'religion': religion,
    };
  }

  /// Step 4: 전공 계열
  static Future<void> saveMajor(String? major) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'major': major},
    );
  }

  /// 생활권(campusLifeZones) 보충 저장.
  ///
  /// 기존 사용자가 학년·학과 정보를 갖고 있지 않아 생활권이 계산되지 않은
  /// 경우, 부족한 값만 채워 저장한다. 저장 자체는 기존
  /// [UserService.saveOnboardingBasicInfo] 를 그대로 쓰므로 병합된 온보딩
  /// 데이터에 대해 기존 [CampusLifeZoneResolver] 가 실행되어
  /// `onboarding.campusLifeZones` 가 기록된다.
  ///
  /// 여기서 생활권을 직접 계산하지 않는다 (분류 로직 단일 소스 유지).
  /// null 인 인자는 기존 값을 덮어쓰지 않는다.
  static Future<bool> saveCampusLifeZoneInputs({
    String? grade,
    String? major,
    String? department,
    bool? isRa,
  }) async {
    final uid = await _getUserId();
    if (uid == null || uid.isEmpty) return false;

    final basicInfo = <String, dynamic>{};
    if (grade != null && grade.isNotEmpty) basicInfo['grade'] = grade;
    if (major != null && major.isNotEmpty) basicInfo['major'] = major;
    if (department != null && department.isNotEmpty) {
      basicInfo['department'] = department;
    }
    if (isRa != null) basicInfo['isRa'] = isRa;
    if (basicInfo.isEmpty) return false;

    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: basicInfo,
    );
    return true;
  }

  /// Step 5: 세부 학과
  static Future<void> saveDepartment(String department) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'department': department},
    );
  }

  /// 키 단일 저장 (height_selection_screen 등에서 사용)
  static Future<void> saveHeight(int height) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'height': height},
    );
  }

  // Step 6(사진): 원본 사진 URL은 클라이언트가 사용자 문서에 기록하지 않는다.
  // 승인된 아바타 URL(onboarding.avatarUrls)은 서버 승인 흐름만 쓴다.

  /// Step 7: 자기소개
  static Future<void> saveSelfIntroduction(String introduction) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'selfIntroduction': introduction},
    );
  }

  /// Step 8: 프로필 문답
  static Future<void> saveProfileQa(List<Map<String, String>> questions) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingProfileQa(
      kakaoUserId: uid,
      profileQa: questions,
    );
  }

  /// Step 9: 키워드
  static Future<void> saveKeywords(List<String> keywords) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingKeywords(
      kakaoUserId: uid,
      keywords: keywords,
    );
  }

  /// Step 9: 이상형 성격 키워드
  static Future<void> saveIdealPersonality(List<String> keywords) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.updateIdealTypeField(
      kakaoUserId: uid,
      fieldName: 'preferredPersonalities',
      value: keywords,
    );
  }

  static Future<void> _saveIdealInfoFromDraft(String uid) async {
    final draft = await _storageService.getOnboardingDraft(uid);

    final idealHeight = draft['idealHeight'];
    int? minHeight;
    int? maxHeight;
    if (idealHeight is Map) {
      minHeight = idealHeight['min'] is int
          ? idealHeight['min'] as int
          : int.tryParse(idealHeight['min']?.toString() ?? '');
      maxHeight = idealHeight['max'] is int
          ? idealHeight['max'] as int
          : int.tryParse(idealHeight['max']?.toString() ?? '');
    }

    final idealAge = draft['idealAge'];
    int? minAge;
    int? maxAge;
    if (idealAge is Map) {
      minAge = idealAge['min'] is int
          ? idealAge['min'] as int
          : int.tryParse(idealAge['min']?.toString() ?? '');
      maxAge = idealAge['max'] is int
          ? idealAge['max'] as int
          : int.tryParse(idealAge['max']?.toString() ?? '');
    }

    final idealMbti = draft['idealMbti'];
    final preferredMbti = <String>[];
    if (idealMbti is Map) {
      for (final key in ['EI', 'NS', 'TF', 'JP']) {
        final value = idealMbti[key]?.toString();
        if (value != null && value.trim().isNotEmpty) {
          preferredMbti.add(value.trim());
        }
      }
    }

    final idealDepartment = draft['idealDepartment'];
    final preferredDepartments = idealDepartment is List
        ? idealDepartment
              .map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toList()
        : <String>[];

    final fields = {
      'minAge': minAge,
      'maxAge': maxAge,
      'minHeight': minHeight,
      'maxHeight': maxHeight,
      'preferredMbti': preferredMbti,
      'preferredDepartments': preferredDepartments,
    };

    for (final entry in fields.entries) {
      await _userService.updateIdealTypeField(
        kakaoUserId: uid,
        fieldName: entry.key,
        value: entry.value,
      );
    }
  }

  /// 이상형 마지막 입력(성격) 저장. 완료 기록은 아바타 선택 화면이 한다.
  static Future<void> saveIdealPersonalityFinal(List<String> keywords) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _saveIdealInfoFromDraft(uid);
    await _userService.updateIdealTypeField(
      kakaoUserId: uid,
      fieldName: 'preferredPersonalities',
      value: keywords,
    );
  }

  /// Step 10: 이상형 라이프스타일
  static Future<void> saveIdealLifestyle({
    required String? drinking,
    required String? smoking,
    required String? exercise,
    required String? religion,
  }) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.updateIdealTypeField(
      kakaoUserId: uid,
      fieldName: 'preferredLifestyles',
      value: {
        'drinking': drinking,
        'smoking': smoking,
        'exercise': exercise,
        'religion': religion,
      },
    );
  }

  /// 이상형 건너뛰기. `idealType.skipped = true` 만 기록하고 온보딩 완료는
  /// 아바타 선택 화면에 맡긴다(resolver 는 skipped 를 완료로 인정한다).
  static Future<void> skipIdealType() async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.skipIdealType(uid);
  }

  /// 이상형 단일 필드 저장 (ideal_age, ideal_height, ideal_mbti, ideal_department 등)
  static Future<void> saveIdealTypeField(
    String fieldName,
    dynamic value,
  ) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.updateIdealTypeField(
      kakaoUserId: uid,
      fieldName: fieldName,
      value: value,
    );
  }
}
