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

  test('friend connection screen blocks progression until consent and the '
      'initial sync succeed (fail-closed, no skip path)', () {
    final screen = _read(
      'lib/features/auth/screens/kakao_friend_connection_screen.dart',
    );
    final service = _read('lib/services/kakao_friend_connection_service.dart');

    // The chain is ordered: OAuth → consent → Friends API verification →
    // identity link → initial exclusion sync → server readiness check.
    final chainStart = service.indexOf('Future<void> runFullConnectionFlow()');
    expect(chainStart, greaterThanOrEqualTo(0));
    final chain = service.substring(chainStart);
    final oauth = chain.indexOf('ensureKakaoOAuthSession()');
    final consent = chain.indexOf('requestFriendsConsent()');
    final verify = chain.indexOf('verifyFriendsApiAccess()');
    final link = chain.indexOf('linkCurrentKakaoIdentity()');
    final sync = chain.indexOf('syncInitialFriendExclusions()');
    final ready = chain.indexOf('verifyFriendConnectionReady()');
    expect(oauth, greaterThanOrEqualTo(0));
    expect(consent, greaterThan(oauth));
    expect(verify, greaterThan(consent));
    expect(link, greaterThan(verify));
    expect(sync, greaterThan(link));
    expect(ready, greaterThan(sync));

    // The sync path reuses the fail-closed begin+sync callables without an
    // extra consent dialog, and consent refusal marks the pending state.
    expect(service, contains('requestConsentIfNeeded: false'));
    expect(
      service,
      contains('markRecommendationPrivacyPendingAfterConsentRefusal()'),
    );
    expect(
      service,
      contains('ensureRequiredConsents(\n        requireTalkMessage: false'),
    );

    // The screen has no "later" escape and keeps the user here on refusal.
    expect(screen, isNot(contains('나중에 하기')));
    expect(screen, contains('markPendingAfterConsentRefusal'));
    expect(screen, contains('consentRefused'));
    expect(screen, contains('다시 동의하고 친구 연결하기'));

    // Success re-enters the setup ladder instead of jumping to /main.
    expect(screen, contains('resolveNextRoute'));
    expect(screen, isNot(contains('RouteNames.main')));
  });

  test('setup ladder gates recommendations behind the friend connection', () {
    final resolver = _read('lib/models/account_setup_state.dart');
    expect(resolver, contains("userDoc['recommendationPrivacyReady'] == true"));
    expect(resolver, contains('kakaoConnectionRequired'));
    expect(resolver, contains('initialFriendSyncRequired'));
    // Grandfather rule is scoped to legacy docs WITHOUT the field.
    expect(resolver, contains('GRANDFATHER'));
  });

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

    for (final path in [
      'lib/features/matching/screens/profile_card_screen.dart',
      'lib/features/matching/screens/mystery_card_screen.dart',
    ]) {
      final screen = _read(path);
      expect(screen, contains('KakaoRecommendationPrivacyPrerequisite'));
      expect(screen, contains('RecommendationLoadFailure'));
      expect(screen, contains('syncKakaoTalkFriendBlocks'));
    }
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
