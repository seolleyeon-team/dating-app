import 'package:cloud_firestore/cloud_firestore.dart';

import '../constants/campus_life_zones.dart';
import '../constants/legal_texts.dart';

class UserService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

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

  Future<void> reactivateForRejoin({
    required String kakaoUserId,
    required String? nickname,
    required String? profileImageUrl,
    String? email,
  }) async {
    final docRef = _firestore.collection('users').doc(kakaoUserId);
    final doc = await docRef.get();
    final data = doc.data();
    if (data == null) return;

    if (await isRejoinRestricted(kakaoUserId)) {
      throw StateError('재가입이 제한된 계정입니다.');
    }
    if (data['status'] != 'withdrawn' && data['isWithdrawn'] != true) {
      return;
    }

    await docRef.update({
      'status': 'active',
      'isWithdrawn': false,
      'canRejoin': true,
      'rejoinRestricted': false,
      'loginDisabled': false,
      'profileVisible': true,
      'nickname': nickname,
      'profileImageUrl': profileImageUrl,
      'email': email,
      'isStudentVerified': false,
      'studentEmail': FieldValue.delete(),
      'studentVerifiedAt': FieldValue.delete(),
      'verifiedAt': FieldValue.delete(),
      'onboarding': FieldValue.delete(),
      'onboardingUpdatedAt': FieldValue.delete(),
      'initialSetupComplete': false,
      'initialSetupCompletedAt': FieldValue.delete(),
      'onboardingCompletedAt': FieldValue.delete(),
      'hasSeenTutorial': false,
      'idealType': FieldValue.delete(),
      'idealTypeUpdatedAt': FieldValue.delete(),
      'rejoinedAt': FieldValue.serverTimestamp(),
      'lastLoginAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });

    await _restoreRejoinedUserInChatRooms(
      kakaoUserId: kakaoUserId,
      nickname: nickname,
      profileImageUrl: profileImageUrl,
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

  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    final doc = await _firestore.collection('users').doc(kakaoUserId).get();
    return doc.data();
  }

  Future<void> savePrivacySettings({
    required String kakaoUserId,
    required Map<String, dynamic> privacySettings,
  }) async {
    await _firestore.collection('users').doc(kakaoUserId).set({
      'privacySettings': privacySettings,
      'privacySettingsUpdatedAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  Future<void> withdrawAccount({
    required String kakaoUserId,
    String? reason,
  }) async {
    final now = DateTime.now();
    final scheduledHardDeleteAt = Timestamp.fromDate(
      now.add(const Duration(days: withdrawalRetentionDays)),
    );

    final userRef = _firestore.collection('users').doc(kakaoUserId);
    await userRef.update({
      'status': 'withdrawn',
      'isWithdrawn': true,
      'withdrawnAt': FieldValue.serverTimestamp(),
      'scheduledHardDeleteAt': scheduledHardDeleteAt,
      'withdrawalRetentionDays': withdrawalRetentionDays,
      if (reason != null && reason.trim().isNotEmpty)
        'withdrawalReason': reason.trim(),
      'profileVisible': false,
      'canRejoin': true,
      'rejoinRestricted': false,
      'loginDisabled': false,
      'nickname': withdrawnDisplayName,
      'profileImageUrl': FieldValue.delete(),
      'email': FieldValue.delete(),
      'studentEmail': FieldValue.delete(),
      'isStudentVerified': false,
      'onboarding': {
        'nickname': withdrawnDisplayName,
        'photoUrls': <String>[],
        'interests': <String>[],
        'keywords': <String>[],
        'profileQa': <Map<String, String>>[],
        'selfIntroduction': '',
      },
      'idealType': FieldValue.delete(),
      'preferenceVector': FieldValue.delete(),
      'privacySettings': {
        'avoidSameDepartment': false,
        'profileVisible': false,
      },
      'withdrawalPolicy': {
        'mode': 'soft_delete',
        'retentionDays': withdrawalRetentionDays,
        'reason': '신고, 제재, 분쟁 및 이용자 보호 대응을 위해 최소 정보만 임시 보관합니다.',
      },
      'updatedAt': FieldValue.serverTimestamp(),
    });

    await _maskWithdrawnUserInChatRooms(kakaoUserId);
  }

  Future<void> _maskWithdrawnUserInChatRooms(String kakaoUserId) async {
    final rooms = await _firestore
        .collection('chat_rooms')
        .where('participantIds', arrayContains: kakaoUserId)
        .get();

    WriteBatch batch = _firestore.batch();
    var writeCount = 0;

    Future<void> commitIfNeeded({bool force = false}) async {
      if (writeCount == 0) return;
      if (!force && writeCount < 420) return;
      await batch.commit();
      batch = _firestore.batch();
      writeCount = 0;
    }

    for (final room in rooms.docs) {
      final roomRef = room.reference;
      final noticeRef = roomRef.collection('messages').doc();

      batch.set(roomRef, {
        'participantInfo.$kakaoUserId.nickname': withdrawnDisplayName,
        'participantInfo.$kakaoUserId.avatarUrl': '',
        'participantInfo.$kakaoUserId.isWithdrawn': true,
        'participantInfo.$kakaoUserId.withdrawnAt':
            FieldValue.serverTimestamp(),
        'withdrawnParticipantIds': FieldValue.arrayUnion([kakaoUserId]),
        'lastMessage': '상대방이 계정을 탈퇴했어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
      writeCount += 1;

      batch.set(noticeRef, {
        'senderId': 'system',
        'text': '상대방이 계정을 탈퇴했어요. 더 이상 메시지를 보낼 수 없습니다.',
        'type': 'account_withdrawn',
        'readBy': const <String>[],
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });
      writeCount += 1;

      await commitIfNeeded();
    }

    await commitIfNeeded(force: true);
  }

  Future<void> _restoreRejoinedUserInChatRooms({
    required String kakaoUserId,
    required String? nickname,
    required String? profileImageUrl,
  }) async {
    final rooms = await _firestore
        .collection('chat_rooms')
        .where('participantIds', arrayContains: kakaoUserId)
        .get();

    WriteBatch batch = _firestore.batch();
    var writeCount = 0;

    Future<void> commitIfNeeded({bool force = false}) async {
      if (writeCount == 0) return;
      if (!force && writeCount < 430) return;
      await batch.commit();
      batch = _firestore.batch();
      writeCount = 0;
    }

    for (final room in rooms.docs) {
      final data = room.data();
      final lastMessage = data['lastMessage']?.toString() ?? '';

      batch.set(room.reference, {
        'participantInfo.$kakaoUserId.nickname':
            (nickname != null && nickname.trim().isNotEmpty)
            ? nickname.trim()
            : '사용자',
        'participantInfo.$kakaoUserId.avatarUrl': profileImageUrl ?? '',
        'participantInfo.$kakaoUserId.isWithdrawn': FieldValue.delete(),
        'participantInfo.$kakaoUserId.withdrawnAt': FieldValue.delete(),
        'withdrawnParticipantIds': FieldValue.arrayRemove([kakaoUserId]),
        if (lastMessage == '상대방이 계정을 탈퇴했어요') ...{
          'lastMessage': '채팅을 다시 시작해 보세요',
          'lastMessageAt': FieldValue.serverTimestamp(),
        },
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
      writeCount += 1;

      final withdrawalMessages = await room.reference
          .collection('messages')
          .where('type', isEqualTo: 'account_withdrawn')
          .get();
      for (final message in withdrawalMessages.docs) {
        batch.update(message.reference, {
          'hiddenAfterRejoin': true,
          'updatedAt': FieldValue.serverTimestamp(),
        });
        writeCount += 1;
        await commitIfNeeded();
      }

      await commitIfNeeded();
    }

    await commitIfNeeded(force: true);
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

    final campusLifeZone = CampusLifeZoneResolver.resolve(
      grade: mergedOnboarding['grade']?.toString(),
      department: mergedOnboarding['department']?.toString(),
      isRa: mergedOnboarding['isRa'] == true,
    );
    if (campusLifeZone != null) {
      mergedOnboarding['campusLifeZones'] = campusLifeZone.zones;
      mergedOnboarding['campusLifeZoneLabels'] = campusLifeZone.labels;
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
        (onboarding['photoUrls'] as List).length < 2) {
      return 5;
    }
    if (onboarding['keywords'] == null) return 6;
    if (onboarding['profileQa'] == null) return 7;

    return 8;
  }
}
