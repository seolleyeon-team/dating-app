import 'package:firebase_auth/firebase_auth.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kDebugMode, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';

import '../../../router/route_names.dart';
import '../../../services/adult_verification_service.dart';
import '../../../services/auth_service.dart';
import '../../../services/contact_block_service.dart';
import '../../../services/friend_invite_service.dart';
import '../../../services/kakao_talk_friend_service.dart';
import '../services/kakao_login_firestore_bootstrap.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/layouts/main_scaffold_args.dart';

/// 카카오 인증 화면
class KakaoAuthScreen extends StatefulWidget {
  const KakaoAuthScreen({super.key});

  @override
  State<KakaoAuthScreen> createState() => _KakaoAuthScreenState();
}

class _KakaoAuthScreenState extends State<KakaoAuthScreen> {
  final _authService = AuthService();
  final _adultVerificationService = AdultVerificationService();
  final _storageService = StorageService();
  final _friendInviteService = FriendInviteService();
  final _contactBlockService = ContactBlockService();
  final _kakaoTalkFriendService = KakaoTalkFriendService();
  final _userService = UserService();
  late final _loginBootstrap = KakaoLoginFirestoreBootstrap(
    authService: _authService,
    userService: _userService,
  );

  bool _isLoading = false;
  String? _errorMessage;
  bool _showWebLoginFallback = false;
  bool _friendsConsentRequired = false;
  Map<String, dynamic>? _pendingKakaoUserInfo;

  String get _currentPlatformLabel {
    if (kIsWeb) return 'web';
    return defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
  }

  /// A completed identity-verification session is the only way to enter the
  /// Kakao flow for a new sign-in. The server still re-fetches and verifies
  /// PortOne's result after Firebase identity is attached.
  Future<bool> _requireAdultVerificationBeforeKakaoLogin() async {
    if (await _adultVerificationService.hasPendingKakaoLoginSession()) {
      return true;
    }
    if (!mounted) return false;
    Navigator.of(context).pushReplacementNamed(RouteNames.adultVerification);
    return false;
  }

  Future<bool> _verifyAdultIdentityAfterKakaoLogin() async {
    final result = await _adultVerificationService
        .verifyPendingSessionAfterLogin();
    if (result.isVerified) return true;

    await _authService.signOutAll();
    await _storageService.clearKakaoUserId();
    await _storageService.clearUserId();
    if (!mounted) return false;
    Navigator.of(context).pushReplacementNamed(RouteNames.adultVerification);
    return false;
  }

  String _formatLoginErrorMessage(String rawMessage) {
    final msg = rawMessage.replaceFirst('Exception: ', '').trim();

    if (kIsWeb &&
        msg.toLowerCase().contains('javascript env validation failed')) {
      final origin = Uri.base.origin;
      return [
        '카카오 웹 로그인 환경 검증에 실패했어요.',
        '',
        '현재 origin',
        origin,
        '',
        '카카오 개발자 콘솔 > 앱 설정 > 플랫폼 > Web 에 아래 값을 등록해 주세요.',
        'JavaScript SDK 도메인: $origin',
        'Redirect URI: $origin/',
      ].join('\n');
    }

    if (msg.contains('permission-denied')) {
      if (!kDebugMode) {
        return '서버 권한 설정 때문에 로그인을 끝내지 못했어요.\n잠시 후 다시 시도하거나 고객센터에 문의해 주세요.';
      }
      final uid = FirebaseAuth.instance.currentUser?.uid;
      return [
        msg,
        '',
        'Firestore 보안 규칙이 이 작업을 거부했어요. 확인 순서:',
        '1) 최신 규칙 배포 여부 — firebase deploy --only firestore:rules',
        '2) App Check 적용(enforce) 중이면 이 기기 디버그 토큰 등록 여부',
        'Firebase uid: ${uid ?? '(세션 없음 · request.auth == null)'}',
      ].join('\n');
    }

    return msg;
  }

  Future<bool> _handlePendingInviteAfterLogin() async {
    final pendingToken = await _friendInviteService.getPendingInviteToken();
    debugPrint(
      '[FriendInvite] after login pendingTokenExists=${pendingToken != null && pendingToken.trim().isNotEmpty}',
    );
    final result = await _friendInviteService.processPendingInviteIfPossible();
    debugPrint('[FriendInvite] after login result=${result?.status}');
    if (!mounted || result == null) return false;

    if (result.status == FriendInviteAcceptStatus.pendingLogin ||
        result.status == FriendInviteAcceptStatus.pendingVerification) {
      return false;
    }

    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('친구 초대'),
        content: Text(result.displayMessage),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(result.isSuccessLike ? '친구 목록 보기' : '확인'),
          ),
        ],
      ),
    );

    if (!mounted) return false;

    if (!result.isSuccessLike) {
      return false;
    }

    Navigator.of(context).pushNamedAndRemoveUntil(
      RouteNames.main,
      (route) => false,
      arguments: const MainScaffoldArgs(
        initialTabIndex: 4,
        pendingRouteName: RouteNames.friendsList,
      ),
    );
    return true;
  }

  /// 로그인 플로우 전체가 하나의 try/catch 로 묶여 있어서 어떤 Firestore 작업이
  /// 거부됐는지 알 수 없었다. 단계 이름과 그 시점의 인증 상태를 함께 남긴다.
  Future<T> _runFirestoreStep<T>(
    String step,
    Future<T> Function() action,
  ) async {
    try {
      return await action();
    } on FirebaseException catch (e) {
      debugPrint(
        '[KAKAO] Firestore step failed: step=$step '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      throw _LoginStepException(step: step, cause: e);
    }
  }

  Future<bool> _stopIfRejoinRestrictedAccount(String kakaoUserId) async {
    final isRestricted = await _userService.isRejoinRestricted(kakaoUserId);
    if (!isRestricted) return false;

    await _authService.signOutAll();
    await _storageService.clearKakaoUserId();
    await _storageService.clearUserId();
    await _storageService.clearStudentVerification(kakaoUserId);

    if (!mounted) return true;
    await showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('재가입이 제한된 계정입니다'),
        content: const Text('운영 정책에 따라 현재 계정은 재가입 또는 로그인이 제한되어 있습니다.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
    return true;
  }

  Future<bool> _reactivateIfWithdrawnForRejoin({
    required String kakaoUserId,
    required Map<String, dynamic> userInfo,
  }) async {
    final isWithdrawn = await _userService.isAccountWithdrawn(kakaoUserId);
    if (!isWithdrawn) return false;

    await _userService.reactivateForRejoin(
      kakaoUserId: kakaoUserId,
      nickname: userInfo['nickname']?.toString(),
      profileImageUrl: userInfo['profileImageUrl']?.toString(),
      email: userInfo['email']?.toString(),
    );
    await _storageService.clearStudentVerification(kakaoUserId);
    await _storageService.clearOnboardingDraft(kakaoUserId);
    return true;
  }

  Future<bool> _pauseForMissingFriendsConsent(
    Map<String, dynamic> userInfo,
  ) async {
    final status = await _kakaoTalkFriendService.getConsentStatus();
    if (!status.friendsUsing) {
      throw const KakaoTalkReviewException(
        code: 'friends_scope_not_enabled',
        userMessage: '카카오디벨로퍼스에서 친구목록 동의항목을 사용 설정하지 않았어요. 설정을 확인해 주세요.',
      );
    }
    if (status.friendsAgreed) {
      _pendingKakaoUserInfo = null;
      if (mounted) {
        setState(() => _friendsConsentRequired = false);
      }
      return false;
    }

    try {
      await _contactBlockService
          .markRecommendationPrivacyPendingAfterConsentRefusal();
    } catch (error) {
      // The user remains on the consent-required screen either way. Do not
      // expose token/server details in UI logs.
      debugPrint(
        '[KAKAO] privacy pending after consent refusal: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }

    _pendingKakaoUserInfo = Map<String, dynamic>.from(userInfo);
    if (mounted) {
      setState(() {
        _friendsConsentRequired = true;
        _errorMessage = null;
        _showWebLoginFallback = false;
      });
    }
    return true;
  }

  Future<void> _continueAfterKakaoLogin(Map<String, dynamic> userInfo) async {
    final kakaoUserId = userInfo['id']?.toString();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw Exception('카카오 사용자 ID를 가져오지 못했습니다.');
    }

    // Firebase 세션을 먼저 붙인다. 이 단계가 실패하면 이후 Firestore
    // 조회/라우팅을 수행하지 않는다. 신규 users 셸은 서버 callable이
    // 검증된 Kakao 토큰으로 생성한다.
    final existedBeforeLogin = await _runFirestoreStep(
      '카카오 Firebase 세션 준비',
      () => _loginBootstrap.bootstrap(
        kakaoUserId: kakaoUserId,
        platform: _currentPlatformLabel,
      ),
    );
    if (!await _verifyAdultIdentityAfterKakaoLogin()) return;
    await _storageService.saveKakaoUserId(kakaoUserId);
    if (await _runFirestoreStep(
      '재가입 제한 확인',
      () => _stopIfRejoinRestrictedAccount(kakaoUserId),
    )) {
      return;
    }
    final reactivatedForRejoin = await _runFirestoreStep(
      '탈퇴 계정 재활성화',
      () => _reactivateIfWithdrawnForRejoin(
        kakaoUserId: kakaoUserId,
        userInfo: userInfo,
      ),
    );
    await _runFirestoreStep(
      '접속 플랫폼 기록(users.lastActivePlatform)',
      () => _userService.setLastActivePlatform(
        kakaoUserId: kakaoUserId,
        platform: _currentPlatformLabel,
      ),
    );
    await _runFirestoreStep(
      '약관 동의 저장(users.legalConsents)',
      () => _authService.syncPendingLegalConsents(kakaoUserId),
    );

    if (!mounted) return;
    if (reactivatedForRejoin) {
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.studentVerification);
      return;
    }

    // 이미 서버에 등록된 유저(재설치 후 약관→카카오 로그인 포함)는
    // 연세메일과 초기설정이 모두 끝났으면 바로 홈으로 보낸다.
    if (existedBeforeLogin) {
      final isVerified = await _authService.isStudentVerified(kakaoUserId);
      final isInitialSetupComplete = await _authService.isInitialSetupComplete(
        kakaoUserId,
      );

      if (isVerified && isInitialSetupComplete) {
        await _reconcileReturningUserRecommendationPrivacy();
        final handledInvite = await _handlePendingInviteAfterLogin();
        if (handledInvite || !mounted) return;
        Navigator.of(
          context,
        ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
        return;
      }

      if (!mounted) return;
      if (!isVerified) {
        Navigator.of(
          context,
        ).pushReplacementNamed(RouteNames.studentVerification);
        return;
      }
      if (!isInitialSetupComplete) {
        final nextRoute = await _authService.getOnboardingNextRoute(
          kakaoUserId,
        );
        if (!mounted) return;
        Navigator.of(
          context,
        ).pushReplacementNamed(nextRoute ?? RouteNames.onboardingBasicInfo);
        return;
      }
      final hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
      if (!hasSeenTutorial) {
        if (!mounted) return;
        Navigator.of(context).pushReplacementNamed(RouteNames.welcomeTutorial);
        return;
      }
    }

    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed(RouteNames.studentVerification);
  }

  Future<void> _reconcileReturningUserRecommendationPrivacy() async {
    try {
      // Always refresh on an explicit Kakao login so newly joined friends and
      // consent revoked in Kakao are reflected before recommendations reopen.
      await _contactBlockService.syncKakaoTalkFriendBlocks(
        requestConsentIfNeeded: false,
      );
    } catch (error) {
      // 로그인과 일반 앱 이용은 계속 허용한다. 동기화가 실패한 계정은
      // recommendationPrivacyReady=false라서 1:1 추천 양쪽에서 제외된다.
      debugPrint(
        '[KAKAO] recommendation privacy sync pending: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }
  }

  Future<void> _requestFriendsConsentAgain() async {
    if (_isLoading) return;
    final pendingUserInfo = _pendingKakaoUserInfo;
    if (pendingUserInfo == null) {
      await _login();
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _showWebLoginFallback = false;
    });

    try {
      final status = await _kakaoTalkFriendService.ensureRequiredConsents(
        requireTalkMessage: false,
      );
      final expectedUserId = pendingUserInfo['id']?.toString();
      if (expectedUserId == null ||
          status.userId?.toString() != expectedUserId) {
        throw Exception('처음 로그인한 카카오 계정과 추가 동의한 계정이 달라요. 다시 로그인해 주세요.');
      }
      if (!mounted) return;
      setState(() => _friendsConsentRequired = false);
      _pendingKakaoUserInfo = null;
      await _continueAfterKakaoLogin(pendingUserInfo);
    } on KakaoTalkReviewException catch (error) {
      if (!mounted) return;
      setState(() {
        _friendsConsentRequired = true;
        _errorMessage = error.userMessage;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _friendsConsentRequired = true;
        _errorMessage = _formatLoginErrorMessage(error.toString());
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _login() async {
    if (_isLoading) return;
    if (!await _requireAdultVerificationBeforeKakaoLogin()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _friendsConsentRequired = false;
      _pendingKakaoUserInfo = null;
    });

    try {
      final userInfo = await _authService.loginWithKakao();
      if (await _pauseForMissingFriendsConsent(userInfo)) return;
      await _continueAfterKakaoLogin(userInfo);
    } catch (e) {
      debugPrint('[KAKAO] login failed: ${PrivacyLogUtils.errorSummary(e)}');
      final msg = _formatLoginErrorMessage(e.toString());
      if (!mounted) return;
      setState(() {
        _errorMessage = msg;
        // 서버 권한/규칙 문제는 웹 로그인으로도 해결되지 않으므로 대안을 권하지 않는다.
        _showWebLoginFallback = e is! _LoginStepException;
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  /// iOS 번들 ID 오류 등으로 카카오톡 앱 로그인이 안 될 때만 사용 (웹 로그인)
  Future<void> _loginWithWeb() async {
    if (_isLoading) return;
    if (!await _requireAdultVerificationBeforeKakaoLogin()) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _showWebLoginFallback = false;
      _friendsConsentRequired = false;
      _pendingKakaoUserInfo = null;
    });
    try {
      final userInfo = await _authService.loginWithKakaoAccountOnly();
      if (await _pauseForMissingFriendsConsent(userInfo)) return;
      await _continueAfterKakaoLogin(userInfo);
    } catch (e) {
      debugPrint(
        '[KAKAO] web login failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!mounted) return;
      final msg = _formatLoginErrorMessage(e.toString());
      setState(() => _errorMessage = msg);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      navigationBar: const CupertinoNavigationBar(middle: Text('카카오 로그인')),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              const Text(
                '카카오로 시작하기',
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                '가입을 계속하려면 카카오 친구목록 동의가 필요해요.\n친구 관계는 1:1 추천 제외 확인에만 사용해요.',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.4,
                  color: Color(0xFF64748B),
                ),
              ),
              const SizedBox(height: 18),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: _friendsConsentRequired
                      ? const Color(0xFFFFF7E6)
                      : const Color(0xFFF3F6FF),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: _friendsConsentRequired
                        ? const Color(0xFFFFD37A)
                        : const Color(0xFFD7E1FF),
                  ),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      _friendsConsentRequired
                          ? CupertinoIcons.exclamationmark_shield_fill
                          : CupertinoIcons.shield_fill,
                      size: 22,
                      color: _friendsConsentRequired
                          ? const Color(0xFFB54708)
                          : const Color(0xFF4969D8),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _friendsConsentRequired
                            ? '친구목록 동의가 완료되지 않았어요. 아래 버튼을 눌러 동의한 뒤 가입을 계속해 주세요.'
                            : '친구의 이름이나 프로필은 저장하지 않으며, 설레연 사용자 간 추천 제외 여부를 확인하는 데만 사용해요.',
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.4,
                          fontWeight: FontWeight.w500,
                          color: _friendsConsentRequired
                              ? const Color(0xFF7A2E0E)
                              : const Color(0xFF3854B5),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              if (_errorMessage != null) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFE8EA),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFFFC2CC)),
                  ),
                  child: Text(
                    _errorMessage!,
                    style: const TextStyle(
                      fontSize: 13,
                      color: Color(0xFFB42318),
                      height: 1.35,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
              ],
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 56,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  borderRadius: BorderRadius.circular(28),
                  color: const Color(0xFFFF6B8A),
                  onPressed: _isLoading
                      ? null
                      : (_friendsConsentRequired
                            ? _requestFriendsConsentAgain
                            : _login),
                  child: _isLoading
                      ? const CupertinoActivityIndicator(color: Colors.white)
                      : Text(
                          _friendsConsentRequired ? '다시 동의하기' : '동의하고 카카오로 로그인',
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                ),
              ),
              if (_showWebLoginFallback && !_friendsConsentRequired) ...[
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    borderRadius: BorderRadius.circular(24),
                    color: const Color(0xFFFEE500),
                    onPressed: _isLoading ? null : _loginWithWeb,
                    child: const Text(
                      '웹으로 로그인',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF191919),
                      ),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 10),
              Center(
                child: CupertinoButton(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 6,
                  ),
                  onPressed: _isLoading
                      ? null
                      : () => Navigator.of(
                          context,
                        ).pushReplacementNamed(RouteNames.terms),
                  child: const Text(
                    '약관으로 돌아가기',
                    style: TextStyle(fontSize: 14, color: Color(0xFF64748B)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 로그인 플로우에서 실패한 Firestore 단계를 식별할 수 있게 감싼 예외.
///
/// 화면은 전체 플로우를 하나의 catch 로 처리하므로, 이 예외가 없으면
/// `[cloud_firestore/permission-denied]` 만 남고 어떤 작업이 거부됐는지
/// 알 수 없다.
class _LoginStepException implements Exception {
  const _LoginStepException({required this.step, required this.cause});

  final String step;
  final FirebaseException cause;

  @override
  String toString() {
    final detail = (cause.message ?? '').trim();
    final code = '[${cause.plugin}/${cause.code}]';
    return '$step 단계에서 실패했어요.\n$code${detail.isEmpty ? '' : ' $detail'}';
  }
}
