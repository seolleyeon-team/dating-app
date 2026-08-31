import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

import '../shared/utils/privacy_log_utils.dart';
import 'auth_service.dart';
import 'contact_block_service.dart';
import 'firebase_runtime.dart';
import 'kakao_login_coordinator.dart';
import 'kakao_talk_friend_service.dart';

/// Steps of the post-auth Kakao friend connection chain.
enum KakaoFriendConnectionStep {
  oauth,
  friendsConsent,
  friendsApiVerification,
  identityLink,
  initialSync,
  readiness,
}

/// Typed failure surfaced by [KakaoFriendConnectionService]. `consentRefused`
/// marks a user-cancelled consent so the screen can keep the fail-closed
/// pending state and offer a retry.
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

/// Kakao friend connection service (identity contract §7).
///
/// AUTH INVARIANT: Kakao OAuth here authorizes FRIEND EXCLUSION only. This
/// service never mints or restores a Firebase session and never assigns any
/// authenticated state — the canonical Yonsei-email session is a strict
/// PRECONDITION for every step. No nickname/profile/email/phone data is
/// collected or persisted from Kakao.
class KakaoFriendConnectionService {
  KakaoFriendConnectionService({
    AuthService? authService,
    KakaoTalkFriendService? kakaoTalkFriendService,
    ContactBlockService? contactBlockService,
    FirebaseAuth? firebaseAuth,
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
  }) : _authService = authService ?? AuthService(),
       _kakaoTalkFriendService =
           kakaoTalkFriendService ?? KakaoTalkFriendService(),
       _contactBlockService = contactBlockService ?? ContactBlockService(),
       _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance,
       _firestore = firestore ?? FirebaseFirestore.instance,
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion);

  final AuthService _authService;
  final KakaoTalkFriendService _kakaoTalkFriendService;
  final ContactBlockService _contactBlockService;
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
    } on KakaoException catch (e) {
      final detail = e.message ?? e.toString();
      debugPrint(
        '[KakaoConnect] loginWithKakaoTalk ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (detail.contains('bundleId') || detail.contains('IOS bundleId')) {
        rethrow;
      }
      debugPrint('[KakaoConnect] fallback to loginWithKakaoAccount');
      await UserApi.instance.loginWithKakaoAccount();
    } catch (e) {
      debugPrint(
        '[KakaoConnect] loginWithKakaoTalk ${PrivacyLogUtils.errorSummary(e)}',
      );
      final detail = e.toString();
      if (detail.contains('bundleId') || detail.contains('IOS bundleId')) {
        rethrow;
      }
      await UserApi.instance.loginWithKakaoAccount();
    }
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
  /// `consentRefused == true`.
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

  /// Verifies real Friends API access. An empty friend list IS success; only
  /// API/scope/session errors fail this step.
  Future<void> verifyFriendsApiAccess() async {
    _requireCanonicalSession();
    try {
      final lookup = await _kakaoTalkFriendService.fetchFriends(
        requestConsentIfNeeded: false,
      );
      debugPrint(
        '[KakaoConnect] friends api verified count=${lookup.friends.length}',
      );
    } on KakaoTalkReviewException catch (e) {
      throw KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.friendsApiVerification,
        code: e.code,
        userMessage: e.userMessage,
        consentRefused: e.code == 'consent_cancelled',
      );
    } catch (e) {
      debugPrint(
        '[KakaoConnect] friends api verify failed '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.friendsApiVerification,
        code: 'friends_api_failed',
        userMessage: '카카오 친구 목록 확인에 실패했어요. 잠시 후 다시 시도해 주세요.',
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

  /// Runs the initial friend-exclusion sync using the existing fail-closed
  /// begin + sync callables (no extra consent dialog from this path).
  Future<void> syncInitialFriendExclusions() async {
    _requireCanonicalSession();
    try {
      await _contactBlockService.syncKakaoTalkFriendBlocks(
        requestConsentIfNeeded: false,
      );
    } catch (e) {
      debugPrint(
        '[KakaoConnect] initial sync failed ${PrivacyLogUtils.errorSummary(e)}',
      );
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.initialSync,
        code: 'initial_sync_failed',
        userMessage: '아는 사람 추천 차단 동기화에 실패했어요. 네트워크 상태를 확인하고 다시 시도해 주세요.',
      );
    }
  }

  /// Server truth check: the account is ready only when the fail-closed
  /// `recommendationPrivacyReady` flag AND the connection marker are both set.
  Future<bool> verifyFriendConnectionReady() async {
    final uid = _requireCanonicalSession();
    final snapshot = await _firestore
        .collection('users')
        .doc(uid)
        .get(const GetOptions(source: Source.server));
    final data = snapshot.data() ?? const <String, dynamic>{};
    final connection = data['kakaoFriendConnection'];
    final connected = connection is Map && connection['connected'] == true;
    return data['recommendationPrivacyReady'] == true && connected;
  }

  /// Marks the fail-closed pending state after a consent refusal (same server
  /// behavior the legacy Kakao login screen used).
  Future<void> markPendingAfterConsentRefusal() async {
    try {
      await _contactBlockService
          .markRecommendationPrivacyPendingAfterConsentRefusal();
    } catch (e) {
      debugPrint(
        '[KakaoConnect] pending mark failed ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  /// Full chain: OAuth → consent → Friends API verification → identity link →
  /// initial sync → server readiness. Throws a step-typed
  /// [KakaoFriendConnectionException] on the first failure.
  Future<void> runFullConnectionFlow() async {
    await ensureKakaoOAuthSession();
    if (!await hasFriendsConsent()) {
      await requestFriendsConsent();
    }
    await verifyFriendsApiAccess();
    await linkCurrentKakaoIdentity();
    await syncInitialFriendExclusions();
    final ready = await verifyFriendConnectionReady();
    if (!ready) {
      throw const KakaoFriendConnectionException(
        step: KakaoFriendConnectionStep.readiness,
        code: 'friend_connection_not_ready',
        userMessage: '친구 연결 상태를 서버에서 확인하지 못했어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }
}
