import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:uuid/uuid.dart';

import '../models/primary_student_email_auth_completion.dart';
import '../models/terms_acceptance.dart';
import '../models/terms_gate_failure.dart';
import '../models/user_model.dart';
import 'firebase_diagnostics.dart';
import 'app_check_readiness.dart';
import 'firebase_runtime.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'adult_verification_service.dart';
import 'storage_service.dart';
import 'user_service.dart';
import 'onboarding_route_resolver.dart';

/// Seolleyeon authentication service (Yonsei-email-primary architecture).
///
/// AUTH INVARIANTS (identity contract §1):
/// - EMAIL AUTH → SEOLLEYEON AUTHENTICATION.
/// - KAKAO OAUTH → FRIEND EXCLUSION AUTHORIZATION ONLY. There is NO code path
///   that exchanges a Kakao access token for a Firebase session in this
///   client. Kakao SDK helpers here exist solely for friend connection,
///   sharing, and cleaning up stale Kakao sessions on logout.
class AuthService {
  AuthService({UserService? userService, AppCheckReadiness? appCheckReadiness})
    : _userService = userService ?? UserService(),
      _appCheckReadiness = appCheckReadiness ?? AppCheckReadiness.firebase();
  final _uuid = const Uuid();
  final UserService _userService;
  final AppCheckReadiness _appCheckReadiness;
  final _storageService = StorageService();
  final FirebaseAuth _firebaseAuth = FirebaseAuth.instance;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: firebaseFunctionsRegion,
  );

  static const _tokenIdPattern = r'^[A-Za-z0-9_-]{1,128}$';
  static String? _primaryEmailLinkInFlightToken;
  static Future<PrimaryStudentEmailAuthCompletion>? _primaryEmailLinkInFlight;
  static String? _lastCompletedPrimaryEmailLinkToken;
  static PrimaryStudentEmailAuthCompletion?
  _lastCompletedPrimaryEmailLinkResult;

  // -------------------------------------------------------------------------
  // Canonical session (primary Yonsei email auth)
  // -------------------------------------------------------------------------

  /// True iff a Firebase session is attached. Grandfathered legacy sessions
  /// (old binaries' Kakao-claim custom tokens) count: the server minted them
  /// and their uid equals the appUserId. No network round-trip, no Kakao.
  Future<bool> ensureCanonicalAppSession() async {
    return _firebaseAuth.currentUser != null;
  }

  /// Requests the primary Yonsei email action link from the server.
  ///
  /// Pre-login: requires NO Kakao identity and NO Firebase session. The
  /// callable is App Check enforced and owns rate limits, token creation and
  /// mail delivery; the client never receives a bearer link.
  Future<void> sendPrimaryStudentEmailLink({
    required String email,
    required String requestId,
  }) async {
    final normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail.endsWith('@yonsei.ac.kr')) {
      throw StateError('primary_email_invalid_domain');
    }
    final normalizedRequestId = requestId.trim().isNotEmpty
        ? requestId.trim()
        : _uuid.v4();

    // Terms gate (contract §4): the acceptance travels with the link request
    // so the server binds it to the `emailLinkTokens` document in the same
    // transaction that later creates the account. Sending without one would
    // create an account carrying no terms record at all (finding F7), so this
    // fails closed and the caller routes the user back to /terms.
    final acceptance = PendingTermsAcceptance.fromStorageMap(
      await _storageService.getPendingLegalConsents(),
    );
    if (acceptance == null || !acceptance.coversRequiredDocuments) {
      throw const TermsGateException(TermsGateFailure.acceptanceRequired);
    }

    FirebaseDiagnostics.logAuthBridgePhase(
      'primary_email_link_send_start',
      functionName: 'sendPrimaryStudentEmailLink',
    );

    final appCheckPreflight = await _appCheckReadiness.preflight();
    if (!appCheckPreflight.isReady) {
      FirebaseDiagnostics.logAuthBridgePhase(
        appCheckPreflight.status == AppCheckPreflightStatus.rejected
            ? 'app_check_token_rejected'
            : 'app_check_token_unavailable',
        functionName: 'sendPrimaryStudentEmailLink',
      );
      throw StateError('app_check_unavailable');
    }

    try {
      await _functions.httpsCallable('sendPrimaryStudentEmailLink').call<void>({
        'email': normalizedEmail,
        'requestId': normalizedRequestId,
        'termsAcceptance': acceptance.toCallablePayload(),
      });
      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_link_send_success',
        functionName: 'sendPrimaryStudentEmailLink',
      );
    } on FirebaseFunctionsException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_link_send_failed',
        functionName: 'sendPrimaryStudentEmailLink',
        error: e,
        stackTrace: st,
      );
      final termsFailure = TermsGateException.fromFunctionsException(e);
      if (termsFailure != null) throw termsFailure;
      rethrow;
    }
  }

  /// Completes the primary Yonsei email authentication.
  ///
  /// Preconditions: the caller already consumed the Firebase action link via
  /// [signInWithEmailLink] (temporary email-link session). The server then
  /// resolves/creates the appUserId, completes the logically single-use token,
  /// and mints the canonical custom token whose uid == appUserId (contract
  /// §4.2). The server can safely replay the same completed result if its
  /// first response was lost.
  Future<PrimaryStudentEmailAuthCompletion> completePrimaryStudentEmailAuth({
    required String token,
  }) async {
    final normalizedToken = token.trim();
    if (!RegExp(_tokenIdPattern).hasMatch(normalizedToken)) {
      throw StateError('invalid_email_link_token');
    }

    FirebaseDiagnostics.logAuthBridgePhase(
      'primary_email_completion_start',
      functionName: 'completePrimaryStudentEmailAuth',
    );

    try {
      final result = await _functions
          .httpsCallable('completePrimaryStudentEmailAuth')
          .call(<String, dynamic>{'token': normalizedToken});
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final customToken = data['customToken']?.toString().trim() ?? '';
      if (customToken.isEmpty) {
        throw StateError('primary_email_completion_response_invalid');
      }
      final completion = PrimaryStudentEmailAuthCompletion.fromMap(data);

      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_signin_start',
        functionName: 'completePrimaryStudentEmailAuth',
      );
      final credential = await _firebaseAuth.signInWithCustomToken(customToken);
      await credential.user?.getIdToken(true);

      final uid = _firebaseAuth.currentUser?.uid;
      if (uid == null || uid != completion.appUserId) {
        // Never keep a session whose runtime uid diverges from the server
        // confirmed appUserId (contract §1 invariant).
        try {
          await _firebaseAuth.signOut();
        } catch (e) {
          debugPrint(
            '[Auth] mismatch sign-out ${PrivacyLogUtils.errorSummary(e)}',
          );
        }
        FirebaseDiagnostics.logAuthBridgePhase(
          'primary_email_uid_mismatch',
          functionName: 'completePrimaryStudentEmailAuth',
        );
        throw StateError('primary_email_auth_uid_mismatch');
      }

      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_completion_success',
        functionName: 'completePrimaryStudentEmailAuth',
      );
      return completion;
    } on FirebaseFunctionsException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_completion_failed',
        functionName: 'completePrimaryStudentEmailAuth',
        error: e,
        stackTrace: st,
      );
      // Contract §5/§9: the account-creating branch rejects a token with no
      // valid terms proof. Surface it as the typed failure so the caller
      // sends the user back to the terms screen (finding F7).
      final termsFailure = TermsGateException.fromFunctionsException(e);
      if (termsFailure != null) throw termsFailure;
      rethrow;
    } on FirebaseAuthException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'primary_email_signin_failed',
        functionName: 'completePrimaryStudentEmailAuth',
        error: e,
        stackTrace: st,
      );
      rethrow;
    }
  }

  bool isSignInWithEmailLink(String link) {
    return _firebaseAuth.isSignInWithEmailLink(link);
  }

  Future<void> signInWithEmailLink({
    required String email,
    required String emailLink,
  }) async {
    await _firebaseAuth.signInWithEmailLink(email: email, emailLink: emailLink);
  }

  /// Records a re-consent for an already signed-in user (contract §6).
  ///
  /// `users/{appUserId}.termsAcceptance` is server-written only, so a
  /// canonical session cannot record its own acceptance — this callable is
  /// the ONLY post-auth path. Idempotent: re-recording the same version
  /// reaches the same terminal state.
  Future<void> recordTermsAcceptance({
    required String version,
    required List<String> acceptedDocumentIds,
    Map<String, bool> optionalConsents = const <String, bool>{},
  }) async {
    if (_firebaseAuth.currentUser == null) {
      throw StateError('primary_email_auth_required');
    }

    final acceptance = PendingTermsAcceptance(
      version: version,
      acceptedDocumentIds: acceptedDocumentIds,
      optionalConsents: optionalConsents,
    );
    if (!acceptance.coversRequiredDocuments) {
      throw const TermsGateException(TermsGateFailure.acceptanceRequired);
    }

    try {
      await _functions
          .httpsCallable('recordTermsAcceptance')
          .call<void>(acceptance.toCallablePayload());
    } on FirebaseFunctionsException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'terms_acceptance_record_failed',
        functionName: 'recordTermsAcceptance',
        error: e,
        stackTrace: st,
      );
      final termsFailure = TermsGateException.fromFunctionsException(e);
      if (termsFailure != null) throw termsFailure;
      rethrow;
    }
  }

  /// Atomically owns the client-side half of primary email-link completion.
  ///
  /// Both [AuthProvider] and [StudentVerificationScreen] may observe the same
  /// native deep link. Firebase action codes are single-use, so this
  /// process-wide gate makes every observer share one sign-in/completion
  /// future. A verified temporary email session is reused after a transient
  /// server failure instead of attempting to consume the action code again.
  Future<PrimaryStudentEmailAuthCompletion> completePrimaryStudentEmailLink({
    required String email,
    required String emailLink,
    required String token,
  }) async {
    final normalizedEmail = email.trim().toLowerCase();
    final normalizedToken = token.trim();
    if (!normalizedEmail.endsWith('@yonsei.ac.kr')) {
      throw StateError('primary_email_invalid_domain');
    }
    if (!RegExp(_tokenIdPattern).hasMatch(normalizedToken)) {
      throw StateError('invalid_email_link_token');
    }

    if (_lastCompletedPrimaryEmailLinkToken == normalizedToken) {
      final completed = _lastCompletedPrimaryEmailLinkResult;
      if (completed != null) return completed;
    }

    final active = _primaryEmailLinkInFlight;
    if (active != null) {
      if (_primaryEmailLinkInFlightToken == normalizedToken) return active;
      throw StateError('primary_email_link_completion_in_progress');
    }

    final request = _completePrimaryStudentEmailLinkOnce(
      email: normalizedEmail,
      emailLink: emailLink,
      token: normalizedToken,
    );
    _primaryEmailLinkInFlightToken = normalizedToken;
    _primaryEmailLinkInFlight = request;

    try {
      final completion = await request;
      _lastCompletedPrimaryEmailLinkToken = normalizedToken;
      _lastCompletedPrimaryEmailLinkResult = completion;
      return completion;
    } finally {
      if (identical(_primaryEmailLinkInFlight, request)) {
        _primaryEmailLinkInFlight = null;
        _primaryEmailLinkInFlightToken = null;
      }
    }
  }

  Future<PrimaryStudentEmailAuthCompletion>
  _completePrimaryStudentEmailLinkOnce({
    required String email,
    required String emailLink,
    required String token,
  }) async {
    final currentUser = _firebaseAuth.currentUser;
    final currentEmail = currentUser?.email?.trim().toLowerCase();
    final hasVerifiedEmailSession =
        currentUser != null &&
        currentUser.emailVerified &&
        currentEmail == email;

    if (!hasVerifiedEmailSession) {
      await signInWithEmailLink(email: email, emailLink: emailLink);
    }
    return completePrimaryStudentEmailAuth(token: token);
  }

  /// Reads the email bound to the opaque token in the continue URL. The token
  /// is deliberately unguessable; the server still re-checks the email after
  /// Firebase completes the one-time email-link sign-in.
  Future<String?> getEmailForStudentEmailLinkToken(String token) async {
    final normalizedToken = token.trim();
    if (!RegExp(_tokenIdPattern).hasMatch(normalizedToken)) {
      return null;
    }

    final snapshot = await _firestore
        .collection('emailLinkTokens')
        .doc(normalizedToken)
        .get();
    final rawEmail = snapshot.data()?['email'];
    final email = rawEmail is String ? rawEmail.trim().toLowerCase() : '';
    return email.endsWith('@yonsei.ac.kr') ? email : null;
  }

  // -------------------------------------------------------------------------
  // Kakao SDK helpers (friend connection / share ONLY — never authentication)
  // -------------------------------------------------------------------------

  static bool _kakaoInited = false;

  /// Idempotent Kakao SDK bootstrap. Needed by the friend-connection flow and
  /// Kakao share features; establishing a Kakao session never authenticates
  /// the Seolleyeon account.
  void ensureKakaoSdkInitialized() {
    if (_kakaoInited) return;

    const kakaoNativeAppKey = 'cb08e2aea50a58b7d0c5e610e0c5a644';
    const kakaoJavaScriptKey = 'bff1db6356fcd7aaf5dc466080359ce0';

    KakaoSdk.init(
      nativeAppKey: kIsWeb ? null : kakaoNativeAppKey,
      javaScriptAppKey: kIsWeb ? kakaoJavaScriptKey : null,
    );

    _kakaoInited = true;
    debugPrint('[Kakao] KakaoSdk.init ensured (kIsWeb=$kIsWeb)');
  }

  /// Drops the TEMPORARY Firebase session that `signInWithEmailLink()` leaves
  /// attached when primary auth completion is rejected at the terms gate.
  ///
  /// That session is not a canonical app session — no `users/{uid}` document
  /// exists for it — so it must not survive into the terms screen, which
  /// classifies by `currentUser != null`.
  ///
  /// Returns whether no session remains. `signOut()` can throw, so the answer
  /// is derived from the observed session rather than from the call
  /// succeeding: a swallowed error can never report success.
  Future<bool> clearTemporaryEmailLinkSession() async {
    try {
      await _firebaseAuth.signOut();
    } catch (e) {
      debugPrint(
        '[Auth] temporary email-link sign-out '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
    return _firebaseAuth.currentUser == null;
  }

  /// Signs out both the Firebase session and any Kakao SDK session so a
  /// different next user on this device cannot inherit a stale Kakao token.
  Future<void> signOutAll() async {
    try {
      await _firebaseAuth.signOut();
    } catch (e) {
      debugPrint('[Auth] Firebase signOut ${PrivacyLogUtils.errorSummary(e)}');
    }

    try {
      await UserApi.instance.logout();
    } catch (e) {
      debugPrint('[Auth] Kakao logout ${PrivacyLogUtils.errorSummary(e)}');
    }
  }

  /// Returns a server-verifiable Kakao access token for callables that
  /// authorize the FRIEND EXCLUSION flow (never authentication).
  Future<String?> getKakaoAccessTokenForFunctions() async {
    try {
      final kakaoToken = await TokenManagerProvider.instance.manager.getToken();
      final accessToken = kakaoToken?.accessToken.trim() ?? '';
      if (accessToken.isEmpty) {
        return null;
      }

      try {
        await UserApi.instance.accessTokenInfo();
        return accessToken;
      } catch (e) {
        debugPrint(
          '[Auth] Kakao access token ${PrivacyLogUtils.errorSummary(e)}',
        );
        // 만료·폐기 토큰이 로컬에 남아 있으면 이후 호출이 계속 실패하므로 세션 정리
        final msg = e.toString();
        if (msg.contains('-401') || msg.contains('does not exist')) {
          try {
            await UserApi.instance.logout();
            debugPrint('[Auth] Kakao logout after invalid access token');
          } catch (logoutErr) {
            debugPrint(
              '[Auth] Kakao logout after invalid token '
              '${PrivacyLogUtils.errorSummary(logoutErr)}',
            );
          }
          // logout이 실패하면 무효 토큰이 로컬에 그대로 남아, 이후 모든 호출이
          // 같은 -401 왕복을 반복한다. 로컬 토큰 저장소를 직접 비워서
          // 다음 호출은 네트워크 요청 없이 곧바로 null을 반환하게 한다.
          try {
            await TokenManagerProvider.instance.manager.clear();
            debugPrint('[Auth] Cleared invalid local Kakao token');
          } catch (clearErr) {
            debugPrint('[Auth] Kakao token clear failed: $clearErr');
          }
        }
        return null;
      }
    } catch (e) {
      debugPrint(
        '[Auth] getKakaoAccessTokenForFunctions '
        '${PrivacyLogUtils.errorSummary(e)}',
      );

      return null;
    }
  }

  // -------------------------------------------------------------------------
  // Firestore passthroughs (keyed by appUserId == users/{docId})
  // -------------------------------------------------------------------------

  Future<bool> kakaoUserExists(String appUserId) async {
    return await _userService.existsKakaoUser(appUserId);
  }

  Future<bool> isAccountWithdrawn(String appUserId) async {
    return await _userService.isAccountWithdrawn(appUserId);
  }

  Future<bool> isRejoinRestricted(String appUserId) async {
    return await _userService.isRejoinRestricted(appUserId);
  }

  /// Flushes the pre-auth acceptance into the legacy `legalConsents` UX
  /// receipt (contract §3). The authoritative record is written server-side
  /// by `completePrimaryStudentEmailAuth`; this write is a receipt only.
  Future<void> syncPendingLegalConsents(String appUserId) async {
    final acceptance = await _storageService.getPendingTermsAcceptance();
    if (acceptance == null) return;

    await _userService.saveLegalConsents(
      kakaoUserId: appUserId,
      acceptance: acceptance,
    );
    await _storageService.clearPendingLegalConsents();
  }

  Future<bool> isInitialSetupComplete(String appUserId) async {
    return await _userService.isInitialSetupComplete(appUserId);
  }

  Future<bool> isAdultVerified(String appUserId) async {
    if (AdultVerificationService.isTemporarilyDisabled) return true;

    final profile = await _userService.getUserProfile(appUserId);
    return profile?['adultVerified'] == true &&
        profile?['realNameVerified'] == true;
  }

  Future<Map<String, dynamic>?> getUserProfile(String appUserId) async {
    return await _userService.getUserProfile(appUserId);
  }

  /// 연세 인증은 됐지만 초기설정이 미완료일 때, 이어서 채울 다음 단계 라우트 (예: 3단계까지 했으면 4단계)
  Future<String?> getOnboardingNextRoute(String appUserId) async {
    final profile = await _userService.getUserProfile(appUserId);
    return resolveOnboardingNextRoute(profile);
  }

  /// Marks an already complete legacy profile as finished after its required
  /// onboarding fields have been verified from Firestore.
  Future<void> completeOnboarding(String appUserId) async {
    await _userService.completeOnboarding(appUserId);
  }

  Future<bool> hasSeenTutorial(String appUserId) async {
    return await _userService.hasSeenTutorial(appUserId);
  }

  Future<void> setTutorialSeen(String appUserId) async {
    await _userService.setTutorialSeen(appUserId);
  }

  Future<bool> isStudentVerified(String appUserId) async {
    return await _userService.isStudentVerified(appUserId);
  }

  Future<String?> getStudentEmail(String appUserId) async {
    return await _userService.getStudentEmail(appUserId);
  }

  Future<void> setStudentVerified({
    required String kakaoUserId,
    required String studentEmail,
  }) async {
    await _userService.setStudentVerification(
      kakaoUserId: kakaoUserId,
      studentEmail: studentEmail,
    );
  }

  // -------------------------------------------------------------------------
  // Legacy stubs (지금 정책상 미사용이지만 당장 삭제는 보류)
  // -------------------------------------------------------------------------

  Future<UserModel?> signUp({
    required String phoneNumber,
    required String verificationCode,
    String? kakaoToken,
  }) async {
    try {
      final user = UserModel(
        id: _uuid.v4(),
        phoneNumber: phoneNumber,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
      );

      await Future.delayed(const Duration(seconds: 1));
      return user;
    } catch (e) {
      throw Exception('Sign up failed: $e');
    }
  }

  Future<bool> verifyStudent({
    required String userId,
    required String portalId,
    required String portalPassword,
  }) async {
    try {
      await Future.delayed(const Duration(seconds: 1));
      return true;
    } catch (e) {
      throw Exception('Student verification failed: $e');
    }
  }

  Future<UserModel?> getUser(String userId) async {
    try {
      await Future.delayed(const Duration(milliseconds: 500));
      return null;
    } catch (e) {
      throw Exception('Get user failed: $e');
    }
  }

  Future<void> updateUser(UserModel user) async {
    try {
      await Future.delayed(const Duration(milliseconds: 500));
    } catch (e) {
      throw Exception('Update user failed: $e');
    }
  }
}
