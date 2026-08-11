import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import 'storage_service.dart';
import 'user_service.dart';

// =============================================================================
// 공통 AI 추천 프로필 모델
// =============================================================================
class AiRecommendedProfile {
  final String candidateUid;
  final String name;
  final int age;
  final String major;
  final String bio;
  final String university;
  final List<String> imageUrls;
  final List<String> tags;
  final int rank;
  final String primaryAlgo;
  final num? sourceScores; // SVD, KNN 등에서 넘어온 스코어
  final String dateKey;
  final num? finalScore;
  final Map<String, dynamic>? flags;
  final String exposureId;

  const AiRecommendedProfile({
    required this.candidateUid,
    required this.name,
    required this.age,
    required this.major,
    this.bio = '',
    this.university = '',
    required this.imageUrls,
    this.tags = const [],
    required this.rank,
    required this.primaryAlgo,
    this.sourceScores,
    required this.dateKey,
    this.finalScore,
    this.flags,
    required this.exposureId,
  });
}

// =============================================================================
// 실제 AI 추천 피드 패치 및 프로필 병합 서비스
// =============================================================================
class AiRecommendationService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final UserService _userService = UserService();
  final StorageService _storageService = StorageService();

  /// blocks/{uid}/targets/* 에서 차단된 UID 세트를 가져온다.
  Future<Set<String>> _fetchBlockedUids(String uid) async {
    try {
      final snap = await _firestore
          .collection('blocks')
          .doc(uid)
          .collection('targets')
          .get();
      return snap.docs.map((d) => d.id).toSet();
    } catch (e) {
      debugPrint('[AI] _fetchBlockedUids error: $e');
      return {};
    }
  }

  /// KST 기준 YYYYMMDD 날짜 키 생성
  String _generateKstDateKey(DateTime dateTime) {
    // Dart의 DateTime은 시스템 로케일을 따르거나 UTC입니다.
    // KST(UTC+9)로 안전하게 변환
    final kst = dateTime.toUtc().add(const Duration(hours: 9));
    final y = kst.year.toString();
    final m = kst.month.toString().padLeft(2, '0');
    final d = kst.day.toString().padLeft(2, '0');
    return '$y$m$d';
  }

  /// 실제 Firestore 경로에서 추천 배열을 가져옵니다.
  /// 없으면 어제 날짜로 폴백.
  Future<Map<String, dynamic>?> _fetchRawRecs(String uid, String algo) async {
    final today = DateTime.now();
    final todayKey = _generateKstDateKey(today);

    // 1순위: 오늘자 추천 피드
    DocumentSnapshot snap = await _firestore
        .collection('modelRecs')
        .doc(uid)
        .collection('daily')
        .doc(todayKey)
        .collection('sources')
        .doc(algo)
        .get();

    if (snap.exists && snap.data() != null) {
      return {'dateKey': todayKey, 'data': snap.data()};
    }

    // 2순위: 어제자 추천 피드 fallback
    final yesterday = today.subtract(const Duration(days: 1));
    final yesterdayKey = _generateKstDateKey(yesterday);

    snap = await _firestore
        .collection('modelRecs')
        .doc(uid)
        .collection('daily')
        .doc(yesterdayKey)
        .collection('sources')
        .doc(algo)
        .get();

    if (snap.exists && snap.data() != null) {
      return {'dateKey': yesterdayKey, 'data': snap.data()};
    }

    return null;
  }

  /// 후보자 UID 리스트를 순회하며 User 프로필(이미지, 기본 정보)을 Hydrate
  Future<List<AiRecommendedProfile>> _hydrateProfiles({
    required List<dynamic> rawItems,
    required String algo,
    required String dateKey,
    required int limit,
    Set<String> blockedUids = const {},
  }) async {
    final List<AiRecommendedProfile> results = [];
    final uuid = const Uuid();

    // 순위를 보장하기 위해 items 안의 rank나 순서를 기반으로 정렬 (Python 스크립트는 이미 rank 순 정렬)
    final sortedItems = List.from(rawItems);
    sortedItems.sort((a, b) {
      final rankA = (a['rank'] as num?)?.toInt() ?? 999;
      final rankB = (b['rank'] as num?)?.toInt() ?? 999;
      return rankA.compareTo(rankB);
    });

    for (final item in sortedItems.take(limit + blockedUids.length)) {
      if (results.length >= limit) break;

      final candUid = item['uid'] as String?;
      if (candUid == null) continue;

      // 차단된 사용자 제외
      if (blockedUids.contains(candUid)) continue;

      // 1. 추천 문서 자체에 이미지가 있는지 확인 (미래 확장성)
      List<String> images = [];
      if (item['imageUrls'] != null) {
        images = List<String>.from(item['imageUrls']);
      }

      // 2. Fallback: users/{uid} 문서에서 onboarding.photoUrls 조회
      final userProfile = await _userService.getUserProfile(candUid);
      if (userProfile == null) continue; // 삭제/탈퇴된 유저 패스

      final onboarding = userProfile['onboarding'];
      if (images.isEmpty && onboarding is Map) {
        final photos = onboarding['photoUrls'];
        if (photos is List && photos.isNotEmpty) {
          images = List<String>.from(photos);
        } else {
          // 사진이 한장도 없으면 렌더링에 문제가 생길 수 있으므로 최소 Fallback
          // images = ['https://placeholder.com/default']; // 기획에 따라 처리 가능. 여기선 빈 리스트 허용
        }
      }

      // 데이터 매핑
      final nickname = userProfile['nickname'] as String? ??
          (onboarding is Map ? onboarding['nickname'] as String? : null) ??
          '익명';
      
      // 나이 계산 (출생년도 기준 대략적 나이 또는 직접 입력값 반영)
      int age = 20;
      if (onboarding is Map && onboarding['birthYear'] != null) {
        final birthYear = int.tryParse(onboarding['birthYear'].toString());
        if (birthYear != null) {
          age = DateTime.now().year - birthYear;
        }
      }

      final major = (onboarding is Map) ? (onboarding['major'] as String? ?? '전공 미상') : '전공 미상';
      final bio = (onboarding is Map) ? (onboarding['bio'] as String? ?? '') : '';
      final university = (onboarding is Map) ? (onboarding['university'] as String? ?? '') : '';

      List<String> tags = [];
      if (onboarding is Map) {
        if (onboarding['keywords'] is List) {
          tags.addAll(List<String>.from(onboarding['keywords']));
        }
        if (onboarding['interests'] is List) {
          tags.addAll(List<String>.from(onboarding['interests']));
        }
      }

      results.add(
        AiRecommendedProfile(
          candidateUid: candUid,
          name: nickname,
          age: age,
          major: major,
          bio: bio,
          university: university,
          imageUrls: images,
          tags: tags,
          rank: (item['rank'] as num?)?.toInt() ?? 999,
          primaryAlgo: algo,
          sourceScores: item['score'] as num?,
          dateKey: dateKey,
          exposureId: uuid.v4(),
        ),
      );
    }

    return results;
  }

  /// modelRecs 비어있을 때 users 컬렉션에서 폴백 프로필 로드
  Future<List<AiRecommendedProfile>> _fetchFallbackFromUsers(
    String currentUserId,
    int limit, {
    Set<String> blockedUids = const {},
  }) async {
    final uuid = const Uuid();
    final todayKey = _generateKstDateKey(DateTime.now());
    final snapshot = await _firestore
        .collection('users')
        .limit(30) // 본인 제외·필터 후 limit 채우기 위해 여유
        .get();

    final results = <AiRecommendedProfile>[];
    for (final doc in snapshot.docs) {
      if (doc.id == currentUserId) continue;
      if (blockedUids.contains(doc.id)) continue;
      if (results.length >= limit) break;

      final data = doc.data();
      if (data['isStudentVerified'] != true) continue;

      final onboarding = data['onboarding'];
      if (onboarding is! Map) continue;

      final photoUrls = onboarding['photoUrls'];
      final images = photoUrls is List && photoUrls.isNotEmpty
          ? List<String>.from(photoUrls)
          : <String>[];
      if (images.isEmpty) continue; // 사진 있는 유저만

      final nickname = onboarding['nickname'] as String? ?? '익명';
      int age = 20;
      final birthYear = onboarding['birthYear'];
      if (birthYear != null) {
        final y = int.tryParse(birthYear.toString());
        if (y != null) age = DateTime.now().year - y;
      }
      final major = onboarding['major'] as String? ?? '전공 미상';

      results.add(
        AiRecommendedProfile(
          candidateUid: doc.id,
          name: nickname,
          age: age,
          major: major,
          bio: '',
          university: '',
          imageUrls: images,
          tags: [],
          rank: 999,
          primaryAlgo: 'fallback',
          dateKey: todayKey,
          exposureId: uuid.v4(),
        ),
      );
    }
    return results;
  }

  /// Profile Card (일반 스와이프 추천) 피드를 불러옵니다.
  /// modelRecs 없으면 users 폴백 사용.
  Future<List<AiRecommendedProfile>> fetchProfileFeed({
    int limit = 10,
    String? userId,
  }) async {
    final uid = userId ?? await _resolveUid();
    if (uid == null || uid.isEmpty) return [];

    try {
      final blockedUids = await _fetchBlockedUids(uid);

      var result = await _fetchRawRecs(uid, 'svd');
      if (result != null) {
        final data = result['data'] as Map<String, dynamic>;
        final dateKey = result['dateKey'] as String;
        final items = data['items'] as List<dynamic>? ?? [];
        return await _hydrateProfiles(
          rawItems: items,
          algo: 'svd',
          dateKey: dateKey,
          limit: limit,
          blockedUids: blockedUids,
        );
      }
      if (kDebugMode) debugPrint('[AI] fetchProfileFeed: modelRecs empty, using users fallback');
      return await _fetchFallbackFromUsers(uid, limit, blockedUids: blockedUids);
    } catch (e) {
      debugPrint('fetchProfileFeed Error: $e');
      if (kDebugMode) debugPrint('[AI] fetchProfileFeed: error, trying users fallback');
      return await _fetchFallbackFromUsers(uid, limit);
    }
  }

  /// Mystery Card (RRF 통합 / CLIP / SVD) 피드를 불러옵니다.
  /// modelRecs/{uid}/daily/{오늘}/sources/rrf 의 rank 1~3 순서대로 표시.
  /// modelRecs 없으면 users 폴백 사용.
  Future<List<AiRecommendedProfile>> fetchMysteryFeed({
    int limit = 3,
    String? userId,
  }) async {
    final uid = userId ?? await _resolveUid();
    if (uid == null || uid.isEmpty) return [];

    try {
      final blockedUids = await _fetchBlockedUids(uid);

      var result = await _fetchRawRecs(uid, 'rrf');
      String algoUsed = 'rrf';

      if (result == null) {
        result = await _fetchRawRecs(uid, 'clip');
        algoUsed = 'clip';
      }
      if (result == null) {
        result = await _fetchRawRecs(uid, 'svd');
        algoUsed = 'svd';
      }

      if (result != null) {
        final data = result['data'] as Map<String, dynamic>;
        final dateKey = result['dateKey'] as String;
        var items = data['items'] as List<dynamic>? ?? [];

        // RRF인 경우 rank 1~3만 필터, 순서 보장
        if (algoUsed == 'rrf') {
          items = items
              .where((item) {
                final r = (item['rank'] as num?)?.toInt() ?? 999;
                return r >= 1 && r <= 3;
              })
              .toList()
            ..sort((a, b) {
              final rankA = (a['rank'] as num?)?.toInt() ?? 999;
              final rankB = (b['rank'] as num?)?.toInt() ?? 999;
              return rankA.compareTo(rankB);
            });
        }

        return await _hydrateProfiles(
          rawItems: items,
          algo: algoUsed,
          dateKey: dateKey,
          limit: limit,
          blockedUids: blockedUids,
        );
      }
      if (kDebugMode) debugPrint('[AI] fetchMysteryFeed: modelRecs empty, using users fallback');
      return await _fetchFallbackFromUsers(uid, limit, blockedUids: blockedUids);
    } catch (e) {
      debugPrint('fetchMysteryFeed Error: $e');
      if (kDebugMode) debugPrint('[AI] fetchMysteryFeed: error, trying users fallback');
      return await _fetchFallbackFromUsers(uid, limit);
    }
  }

  Future<String?> _resolveUid() async {
    final firebaseUid = FirebaseAuth.instance.currentUser?.uid;
    if (firebaseUid != null && firebaseUid.isNotEmpty) return firebaseUid;
    return await _storageService.getKakaoUserId();
  }
}
