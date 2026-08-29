import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import 'storage_service.dart';
import 'user_service.dart';
import '../shared/utils/privacy_log_utils.dart';
import '../shared/utils/recommendation_eligibility.dart';
import 'campus_life_zone_repair_service.dart';

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
  final CampusLifeZoneRepairService _campusLifeZoneRepairService =
      CampusLifeZoneRepairService();
  final StorageService _storageService = StorageService();

  /// blocks/{uid}/targets/* 에서 차단된 UID 세트를 가져온다.
  Future<Set<String>> _fetchBlockedUids(String uid) async {
    // Safety/privacy filters must never fall back to an empty set. Requiring a
    // server response also prevents an offline stale cache from reopening a
    // recommendation that was excluded on another device.
    final snap = await _firestore
        .collection('blocks')
        .doc(uid)
        .collection('targets')
        .get(const GetOptions(source: Source.server));
    return snap.docs.map((d) => d.id).toSet();
  }

  /// Recommendation-only exclusions are separate from safety blocks because
  /// Kakao friend privacy must not disable chat, push, or other meeting flows.
  /// A read failure is allowed to propagate so the feed fails closed.
  Future<Set<String>> _fetchRecommendationExcludedUids(String uid) async {
    final snap = await _firestore
        .collection('recommendationExclusions')
        .doc(uid)
        .collection('targets')
        .get(const GetOptions(source: Source.server));
    final excluded = <String>{};
    for (final doc in snap.docs) {
      final enabledBy = doc.data()['enabledBy'];
      final active = doc.data()['active'] == true;
      if (active ||
          (enabledBy is Map &&
              enabledBy.values.any((value) => value == true))) {
        excluded.add(doc.id);
      }
    }
    return excluded;
  }

  Future<bool> _isViewerRecommendationPrivacyReady(String uid) async {
    final snapshot = await _firestore
        .collection('users')
        .doc(uid)
        .get(const GetOptions(source: Source.server));
    final profile = snapshot.data();
    if (profile == null) return false;
    // Missing is not ready: legacy accounts must also reconcile before they
    // can receive recommendations.
    return profile['recommendationPrivacyReady'] == true;
  }

  /// Server-authoritative state used by recommendation screens to distinguish
  /// missing Kakao consent from a genuinely empty recommendation day.
  Future<bool> isViewerRecommendationPrivacyReady(String uid) {
    return _isViewerRecommendationPrivacyReady(uid);
  }

  /// Keeps already-rendered cards from surviving an ON/OFF change made in a
  /// different tab or on the other member's device.
  Stream<void> watchRecommendationPrivacyChanges(String uid) {
    late final StreamController<void> controller;
    StreamSubscription<DocumentSnapshot<Map<String, dynamic>>>? userSub;
    StreamSubscription<QuerySnapshot<Map<String, dynamic>>>? exclusionsSub;

    controller = StreamController<void>(
      onListen: () {
        userSub = _firestore
            .collection('users')
            .doc(uid)
            .snapshots()
            .listen((_) => controller.add(null), onError: controller.addError);
        exclusionsSub = _firestore
            .collection('recommendationExclusions')
            .doc(uid)
            .collection('targets')
            .snapshots()
            .listen((_) => controller.add(null), onError: controller.addError);
      },
      onCancel: () async {
        await userSub?.cancel();
        await exclusionsSub?.cancel();
      },
    );
    return controller.stream;
  }

  /// Watches only the small set of cards currently rendered. An account that
  /// becomes hidden, suspended, or privacy-not-ready is removed without
  /// waiting for the tab to be recreated.
  Stream<void> watchCandidateRecommendationChanges(Iterable<String> uids) {
    final candidateUids = uids
        .map((uid) => uid.trim())
        .where((uid) => uid.isNotEmpty)
        .toSet();
    late final StreamController<void> controller;
    final subscriptions =
        <StreamSubscription<DocumentSnapshot<Map<String, dynamic>>>>[];

    controller = StreamController<void>(
      onListen: () {
        for (final uid in candidateUids) {
          var receivedInitialEligibleSnapshot = false;
          final subscription = _firestore
              .collection('publicProfiles')
              .doc(uid)
              .snapshots()
              .listen((snapshot) {
                final data = snapshot.data();
                final eligible =
                    data != null &&
                    data['recommendationPrivacyReady'] == true &&
                    data['status'] != 'withdrawn' &&
                    data['isWithdrawn'] != true &&
                    data['profileVisible'] != false;
                if (!receivedInitialEligibleSnapshot) {
                  receivedInitialEligibleSnapshot = eligible;
                  if (eligible) return;
                }
                controller.add(null);
              }, onError: controller.addError);
          subscriptions.add(subscription);
        }
      },
      onCancel: () async {
        for (final subscription in subscriptions) {
          await subscription.cancel();
        }
      },
    );
    return controller.stream;
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
        .get(const GetOptions(source: Source.server));

    if (snap.exists && snap.data() != null) {
      final data = snap.data() as Map<String, dynamic>;
      if (data['status'] == 'ready') {
        return {'dateKey': todayKey, 'data': data};
      }
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
        .get(const GetOptions(source: Source.server));

    if (snap.exists && snap.data() != null) {
      final data = snap.data() as Map<String, dynamic>;
      if (data['status'] == 'ready') {
        return {'dateKey': yesterdayKey, 'data': data};
      }
    }

    return null;
  }

  /// 추천 문서에 서버가 남긴 생활권 정책 상태.
  ///
  /// 배치가 문서를 만들 때의 정책이 그대로 기록돼 있다. config 를 못 읽는
  /// 순간에도 이 값이 "이 문서가 어떤 정책으로 만들어졌는지"의 근거가 된다.
  /// provenance 가 없는 legacy 문서는 `null`.
  static String? policyStateOf(Map<String, dynamic>? recDoc) {
    final policy = recDoc?['policy'];
    if (policy is! Map) return null;
    final state = policy['campusLifeZone'];
    return state is String && state.isNotEmpty ? state : null;
  }

  /// 이 피드에 생활권 hard filter 를 적용해야 하는지 정한다.
  ///
  /// 클라이언트가 정책을 직접 정하지 않는다. 서버가 남긴 두 가지 근거
  /// (추천 문서의 정책 metadata, config 문서의 activation)를 합칠 뿐이다.
  ///
  ///  - 문서가 `enforced` 로 만들어졌다  -> 적용 (config 를 못 읽어도)
  ///  - config 가 `enforced` 다           -> 적용 (문서가 낡아 `off` 여도)
  ///  - 이 세션에서 활성화를 확인한 적이 있다 -> 적용 (조회 실패 중이어도)
  ///  - 그 밖에                            -> 미적용 (준비 단계 기본값)
  ///
  /// 마지막 항목이 준비 단계의 안전한 기본값이다. 조회 실패를 무조건 적용으로
  /// 바꾸면 아직 생활권이 없는 기존 사용자가 장애 때 전부 빈 피드를 받는다.
  static bool shouldEnforceCampusLifeZone({
    required String? documentPolicyState,
    required CampusLifeZoneActivation activation,
    required bool enforcedObserved,
  }) {
    if (documentPolicyState == 'enforced') return true;
    switch (activation) {
      case CampusLifeZoneActivation.enforced:
        return true;
      case CampusLifeZoneActivation.off:
        return false;
      case CampusLifeZoneActivation.unknown:
        // 활성화를 확인한 적이 있으면 그 상태를 유지한다 (last-known-good).
        return enforcedObserved;
    }
  }

  /// 후보자 UID 리스트를 순회하며 User 프로필(이미지, 기본 정보)을 Hydrate
  Future<List<AiRecommendedProfile>> _hydrateProfiles({
    required List<dynamic> rawItems,
    required String algo,
    required String dateKey,
    required int limit,
    required String viewerUid,
    Set<String> blockedUids = const {},
    String? documentPolicyState,
  }) async {
    final List<AiRecommendedProfile> results = [];
    final uuid = const Uuid();

    // 최종 serving guard: 생활권은 hard eligibility다.
    // 배치 단계에서 이미 걸러지지만, 어제자 fallback 문서나 낡은 source가
    // 남아 있어도 다른 생활권 후보가 노출되지 않도록 여기서 다시 확인한다.
    //
    // 단 rollout activation 이 OFF 인 동안에는 강제하지 않는다. 활성화
    // 여부는 클라이언트가 판단하지 않고 서버가 남긴 근거를 따른다.
    // (OFF 에서 강제하면 아직 생활권이 없는 기존 사용자가 빈 피드를 받는다)
    if (documentPolicyState == 'enforced') {
      // 서버가 이미 활성화된 정책으로 만든 문서다. config 조회 실패가
      // 이후에 정책을 되돌리지 못하게 기록한다.
      CampusLifeZoneRepairService.latchEnforcedObserved();
    }
    final activation = await _campusLifeZoneRepairService.loadActivation();
    final enforceCampusLifeZone = shouldEnforceCampusLifeZone(
      documentPolicyState: documentPolicyState,
      activation: activation,
      enforcedObserved: CampusLifeZoneRepairService.enforcedObserved,
    );
    final viewerZones = enforceCampusLifeZone
        ? RecommendationEligibility.campusLifeZonesOf(
            await _userService.getUserProfile(viewerUid),
          )
        : const <String>{};

    // 순위를 보장하기 위해 items 안의 rank나 순서를 기반으로 정렬 (Python 스크립트는 이미 rank 순 정렬)
    final sortedItems = List.from(rawItems);
    sortedItems.sort((a, b) {
      final rankA = (a['rank'] as num?)?.toInt() ?? 999;
      final rankB = (b['rank'] as num?)?.toInt() ?? 999;
      return rankA.compareTo(rankB);
    });

    for (final item in sortedItems) {
      if (results.length >= limit) break;

      if (item is! Map) continue;
      final candUid = item['uid']?.toString().trim();
      if (candUid == null || candUid.isEmpty) continue;

      // 차단된 사용자 제외
      if (blockedUids.contains(candUid)) continue;

      // 1. 추천 문서 자체에 이미지가 있는지 확인 (미래 확장성)
      List<String> images = [];
      if (item['imageUrls'] != null) {
        images = List<String>.from(item['imageUrls']);
      }

      // 2. Fallback: users/{uid} 문서에서 onboarding.photoUrls 조회
      // Candidate eligibility is privacy-sensitive, so never trust an offline
      // public-profile cache that may predate consent revocation or suspension.
      final publicSnapshot = await _firestore
          .collection('publicProfiles')
          .doc(candUid)
          .get(const GetOptions(source: Source.server));
      final userProfile = publicSnapshot.data();
      if (userProfile == null) continue; // 삭제/탈퇴된 유저 패스
      // Missing is not ready so legacy candidates cannot bypass the gate.
      if (userProfile['recommendationPrivacyReady'] != true) continue;
      final schemaVersion =
          (userProfile['schemaVersion'] as num?)?.toInt() ?? 1;
      final isDisplayable = schemaVersion >= 2
          ? RecommendationEligibility.isCandidateDisplayable(userProfile)
          : RecommendationEligibility.isAccountActive(userProfile) &&
                userProfile['isStudentVerified'] == true;
      if (!isDisplayable) {
        continue;
      }

      // 생활권 교집합이 없으면 제외한다 (값이 없으면 fail-closed).
      // activation OFF 면 이 조건을 적용하지 않는다.
      if (!RecommendationEligibility.passesCampusLifeZoneGate(
        enforced: enforceCampusLifeZone,
        viewerZones: viewerZones,
        candidateZones: RecommendationEligibility.campusLifeZonesOf(
          userProfile,
        ),
      )) {
        continue;
      }

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
      final nickname =
          userProfile['nickname'] as String? ??
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

      final major = (onboarding is Map)
          ? (onboarding['major'] as String? ?? '전공 미상')
          : '전공 미상';
      final bio = (onboarding is Map)
          ? (onboarding['bio'] as String? ?? '')
          : '';
      final university = (onboarding is Map)
          ? (onboarding['university'] as String? ?? '')
          : '';

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

  /// modelRecs가 없을 때의 안전한 동작: 빈 피드.
  ///
  /// 과거 `/users` collection scan 폴백은 인증된 클라이언트의 전체 roster 조회를
  /// 유도했고, 차단·탈퇴 정책을 우회할 위험도 있어 제거했다.
  Future<List<AiRecommendedProfile>> _emptyFeedBecauseNoModelRecs(
    String reason,
  ) async {
    debugPrint('[AI] refusing users-collection fallback ($reason)');
    return const <AiRecommendedProfile>[];
  }

  /// Profile Card 피드. modelRecs 없으면 빈 목록 (users 스캔 폴백 없음).
  Future<List<AiRecommendedProfile>> fetchProfileFeed({
    int limit = 10,
    String? userId,
  }) async {
    final uid = userId ?? await _resolveUid();
    if (uid == null || uid.isEmpty) return [];

    try {
      if (!await _isViewerRecommendationPrivacyReady(uid)) return [];
      final blockedUids = <String>{
        ...await _fetchBlockedUids(uid),
        ...await _fetchRecommendationExcludedUids(uid),
      };

      final result = await _fetchRawRecs(uid, 'svd');
      if (result != null) {
        final data = result['data'] as Map<String, dynamic>;
        final dateKey = result['dateKey'] as String;
        final items = data['items'] as List<dynamic>? ?? [];
        return await _hydrateProfiles(
          rawItems: items,
          algo: 'svd',
          dateKey: dateKey,
          limit: limit,
          viewerUid: uid,
          blockedUids: blockedUids,
          documentPolicyState: policyStateOf(data),
        );
      }
      return await _emptyFeedBecauseNoModelRecs('profile_feed_no_modelRecs');
    } catch (e) {
      debugPrint('fetchProfileFeed Error: ${PrivacyLogUtils.errorSummary(e)}');
      rethrow;
    }
  }

  /// Mystery Card 피드. modelRecs 없으면 빈 목록 (users 스캔 폴백 없음).
  Future<List<AiRecommendedProfile>> fetchMysteryFeed({
    int limit = 3,
    String? userId,
  }) async {
    final uid = userId ?? await _resolveUid();
    if (uid == null || uid.isEmpty) return [];

    try {
      if (!await _isViewerRecommendationPrivacyReady(uid)) return [];
      final blockedUids = <String>{
        ...await _fetchBlockedUids(uid),
        ...await _fetchRecommendationExcludedUids(uid),
      };

      var result = await _fetchRawRecs(uid, 'rrf');
      var algoUsed = 'rrf';

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

        return await _hydrateProfiles(
          rawItems: items,
          algo: algoUsed,
          dateKey: dateKey,
          limit: limit,
          viewerUid: uid,
          blockedUids: blockedUids,
          documentPolicyState: policyStateOf(data),
        );
      }
      return await _emptyFeedBecauseNoModelRecs('mystery_feed_no_modelRecs');
    } catch (e) {
      debugPrint('fetchMysteryFeed Error: ${PrivacyLogUtils.errorSummary(e)}');
      rethrow;
    }
  }

  Future<String?> _resolveUid() async {
    final kakaoUid = await _storageService.getKakaoUserId();
    if (kakaoUid != null && kakaoUid.isNotEmpty) return kakaoUid;
    final firebaseUid = FirebaseAuth.instance.currentUser?.uid;
    if (firebaseUid != null && firebaseUid.isNotEmpty) return firebaseUid;
    return null;
  }
}
