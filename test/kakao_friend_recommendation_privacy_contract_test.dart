import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test(
    'server verifies Kakao friends and writes both exclusion directions',
    () {
      final source = _read('functions/src/index.ts');
      final start = source.indexOf('export const syncKakaoTalkFriendBlocks');
      final end = source.indexOf('\nexport const ', start + 1);
      final callable = source.substring(start, end < 0 ? source.length : end);

      expect(callable, contains('fetchKakaoFriendServiceUserIds(accessToken)'));
      expect(callable, isNot(contains('data.friendUserIds')));
      expect(source, contains('transaction.getAll('));
      expect(source, contains('recommendationExclusionRef(userA, userB)'));
      expect(source, contains('recommendationExclusionRef(userB, userA)'));
      expect(callable, contains('kakaoFriendReconcileId: reconcileId'));
      expect(
        callable,
        contains('latestData.kakaoFriendReconcileId !== reconcileId'),
      );
      expect(callable, contains('syncPublicProfileForUser('));
    },
  );

  test('client closes eligibility before inspecting the Kakao token', () {
    final client = _read('lib/services/contact_block_service.dart');
    final pending = client.indexOf(
      "httpsCallable('beginKakaoFriendRecommendationPrivacySync')",
    );
    final token = client.indexOf('getKakaoAccessTokenForFunctions()');
    expect(pending, greaterThanOrEqualTo(0));
    expect(token, greaterThan(pending));

    final server = _read('functions/src/index.ts');
    final start = server.indexOf(
      'export const beginKakaoFriendRecommendationPrivacySync',
    );
    final end = server.indexOf('export const syncKakaoTalkFriendBlocks', start);
    final callable = server.substring(start, end);
    expect(callable, contains('recommendationPrivacyReady: false'));
    expect(callable, contains('kakaoFriendReconcileId: pendingId'));
    expect(callable, contains('syncPublicProfileForUser('));
    expect(callable, contains('verifyKakaoAccessToken(accessToken)'));
  });

  test('recommendation feed fails closed and applies mutual exclusions', () {
    final source = _read('lib/services/ai_recommendation_service.dart');

    expect(source, contains("collection('recommendationExclusions')"));
    expect(source, contains("profile['recommendationPrivacyReady'] == true"));
    expect(
      source,
      contains("userProfile['recommendationPrivacyReady'] != true"),
    );
    expect(source, contains('_fetchRecommendationExcludedUids(uid)'));
    expect(source, contains('GetOptions(source: Source.server)'));
    expect(source, contains('watchRecommendationPrivacyChanges'));
    expect(source, contains('watchCandidateRecommendationChanges'));
    expect(
      source,
      contains('RecommendationEligibility.isCandidateDisplayable'),
    );
    expect(source, isNot(contains('.take(limit + blockedUids.length)')));
  });

  test('onboarding reconciles before recommendation eligibility', () {
    final source = _read('lib/services/onboarding_save_helper.dart');
    final syncIndex = source.indexOf('syncKakaoTalkFriendBlocks()');
    final completeIndex = source.indexOf(
      '_userService.completeOnboarding(uid)',
    );

    expect(syncIndex, greaterThanOrEqualTo(0));
    expect(completeIndex, greaterThan(syncIndex));
  });

  test(
    'Kakao login blocks Yonsei email routing until friends consent succeeds',
    () {
      final source = _read('lib/features/auth/screens/kakao_auth_screen.dart');

      expect(source, contains('_pauseForMissingFriendsConsent(userInfo)'));
      expect(
        source,
        contains('markRecommendationPrivacyPendingAfterConsentRefusal()'),
      );
      expect(source, contains('if (status.friendsAgreed)'));
      expect(source, contains('_friendsConsentRequired = true'));
      expect(
        source,
        contains('ensureRequiredConsents(\n        requireTalkMessage: false'),
      );
      expect(
        source,
        contains("pushReplacementNamed(RouteNames.studentVerification)"),
      );
      expect(source, contains('다시 동의하기'));
      expect(source, contains('동의하고 카카오로 로그인'));
      expect(
        source,
        contains('_reconcileReturningUserRecommendationPrivacy()'),
      );
      expect(source, contains('requestConsentIfNeeded: false'));

      final nativeGate = source.indexOf(
        'if (await _pauseForMissingFriendsConsent(userInfo)) return;',
      );
      final nativeContinue = source.indexOf(
        'await _continueAfterKakaoLogin(userInfo);',
        nativeGate,
      );
      expect(nativeGate, greaterThanOrEqualTo(0));
      expect(nativeContinue, greaterThan(nativeGate));
    },
  );

  test(
    'legacy completed accounts reconcile on the next authenticated start',
    () {
      final source = _read('lib/providers/auth_provider.dart');

      expect(source, contains('_reconcileRecommendationPrivacyIfNeeded()'));
      expect(source, contains('requestConsentIfNeeded: false'));
      expect(
        source,
        isNot(contains('if (!status.recommendationPrivacyReady)')),
      );
    },
  );

  test('every model export and verification applies privacy policy', () {
    for (final path in [
      'lib/ai_recommend_model/seolleyeon_clip_train_export_v3.py',
      'lib/ai_recommend_model/seolleyeon_svd_train_export_v3.py',
      'lib/ai_recommend_model/seolleyeon_knn_train_export_v3.py',
      'lib/ai_recommend_model/seolleyeon_rrf_export.py',
    ]) {
      final source = _read(path);
      expect(
        source,
        contains('load_recommendation_privacy_policy'),
        reason: path,
      );
      expect(source, contains('"status": "ineligible"'), reason: path);
      expect(source, contains('"items": []'), reason: path);
    }

    final verify = _read('recsys/jobs/verify_job.py');
    expect(verify, contains('privacy_violations'));
    expect(verify, contains('privacy_policy.allows(uid, candidate_uid)'));

    final rrf = _read('lib/ai_recommend_model/seolleyeon_rrf_export.py');
    expect(rrf, contains('privacy_prefilter_limit'));
    expect(rrf, contains('merged = privacy_policy.filter_items(uid, merged)'));

    final daily = _read('recsys/jobs/daily_job.py');
    expect(daily, contains('load_recommendation_privacy_policy'));
    expect(daily, contains('privacy_policy.filter_items'));
    expect(daily, contains('viewer_privacy_not_ready'));

    final workflow = _read('infra/workflows/recs_pipeline.yaml');
    expect(workflow, contains('recs-daily'));
    expect(workflow, contains('raise_verify'));
  });

  test('1:1 screens distinguish consent, load failure, and empty feed', () {
    final prerequisite = _read(
      'lib/shared/widgets/kakao_recommendation_privacy_prerequisite.dart',
    );
    expect(prerequisite, contains('카카오 친구목록 동의가 필요해요'));
    expect(prerequisite, contains('추천 정보를 불러오지 못했어요.'));
    expect(prerequisite, contains('인터넷 연결을 확인하고 다시 시도해 주세요.'));

    final screen = _read(
      'lib/features/matching/screens/mystery_card_screen.dart',
    );
    expect(screen, contains('KakaoRecommendationPrivacyPrerequisite'));
    expect(screen, contains('RecommendationLoadFailure'));
    expect(screen, contains('syncKakaoTalkFriendBlocks'));
  });

  test('legacy general profile-card system is removed from the app graph', () {
    expect(
      File(
        'lib/features/matching/screens/profile_card_screen.dart',
      ).existsSync(),
      isFalse,
    );

    final router = _read('lib/router/app_router.dart');
    final routes = _read('lib/router/route_names.dart');
    final recommendationService = _read(
      'lib/services/ai_recommendation_service.dart',
    );

    expect(router, isNot(contains('ProfileCardScreen')));
    expect(router, isNot(contains("profile_card_screen.dart")));
    expect(routes, isNot(contains("profileCard = '/matching/profile-card'")));
    expect(recommendationService, isNot(contains('fetchProfileFeed')));
  });

  test('clients cannot write recommendation exclusion pairs', () {
    final rules = _read('firestore.rules');
    final start = rules.indexOf('match /recommendationExclusions/{viewerUid}');
    final end = rules.indexOf('// Blocks and Reports', start);
    final section = rules.substring(start, end);

    expect(section, contains('allow get, list: if isSelf(viewerUid);'));
    expect(section, contains('allow create, update, delete: if false;'));

    expect(rules, contains('match /dailyRecs/{userId}/days/{dateKey}'));
    expect(rules, contains('allow read: if isSelf(userId);'));
  });
}
