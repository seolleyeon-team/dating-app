import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/services/recommendation_refresh_service.dart';
import 'package:seolleyeon/services/ai_recommendation_service.dart';

AiRecommendedProfile profileAt(int rank) => AiRecommendedProfile(
  candidateUid: 'cand_$rank',
  name: '후보$rank',
  age: 22,
  major: '전공',
  imageUrls: const [],
  rank: rank,
  primaryAlgo: 'rrf',
  dateKey: '20260830',
  exposureId: 'exp_$rank',
);

void main() {
  final sixEligible = [for (var rank = 1; rank <= 6; rank++) profileAt(rank)];

  test('initial window shows the first three eligible candidates', () {
    final displayed =
        RecommendationRefreshService.selectDisplayedRecommendations(
          sixEligible,
          refreshed: false,
        );
    expect(displayed.map((p) => p.candidateUid), [
      'cand_1',
      'cand_2',
      'cand_3',
    ]);
  });

  test('refreshed window shows the next three eligible candidates', () {
    final displayed =
        RecommendationRefreshService.selectDisplayedRecommendations(
          sixEligible,
          refreshed: true,
        );
    expect(displayed.map((p) => p.candidateUid), [
      'cand_4',
      'cand_5',
      'cand_6',
    ]);
  });

  test(
    'windows never overlap, so a paid refresh never re-shows a seen card',
    () {
      final initial =
          RecommendationRefreshService.selectDisplayedRecommendations(
            sixEligible,
            refreshed: false,
          ).map((p) => p.candidateUid).toSet();
      final refreshed =
          RecommendationRefreshService.selectDisplayedRecommendations(
            sixEligible,
            refreshed: true,
          ).map((p) => p.candidateUid).toSet();
      expect(initial.intersection(refreshed), isEmpty);
    },
  );

  test('a short eligible list yields an empty or partial refreshed window', () {
    expect(
      RecommendationRefreshService.selectDisplayedRecommendations(
        sixEligible.take(3).toList(),
        refreshed: true,
      ),
      isEmpty,
    );
    final partial = RecommendationRefreshService.selectDisplayedRecommendations(
      sixEligible.take(5).toList(),
      refreshed: true,
    );
    expect(partial.map((p) => p.candidateUid), ['cand_4', 'cand_5']);
  });

  test('the client price constant matches the v1 contract', () {
    expect(RecommendationRefreshService.costHearts, 5);
    expect(RecommendationRefreshService.windowSize, 3);
  });

  test('server error message keys map to typed purchase statuses', () {
    expect(
      RecommendationRefreshService.statusFromServerErrorMessage(
        'insufficient_hearts',
      ),
      RecommendationRefreshStatus.insufficientHearts,
    );
    expect(
      RecommendationRefreshService.statusFromServerErrorMessage(
        'refresh_stale_eligibility',
      ),
      RecommendationRefreshStatus.staleEligibility,
    );
    expect(
      RecommendationRefreshService.statusFromServerErrorMessage(
        'refresh_stale_feed',
      ),
      RecommendationRefreshStatus.staleFeed,
    );
    expect(
      RecommendationRefreshService.statusFromServerErrorMessage(
        'refresh_unavailable',
      ),
      RecommendationRefreshStatus.unavailable,
    );
    // 알 수 없는 오류는 rethrow 대상이라 매핑하지 않는다.
    expect(
      RecommendationRefreshService.statusFromServerErrorMessage('internal'),
      isNull,
    );
  });

  test('CASE C: filtered-out raw rank keeps original ranks in both windows '
      '(no renumbering)', () {
    // raw rank 3 이 차단으로 빠진 뒤의 eligible 목록 (rank 순 유지).
    final eligibleWithGap = [
      for (final rank in [1, 2, 4, 5, 6, 7]) profileAt(rank),
    ];
    final initial = RecommendationRefreshService.selectDisplayedRecommendations(
      eligibleWithGap,
      refreshed: false,
    );
    final refreshed =
        RecommendationRefreshService.selectDisplayedRecommendations(
          eligibleWithGap,
          refreshed: true,
        );
    // analytics 의 'rank' 필드로 그대로 나가는 원본 model rank.
    expect(initial.map((p) => p.rank), [1, 2, 4]);
    expect(refreshed.map((p) => p.rank), [5, 6, 7]);
  });

  test('CASE E: purchased candidate uids restore the exact paid trio in '
      'entitlement order', () {
    final purchased = ['cand_4', 'cand_5', 'cand_6'];
    final restored =
        RecommendationRefreshService.selectDisplayedRecommendations(
          sixEligible,
          refreshed: true,
          purchasedCandidateUids: purchased,
        );
    expect(restored.map((p) => p.candidateUid), purchased);

    // 결제 후 상위 후보 하나가 차단돼 eligible 목록이 밀려도, offset 이
    // 아니라 identity 로 복원하므로 구매 결과가 그대로 유지된다.
    final shifted = sixEligible.skip(1).toList();
    final restoredAfterShift =
        RecommendationRefreshService.selectDisplayedRecommendations(
          shifted,
          refreshed: true,
          purchasedCandidateUids: purchased,
        );
    expect(restoredAfterShift.map((p) => p.candidateUid), purchased);
  });

  test('purchased uids missing from the eligible list fall back to the offset '
      'window instead of an empty screen', () {
    final restored =
        RecommendationRefreshService.selectDisplayedRecommendations(
          sixEligible,
          refreshed: true,
          purchasedCandidateUids: const ['gone_1', 'gone_2', 'gone_3'],
        );
    expect(restored.map((p) => p.candidateUid), ['cand_4', 'cand_5', 'cand_6']);
  });
}
