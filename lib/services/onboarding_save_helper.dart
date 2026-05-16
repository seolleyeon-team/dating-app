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
  static Future<void> saveInterests(List<String> interests) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {'interests': interests},
    );
  }

  /// Step 3: 라이프스타일
  static Future<void> saveLifestyle({
    required String? drinking,
    required String? smoking,
    required String? exercise,
    required String? religion,
  }) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingBasicInfo(
      kakaoUserId: uid,
      basicInfo: {
        'lifestyle': {
          'drinking': drinking,
          'smoking': smoking,
          'exercise': exercise,
          'religion': religion,
        },
      },
    );
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

  /// Step 6: 사진
  static Future<void> savePhotos(List<String> photoUrls) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.saveOnboardingPhotos(
      kakaoUserId: uid,
      photoUrls: photoUrls,
    );
  }

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
      interests: [],
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

  static Future<void> saveIdealPersonalityAndComplete(
    List<String> keywords,
  ) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _saveIdealInfoFromDraft(uid);
    await _userService.updateIdealTypeField(
      kakaoUserId: uid,
      fieldName: 'preferredPersonalities',
      value: keywords,
    );
    await _userService.completeOnboarding(uid);
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

  /// Step 10: 이상형 라이프스타일 + 온보딩 완료
  static Future<void> saveIdealLifestyleAndComplete({
    required String? drinking,
    required String? smoking,
    required String? exercise,
    required String? religion,
  }) async {
    final uid = await _getUserId();
    if (uid == null) return;
    await saveIdealLifestyle(
      drinking: drinking,
      smoking: smoking,
      exercise: exercise,
      religion: religion,
    );
    await _userService.completeOnboarding(uid);
  }

  /// 이상형 건너뛰기
  static Future<void> skipIdealType() async {
    final uid = await _getUserId();
    if (uid == null) return;
    await _userService.skipIdealType(uid);
    await _userService.completeOnboarding(uid);
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
