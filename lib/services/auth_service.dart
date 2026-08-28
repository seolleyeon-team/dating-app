import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:uuid/uuid.dart';

import '../models/email_link_completion.dart';
import '../models/user_model.dart';
import 'firebase_diagnostics.dart';
import 'app_check_readiness.dart';
import 'firebase_session_failure.dart';
import 'firebase_session_inspector.dart';
import 'firebase_runtime.dart';
import '../utils/phone_hash_utils.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'adult_verification_service.dart';
import 'kakao_login_coordinator.dart';
import 'storage_service.dart';
import 'user_service.dart';
import 'onboarding_route_resolver.dart';

class AuthService {
  AuthService({UserService? userService, AppCheckReadiness? appCheckReadiness})
    : _userService = userService ?? UserService(),
      _appCheckReadiness = appCheckReadiness ?? AppCheckReadiness.firebase();
  final _uuid = const Uuid();
  final UserService _userService;
  final AppCheckReadiness _appCheckReadiness;
  static const _sessionInspector = FirebaseSessionInspector();
  final _storageService = StorageService();
  final FirebaseAuth _firebaseAuth = FirebaseAuth.instance;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: firebaseFunctionsRegion,
  );
  FirebaseSessionFailure? _lastFirebaseSessionFailure;

  FirebaseSessionFailure? get lastFirebaseSessionFailure =>
      _lastFirebaseSessionFailure;

  Future<FirebaseSessionInspection> _inspectFirebaseSession(
    String kakaoUserId,
  ) async {
    final currentUser = _firebaseAuth.currentUser;
    final inspection = await _sessionInspector.inspect(
      expectedKakaoUserId: kakaoUserId,
      currentUid: currentUser?.uid,
      loadClaims: (forceRefresh) async {
        final tokenResult = await currentUser!.getIdTokenResult(forceRefresh);
        return tokenResult.claims;
      },
    );

    if (inspection.state == FirebaseSessionIdentityState.mismatched) {
      debugPrint(
        '[Auth] Firebase session mismatch '
        '${PrivacyLogUtils.idFingerprint(inspection.firebaseUid)} '
        'claim=${PrivacyLogUtils.idFingerprint(inspection.claimedKakaoUserId)} '
        'expected=${PrivacyLogUtils.idFingerprint(kakaoUserId)}',
      );
    } else if (inspection.state ==
        FirebaseSessionIdentityState.inspectionFailed) {
      debugPrint(
        '[Auth] Firebase session inspection '
        '${PrivacyLogUtils.errorSummary(inspection.error ?? StateError('unknown'))}',
      );
    }

    return inspection;
  }

  Future<void> _signOutFirebaseIfMismatched(
    String kakaoUserId,
    FirebaseSessionInspection inspection,
  ) async {
    if (inspection.state != FirebaseSessionIdentityState.mismatched) {
      return;
    }

    if (_firebaseAuth.currentUser == null) {
      return;
    }

    await _firebaseAuth.signOut();
    debugPrint(
      '[Auth] Signed out mismatched Firebase session '
      '${PrivacyLogUtils.idFingerprint(kakaoUserId)}',
    );
  }

  void _setFirebaseSessionFailure(
    FirebaseSessionFailure failure, {
    String? kakaoUserId,
  }) {
    _lastFirebaseSessionFailure = failure;
    FirebaseDiagnostics.logAuthBridgePhase(
      'firebase_session_failure',
      kakaoUserId: kakaoUserId,
    );
    debugPrint(
      '[Auth] Firebase bridge failure '
      'reason=${failure.diagnosticCode} '
      'code=${failure.errorCode ?? 'unknown'}',
    );
  }

  void _clearFirebaseSessionFailure() {
    _lastFirebaseSessionFailure = null;
  }

  /// ✅ 카카오 로그인
  /// - Web: 카카오 계정 로그인
  /// - Mobile(iOS/Android): 카카오톡 앱 우선 -> 실패/미설치 시 계정 로그인 fallback
  /// 반환: userInfo(Map) = {id, nickname, profileImageUrl, email}
  Future<Map<String, dynamic>> loginWithKakao() {
    return KakaoLoginCoordinator.run(_loginWithKakao);
  }

  Future<Map<String, dynamic>> _loginWithKakao() async {
    _ensureKakaoInit();
    FirebaseDiagnostics.logAuthBridgePhase('kakao_login_start');

    try {
      if (kIsWeb) {
        // Web: JS SDK 기반 카카오 계정 로그인
        await UserApi.instance.loginWithKakaoAccount();
      } else {
        // Mobile: 카카오톡 설치되어 있으면 카톡 앱 로그인 우선, 실패/미설치/크래시 시 웹 로그인
        bool tryKakaoTalk = false;
        try {
          final installed = await isKakaoTalkInstalled();
          debugPrint('[Kakao] isKakaoTalkInstalled=$installed');
          tryKakaoTalk = installed;
        } catch (e) {
          debugPrint(
            '[Kakao] isKakaoTalkInstalled ${PrivacyLogUtils.errorSummary(e)}',
          );
        }

        if (tryKakaoTalk) {
          try {
            await UserApi.instance.loginWithKakaoTalk();
          } on KakaoException catch (e) {
            final detail = e.message ?? e.toString();
            debugPrint(
              '[Kakao] loginWithKakaoTalk ${PrivacyLogUtils.errorSummary(e)}',
            );
            if (detail.contains('bundleId') ||
                detail.contains('IOS bundleId')) {
              rethrow;
            }
            debugPrint('[Kakao] fallback to loginWithKakaoAccount');
            await UserApi.instance.loginWithKakaoAccount();
          } catch (e) {
            debugPrint(
              '[Kakao] loginWithKakaoTalk ${PrivacyLogUtils.errorSummary(e)}',
            );

            final detail = e.toString();
            if (detail.contains('bundleId') ||
                detail.contains('IOS bundleId')) {
              rethrow;
            }
            await UserApi.instance.loginWithKakaoAccount();
          }
        } else {
          await UserApi.instance.loginWithKakaoAccount();
        }
      }

      // 사용자 정보
      final user = await UserApi.instance.me();
      final kakaoUserId = user.id.toString();

      if (kakaoUserId.isEmpty) {
        throw Exception('카카오 사용자 ID를 가져오지 못했습니다.');
      }

      final phoneNumber = user.kakaoAccount?.phoneNumber;

      // 전화번호가 있으면 비동기로 phoneHash 저장 (실패해도 로그인 막지 않음)
      if (phoneNumber != null && phoneNumber.trim().isNotEmpty) {
        _savePhoneHashInBackground(kakaoUserId, phoneNumber);
      }

      FirebaseDiagnostics.logAuthBridgePhase(
        'kakao_login_success',
        kakaoUserId: kakaoUserId,
      );

      return {
        'id': kakaoUserId,
        'nickname': user.kakaoAccount?.profile?.nickname,
        'profileImageUrl': user.kakaoAccount?.profile?.profileImageUrl,
        'email': user.kakaoAccount?.email,
        'phoneNumber': phoneNumber,
      };
    } on KakaoException catch (e) {
      final detail = e.message ?? e.toString();
      FirebaseDiagnostics.logAuthBridgePhase('kakao_login_failed', error: e);
      throw Exception('카카오 로그인 실패: $detail');
    } catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'kakao_login_failed',
        error: e,
        stackTrace: st,
      );
      throw Exception('로그인 실패: $e');
    }
  }

  static bool _kakaoInited = false;

  void _ensureKakaoInit() {
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

  /// 카카오 계정(웹) 로그인만 수행. iOS 번들 ID 오류 시 사용자가 "웹으로 로그인" 선택할 때 사용.
  Future<Map<String, dynamic>> loginWithKakaoAccountOnly() {
    return KakaoLoginCoordinator.run(_loginWithKakaoAccountOnly);
  }

  Future<Map<String, dynamic>> _loginWithKakaoAccountOnly() async {
    _ensureKakaoInit();
    await UserApi.instance.loginWithKakaoAccount();
    final user = await UserApi.instance.me();
    final kakaoUserId = user.id.toString();
    if (kakaoUserId.isEmpty) {
      throw Exception('카카오 사용자 ID를 가져오지 못했습니다.');
    }
    final phoneNumber = user.kakaoAccount?.phoneNumber;
    if (phoneNumber != null && phoneNumber.trim().isNotEmpty) {
      _savePhoneHashInBackground(kakaoUserId, phoneNumber);
    }
    return {
      'id': kakaoUserId,
      'nickname': user.kakaoAccount?.profile?.nickname,
      'profileImageUrl': user.kakaoAccount?.profile?.profileImageUrl,
      'email': user.kakaoAccount?.email,
      'phoneNumber': phoneNumber,
    };
  }

  /// 전화번호 해시를 서버에 저장 (fire-and-forget)
  void _savePhoneHashInBackground(String kakaoUserId, String rawPhone) {
    Future(() async {
      try {
        final phoneHash = PhoneHashUtils.normalizeAndHash(rawPhone);
        if (phoneHash == null) {
          debugPrint(
            '[Auth] phone normalization failed hasPhone=${rawPhone.isNotEmpty}',
          );
          return;
        }
        final callable = _functions.httpsCallable('saveUserPhoneHash');
        await callable.call(<String, dynamic>{
          'phoneHash': phoneHash,
          'phoneSource': 'kakao',
        });
        debugPrint('[Auth] phoneHash 저장 완료');
      } catch (e) {
        debugPrint('[Auth] phoneHash save ${PrivacyLogUtils.errorSummary(e)}');
      }
    });
  }

  // -------------------------
  // 이하 기존 기능 (너 코드 유지)
  // -------------------------

  Future<bool> kakaoUserExists(String kakaoUserId) async {
    return await _userService.existsKakaoUser(kakaoUserId);
  }

  Future<bool> isAccountWithdrawn(String kakaoUserId) async {
    return await _userService.isAccountWithdrawn(kakaoUserId);
  }

  Future<bool> isRejoinRestricted(String kakaoUserId) async {
    return await _userService.isRejoinRestricted(kakaoUserId);
  }

  Future<void> syncPendingLegalConsents(String kakaoUserId) async {
    final pendingConsents = await _storageService.getPendingLegalConsents();
    if (pendingConsents == null) return;

    await _userService.saveLegalConsents(
      kakaoUserId: kakaoUserId,
      consentData: pendingConsents,
    );
    await _storageService.clearPendingLegalConsents();
  }

  Future<bool> isInitialSetupComplete(String kakaoUserId) async {
    return await _userService.isInitialSetupComplete(kakaoUserId);
  }

  Future<bool> isAdultVerified(String kakaoUserId) async {
    if (AdultVerificationService.isTemporarilyDisabled) return true;

    final profile = await _userService.getUserProfile(kakaoUserId);
    return profile?['adultVerified'] == true &&
        profile?['realNameVerified'] == true;
  }

  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    return await _userService.getUserProfile(kakaoUserId);
  }

  /// 연세 인증은 됐지만 초기설정이 미완료일 때, 이어서 채울 다음 단계 라우트 (예: 3단계까지 했으면 4단계)
  Future<String?> getOnboardingNextRoute(String kakaoUserId) async {
    final profile = await _userService.getUserProfile(kakaoUserId);
    return resolveOnboardingNextRoute(profile);
  }

  /// Marks an already complete legacy profile as finished after its required
  /// onboarding fields have been verified from Firestore.
  Future<void> completeOnboarding(String kakaoUserId) async {
    await _userService.completeOnboarding(kakaoUserId);
  }

  Future<bool> hasSeenTutorial(String kakaoUserId) async {
    return await _userService.hasSeenTutorial(kakaoUserId);
  }

  Future<void> setTutorialSeen(String kakaoUserId) async {
    await _userService.setTutorialSeen(kakaoUserId);
  }

  Future<bool> isStudentVerified(String kakaoUserId) async {
    return await _userService.isStudentVerified(kakaoUserId);
  }

  Future<String?> getStudentEmail(String kakaoUserId) async {
    return await _userService.getStudentEmail(kakaoUserId);
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

  Future<void> sendStudentEmailLink({
    required String email,
    String? requestId,
  }) async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw StateError('카카오 로그인 정보가 없습니다.');
    }

    // The callable only accepts the Kakao-backed Firebase session. Keeping the
    // session bridge here prevents a bare email-link account from using this
    // endpoint as a mail-sending relay.
    final hasSession = await ensureFirebaseSessionForKakao(kakaoUserId);
    if (!hasSession) {
      throw StateError('로그인 세션을 확인하지 못했습니다. 다시 로그인해주세요.');
    }

    await _functions.httpsCallable('sendStudentVerificationEmail').call<void>({
      'email': email,
      'requestId': requestId?.trim().isNotEmpty == true
          ? requestId!.trim()
          : _uuid.v4(),
    });
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

  /// Reads the email bound to the opaque token in the continue URL. The token
  /// is deliberately unguessable; the server still re-checks the email after
  /// Firebase completes the one-time email-link sign-in.
  Future<String?> getEmailForStudentEmailLinkToken(String token) async {
    final normalizedToken = token.trim();
    if (!RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(normalizedToken)) {
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

  /// Completes an already-authenticated Firebase email-link session by
  /// atomically binding the verified mailbox to the Kakao-backed user.
  Future<EmailLinkCompletion> completeStudentEmailLink({
    required String token,
    String? expectedKakaoUserId,
  }) async {
    final normalizedToken = token.trim();
    final normalizedExpectedKakaoUserId = expectedKakaoUserId?.trim() ?? '';
    if (!RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(normalizedToken)) {
      throw StateError('invalid_email_link_token');
    }

    FirebaseDiagnostics.logAuthBridgePhase(
      'email_link_completion_start',
      functionName: 'completeStudentEmailLink',
      kakaoUserId: normalizedExpectedKakaoUserId.isEmpty
          ? null
          : normalizedExpectedKakaoUserId,
    );

    final callable = _functions.httpsCallable('completeStudentEmailLink');
    final payload = <String, dynamic>{
      'token': normalizedToken,
      if (normalizedExpectedKakaoUserId.isNotEmpty)
        'expectedKakaoUserId': normalizedExpectedKakaoUserId,
    };

    try {
      final result = await callable.call(payload);
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final customToken = data['customToken']?.toString().trim() ?? '';
      final kakaoUserId = data['kakaoUserId']?.toString().trim() ?? '';
      final email = data['email']?.toString().trim().toLowerCase() ?? '';
      if (customToken.isEmpty ||
          kakaoUserId.isEmpty ||
          !email.endsWith('@yonsei.ac.kr')) {
        throw StateError('email_link_completion_response_invalid');
      }

      final credential = await _firebaseAuth.signInWithCustomToken(customToken);
      await credential.user?.getIdToken(true);
      FirebaseDiagnostics.logAuthBridgePhase(
        'email_link_completion_success',
        functionName: 'completeStudentEmailLink',
        kakaoUserId: kakaoUserId,
      );
      return EmailLinkCompletion(kakaoUserId: kakaoUserId, email: email);
    } on FirebaseFunctionsException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'email_link_completion_failed',
        functionName: 'completeStudentEmailLink',
        kakaoUserId: normalizedExpectedKakaoUserId.isEmpty
            ? null
            : normalizedExpectedKakaoUserId,
        error: e,
        stackTrace: st,
      );
      rethrow;
    }
  }

  Future<bool> ensureFirebaseSessionForKakao(String kakaoUserId) async {
    _clearFirebaseSessionFailure();
    FirebaseDiagnostics.logAuthBridgePhase(
      'firebase_session_prepare_start',
      kakaoUserId: kakaoUserId,
    );

    try {
      final inspection = await _inspectFirebaseSession(kakaoUserId);
      switch (inspection.state) {
        case FirebaseSessionIdentityState.matching:
          FirebaseDiagnostics.logAuthBridgePhase(
            'firebase_session_already_attached',
            kakaoUserId: kakaoUserId,
          );
          debugPrint(
            '[Auth] Firebase session attached '
            '${PrivacyLogUtils.idFingerprint(kakaoUserId)}',
          );
          return true;
        case FirebaseSessionIdentityState.inspectionFailed:
          _setFirebaseSessionFailure(
            const FirebaseSessionFailure(
              reason: FirebaseSessionFailureReason.sessionInspectionFailed,
            ),
            kakaoUserId: kakaoUserId,
          );
          return false;
        case FirebaseSessionIdentityState.mismatched:
          await _signOutFirebaseIfMismatched(kakaoUserId, inspection);
        case FirebaseSessionIdentityState.noSession:
          break;
      }

      final kakaoToken = await TokenManagerProvider.instance.manager.getToken();
      final accessToken = kakaoToken?.accessToken.trim() ?? '';

      if (accessToken.isEmpty) {
        FirebaseDiagnostics.logAuthBridgePhase(
          'kakao_access_token_missing',
          kakaoUserId: kakaoUserId,
        );
        debugPrint(
          '[Auth] No Kakao access token available for Firebase auth bridge',
        );
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.kakaoAccessTokenMissing,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }

      FirebaseDiagnostics.logAuthBridgePhase(
        'kakao_access_token_info_start',
        kakaoUserId: kakaoUserId,
      );
      try {
        await UserApi.instance.accessTokenInfo();
      } on KakaoException catch (e, st) {
        FirebaseDiagnostics.logAuthBridgePhase(
          'kakao_access_token_info_failed',
          kakaoUserId: kakaoUserId,
          error: e,
          stackTrace: st,
        );
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.kakaoAccessTokenInvalid,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      } catch (e, st) {
        FirebaseDiagnostics.logAuthBridgePhase(
          'kakao_access_token_info_failed',
          kakaoUserId: kakaoUserId,
          error: e,
          stackTrace: st,
        );
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.kakaoAccessTokenInvalid,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }
      FirebaseDiagnostics.logAuthBridgePhase(
        'kakao_access_token_info_success',
        kakaoUserId: kakaoUserId,
      );

      FirebaseDiagnostics.logAuthBridgePhase(
        'app_check_preflight_start',
        kakaoUserId: kakaoUserId,
      );
      final appCheckPreflight = await _appCheckReadiness.preflight();
      if (!appCheckPreflight.isReady) {
        final reason =
            appCheckPreflight.status == AppCheckPreflightStatus.rejected
            ? FirebaseSessionFailureReason.appCheckRejected
            : FirebaseSessionFailureReason.appCheckUnavailable;
        FirebaseDiagnostics.logAuthBridgePhase(
          reason == FirebaseSessionFailureReason.appCheckRejected
              ? 'app_check_token_rejected'
              : 'app_check_token_unavailable',
          kakaoUserId: kakaoUserId,
        );
        _setFirebaseSessionFailure(
          FirebaseSessionFailure(
            reason: reason,
            errorCode: appCheckPreflight.errorCode,
            supportCode: appCheckPreflight.supportCode,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }
      FirebaseDiagnostics.logAuthBridgePhase(
        'app_check_preflight_pass',
        kakaoUserId: kakaoUserId,
      );

      final callable = _functions.httpsCallable('createFirebaseCustomToken');
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_request_start',
        kakaoUserId: kakaoUserId,
      );
      final result = await callable.call(<String, dynamic>{
        'accessToken': accessToken,
      });
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_request_success',
        kakaoUserId: kakaoUserId,
      );
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final customToken = data['customToken']?.toString().trim() ?? '';
      if (customToken.isEmpty) {
        FirebaseDiagnostics.logAuthBridgePhase(
          'firebase_custom_token_response_empty',
          kakaoUserId: kakaoUserId,
        );
        debugPrint('[Auth] Firebase custom token response was empty');
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.customTokenEmpty,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }

      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_signin_start',
        kakaoUserId: kakaoUserId,
      );
      final credential = await _firebaseAuth.signInWithCustomToken(customToken);
      final signedInInspection = await _inspectFirebaseSession(kakaoUserId);
      if (signedInInspection.state ==
          FirebaseSessionIdentityState.inspectionFailed) {
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.sessionInspectionFailed,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }
      if (signedInInspection.state == FirebaseSessionIdentityState.mismatched) {
        await _signOutFirebaseIfMismatched(kakaoUserId, signedInInspection);
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.identityMismatch,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }
      if (signedInInspection.state != FirebaseSessionIdentityState.matching ||
          credential.user == null) {
        _setFirebaseSessionFailure(
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.firebaseSignInFailed,
          ),
          kakaoUserId: kakaoUserId,
        );
        return false;
      }
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_session_identity_verified',
        kakaoUserId: kakaoUserId,
      );
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_signin_success',
        kakaoUserId: kakaoUserId,
      );
      debugPrint(
        '[Auth] Firebase custom auth ${PrivacyLogUtils.idFingerprint(kakaoUserId)}',
      );
      return true;
    } on FirebaseFunctionsException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_request_failed',
        kakaoUserId: kakaoUserId,
        error: e,
        stackTrace: st,
      );
      debugPrint(
        '[Auth] ensureFirebaseSessionForKakao functions error: '
        'code=${e.code} '
        'message=${FirebaseDiagnostics.safeErrorForLog(e.message)}',
      );
      _setFirebaseSessionFailure(
        FirebaseSessionFailure(
          reason: e.code == 'unauthenticated'
              ? FirebaseSessionFailureReason.callableUnauthenticated
              : FirebaseSessionFailureReason.callableFailed,
          errorCode: e.code,
        ),
        kakaoUserId: kakaoUserId,
      );
      return false;
    } on FirebaseAuthException catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_custom_token_signin_failed',
        kakaoUserId: kakaoUserId,
        error: e,
        stackTrace: st,
      );
      debugPrint(
        '[Auth] ensureFirebaseSessionForKakao FirebaseAuth error: '
        'code=${e.code} '
        'message=${FirebaseDiagnostics.safeErrorForLog(e.message)}',
      );
      _setFirebaseSessionFailure(
        FirebaseSessionFailure(
          reason: FirebaseSessionFailureReason.firebaseSignInFailed,
          errorCode: e.code,
        ),
        kakaoUserId: kakaoUserId,
      );
      return false;
    } catch (e, st) {
      FirebaseDiagnostics.logAuthBridgePhase(
        'firebase_session_prepare_failed',
        kakaoUserId: kakaoUserId,
        error: e,
        stackTrace: st,
      );
      debugPrint(
        '[Auth] ensureFirebaseSessionForKakao error: '
        '${FirebaseDiagnostics.safeErrorForLog(e)}',
      );
      _setFirebaseSessionFailure(
        const FirebaseSessionFailure(
          reason: FirebaseSessionFailureReason.callableFailed,
        ),
        kakaoUserId: kakaoUserId,
      );
      return false;
    }
  }

  Future<bool> ensureFirebaseSessionForVerifiedUser(String kakaoUserId) async {
    return ensureFirebaseSessionForKakao(kakaoUserId);

    // 학생 인증 토큰(emailLinkTokens)으로 세션을 복구하던 경로는 제거했다.
    // 그 토큰 문서는 클라이언트가 비인증으로 생성할 수 있어서, 서버가 그것을
    // bearer credential 로 신뢰하면 임의 계정의 custom token 을 발급받을 수
    // 있었다. 세션 복구는 카카오 액세스 토큰을 서버에서 Kakao API 로 검증하는
    // 경로만 사용한다.
  }

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

  /// Firebase Auth 세션이 없을 때 Cloud Functions에서 카카오로 본인 확인할 때 사용
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
