import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:flutter/services.dart' show PlatformException;
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

import '../shared/utils/privacy_log_utils.dart';
import 'auth_service.dart';
import 'firebase_runtime.dart';
import 'kakao_login_coordinator.dart';
import 'kakao_talk_friend_service.dart';

/// Steps of the post-auth Kakao friend connection chain.
enum KakaoFriendConnectionStep {
  oauth,
  friendsConsent,
  identityLink,
  friendSnapshot,
  readiness,
}

/// Typed failure surfaced by [KakaoFriendConnectionService]. `consentRefused`
/// marks a user-cancelled consent so the screen can stay put and offer a
/// retry (no server pending write is needed anymore).
class KakaoFriendConnectionException implements Exception {
  const KakaoFriendConnectionException({
    required this.step,
    required this.code,
    required this.userMessage,
    this.consentRefused = false,
  });

  final KakaoFriendConnectionStep step;
  final String code;
  final String userMessage;
  final bool consentRefused;

  @override
  String toString() => userMessage;
}

/// Result of the one-time friend snapshot callable.
class KakaoFriendSnapshotResult {
  const KakaoFriendSnapshotResult({
    required this.completed,
    required this.pairCount,
    this.alreadyCompleted = false,
  });

  final bool completed;
  final int pairCount;
  final bool alreadyCompleted;
}

/// Kakao friend connection service (kakao-friend-pairs contract §8).
///
/// AUTH INVARIANT: Kakao OAuth here authorizes FRIEND EXCLUSION only. This
/// service never mints or restores a Firebase session and never assigns any
/// authenticated state — the canonical Yonsei-email session is a strict
/// PRECONDITION for every step. No nickname/profile/email/phone data is
/// collected or persisted from Kakao.
///
/// SNAPSHOT INVARIANT: the Kakao Friends API is consumed EXACTLY ONCE per
/// account, server-side, by the `createKakaoFriendPairsOnce` callable. The
/// client never fetches the friend list itself and never re-fetches after
/// the server snapshot status is `completed`. There is no per-launch sync.
class KakaoFriendConnectionService {
  KakaoFriendConnectionService({
    AuthService? authService,
    KakaoTalkFriendService? kakaoTalkFriendService,
    FirebaseAuth? firebaseAuth,
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
  }) : _authService = authService ?? AuthService(),
       _kakaoTalkFriendService =
           kakaoTalkFriendService ?? KakaoTalkFriendService(),
       _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance,
       _firestore = firestore ?? FirebaseFirestore.instance,
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion);

  final AuthService _authService;
  final KakaoTalkFriendService _kakaoTalkFriendService;
  final FirebaseAuth _firebaseAuth;
  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;

  String _requireCanonicalSession() {
    final uid = _firebaseAuth.currentUser?.uid;
    if (uid == null || uid.isEmpty) {
      throw StateError('primary_email_auth_required');
    }
    return uid;
  }

  /// Ensures a live Kakao OAuth session for the friends connection.
  ///
  /// PRECONDITION: canonical Firebase session (else
  /// `StateError('primary_email_auth_required')`). Reuses an existing valid
  /// Kakao token; otherwise runs KakaoTalk-app login with account-login
  /// fallback (bundleId misconfiguration is rethrown, matching the legacy
  /// login handling). Never reads profile fields, never touches phone data.
  Future<void> ensureKakaoOAuthSession() async {
    _requireCanonicalSession();
    _authService.ensureKakaoSdkInitialized();

    final existingToken = await _authService.getKakaoAccessTokenForFunctions();
    if (existingToken != null && existingToken.isNotEmpty) {
      return;
    }

    try {
      await KakaoLoginCoordinator.run(() async {
        await _performKakaoOAuth();
        return const <String, dynamic>{};
      });
    } on KakaoFriendConnectionException {
      rethrow;
    } catch (e) {
      debugPrint(
        '[KakaoConnect] oauth failed ${PrivacyLogUtils.errorSummary(e)}',
      );
      throw KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.oauth,
        code: 'kakao_oauth_failed',
        userMessage: _isCancellation(e)
            ? '카카오 연결이 취소되었어요. 친구 연결을 완료해야 추천에서 아는 사람을 제외할 수 있어요.'
            : '카카오 연결에 실패했어요. 잠시 후 다시 시도해 주세요.',
        consentRefused: _isCancellation(e),
      );
    }
  }

  Future<void> _performKakaoOAuth() async {
    if (kIsWeb) {
      await UserApi.instance.loginWithKakaoAccount();
      return;
    }

    bool tryKakaoTalk = false;
    try {
      final installed = await isKakaoTalkInstalled();
      debugPrint('[KakaoConnect] isKakaoTalkInstalled=$installed');
      tryKakaoTalk = installed;
    } catch (e) {
      debugPrint(
        '[KakaoConnect] isKakaoTalkInstalled ${PrivacyLogUtils.errorSummary(e)}',
      );
    }

    if (!tryKakaoTalk) {
      await UserApi.instance.loginWithKakaoAccount();
      return;
    }

    try {
      await UserApi.instance.loginWithKakaoTalk();
    } catch (e) {
      debugPrint(
        '[KakaoConnect] loginWithKakaoTalk ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!_shouldFallbackToKakaoAccount(e)) rethrow;
      debugPrint('[KakaoConnect] fallback to loginWithKakaoAccount');
      await UserApi.instance.loginWithKakaoAccount();
    }
  }

  /// A consent cancellation or an OAuth/configuration rejection happened
  /// after KakaoTalk was already shown. Opening the browser in those cases
  /// repeats the same consent screen and cannot repair the failure. Keep the
  /// account-login fallback only for failures to launch/use KakaoTalk itself.
  bool _shouldFallbackToKakaoAccount(Object error) {
    if (_isCancellation(error)) return false;
    if (error is KakaoAuthException) return false;

    final detail = error is KakaoException
        ? (error.message ?? error.toString())
        : error.toString();
    if (detail.contains('bundleId') || detail.contains('IOS bundleId')) {
      return false;
    }
    return true;
  }

  bool _isCancellation(Object error) {
    if (error is KakaoAuthException &&
        error.error == AuthErrorCause.accessDenied) {
      return true;
    }
    if (error is KakaoClientException &&
        error.reason == ClientErrorCause.cancelled) {
      return true;
    }
    if (error is PlatformException) {
      final code = error.code.toUpperCase();
      if (code == 'CANCELED' || code == 'CANCELLED') return true;
    }
    final text = error.toString().toLowerCase();
    return text.contains('cancel') || text.contains('access_denied');
  }

  /// True when the friends scope is already agreed for the current Kakao
  /// session.
  Future<bool> hasFriendsConsent() async {
    _requireCanonicalSession();
    final status = await _kakaoTalkFriendService.getConsentStatus();
    return status.friendsUsing && status.friendsAgreed;
  }

  /// Requests the friends-scope consent (loginWithNewScopes) and re-verifies.
  /// Cancellation surfaces as a [KakaoFriendConnectionException] with
  /// `consentRefused == true`; the caller keeps the user on the connection
  /// screen — there is no server-side pending write on refusal anymore.
  Future<void> requestFriendsConsent() async {
    _requireCanonicalSession();
    try {
      await _kakaoTalkFriendService.ensureRequiredConsents(
        requireTalkMessage: false,
      );
    } on KakaoTalkReviewException catch (e) {
      throw KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.friendsConsent,
        code: e.code,
        userMessage: e.userMessage,
        consentRefused: e.code == 'consent_cancelled',
      );
    }
  }

  /// Binds the server-verified Kakao identity to the canonical appUserId via
  /// the `linkKakaoFriendIdentity` callable. The access token is passed to
  /// the server for verification and never logged.
  Future<void> linkCurrentKakaoIdentity() async {
    _requireCanonicalSession();
    final accessToken = await _authService.getKakaoAccessTokenForFunctions();
    if (accessToken == null || accessToken.isEmpty) {
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.identityLink,
        code: 'kakao_access_token_missing',
        userMessage: '카카오 연결 세션이 만료되었어요. 카카오 연결을 다시 진행해 주세요.',
      );
    }

    try {
      await _functions.httpsCallable('linkKakaoFriendIdentity').call<void>({
        'kakaoAccessToken': accessToken,
      });
    } on FirebaseFunctionsException catch (e) {
      final detail = '${e.message ?? ''} ${e.details ?? ''}';
      debugPrint('[KakaoConnect] identity link failed code=${e.code}');
      if (detail.contains('identity_conflict')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.identityLink,
          code: 'identity_conflict',
          userMessage:
              '이 카카오 계정은 이미 다른 설레연 계정에 연결되어 있어요. 본인 계정이 맞다면 고객센터에 문의해 주세요.',
        );
      }
      if (detail.contains('relink_required')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.identityLink,
          code: 'relink_required',
          userMessage: '이전에 연결한 카카오 계정과 달라요. 기존 카카오 계정으로 다시 연결해 주세요.',
        );
      }
      if (detail.contains('primary_email_auth_required')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.identityLink,
          code: 'primary_email_auth_required',
          userMessage: '연세 이메일 인증을 먼저 완료해 주세요.',
        );
      }
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.identityLink,
        code: 'identity_link_failed',
        userMessage: '카카오 친구 연결 저장에 실패했어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }

  /// Runs the ONE-TIME server friend snapshot via the
  /// `createKakaoFriendPairsOnce` callable. This IS the Friends-API access
  /// verification — there is no separate client-side friends fetch. The
  /// server verifies the token, reads the friend list once, and materializes
  /// `kakaoFriendPairs` + bilateral `recommendationExclusions`.
  Future<KakaoFriendSnapshotResult> createFriendSnapshotOnce() async {
    _requireCanonicalSession();
    final accessToken = await _authService.getKakaoAccessTokenForFunctions();
    if (accessToken == null || accessToken.isEmpty) {
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.friendSnapshot,
        code: 'kakao_access_token_missing',
        userMessage: '카카오 연결 세션이 만료되었어요. 카카오 연결을 다시 진행해 주세요.',
      );
    }

    try {
      final result = await _functions
          .httpsCallable('createKakaoFriendPairsOnce')
          .call<dynamic>({'kakaoAccessToken': accessToken});
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? {},
      );
      // alreadyCompleted is success: the snapshot ran before and is immutable.
      return KakaoFriendSnapshotResult(
        completed:
            data['completed'] == true || data['alreadyCompleted'] == true,
        pairCount: (data['pairCount'] as num?)?.toInt() ?? 0,
        alreadyCompleted: data['alreadyCompleted'] == true,
      );
    } on FirebaseFunctionsException catch (e) {
      final detail = '${e.message ?? ''} ${e.details ?? ''}';
      debugPrint('[KakaoConnect] friend snapshot failed code=${e.code}');
      if (detail.contains('snapshot_in_progress')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.friendSnapshot,
          code: 'snapshot_in_progress',
          userMessage: '친구 확인이 이미 진행 중이에요. 잠시 후 다시 시도해 주세요.',
        );
      }
      if (detail.contains('identity_conflict')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.friendSnapshot,
          code: 'identity_conflict',
          userMessage:
              '이 카카오 계정은 이미 다른 설레연 계정에 연결되어 있어요. 본인 계정이 맞다면 고객센터에 문의해 주세요.',
        );
      }
      if (detail.contains('kakao_identity_not_linked')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.friendSnapshot,
          code: 'kakao_identity_not_linked',
          userMessage: '카카오 연결 정보가 확인되지 않았어요. 카카오 연결을 다시 진행해 주세요.',
        );
      }
      if (detail.contains('primary_email_auth_required')) {
        throw const KakaoFriendConnectionException(
          step: KakaoFriendConnectionStep.friendSnapshot,
          code: 'primary_email_auth_required',
          userMessage: '연세 이메일 인증을 먼저 완료해 주세요.',
        );
      }
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.friendSnapshot,
        code: 'friend_snapshot_failed',
        userMessage: '카카오 친구 확인에 실패했어요. 네트워크 상태를 확인하고 다시 시도해 주세요.',
      );
    }
  }

  /// Server truth read of `users/{uid}.kakaoFriendSnapshot.status`.
  /// Fail-closed: a missing field means the snapshot never ran
  /// (`not_started`), which keeps legacy accounts gated at the migration
  /// step. This performs NO Kakao API call.
  Future<String> loadFriendSnapshotStatus() async {
    final uid = _requireCanonicalSession();
    final snapshot = await _firestore
        .collection('users')
        .doc(uid)
        .get(const GetOptions(source: Source.server));
    final data = snapshot.data() ?? const <String, dynamic>{};
    final rawSnapshot = data['kakaoFriendSnapshot'];
    if (rawSnapshot is Map) {
      final status = rawSnapshot['status'];
      if (status is String && status.isNotEmpty) return status;
    }
    return 'not_started';
  }

  /// Toggles the avoidance preference via the `setKakaoFriendAvoidanceEnabled`
  /// callable. Pair reconciliation is entirely server-side over the stored
  /// `kakaoFriendPairs` — no consent flow, no friends fetch, ever.
  Future<void> setFriendAvoidanceEnabled(bool enabled) async {
    _requireCanonicalSession();
    await _functions.httpsCallable('setKakaoFriendAvoidanceEnabled').call<void>(
      {'enabled': enabled},
    );
  }

  /// Full chain: OAuth → friends consent → identity link → one-time snapshot
  /// (skipped when the server already recorded `completed`) → server status
  /// check. Throws a step-typed [KakaoFriendConnectionException] on the first
  /// failure. Consent refusal throws with `consentRefused == true` and makes
  /// NO server call — the screen simply keeps the user here with retry copy.
  Future<void> runFullConnectionFlow() async {
    await ensureKakaoOAuthSession();
    if (!await hasFriendsConsent()) {
      await requestFriendsConsent();
    }
    await linkCurrentKakaoIdentity();

    // ONE-TIME guard: a completed snapshot is immutable and must never
    // trigger another Kakao Friends read (contract §3, spec §7/§42).
    var status = await loadFriendSnapshotStatus();
    if (status != 'completed') {
      await createFriendSnapshotOnce();
      status = await loadFriendSnapshotStatus();
    }
    if (status != 'completed') {
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.readiness,
        code: 'friend_snapshot_not_completed',
        userMessage: '친구 확인 상태를 서버에서 확인하지 못했어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }
}
