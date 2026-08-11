import 'package:firebase_auth/firebase_auth.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kDebugMode, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/friend_invite_service.dart';
import '../services/kakao_login_firestore_bootstrap.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/layouts/main_scaffold_args.dart';
import '../../../utils/kakao_key_hash_util.dart';

/// 카카오 인증 화면
class KakaoAuthScreen extends StatefulWidget {
  const KakaoAuthScreen({super.key});

  @override
  State<KakaoAuthScreen> createState() => _KakaoAuthScreenState();
}

class _KakaoAuthScreenState extends State<KakaoAuthScreen> {
  final _authService = AuthService();
  final _storageService = StorageService();
  final _friendInviteService = FriendInviteService();
  final _userService = UserService();
  late final _loginBootstrap = KakaoLoginFirestoreBootstrap(
    authService: _authService,
    userService: _userService,
  );

  bool _isLoading = false;
  String? _errorMessage;
  bool _showWebLoginFallback = false;

  String get _currentPlatformLabel {
    if (kIsWeb) return 'web';
    return defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
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

  Future<void> _login() async {
    if (_isLoading) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final userInfo = await _authService.loginWithKakao();
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
      // ✅ 이미 서버에 등록된 유저(재설치 후 약관→카카오 로그인 포함): 연세+초기설정 완료 시 홈으로
      if (existedBeforeLogin) {
        final isVerified = await _authService.isStudentVerified(kakaoUserId);
        final isInitialSetupComplete = await _authService
            .isInitialSetupComplete(kakaoUserId);

        if (isVerified && isInitialSetupComplete) {
          final handledInvite = await _handlePendingInviteAfterLogin();
          if (handledInvite || !mounted) return;
          if (!mounted) return;
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
          Navigator.of(
            context,
          ).pushReplacementNamed(RouteNames.welcomeTutorial);
          return;
        }
      }

      // 신규/미완료 유저 기본 플로우
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.studentVerification);
    } catch (e) {
      debugPrint('[KAKAO] login failed: ${PrivacyLogUtils.errorSummary(e)}');
      final msg = _formatLoginErrorMessage(e.toString());
      if (!mounted) return;
      final isKeyHashError =
          msg.toLowerCase().contains('keyhash') ||
          msg.toLowerCase().contains('key hash');
      if (isKeyHashError) {
        final keyHash = await getAndroidKeyHash();
        if (keyHash != null && keyHash.isNotEmpty && mounted) {
          await _showKeyHashDialog(keyHash);
        }
      }
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

  Future<void> _showKeyHashIfAndroid() async {
    final keyHash = await getAndroidKeyHash();
    if (keyHash != null && keyHash.isNotEmpty && mounted) {
      await _showKeyHashDialog(keyHash);
    }
  }

  Future<void> _showKeyHashDialog(String keyHash) async {
    await showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text('키 해시 등록 필요'),
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '카카오 개발자 콘솔에 아래 키 해시를 등록해주세요.\n\n'
                '1. developers.kakao.com 접속\n'
                '2. 앱 선택 → 앱 설정 → 플랫폼 → Android\n'
                '3. 키 해시에 아래 값을 추가 후 저장',
                style: TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 12),
              GestureDetector(
                onLongPress: () {
                  Clipboard.setData(ClipboardData(text: keyHash));
                  HapticFeedback.mediumImpact();
                },
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: CupertinoColors.systemGrey6,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SelectableText(
                    keyHash,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 14,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '길게 눌러 복사',
                style: TextStyle(
                  fontSize: 11,
                  color: CupertinoColors.systemGrey,
                ),
              ),
            ],
          ),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  /// iOS 번들 ID 오류 등으로 카카오톡 앱 로그인이 안 될 때만 사용 (웹 로그인)
  Future<void> _loginWithWeb() async {
    if (_isLoading) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _showWebLoginFallback = false;
    });
    try {
      final userInfo = await _authService.loginWithKakaoAccountOnly();
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
      if (existedBeforeLogin) {
        final isVerified = await _authService.isStudentVerified(kakaoUserId);
        final isInitialSetupComplete = await _authService
            .isInitialSetupComplete(kakaoUserId);
        if (isVerified && isInitialSetupComplete) {
          final handledInvite = await _handlePendingInviteAfterLogin();
          if (handledInvite || !mounted) return;
          if (!mounted) return;
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
          Navigator.of(
            context,
          ).pushReplacementNamed(RouteNames.welcomeTutorial);
          return;
        }
      }
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.studentVerification);
    } catch (e) {
      debugPrint(
        '[KAKAO] web login failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!mounted) return;
      final msg = _formatLoginErrorMessage(e.toString());
      final isKeyHashError =
          msg.toLowerCase().contains('keyhash') ||
          msg.toLowerCase().contains('key hash');
      if (isKeyHashError) {
        final keyHash = await getAndroidKeyHash();
        if (keyHash != null && keyHash.isNotEmpty && mounted) {
          await _showKeyHashDialog(keyHash);
        }
      }
      if (!mounted) return;
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
                '카카오 계정으로 로그인하면\n바로 프로필 설정을 진행할 수 있어요.',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.4,
                  color: Color(0xFF64748B),
                ),
              ),
              const SizedBox(height: 18),
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
                  onPressed: _isLoading ? null : _login,
                  child: _isLoading
                      ? const CupertinoActivityIndicator(color: Colors.white)
                      : const Text(
                          '카카오로 로그인',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                ),
              ),
              if (_showWebLoginFallback) ...[
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
              if (!kIsWeb &&
                  defaultTargetPlatform == TargetPlatform.android) ...[
                const SizedBox(height: 8),
                Center(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    onPressed: _isLoading ? null : _showKeyHashIfAndroid,
                    child: const Text(
                      '키 해시 확인',
                      style: TextStyle(fontSize: 12, color: Color(0xFF94A3B8)),
                    ),
                  ),
                ),
              ],
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
