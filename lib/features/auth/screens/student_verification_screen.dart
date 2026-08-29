import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../../providers/auth_provider.dart';
import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/contact_block_service.dart';
import '../../../services/firebase_diagnostics.dart';
import '../../../services/friend_invite_service.dart';
import '../../../services/storage_service.dart';
import '../../../shared/layouts/main_scaffold_args.dart';
import '../../../utils/open_mail_app.dart';
import '../utils/email_link_continue_url.dart';
import '../utils/post_student_verification_route.dart';

class StudentVerificationScreen extends StatefulWidget {
  const StudentVerificationScreen({super.key});

  @override
  State<StudentVerificationScreen> createState() =>
      _StudentVerificationScreenState();
}

class _StudentVerificationScreenState extends State<StudentVerificationScreen>
    with WidgetsBindingObserver {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _authService = AuthService();
  final _contactBlockService = ContactBlockService();
  final _storageService = StorageService();
  final _friendInviteService = FriendInviteService();

  bool _isSending = false;
  bool _isVerifying = false;
  String? _statusMessage;
  String? _pendingEmailRequestId;
  String? _pendingEmailRequestEmail;
  StreamSubscription<Uri>? _linkSubscription;
  int _resumeKey = 0; // 앱 복귀 시 위젯 강제 재생성용

  static const String _yonseiDomain = '@yonsei.ac.kr';

  String _buildYonseiEmail(String input) {
    final raw = input.trim().toLowerCase();
    if (raw.isEmpty) return '';

    // 사용자가 전체 이메일을 붙여넣어도 안전하게 처리
    final localPart = raw.contains('@') ? raw.split('@').first : raw;
    return '$localPart$_yonseiDomain';
  }

  Future<void> _showDialogMessage(String title, String message) async {
    if (!mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: const [CupertinoDialogAction(child: Text('확인'))],
      ),
    );
  }

  Future<bool> _ensureFirebaseSessionAfterVerification(
    String kakaoUserId, {
    bool showDialogOnFailure = true,
  }) async {
    final hasFirebaseSession = await _authService
        .ensureFirebaseSessionForVerifiedUser(kakaoUserId);
    if (hasFirebaseSession) {
      return true;
    }

    if (!mounted) return false;

    const detailMessage =
        '학생 인증은 확인됐지만 현재 브라우저의 로그인 세션을 복구하지 못했어요.\n\n'
        '가장 최근에 받은 인증 메일 링크를 이 브라우저에서 다시 열어주세요.';

    setState(() {
      _statusMessage = '학생 인증은 확인됐지만 현재 브라우저 로그인 세션을 복구하지 못했어요.';
    });

    if (showDialogOnFailure) {
      await _showDialogMessage('인증 세션 확인 필요', detailMessage);
    }
    return false;
  }

  Future<bool> _handlePendingInviteAfterVerification() async {
    final pendingToken = await _friendInviteService.getPendingInviteToken();
    debugPrint(
      '[FriendInvite] after verification pendingTokenExists=${pendingToken != null && pendingToken.trim().isNotEmpty}',
    );
    final result = await _friendInviteService.processPendingInviteIfPossible();
    debugPrint('[FriendInvite] after verification result=${result?.status}');
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

    if (!mounted || !result.isSuccessLike) {
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

  /// Reads the server-owned onboarding marker after Yonsei verification.
  /// A returning user who has already completed every required profile step
  /// should never be sent back through onboarding merely to verify email.
  Future<void> _navigateAfterStudentVerification(String kakaoUserId) async {
    final initialSetupComplete = await _authService.isInitialSetupComplete(
      kakaoUserId,
    );
    final nextOnboardingRoute = initialSetupComplete
        ? null
        : await _authService.getOnboardingNextRoute(kakaoUserId);
    if (!mounted) return;

    // Some existing users completed every required profile field before this
    // explicit marker was introduced. Persist the marker before entering main
    // so the rest of the app observes the same server-confirmed state.
    final inferredComplete =
        !initialSetupComplete && nextOnboardingRoute == null;
    if (inferredComplete) {
      await _contactBlockService.syncKakaoTalkFriendBlocks();
      await _authService.completeOnboarding(kakaoUserId);
      if (!mounted) return;
      context.read<AuthProvider>().markInitialSetupComplete();
    }

    final route = resolvePostStudentVerificationRoute(
      initialSetupComplete: initialSetupComplete,
      nextOnboardingRoute: nextOnboardingRoute,
    );
    if (route != RouteNames.main) {
      await _storageService.saveStudentVerificationWelcome(kakaoUserId);
    }
    if (!mounted) return;
    if (route == RouteNames.main) {
      final privacyStatus = await _contactBlockService
          .getKakaoFriendAvoidanceStatus();
      if (!privacyStatus.recommendationPrivacyReady) {
        await _contactBlockService.syncKakaoTalkFriendBlocks();
      }
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
      return;
    }
    Navigator.of(context).pushReplacementNamed(route);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prefillSavedEmail();
      _checkForEmailLink();
      _listenForEmailLink();
    });
  }

  /// 딥링크로 앱이 열렸을 때 이메일 링크 처리 (getInitialLink + uriLinkStream)
  void _listenForEmailLink() {
    AppLinks().getInitialLink().then((uri) {
      if (uri != null && _authService.isSignInWithEmailLink(uri.toString())) {
        _handleEmailLink(uri.toString());
      }
    });
    _linkSubscription = AppLinks().uriLinkStream.listen((uri) {
      if (_authService.isSignInWithEmailLink(uri.toString())) {
        _handleEmailLink(uri.toString());
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.resumed) {
      // 브라우저/메일 앱 복귀 시 흰 화면 방지: 지연 후 위젯 트리 완전 재생성
      Future.delayed(const Duration(milliseconds: 150), () {
        if (!mounted) return;
        WidgetsBinding.instance.scheduleFrame();
        setState(() => _resumeKey++);
        _checkVerificationOnResume();
      });
    }
  }

  Future<void> _prefillSavedEmail() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null) return;

    final saved = await _storageService.getStudentEmail(kakaoUserId);
    if (saved == null || saved.trim().isEmpty) return;

    final localPart = saved.trim().toLowerCase().split('@').first;
    if (localPart.isEmpty) return;

    if (!mounted) return;
    setState(() => _emailController.text = localPart);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _linkSubscription?.cancel();
    _emailController.dispose();
    super.dispose();
  }

  /// 앱 복귀 시 인증 완료 여부 확인 (웹에서 인증 후 돌아온 경우)
  Future<void> _checkVerificationOnResume() async {
    if (_isVerifying || _isSending) return;
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null) return;

    try {
      final isVerified = await _authService.isStudentVerified(kakaoUserId);
      if (isVerified && mounted) {
        final hasFirebaseSession =
            await _ensureFirebaseSessionAfterVerification(
              kakaoUserId,
              showDialogOnFailure: false,
            );
        if (!hasFirebaseSession || !mounted) return;
        final handledInvite = await _handlePendingInviteAfterVerification();
        if (handledInvite || !mounted) return;
        await _navigateAfterStudentVerification(kakaoUserId);
      }
    } catch (_) {}
  }

  // Web에서 이메일 링크로 들어온 경우에만 동작 (native는 app_links로 처리)
  Future<void> _checkForEmailLink() async {
    final link = Uri.base.toString();
    if (!_authService.isSignInWithEmailLink(link)) return;
    await _handleEmailLink(link);
  }

  Future<void> _handleEmailLink(String link) async {
    if (_isVerifying) return;

    if (!mounted) return;
    setState(() {
      _isVerifying = true;
      _statusMessage = '이메일 링크 인증을 완료하는 중...';
    });

    try {
      final localKakaoUserId = (await _storageService.getKakaoUserId())?.trim();
      final verificationToken = extractStudentEmailLinkToken(link);
      if (verificationToken == null || verificationToken.isEmpty) {
        throw Exception('Firebase 인증 정보가 포함된 링크를 찾을 수 없습니다. 메일의 링크를 다시 눌러주세요.');
      }

      // 새 탭/새 브라우저에서는 로컬 이메일이 없을 수 있으므로, continue URL의
      // 불투명 토큰으로 서버가 저장한 이메일을 먼저 읽는다.
      final tokenEmail = await _authService.getEmailForStudentEmailLinkToken(
        verificationToken,
      );
      final savedEmail = localKakaoUserId == null
          ? ''
          : (await _storageService.getStudentEmail(localKakaoUserId) ?? '')
                .trim()
                .toLowerCase();
      final email = (tokenEmail ?? savedEmail).isNotEmpty
          ? (tokenEmail ?? savedEmail)
          : _buildYonseiEmail(_emailController.text);

      if (email.isEmpty) {
        throw Exception('이메일 정보를 찾을 수 없습니다. 다시 시도해주세요.');
      }

      // 1) Firebase가 원본 action URL의 일회성 oobCode로 메일 소유권을 확인한다.
      await _authService.signInWithEmailLink(email: email, emailLink: link);

      // 2) 서버가 인증된 메일 세션과 token 문서를 대조하고, 같은 트랜잭션에서
      //    users 문서를 갱신·토큰 소모 후 카카오 UID custom token을 발급한다.
      final completion = await _authService.completeStudentEmailLink(
        token: verificationToken,
        expectedKakaoUserId: localKakaoUserId,
      );
      final kakaoUserId = completion.kakaoUserId;
      await _storageService.saveKakaoUserId(kakaoUserId);
      await _storageService.saveStudentEmail(kakaoUserId, completion.email);
      await _storageService.saveStudentVerificationToken(
        kakaoUserId,
        verificationToken,
      );
      await _storageService.setStudentVerified(kakaoUserId, true);

      if (!mounted) return;
      await context.read<AuthProvider>().applyEmailLinkCompletion(
        kakaoUserId: kakaoUserId,
        email: completion.email,
      );

      if (!mounted) return;
      setState(() => _statusMessage = '학생 인증 완료!');
      final handledInvite = await _handlePendingInviteAfterVerification();
      if (handledInvite || !mounted) return;
      await _navigateAfterStudentVerification(kakaoUserId);
    } catch (e) {
      if (!mounted) return;
      setState(() => _statusMessage = '인증 실패: ${e.toString()}');
      await _showDialogMessage('인증 실패', e.toString());
    } finally {
      if (mounted) setState(() => _isVerifying = false);
    }
  }

  Future<void> _sendEmailLink() async {
    if (!_formKey.currentState!.validate()) return;

    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null) {
      if (!mounted) return;
      await _showDialogMessage('전송 불가', '카카오 로그인 정보가 없습니다.');
      return;
    }

    final email = _buildYonseiEmail(_emailController.text);
    final requestId =
        _pendingEmailRequestEmail == email && _pendingEmailRequestId != null
        ? _pendingEmailRequestId!
        : const Uuid().v4();
    _pendingEmailRequestEmail = email;
    _pendingEmailRequestId = requestId;

    setState(() {
      _isSending = true;
      _statusMessage = '인증 링크를 전송하는 중...';
    });

    try {
      // The server owns the token, Firebase action-link generation, rate
      // limits, and mail delivery. The client never receives a bearer link.
      debugPrint('📧 학생 인증 메일 서버 발송 요청 시작');
      try {
        await _authService.sendStudentEmailLink(
          email: email,
          requestId: requestId,
        );
        debugPrint('✅ 학생 인증 메일 발송 요청 완료');
      } catch (e) {
        debugPrint(
          '❌ 학생 인증 메일 서버 발송 오류 → '
          '${FirebaseDiagnostics.safeErrorForLog(e)}',
        );
        rethrow;
      }

      // 로컬에 이메일 저장 (웹 인증 후 앱에서 확인용)
      await _storageService.saveStudentEmail(kakaoUserId, email);
      await _storageService.setStudentVerified(kakaoUserId, false);
      _pendingEmailRequestId = null;
      _pendingEmailRequestEmail = null;

      if (!mounted) return;
      setState(() => _statusMessage = '연세 메일로 인증 링크를 보냈습니다');
    } catch (e) {
      final safeError = FirebaseDiagnostics.safeErrorForLog(e);
      debugPrint(
        '[StudentVerification] email link '
        '${FirebaseDiagnostics.safeErrorForLog(e)}',
      );

      if (!mounted) return;
      setState(() => _statusMessage = '전송 실패: $safeError');

      await _showDialogMessage('전송 실패', safeError);
    } finally {
      if (mounted) setState(() => _isSending = false);
    }
  }

  Future<void> _checkVerificationStatus() async {
    setState(() {
      _isVerifying = true;
      _statusMessage = '인증 상태를 확인하는 중...';
    });

    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null) {
        throw Exception('카카오 로그인 정보가 없습니다.');
      }

      // ✅ 사용자가 이 기기에서 인증 링크를 보낸 적이 없으면 통과 불가
      final savedEmail =
          (await _storageService.getStudentEmail(kakaoUserId) ?? '')
              .trim()
              .toLowerCase();
      if (savedEmail.isEmpty) {
        if (!mounted) return;
        setState(() => _statusMessage = '❗ 아직 이메일 인증이 완료되지 않았습니다');
        return;
      }

      // Firestore에서 최신 학생 인증 상태 다시 조회
      final isVerified = await _authService.isStudentVerified(kakaoUserId);

      if (isVerified) {
        // ✅ Firestore에 저장된 이메일이 저장된 이메일과 일치할 때만 통과
        final firestoreEmail =
            (await _authService.getStudentEmail(kakaoUserId) ?? '')
                .trim()
                .toLowerCase();
        if (firestoreEmail.isEmpty || firestoreEmail != savedEmail) {
          if (!mounted) return;
          setState(() => _statusMessage = '❗ 아직 이메일 인증이 완료되지 않았습니다');
          return;
        }

        // 로컬에도 verified 기록 (다음 실행에서 UX 개선)
        await _storageService.saveKakaoUserId(kakaoUserId);
        await _storageService.setStudentVerified(kakaoUserId, true);
        final hasFirebaseSession =
            await _ensureFirebaseSessionAfterVerification(kakaoUserId);
        if (!hasFirebaseSession || !mounted) return;

        if (!mounted) return;
        setState(() => _statusMessage = '학생 인증이 확인되었습니다!');
        HapticFeedback.mediumImpact();
        final handledInvite = await _handlePendingInviteAfterVerification();
        if (handledInvite || !mounted) return;
        await _navigateAfterStudentVerification(kakaoUserId);
        return;
      }

      if (!mounted) return;
      setState(() => _statusMessage = '❗ 아직 이메일 인증이 완료되지 않았습니다');
    } catch (e) {
      if (!mounted) return;
      setState(() => _statusMessage = '확인 실패: ${e.toString()}');
      await _showDialogMessage('확인 실패', e.toString());
    } finally {
      if (mounted) setState(() => _isVerifying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      key: ValueKey('student_verification_$_resumeKey'),
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: const CupertinoNavigationBar(middle: Text('연세 이메일 인증')),
      child: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.manual,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 8),
                    const Text(
                      '연세대학교 이메일\n인증이 필요해요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        height: 1.25,
                        letterSpacing: -0.4,
                        color: _AppColors.textMain,
                      ),
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      '@yonsei.ac.kr 메일로 인증 링크를 보내드릴게요.\n메일에서 인증을 완료한 뒤, 아래에서 확인을 눌러주세요.',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 15,
                        height: 1.5,
                        color: _AppColors.textSub,
                      ),
                    ),
                    const SizedBox(height: 18),
                    Form(
                      key: _formKey,
                      child: Material(
                        color: Colors.transparent,
                        child: TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          style: const TextStyle(fontFamily: 'Pretendard'),
                          decoration: InputDecoration(
                            labelText: '연세 메일 아이디',
                            hintText: 'example',
                            suffixText: _yonseiDomain,
                            filled: true,
                            fillColor: _AppColors.surfaceLight,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(14),
                              borderSide: const BorderSide(
                                color: _AppColors.border,
                              ),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(14),
                              borderSide: const BorderSide(
                                color: _AppColors.border,
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(14),
                              borderSide: const BorderSide(
                                color: _AppColors.primary,
                                width: 2,
                              ),
                            ),
                          ),
                          validator: (value) {
                            final raw = (value ?? '').trim().toLowerCase();
                            if (raw.isEmpty) return '아이디를 입력해주세요';

                            // 전체 이메일을 붙여넣는 케이스도 허용하되, 연세 도메인만 통과
                            if (raw.contains('@')) {
                              if (!raw.endsWith(_yonseiDomain)) {
                                return '연세 이메일만 가능합니다';
                              }
                            }

                            final local = raw.contains('@')
                                ? raw.split('@').first
                                : raw;
                            final isValidLocal = RegExp(
                              r'^[a-z0-9._-]{2,}$',
                            ).hasMatch(local);
                            if (!isValidLocal) return '아이디 형식을 확인해주세요';
                            return null;
                          },
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_statusMessage != null) ...[
                      Text(
                        _statusMessage!,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 13,
                          height: 1.35,
                          color: _AppColors.textSub,
                        ),
                      ),
                      const SizedBox(height: 8),
                    ],
                  ],
                ),
              ),
            ),
            // Bottom actions (스크롤 영역 아래에 배치 → 키보드 시 가려지지 않음)
            Container(
              padding: EdgeInsets.fromLTRB(24, 14, 24, bottomPadding + 16),
              decoration: BoxDecoration(
                color: _AppColors.backgroundLight.withValues(alpha: 0.96),
                border: const Border(
                  top: BorderSide(color: _AppColors.divider),
                ),
              ),
              child: Column(
                children: [
                  SizedBox(
                    width: double.infinity,
                    height: 54,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      borderRadius: BorderRadius.circular(28),
                      color: _AppColors.primary,
                      onPressed: _isSending ? null : _sendEmailLink,
                      child: _isSending
                          ? const CupertinoActivityIndicator(
                              color: Colors.white,
                            )
                          : const Text(
                              '인증 링크 보내기',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 17,
                                fontWeight: FontWeight.w700,
                                color: Colors.white,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: SizedBox(
                          height: 48,
                          child: CupertinoButton(
                            padding: EdgeInsets.zero,
                            borderRadius: BorderRadius.circular(14),
                            color: _AppColors.surfaceLight,
                            onPressed: () => openGmailApp(context),
                            child: const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  CupertinoIcons.mail,
                                  size: 18,
                                  color: _AppColors.textMain,
                                ),
                                SizedBox(width: 6),
                                Text(
                                  '메일 앱 열기',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                    color: _AppColors.textMain,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: SizedBox(
                          height: 48,
                          child: CupertinoButton(
                            padding: EdgeInsets.zero,
                            borderRadius: BorderRadius.circular(14),
                            color: _AppColors.gray700,
                            onPressed: _isVerifying
                                ? null
                                : _checkVerificationStatus,
                            child: _isVerifying
                                ? const CupertinoActivityIndicator(
                                    color: Colors.white,
                                  )
                                : const Text(
                                    '인증 완료 확인',
                                    style: TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 15,
                                      fontWeight: FontWeight.w700,
                                      color: Colors.white,
                                    ),
                                  ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (_isVerifying) ...[
                    const SizedBox(height: 10),
                    const CupertinoActivityIndicator(),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AppColors {
  static const Color primary = Color(0xFFFF6B8A);
  static const Color backgroundLight = Color(0xFFFAFAFA);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF0F172A);
  static const Color textSub = Color(0xFF64748B);
  static const Color border = Color(0xFFE5E7EB);
  static const Color divider = Color(0xFFF0F0F0);
  static const Color gray700 = Color(0xFF374151);
}
