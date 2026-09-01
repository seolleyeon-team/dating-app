import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import '../constants/campus_life_zones.dart';
import '../constants/legal_texts.dart';
import 'onboarding_write_payload.dart';

class UserService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: 'asia-northeast3',
  );
  final FirebaseAuth _auth = FirebaseAuth.instance;

  static const String withdrawnDisplayName = '탈퇴한 사용자';
  static const int withdrawalRetentionDays = 30;

  Future<void> setLastActivePlatform({
    required String kakaoUserId,
    required String platform,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'lastActivePlatform': platform,
      'lastActivePlatformUpdatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

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

  Future<bool> isAccountWithdrawn(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    final data = doc.data();
    if (data == null) return false;
    return data['status'] == 'withdrawn' || data['isWithdrawn'] == true;
  }

  Future<bool> isRejoinRestricted(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    final data = doc.data();
    if (data == null) return false;

    final restrictedUntil = data['rejoinRestrictedUntil'];
    final isStillRestricted =
        restrictedUntil is Timestamp &&
        restrictedUntil.toDate().isAfter(DateTime.now());

    return data['status'] == 'banned' ||
        data['status'] == 'restricted_rejoin' ||
        data['rejoinRestricted'] == true ||
        data['canRejoin'] == false ||
        data['loginDisabled'] == true ||
        isStillRestricted;
  }

  /// Legacy soft-rejoin path is disabled. Hard-deleted accounts re-onboard via
  /// Kakao bootstrap as a new shell; clients must not mutate moderation fields.
  Future<void> reactivateForRejoin({
    required String kakaoUserId,
    required String? nickname,
    required String? profileImageUrl,
    String? email,
  }) async {
    throw UnsupportedError(
      'Client rejoin reactivation is disabled. Complete Kakao sign-in to create a fresh account shell.',
    );
  }

  // ---------------------------------------------------------------------------
  // 필수 약관/개인정보 동의 저장
  // ---------------------------------------------------------------------------

  Future<void> saveLegalConsents({
    required String kakaoUserId,
    Map<String, dynamic>? consentData,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'legalConsents': {
        'termsOfService': _readConsentBool(
          consentData?['termsOfService'],
          fallback: true,
        ),
        'privacyPolicy': _readConsentBool(
          consentData?['privacyPolicy'],
          fallback: true,
        ),
        'kakaoNamePhone': _readConsentBool(
          consentData?['kakaoNamePhone'],
          fallback: true,
        ),
        'ageOver20': _readConsentBool(
          consentData?['ageOver20'],
          fallback: true,
        ),
        'ageOver18': _readConsentBool(
          consentData?['ageOver18'] ?? consentData?['ageOver14'],
          fallback: true,
        ),
        'ageOver14': FieldValue.delete(),
        'agreedAt': FieldValue.serverTimestamp(),
        if (consentData?['agreedAtClientIso'] != null)
          'agreedAtClientIso': consentData!['agreedAtClientIso'],
        'version': consentData?['version']?.toString() ?? LegalTexts.version,
      },
    }, SetOptions(merge: true));
  }

  bool _readConsentBool(dynamic value, {required bool fallback}) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    if (value is String) return value.toLowerCase() == 'true';
    return fallback;
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

  /// Own private `users/{uid}` when [kakaoUserId] is the signed-in user;
  /// otherwise AUTHENTICATED_LIMITED_PROFILE from `publicProfiles/{uid}`.
  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    final selfUid = _auth.currentUser?.uid;
    if (selfUid != null && selfUid == kakaoUserId) {
      final doc = await _firestore.collection('users').doc(kakaoUserId).get();
      return doc.data();
    }
    return getPublicProfile(kakaoUserId);
  }

  Future<Map<String, dynamic>?> getPublicProfile(String uid) async {
    final doc = await _firestore.collection('publicProfiles').doc(uid).get();
    return doc.data();
  }

  Future<void> savePrivacySettings({
    required String kakaoUserId,
    required Map<String, dynamic> privacySettings,
  }) async {
    final updateData = buildPrivacyFieldUpdates(privacySettings);
    updateData['updatedAt'] = FieldValue.serverTimestamp();
    await _firestore.collection('users').doc(kakaoUserId).update(updateData);
  }

  /// Requests server-orchestrated hard deletion. Success only after callable
  /// returns `completed`. Does not mutate protected moderation fields client-side.
  Future<void> withdrawAccount({
    required String kakaoUserId,
    String? reason,
  }) async {
    // Local reason is accepted for API compatibility but never logged or
    // written client-side; server owns withdrawal moderation fields.
    final clientRequestId =
        'account_deletion_${DateTime.now().millisecondsSinceEpoch}';
    final callable = _functions.httpsCallable('cleanupAvatarMedia');
    final result = await callable.call<Map<String, dynamic>>({
      'reason': 'account_deletion',
      'clientRequestId': clientRequestId,
    });
    final data = result.data;
    final status = data['status']?.toString();
    if (status != 'completed') {
      throw StateError('account_deletion_incomplete');
    }
    // Preserve API surface; server owns audit reason fields.
    void keepCompat(String? value) {}
    keepCompat(reason);
  }

  // ---------------------------------------------------------------------------
  // 학생 인증
  // ---------------------------------------------------------------------------

  Future<bool> isStudentVerified(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    if (!doc.exists) return false;
    final data = doc.data();
    final v = data?['isStudentVerified'];
    return v == true;
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
  /// Saves only fields owned by the current onboarding step.
  Future<void> saveOnboardingBasicInfo({
    required String kakaoUserId,
    required Map<String, dynamic> basicInfo,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();
    final mergedOnboarding = <String, dynamic>{};

    if (doc.exists) {
      final existing = doc.data()?['onboarding'];
      if (existing is Map) {
        for (final entry in existing.entries) {
          mergedOnboarding[entry.key.toString()] = entry.value;
        }
      }
    }
    mergedOnboarding.addAll(basicInfo);

    final campusLifeZone = CampusLifeZoneResolver.resolve(
      grade: mergedOnboarding['grade']?.toString(),
      department: mergedOnboarding['department']?.toString(),
      isRa: mergedOnboarding['isRa'] == true,
    );

    final fieldsToWrite = <String, dynamic>{...basicInfo};
    if (campusLifeZone != null) {
      fieldsToWrite['campusLifeZones'] = campusLifeZone.zones;
      fieldsToWrite['campusLifeZoneLabels'] = campusLifeZone.labels;
    }

    await docRef.update(buildOnboardingFieldUpdates(fieldsToWrite));
  }

  // onboarding.photoUrls 클라이언트 쓰기는 firestore.rules의
  // onboardingAvatarPhotoFieldsUnchanged 가드가 거부하므로 저장 API를 두지 않는다.

  /// Saves interests only. Keyword writes must use saveOnboardingKeywords.
  Future<void> saveOnboardingInterests({
    required String kakaoUserId,
    required List<String> interests,
  }) async {
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(
          buildOnboardingFieldUpdate(fieldName: 'interests', value: interests),
        );
  }

  /// Saves keywords only. Interest writes must use saveOnboardingInterests.
  Future<void> saveOnboardingKeywords({
    required String kakaoUserId,
    required List<String> keywords,
  }) async {
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(
          buildOnboardingFieldUpdate(fieldName: 'keywords', value: keywords),
        );
  }

  /// Saves profile Q&A without replacing other onboarding fields.
  Future<void> saveOnboardingProfileQa({
    required String kakaoUserId,
    required List<Map<String, String>> profileQa,
  }) async {
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(
          buildOnboardingFieldUpdate(fieldName: 'profileQa', value: profileQa),
        );
  }

  /// Completes onboarding after the final ideal-type step.
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
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(buildIdealTypeFieldUpdates(idealType));
  }

  /// 이상형 부분 업데이트 (키, 나이, MBTI, 학과, 성격, 라이프스타일 각각)
  Future<void> updateIdealTypeField({
    required String kakaoUserId,
    required String fieldName,
    required dynamic value,
  }) async {
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(buildIdealTypeFieldUpdate(fieldName: fieldName, value: value));
  }

  /// 이상형 설정 건너뛰기
  Future<void> skipIdealType(String kakaoUserId) async {
    await _firestore
        .collection('users')
        .doc(kakaoUserId)
        .update(buildIdealTypeFieldUpdate(fieldName: 'skipped', value: true));
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
        (onboarding['photoUrls'] as List).length < 2) {
      return 5;
    }
    if (onboarding['keywords'] == null) return 6;
    if (onboarding['profileQa'] == null) return 7;

    return 8;
  }
}
