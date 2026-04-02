import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

import '../../../router/route_names.dart';
import '../../../screens/auth/kakao_callback_screen.dart';
import '../../../services/auth_service.dart';
import '../../../services/friend_invite_service.dart';
import '../../../services/storage_service.dart';
import '../../../shared/layouts/main_scaffold_args.dart';
import '../../../utils/kakao_key_hash_util.dart';

/// 카카오 인증 화면
class KakaoAuthScreen extends StatefulWidget {
  const KakaoAuthScreen({super.key});

  @override
  State<KakaoAuthScreen> createState() => _KakaoAuthScreenState();
}

class _KakaoAuthScreenState extends State<KakaoAuthScreen>
    with WidgetsBindingObserver {
  final _authService = AuthService();
  final _storageService = StorageService();
  final _friendInviteService = FriendInviteService();

  bool _isLoading = false;
  String? _errorMessage;
  bool _showWebLoginFallback = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !mounted) return;
    _onReturnFromExternalApp();
  }

  /// 카카오톡 앱에서 돌아왔을 때 URL에 code가 있으면 콜백 화면으로 이동
  Future<void> _onReturnFromExternalApp() async {
    try {
      final url = await receiveKakaoScheme();
      if (url == null || url.isEmpty || !url.contains('code=')) return;
      final uri = Uri.tryParse(url);
      if (uri == null) return;
      final pathAndQuery = uri.hasQuery ? '${uri.path}?${uri.query}' : uri.path;
      if (!pathAndQuery.contains('code=')) return;
      if (!mounted) return;
      await Navigator.of(context).push(
        CupertinoPageRoute<void>(
          builder: (_) => KakaoCallbackScreen(
            callbackPathAndQuery: pathAndQuery.startsWith('?') ? pathAndQuery : '/$pathAndQuery',
          ),
        ),
      );
    } catch (_) {}
  }

  Future<bool> _handlePendingInviteAfterLogin() async {
    final result = await _friendInviteService.processPendingInviteIfPossible();
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

      await _storageService.saveKakaoUserId(kakaoUserId);
      await _authService.ensureFirebaseSessionForKakao(kakaoUserId);

      if (!mounted) return;
      // ✅ 이미 서버에 등록된 유저(재설치 후 약관→카카오 로그인 포함): 연세+초기설정 완료 시 홈으로
      final exists = await _authService.kakaoUserExists(kakaoUserId);
      if (exists) {
        final isVerified = await _authService.isStudentVerified(kakaoUserId);
        final isInitialSetupComplete = await _authService
            .isInitialSetupComplete(kakaoUserId);

        if (isVerified && isInitialSetupComplete) {
          final handledInvite = await _handlePendingInviteAfterLogin();
          if (handledInvite || !mounted) return;
          if (!mounted) return;
          Navigator.of(context)
              .pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
          return;
        }

        if (!mounted) return;
        if (!isVerified) {
          Navigator.of(context)
              .pushReplacementNamed(RouteNames.studentVerification);
          return;
        }
        if (!isInitialSetupComplete) {
          final nextRoute =
              await _authService.getOnboardingNextRoute(kakaoUserId);
          if (!mounted) return;
          Navigator.of(context).pushReplacementNamed(
            nextRoute ?? RouteNames.onboardingBasicInfo,
          );
          return;
        }
        final hasSeenTutorial =
            await _authService.hasSeenTutorial(kakaoUserId);
        if (!hasSeenTutorial) {
          Navigator.of(context)
              .pushReplacementNamed(RouteNames.welcomeTutorial);
          return;
        }
      }

      // 신규/미완료 유저 기본 플로우
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.studentVerification);
    } catch (e, st) {
      debugPrint('[KAKAO] login failed: $e\n$st');
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (!mounted) return;
      final isKeyHashError = msg.toLowerCase().contains('keyhash') ||
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
        _showWebLoginFallback = true;
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
      await _storageService.saveKakaoUserId(kakaoUserId);
      await _authService.ensureFirebaseSessionForKakao(kakaoUserId);
      if (!mounted) return;
      final exists = await _authService.kakaoUserExists(kakaoUserId);
      if (exists) {
        final isVerified = await _authService.isStudentVerified(kakaoUserId);
        final isInitialSetupComplete =
            await _authService.isInitialSetupComplete(kakaoUserId);
        if (isVerified && isInitialSetupComplete) {
          final handledInvite = await _handlePendingInviteAfterLogin();
          if (handledInvite || !mounted) return;
          if (!mounted) return;
          Navigator.of(context)
              .pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
          return;
        }
        if (!mounted) return;
        if (!isVerified) {
          Navigator.of(context)
              .pushReplacementNamed(RouteNames.studentVerification);
          return;
        }
        if (!isInitialSetupComplete) {
          final nextRoute =
              await _authService.getOnboardingNextRoute(kakaoUserId);
          if (!mounted) return;
          Navigator.of(context).pushReplacementNamed(
            nextRoute ?? RouteNames.onboardingBasicInfo,
          );
          return;
        }
        final hasSeenTutorial =
            await _authService.hasSeenTutorial(kakaoUserId);
        if (!hasSeenTutorial) {
          Navigator.of(context)
              .pushReplacementNamed(RouteNames.welcomeTutorial);
          return;
        }
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(RouteNames.studentVerification);
    } catch (e, st) {
      debugPrint('[KAKAO] web login failed: $e\n$st');
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      final isKeyHashError = msg.toLowerCase().contains('keyhash') ||
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
              if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) ...[
                const SizedBox(height: 8),
                Center(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
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
