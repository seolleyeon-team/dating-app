import 'package:cloud_firestore/cloud_firestore.dart';

class UserService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  // ---------------------------------------------------------------------------
  // 카카오 유저 생성/갱신
  // ---------------------------------------------------------------------------

  Future<void> upsertKakaoUser({
    required String kakaoUserId,
    required String? nickname,
    required String? profileImageUrl,
    String? email,
    Map<String, dynamic>? extraFields,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final now = FieldValue.serverTimestamp();

    final snapshot = await docRef.get();
    if (!snapshot.exists) {
      final data = {
        'kakaoUserId': kakaoUserId,
        'nickname': nickname,
        'profileImageUrl': profileImageUrl,
        'email': email,
        'createdAt': now,
        'lastLoginAt': now,
      };
      if (extraFields != null) {
        data.addAll(extraFields);
      }
      await docRef.set(data);
      return;
    }

    final updateData = {
      'nickname': nickname,
      'profileImageUrl': profileImageUrl,
      'email': email,
      'lastLoginAt': now,
    };
    if (extraFields != null) {
      updateData.addAll(extraFields);
    }
    await docRef.update(updateData);
  }

  Future<bool> existsKakaoUser(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    return doc.exists;
  }

  // ---------------------------------------------------------------------------
  // 온보딩 상태
  // ---------------------------------------------------------------------------

  Future<bool> isInitialSetupComplete(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return false;
    final data = doc.data();
    final v = data?['initialSetupComplete'];
    if (v == true || v == 'true' || (v is num && v != 0)) return true;
    // initialSetupComplete가 명시적으로 true일 때만 완료. 온보딩 중간에 나갔다 들어와도 온보딩으로 복귀
    return false;
  }

  Future<bool> hasSeenTutorial(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return false;
    final data = doc.data();
    return data?['hasSeenTutorial'] == true;
  }

  Future<void> setTutorialSeen(String kakaoUserId) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'hasSeenTutorial': true,
    }, SetOptions(merge: true));
  }

  // ---------------------------------------------------------------------------
  // 프로필 조회
  // ---------------------------------------------------------------------------

  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    return doc.data();
  }

  // ---------------------------------------------------------------------------
  // 학생 인증
  // ---------------------------------------------------------------------------

  Future<bool> isStudentVerified(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return false;
    final data = doc.data();
    final v = data?['isStudentVerified'];
    return v == true || v == 'true' || (v is num && v != 0);
  }

  Future<String?> getStudentEmail(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return null;
    final data = doc.data();
    return data?['studentEmail']?.toString();
  }

  Future<void> setStudentVerification({
    required String kakaoUserId,
    required String studentEmail,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'studentEmail': studentEmail,
      'isStudentVerified': true,
      'studentVerifiedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  // ---------------------------------------------------------------------------
  // 온보딩 정보 저장 (단계별 merge)
  // ---------------------------------------------------------------------------

  /// 온보딩 기본 정보 (성별, 나이, 키, MBTI 등) — 기존 onboarding에 병합 후 저장, 완료 플래그 설정
  Future<void> saveOnboardingBasicInfo({
    required String kakaoUserId,
    required Map<String, dynamic> basicInfo,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();
    final Map<String, dynamic> mergedOnboarding = {};
    if (doc.exists) {
      final existing = doc.data()?['onboarding'];
      if (existing is Map) {
        for (final e in existing.entries) {
          mergedOnboarding[e.key.toString()] = e.value;
        }
      }
    }
    for (final e in basicInfo.entries) {
      mergedOnboarding[e.key.toString()] = e.value;
    }
    await docRef.set({
      'onboarding': mergedOnboarding,
      'onboardingUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 온보딩 사진 URL 저장
  Future<void> saveOnboardingPhotos({
    required String kakaoUserId,
    required List<String> photoUrls,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();

    final Map<String, dynamic> mergedOnboarding = {};

    if (doc.exists) {
      final existing = doc.data()?['onboarding'];
      if (existing is Map) {
        for (final e in existing.entries) {
          mergedOnboarding[e.key.toString()] = e.value;
        }
      }
    }

    mergedOnboarding['photoUrls'] = photoUrls;

    await docRef.set({
      'onboarding': mergedOnboarding,
      'onboardingUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 온보딩 키워드/관심사 저장
  Future<void> saveOnboardingKeywords({
    required String kakaoUserId,
    required List<String> keywords,
    required List<String> interests,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();

    final Map<String, dynamic> mergedOnboarding = {};

    if (doc.exists) {
      final existing = doc.data()?['onboarding'];
      if (existing is Map) {
        for (final e in existing.entries) {
          mergedOnboarding[e.key.toString()] = e.value;
        }
      }
    }

    mergedOnboarding['keywords'] = keywords;
    mergedOnboarding['interests'] = interests;

    await docRef.set({
      'onboarding': mergedOnboarding,
      'onboardingUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 온보딩 프로필 문답 저장
  Future<void> saveOnboardingProfileQa({
    required String kakaoUserId,
    required List<Map<String, String>> profileQa,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();

    final Map<String, dynamic> mergedOnboarding = {};

    if (doc.exists) {
      final existing = doc.data()?['onboarding'];
      if (existing is Map) {
        for (final e in existing.entries) {
          mergedOnboarding[e.key.toString()] = e.value;
        }
      }
    }

    mergedOnboarding['profileQa'] = profileQa;

    await docRef.set({
      'onboarding': mergedOnboarding,
      'onboardingUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 온보딩 완료 플래그
  Future<void> completeOnboarding(String kakaoUserId) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'initialSetupComplete': true,
      'onboardingCompletedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  // ---------------------------------------------------------------------------
  // 이상형 정보 저장
  // ---------------------------------------------------------------------------

  /// 이상형 전체 저장 (한 번에 또는 마지막 단계 완료 시)
  Future<void> saveIdealType({
    required String kakaoUserId,
    required Map<String, dynamic> idealType,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'idealType': idealType,
      'idealTypeUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 이상형 부분 업데이트 (키, 나이, MBTI, 학과, 성격, 라이프스타일 각각)
  Future<void> updateIdealTypeField({
    required String kakaoUserId,
    required String fieldName,
    required dynamic value,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'idealType': {fieldName: value},
      'idealTypeUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 이상형 설정 건너뛰기
  Future<void> skipIdealType(String kakaoUserId) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'idealType': {'skipped': true},
      'idealTypeUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  /// 이상형 정보 조회
  Future<Map<String, dynamic>?> getIdealType(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return null;
    return doc.data()?['idealType'] as Map<String, dynamic>?;
  }

  Future<int> getOnboardingStep(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();

    if (!doc.exists) return 0;

    final data = doc.data();
    final onboarding = data?['onboarding'];

    if (onboarding == null) return 1;

    if (onboarding['basicInfo'] == null) return 1;
    if (onboarding['photoUrls'] == null ||
        (onboarding['photoUrls'] as List).length < 2)
      return 5;
    if (onboarding['keywords'] == null) return 6;
    if (onboarding['profileQa'] == null) return 7;

    return 8;
  }
}
