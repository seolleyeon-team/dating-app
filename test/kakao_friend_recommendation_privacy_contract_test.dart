import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Contract tests for the ONE-TIME Kakao friend snapshot architecture
/// (docs/auth-rearchitecture/kakao-friend-pairs-contract.md).
///
/// The legacy repeated sync (`beginKakaoFriendRecommendationPrivacySync` /
/// `syncKakaoTalkFriendBlocks` / whole-user `recommendationPrivacyReady`
/// pending gate) has ZERO call sites in the new client. Serving privacy is
/// pair-based only: `kakaoFriendPairs` → bilateral `recommendationExclusions`
/// → client/server/python exclusion filters.
String _read(String path) => File(path).readAsStringSync();

Iterable<File> _dartFilesUnder(String dir) => Directory(dir)
    .listSync(recursive: true)
    .whereType<File>()
    .where((f) => f.path.endsWith('.dart'));

void main() {
  test('server snapshot callable fetches friends itself and never trusts '
      'client-submitted friend ids (contract §4/§12)', () {
    final source = _read('functions/src/kakaoFriendPairs.ts');

    expect(source, contains('createKakaoFriendPairsOnce'));
    // The server consumes the OFFICIAL Friends API behind the verified
    // token. A client-submitted uid list must never influence pairs: the
    // only request.data field the snapshot reads is the access token, and
    // the injected fetchFriends dependency is bound (in index.ts) to the
    // existing SSRF/pagination-hardened fetchKakaoFriendServiceUserIds.
    expect(source, contains('deps.fetchFriends(accessToken)'));
    expect(source, isNot(contains('data.friendUserIds')));
    expect(source, contains('data.kakaoAccessToken'));
    final index = _read('functions/src/index.ts');
    final wiringStart = index.indexOf(
      'export const createKakaoFriendPairsOnce',
    );
    expect(wiringStart, greaterThanOrEqualTo(0));
    final wiring = index.substring(wiringStart, wiringStart + 400);
    expect(wiring, contains('fetchKakaoFriendServiceUserIds(accessToken'));
    // Member resolution reuses the existing legacy-or-mapping resolver.
    expect(source, contains('resolveFriendExclusionAppUserIds'));
    // One-time semantics live in users/{uid}.kakaoFriendSnapshot.
    expect(source, contains('kakaoFriendSnapshot'));
    expect(source, contains('kakaoFriendPairs'));
    // Exclusion deletion is source-guarded so manual/report blocks are
    // never touched (contract §6).
    expect(source, contains('kakao_friend_pair'));
    expect(source, contains('kakao_talk_friend'));

    // The avoidance toggle callable exists server-side and never calls
    // the Kakao API (pair docs are the only input).
    expect(source, contains('setKakaoFriendAvoidanceEnabled'));
  });

  test('recommendation feed applies pair exclusions fail-closed with no '
      'whole-user privacy gate (contract §7)', () {
    final source = _read('lib/services/ai_recommendation_service.dart');

    // Pair filter: recommendationExclusions unioned into blockedUids, read
    // from the SERVER (an offline cache must not reopen an exclusion).
    expect(source, contains("collection('recommendationExclusions')"));
    expect(source, contains('_fetchRecommendationExcludedUids(uid)'));
    expect(source, contains('GetOptions(source: Source.server)'));
    // Filter-then-take with backfill: iterate rank order, skip excluded,
    // stop at limit. The take-then-filter shortcut stays banned because it
    // caps the scan window before exclusions are applied and produces short
    // feeds exactly when multiple exclusions cluster at the top ranks.
    expect(source, contains('if (results.length >= limit) break;'));
    expect(source, contains('if (blockedUids.contains(candUid)) continue;'));
    expect(source, isNot(contains('.take(limit + blockedUids.length)')));
    // Live invalidation streams stay: viewer-side exclusions and per-card
    // candidate eligibility.
    expect(source, contains('watchRecommendationPrivacyChanges'));
    expect(source, contains('watchCandidateRecommendationChanges'));
    expect(
      source,
      contains('RecommendationEligibility.isCandidateDisplayable'),
    );

    // The whole-user pending gate is REMOVED on both sides: no viewer
    // early-return and no candidate-side recommendationPrivacyReady filter.
    expect(source, isNot(contains('recommendationPrivacyReady')));
    expect(source, isNot(contains('isViewerRecommendationPrivacyReady')));
  });

  test('onboarding completion no longer runs any Kakao friend sync '
      '(snapshot is pre-onboarding, contract §8)', () {
    final source = _read('lib/services/onboarding_save_helper.dart');
    expect(source, contains('completeOnboarding'));
    expect(source, isNot(contains('syncKakaoTalkFriendBlocks')));
    expect(source, isNot(contains('ContactBlockService')));

    final initialSetup = _read('lib/screens/auth/initial_setup_screen.dart');
    expect(initialSetup, contains('completeOnboarding'));
    expect(initialSetup, isNot(contains('syncKakaoTalkFriendBlocks')));
  });

  test('friend connection flow is oauth → consent → link → one-time '
      'snapshot, fail-closed with no skip path (contract §8)', () {
    final screen = _read(
      'lib/features/auth/screens/kakao_friend_connection_screen.dart',
    );
    final service = _read('lib/services/kakao_friend_connection_service.dart');

    final chainStart = service.indexOf('Future<void> runFullConnectionFlow()');
    expect(chainStart, greaterThanOrEqualTo(0));
    final chain = service.substring(chainStart);
    final oauth = chain.indexOf('ensureKakaoOAuthSession()');
    final consent = chain.indexOf('requestFriendsConsent()');
    final link = chain.indexOf('linkCurrentKakaoIdentity()');
    final statusBeforeSnapshot = chain.indexOf('loadFriendSnapshotStatus()');
    final snapshot = chain.indexOf('createFriendSnapshotOnce()');
    expect(oauth, greaterThanOrEqualTo(0));
    expect(consent, greaterThan(oauth));
    expect(link, greaterThan(consent));
    expect(
      statusBeforeSnapshot,
      greaterThan(link),
      reason: 'the completed-check must precede the snapshot call',
    );
    expect(snapshot, greaterThan(statusBeforeSnapshot));
    // Snapshot runs ONLY when the server status is not already completed —
    // a completed snapshot is immutable and never re-fetched.
    expect(chain, contains("if (status != 'completed') {"));

    // The snapshot callable is the Friends-API verification: no client-side
    // friends fetch and no legacy sync remain in the service.
    expect(service, contains("httpsCallable('createKakaoFriendPairsOnce')"));
    expect(
      service,
      contains("httpsCallable('setKakaoFriendAvoidanceEnabled')"),
    );
    expect(service, isNot(contains('fetchFriends')));
    expect(service, isNot(contains('verifyFriendsApiAccess')));
    expect(service, isNot(contains('syncInitialFriendExclusions')));
    expect(service, isNot(contains('syncKakaoTalkFriendBlocks')));
    expect(service, isNot(contains('markPendingAfterConsentRefusal')));
    expect(service, isNot(contains('syncFriendsEveryLaunch')));
    // Server error mapping for the retry UX.
    expect(service, contains('snapshot_in_progress'));
    expect(service, contains('identity_conflict'));
    expect(service, contains('alreadyCompleted'));

    // The screen has no "later" escape, keeps the user here on refusal
    // WITHOUT any server pending write, and resumes via a server read only.
    expect(screen, isNot(contains('나중에 하기')));
    expect(screen, isNot(contains('markPendingAfterConsentRefusal')));
    expect(screen, contains('consentRefused'));
    expect(screen, contains('다시 동의하고 친구 연결하기'));
    expect(screen, contains('loadFriendSnapshotStatus'));

    // Success re-enters the setup ladder instead of jumping to /main.
    expect(screen, contains('resolveNextRoute'));
    expect(screen, isNot(contains('RouteNames.main')));
  });

  test('setup ladder gates on connection + one-time snapshot, with the '
      'legacy readiness flag removed (contract §8, spec §30)', () {
    final resolver = _read('lib/models/account_setup_state.dart');
    expect(resolver, contains('kakaoConnectionRequired'));
    expect(resolver, contains('kakaoFriendSnapshotRequired'));
    expect(resolver, contains("rawSnapshot['status'] == 'completed'"));
    // Migration gate for legacy users is documented in the resolver itself.
    expect(resolver, contains('GRANDFATHER'));
    expect(resolver, contains('MIGRATION'));
    // recommendationPrivacyReady is no longer consulted by the ladder.
    expect(resolver, isNot(contains("userDoc['recommendationPrivacyReady']")));
    expect(resolver, isNot(contains('initialFriendSyncRequired')));

    final flow = _read('lib/services/account_setup_flow.dart');
    expect(flow, contains('AccountSetupState.kakaoFriendSnapshotRequired:'));
    expect(flow, contains('RouteNames.kakaoFriendConnect'));
  });

  test('avoidance toggle flips the server preference only — no consent '
      'flow, no friend re-fetch (contract §5/§8)', () {
    final screen = _read(
      'lib/features/profile/screens/contact_block_screen.dart',
    );
    expect(screen, contains('setFriendAvoidanceEnabled'));
    expect(screen, contains('켜면, 가입 시 확인된 카카오 친구 중 설레연 이용자와 서로 추천되지 않아요.'));
    expect(screen, isNot(contains('ensureRequiredConsents')));
    expect(screen, isNot(contains('syncKakaoTalkFriendBlocks')));
    expect(screen, isNot(contains('친구 관계 다시 확인')));
    expect(screen, isNot(contains('매번 다시 확인')));

    final service = _read('lib/services/contact_block_service.dart');
    // Status read is server-truth: preference + snapshot state, no
    // reconcile/pending vocabulary and no legacy callables.
    expect(service, contains('kakaoFriendAvoidanceEnabled'));
    expect(service, contains('kakaoFriendSnapshot'));
    expect(service, contains('GetOptions(source: Source.server)'));
    expect(service, isNot(contains('syncKakaoTalkFriendBlocks')));
    expect(
      service,
      isNot(contains('beginKakaoFriendRecommendationPrivacySync')),
    );
    expect(service, isNot(contains('recommendationPrivacyReady')));
  });

  test('static audit (spec §59): the new client has ZERO call sites of the '
      'legacy sync callables and bootstrap reconciliation', () {
    final offenders = <String>[];
    for (final file in _dartFilesUnder('lib')) {
      final source = file.readAsStringSync();
      for (final banned in [
        'syncKakaoTalkFriendBlocks',
        'beginKakaoFriendRecommendationPrivacySync',
        '_reconcileRecommendationPrivacyIfNeeded',
        'markRecommendationPrivacyPendingAfterConsentRefusal',
      ]) {
        if (source.contains(banned)) {
          offenders.add('${file.path}: $banned');
        }
      }
    }
    expect(
      offenders,
      isEmpty,
      reason:
          'legacy Kakao sync paths must have no active client call sites: '
          '$offenders',
    );
  });

  test('client feed screens keep the failure/retry surface without the '
      'legacy consent prerequisite gate (contract §7)', () {
    final failure = _read(
      'lib/shared/widgets/recommendation_load_failure.dart',
    );
    expect(failure, contains('추천 정보를 불러오지 못했어요.'));
    expect(failure, contains('인터넷 연결을 확인하고 다시 시도해 주세요.'));

    expect(
      File(
        'lib/shared/widgets/kakao_recommendation_privacy_prerequisite.dart',
      ).existsSync(),
      isFalse,
    );

    // profile_card_screen 은 main 에서 제거됐다 (부재는 별도 테스트가 고정).
    for (final path in [
      'lib/features/matching/screens/mystery_card_screen.dart',
    ]) {
      final screen = _read(path);
      expect(screen, contains('RecommendationLoadFailure'), reason: path);
      // Exclusion watch + refetch stays live.
      expect(
        screen,
        contains('watchRecommendationPrivacyChanges'),
        reason: path,
      );
      expect(
        screen,
        contains('watchCandidateRecommendationChanges'),
        reason: path,
      );
      // The consent-gate rendering and feed-side sync retry are gone.
      expect(
        screen,
        isNot(contains('KakaoRecommendationPrivacyPrerequisite')),
        reason: path,
      );
      expect(
        screen,
        isNot(contains('syncKakaoTalkFriendBlocks')),
        reason: path,
      );
      expect(screen, isNot(contains('_privacyConsentRequired')), reason: path);
    }
  });

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

  test('python ready-predicate keeps account-state checks but no longer '
      'reads the Kakao pending flag (contract §7)', () {
    final policy = _read(
      'lib/ai_recommend_model/seolleyeon_recommendation_privacy.py',
    );
    final start = policy.indexOf('def _is_recommendation_ready_user');
    expect(start, greaterThanOrEqualTo(0));
    final end = policy.indexOf('\ndef ', start + 1);
    final predicate = policy.substring(start, end < 0 ? policy.length : end);

    expect(predicate, isNot(contains('recommendationPrivacyReady')));
    // Account-state gates stay (these are not Kakao pending state).
    expect(predicate, contains('isStudentVerified'));
    expect(predicate, contains('initialSetupComplete'));
    expect(predicate, contains('profileVisible'));
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

  test('clients cannot write recommendation exclusion pairs and the pair '
      'collection is fully server-only', () {
    final rules = _read('firestore.rules');
    final start = rules.indexOf('match /recommendationExclusions/{viewerUid}');
    final end = rules.indexOf('// Blocks and Reports', start);
    final section = rules.substring(start, end);

    expect(section, contains('allow get, list: if isSelf(viewerUid);'));
    expect(section, contains('allow create, update, delete: if false;'));

    // kakaoFriendPairs is a social graph: deny-all, even for members.
    final pairStart = rules.indexOf('match /kakaoFriendPairs/{pairId}');
    expect(pairStart, greaterThanOrEqualTo(0));
    final pairSection = rules.substring(pairStart, pairStart + 200);
    expect(pairSection, contains('allow read, write: if false;'));

    expect(rules, contains('match /dailyRecs/{userId}/days/{dateKey}'));
    expect(rules, contains('allow read: if isSelf(userId);'));
  });
}
