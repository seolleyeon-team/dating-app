import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/foundation.dart';

import '../../../services/ai_recommendation_service.dart';
import '../../../services/auth_service.dart';
import '../../../services/firebase_runtime.dart';
import '../../../services/storage_service.dart';
import '../../../shared/utils/privacy_log_utils.dart';

/// 1대1 설레연 유료 추천 새로고침의 클라이언트 게이트웨이.
///
/// Heart 차감·자격 발급은 전부 `purchaseRecommendationRefresh` callable 이
/// 서버 트랜잭션으로 처리한다. 이 서비스는 절대 잔액을 직접 수정하지 않는다.
///
/// 중요: 클라이언트에서 하는 eligibility 검사(후보 6명 가드, selector 등)는
/// 전부 **UX precheck** 다. 결제 가부와 유료 노출 3명의 identity 는 서버가
/// 결제 commit 시점 트랜잭션 안에서 재검증해 확정하며, server response 와
/// entitlement 문서만이 authoritative 하다.
class RecommendationRefreshService {
  RecommendationRefreshService({
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  }) : _firestore = firestore ?? FirebaseFirestore.instance,
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion),
       _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService();

  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;

  /// 서버 상수(recommendationRefresh.ts)와 동일해야 한다. UI 표시 전용이며
  /// 실제 차감 가격은 서버가 결정한다.
  static const int costHearts = 5;

  /// 한 화면에 노출되는 추천 카드 수 (initial: 1~3위, refreshed: 4~6위).
  static const int windowSize = 3;

  /// eligible 후보 리스트(rank 순)에서 현재 window 에 해당하는 카드를 고른다.
  ///
  /// 화면의 "1~3위"는 원래부터 raw rank 가 아니라 "차단/탈퇴 필터를 통과한
  /// 후보 중 rank 순 상위 3명"이다. 새로고침 window 도 같은 기준의 다음 3명을
  /// 쓴다 — raw rank 4~6 으로 자르면 필터로 빠진 자리 때문에 결제 전에 보이던
  /// 카드가 결제 후에 다시 보일 수 있다. 각 프로필의 원본 model rank 는
  /// [AiRecommendedProfile.rank] 에 그대로 남는다 (재번호 없음).
  ///
  /// [purchasedCandidateUids]는 서버 entitlement 가 결제 시점에 확정한 유료
  /// 노출 3명이다. 값이 있으면 offset 대신 그 identity 로 복원해, 결제 이후
  /// eligibility 변동(차단 해제 등)으로 리스트가 밀려도 사용자가 구매한
  /// 결과가 그대로 유지된다. eligible 목록에 하나도 남아 있지 않을 때만
  /// offset window 로 폴백한다.
  ///
  /// Safety > paid entitlement: [eligibleProfiles] 는 이미 차단/탈퇴/모더레이션
  /// 필터를 통과한 목록이므로, 결제 이후 unsafe 해진 구매 후보는 여기에 없어
  /// 자동으로 숨겨진다. 이때 Heart 를 다시 차감하거나 두 번째 구매를 유도하지
  /// 않는다 — entitlement 는 completed 로 유지되고 남은 유효 후보만 표시한다.
  static List<AiRecommendedProfile> selectDisplayedRecommendations(
    List<AiRecommendedProfile> eligibleProfiles, {
    required bool refreshed,
    List<String> purchasedCandidateUids = const [],
  }) {
    if (refreshed && purchasedCandidateUids.isNotEmpty) {
      final byUid = {
        for (final profile in eligibleProfiles) profile.candidateUid: profile,
      };
      final purchased = <AiRecommendedProfile>[
        for (final uid in purchasedCandidateUids)
          if (byUid[uid] != null) byUid[uid]!,
      ];
      if (purchased.isNotEmpty) return purchased;
      // 구매한 3명이 전부 노출 불가(차단/탈퇴)가 된 극단적 경우에만 폴백.
    }
    final start = refreshed ? windowSize : 0;
    if (eligibleProfiles.length <= start) return const [];
    return eligibleProfiles.skip(start).take(windowSize).toList();
  }

  /// 해당 dateKey 의 새로고침 entitlement 를 서버에서 읽는다.
  ///
  /// 읽기 실패는 null(= initial window 유지)로 처리한다. 자격이 있는데 null 이
  /// 되어도 결제 재시도는 서버에서 already_purchased 로 끝나므로 이중 차감은
  /// 발생하지 않는다.
  Future<RecommendationRefreshEntitlement?> fetchEntitlement(
    String userId,
    String dateKey,
  ) async {
    try {
      final snap = await _firestore
          .collection('users')
          .doc(userId)
          .collection('recommendationRefreshes')
          .doc(dateKey)
          .get(const GetOptions(source: Source.server));
      final data = snap.data();
      if (data == null) return null;
      return RecommendationRefreshEntitlement(
        dateKey: dateKey,
        completed: data['status'] == 'completed',
        displayCandidateUids: _readUidList(data['displayCandidateUids']),
      );
    } catch (error) {
      debugPrint(
        '[RecRefresh] entitlement read failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      return null;
    }
  }

  /// 서버 error message key -> 결제 결과 상태. 알 수 없는 오류는 null
  /// (호출자가 rethrow).
  @visibleForTesting
  static RecommendationRefreshStatus? statusFromServerErrorMessage(
    String message,
  ) {
    if (message.contains('insufficient_hearts')) {
      return RecommendationRefreshStatus.insufficientHearts;
    }
    if (message.contains('refresh_stale_eligibility')) {
      return RecommendationRefreshStatus.staleEligibility;
    }
    if (message.contains('refresh_stale_feed')) {
      return RecommendationRefreshStatus.staleFeed;
    }
    if (message.contains('refresh_unavailable')) {
      return RecommendationRefreshStatus.unavailable;
    }
    return null;
  }

  static List<String> _readUidList(Object? value) {
    if (value is! List) return const [];
    return [
      for (final item in value)
        if (item is String && item.trim().isNotEmpty) item.trim(),
    ];
  }

  /// 서버에 새로고침 결제를 요청한다.
  ///
  /// [expectedDateKey]/[expectedAlgo]는 현재 화면이 보고 있는 추천 세트의
  /// 식별자다. 서버가 결정한 세트와 다르면 결제 없이
  /// [RecommendationRefreshStatus.staleFeed]로 끝나므로, 결제 도중 추천 세트가
  /// 교체되는 race 에서 엉뚱한 세트에 결제되지 않는다.
  Future<RecommendationRefreshPurchaseResult> purchaseRefresh({
    required String expectedDateKey,
    String? expectedAlgo,
  }) async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw StateError('로그인 정보를 찾을 수 없어요. 다시 로그인해주세요.');
    }
    // Callable 은 request.auth 로 사용자를 결정한다. 세션 준비 실패 시 결제를
    // 시작하지 않는다.
    final isSessionReady = await _authService.ensureCanonicalAppSession();
    if (!isSessionReady) {
      throw StateError('결제를 처리할 로그인 세션을 준비하지 못했어요.');
    }

    final dynamic response;
    try {
      response = await _functions
          .httpsCallable('purchaseRecommendationRefresh')
          .call(<String, dynamic>{
            'expectedDateKey': expectedDateKey,
            if (expectedAlgo != null) 'expectedAlgo': expectedAlgo,
          });
    } on FirebaseFunctionsException catch (error) {
      final mapped = statusFromServerErrorMessage(error.message ?? '');
      if (mapped != null) {
        return RecommendationRefreshPurchaseResult(status: mapped);
      }
      rethrow;
    }

    final raw = response.data;
    if (raw is! Map) {
      throw StateError('새로고침 서버의 응답 형식이 올바르지 않아요.');
    }
    final data = Map<String, dynamic>.from(raw);
    final status = data['status'];
    if (data['ok'] != true ||
        (status != 'purchased' && status != 'already_purchased')) {
      throw StateError('새로고침 결제 결과를 확인하지 못했어요.');
    }
    return RecommendationRefreshPurchaseResult(
      status: status == 'purchased'
          ? RecommendationRefreshStatus.purchased
          : RecommendationRefreshStatus.alreadyPurchased,
      dateKey: data['dateKey'] as String?,
      remainingHearts: (data['remainingHearts'] as num?)?.toInt(),
      displayCandidateUids: _readUidList(data['displayCandidateUids']),
    );
  }
}

/// users/{uid}/recommendationRefreshes/{dateKey} 문서의 클라이언트 뷰.
@immutable
class RecommendationRefreshEntitlement {
  const RecommendationRefreshEntitlement({
    required this.dateKey,
    required this.completed,
    this.displayCandidateUids = const [],
  });

  final String dateKey;
  final bool completed;

  /// 결제 시점에 서버가 확정한 유료 노출 후보 3명 (eligible 4~6번째).
  final List<String> displayCandidateUids;
}

enum RecommendationRefreshStatus {
  /// 이번 요청으로 Heart 5개가 차감되고 자격이 발급됐다.
  purchased,

  /// 같은 dateKey 로 이미 결제 완료 — 재차감 없음 (idempotent 성공).
  alreadyPurchased,

  /// 잔액 부족 — 차감 없음. 하트 충전 flow 로 안내한다.
  insufficientHearts,

  /// 추천 세트 없음/후보 부족 등 — 차감 없음.
  unavailable,

  /// 화면의 세트와 서버의 현재 세트가 다름 — 차감 없음. 피드 재로드 필요.
  staleFeed,

  /// precheck 와 결제 commit 사이에 유료 노출 3명 중 누군가가 eligible 하지
  /// 않게 됨(차단/탈퇴 등) — 차감 없음. 피드 재로드 후 구매 가능 여부 재계산.
  staleEligibility,
}

@immutable
class RecommendationRefreshPurchaseResult {
  const RecommendationRefreshPurchaseResult({
    required this.status,
    this.dateKey,
    this.remainingHearts,
    this.displayCandidateUids = const [],
  });

  final RecommendationRefreshStatus status;
  final String? dateKey;
  final int? remainingHearts;

  /// 서버가 결제 시점에 확정한 유료 노출 후보 3명 (idempotent 재시도 포함).
  final List<String> displayCandidateUids;

  bool get isCompleted =>
      status == RecommendationRefreshStatus.purchased ||
      status == RecommendationRefreshStatus.alreadyPurchased;
}
