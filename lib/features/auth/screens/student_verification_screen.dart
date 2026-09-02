import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart' show FirebaseAuth;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../../models/terms_gate_failure.dart';
import '../../../providers/auth_provider.dart';
import '../../../router/route_names.dart';
import '../../../services/account_setup_flow.dart';
import '../../../services/auth_service.dart';
import '../../../services/firebase_diagnostics.dart';
import '../../../services/friend_invite_service.dart';
import '../../../services/storage_service.dart';
import '../../../utils/open_mail_app.dart';
import '../utils/email_link_continue_url.dart';

/// 연세 이메일 인증 = 설레연 PRIMARY 로그인 화면.
///
/// 카카오 계정/세션과 무관하게 동작한다: 메일 발송에도, 링크 완료에도 카카오
/// 전제조건이 없다. 링크 완료 → `completePrimaryStudentEmailAuth` → canonical
/// Firebase 세션(uid == appUserId) → 성인인증 확인 → 설정 사다리 라우팅.
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
  final _storageService = StorageService();
  final _friendInviteService = FriendInviteService();
  final _setupFlow = AccountSetupFlow();

  bool _isSending = false;
  bool _isVerifying = false;
  String? _statusMessage;
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

  /// Terms-gate contract §7/§9: a missing or stale acceptance — whether it
  /// was caught locally before sending, or returned by the server on the link
  /// request or the completion — sends the user back to the terms screen.
  /// This is what closes the cold-start deep-link bypass (finding F7): the
  /// email-link branch may reach this screen without ever passing terms, but
  /// it cannot get past the server.
  Future<void> _handleTermsGateFailure(TermsGateException failure) async {
    // `signInWithEmailLink()` above left a TEMPORARY Firebase session attached.
    // It is not a canonical app session (no `users/{uid}` document exists for
    // it), but the terms screen classifies by `currentUser != null`, so leaving
    // it in place would send the user into the post-auth re-consent branch and
    // dead-end on `identity_conflict`. Drop it before going back.
    final recovery = resolveTermsGateRecovery(
      temporarySessionCleared: await _authService
          .clearTemporaryEmailLinkSession(),
    );
    if (!mounted) return;

    if (recovery == TermsGateRecovery.blockedSessionNotCleared) {
      // Fail closed: never hand the terms screen a live session it would read
      // as a canonical account.
      const message = '로그인 상태를 정리하지 못했어요. 앱을 다시 시작한 뒤 시도해 주세요.';
      setState(() => _statusMessage = message);
      await _showDialogMessage('세션 정리 실패', message);
      return;
    }

    setState(() => _statusMessage = failure.userMessage);
    await _showDialogMessage('약관 동의 필요', failure.userMessage);
    if (!mounted) return;
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.terms, (route) => false);
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
            child: const Text('확인'),
          ),
        ],
      ),
    );

    // 초대 수락 후에도 반드시 설정 사다리를 다시 통과한다. (친구 연결,
    // 온보딩 등이 남아 있으면 main 으로 직행할 수 없다.)
    return false;
  }

  /// 이메일 인증 확정 이후의 공통 체인: 성인인증 확인 → 약관 동의 서버 반영 →
  /// 대기 중 친구초대 처리 → 설정 사다리 라우팅.
  Future<void> _continueAfterPrimaryAuth(String appUserId) async {
    final adultConfirmed = await _setupFlow
        .confirmPendingAdultVerificationIfNeeded();
    await _setupFlow.flushPendingLegalConsents();

    if (!mounted) return;
    if (!adultConfirmed) {
      Navigator.of(context).pushReplacementNamed(RouteNames.adultVerification);
      return;
    }

    await _handlePendingInviteAfterVerification();
    if (!mounted) return;

    final route = await _setupFlow.resolveNextRoute();
    if (route != RouteNames.main) {
      await _storageService.saveStudentVerificationWelcome(appUserId);
    }
    if (!mounted) return;
    Navigator.of(context).pushNamedAndRemoveUntil(route, (r) => false);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prefillSavedEmail();
      _checkForEmailLink();
      _listenForEmailLink();
      _resumeExistingSessionIfComplete();
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
    final saved = await _storageService.getPendingStudentEmail();
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

  /// 이미 canonical 세션이 붙어 있고 학생 인증이 끝난 계정이 이 화면에
  /// 들어온 경우(성인인증 게이트에서 되돌아온 재개 등) 사다리로 복귀시킨다.
  Future<void> _resumeExistingSessionIfComplete() async {
    if (_isVerifying || _isSending) return;
    final uid = FirebaseAuth.instance.currentUser?.uid;
    if (uid == null || uid.isEmpty) return;

    try {
      final isVerified = await _authService.isStudentVerified(uid);
      if (isVerified && mounted) {
        await _continueAfterPrimaryAuth(uid);
      }
    } catch (_) {}
  }

  /// 앱 복귀 시 인증 완료 여부 확인 (링크가 다른 곳에서 완료된 경우 등)
  Future<void> _checkVerificationOnResume() async {
    await _resumeExistingSessionIfComplete();
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
      final verificationToken = extractStudentEmailLinkToken(link);
      if (verificationToken == null || verificationToken.isEmpty) {
        throw Exception('Firebase 인증 정보가 포함된 링크를 찾을 수 없습니다. 메일의 링크를 다시 눌러주세요.');
      }

      // 새 탭/새 브라우저에서는 로컬 이메일이 없을 수 있으므로, continue URL의
      // 불투명 토큰으로 서버가 저장한 이메일을 먼저 읽는다.
      final tokenEmail = await _authService.getEmailForStudentEmailLinkToken(
        verificationToken,
      );
      final pendingEmail =
          (await _storageService.getPendingStudentEmail() ?? '')
              .trim()
              .toLowerCase();
      final email = (tokenEmail ?? pendingEmail).isNotEmpty
          ? (tokenEmail ?? pendingEmail)
          : _buildYonseiEmail(_emailController.text);

      if (email.isEmpty) {
        throw Exception('이메일 정보를 찾을 수 없습니다. 다시 시도해주세요.');
      }

      // 1) Firebase가 원본 action URL의 일회성 oobCode로 메일 소유권을 확인한다.
      //    이 시점의 세션은 임시 email-link 세션이다.
      await _authService.signInWithEmailLink(email: email, emailLink: link);

      // 2) 서버가 인증된 메일 세션과 token 문서를 대조하고, 같은 트랜잭션에서
      //    appUserId 를 확정·토큰 소모 후 canonical custom token 을 발급한다.
      //    signInWithCustomToken 후 uid == appUserId 가 검증된다.
      final completion = await _authService.completePrimaryStudentEmailAuth(
        token: verificationToken,
      );
      final appUserId = completion.appUserId;
      await _storageService.saveAppUserId(appUserId);
      await _storageService.saveStudentEmail(
        appUserId,
        completion.normalizedEmail,
      );
      await _storageService.setStudentVerified(appUserId, true);
      await _storageService.clearPendingStudentEmail();
      await _storageService.clearPendingStudentEmailRequestId();

      if (!mounted) return;
      await context.read<AuthProvider>().applyPrimaryEmailAuthCompletion(
        completion,
      );

      if (!mounted) return;
      setState(() => _statusMessage = '학생 인증 완료!');
      await _continueAfterPrimaryAuth(appUserId);
    } on TermsGateException catch (failure) {
      await _handleTermsGateFailure(failure);
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

    final email = _buildYonseiEmail(_emailController.text);
    final savedEmail = (await _storageService.getPendingStudentEmail() ?? '')
        .trim()
        .toLowerCase();
    final savedRequestId = await _storageService
        .getPendingStudentEmailRequestId();
    final requestId =
        savedEmail == email &&
            savedRequestId != null &&
            savedRequestId.isNotEmpty
        ? savedRequestId
        : const Uuid().v4();

    if (!mounted) return;
    setState(() {
      _isSending = true;
      _statusMessage = '인증 링크를 전송하는 중...';
    });

    try {
      // The server owns the token, Firebase action-link generation, rate
      // limits, and mail delivery. The client never receives a bearer link.
      // Kakao 관련 전제조건은 일절 없다 (primary 이메일 인증).
      debugPrint('📧 학생 인증 메일 서버 발송 요청 시작');
      try {
        await _storageService.savePendingStudentEmail(email);
        await _storageService.savePendingStudentEmailRequestId(requestId);
        await _authService.sendPrimaryStudentEmailLink(
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

      if (!mounted) return;
      setState(() => _statusMessage = '연세 메일로 인증 링크를 보냈습니다');
    } on TermsGateException catch (failure) {
      await _handleTermsGateFailure(failure);
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
      final uid = FirebaseAuth.instance.currentUser?.uid;
      if (uid == null || uid.isEmpty) {
        // Primary 인증은 이 기기에서 메일 링크를 열어야만 완료된다.
        if (!mounted) return;
        setState(
          () => _statusMessage = '❗ 아직 인증이 완료되지 않았어요. 메일의 인증 링크를 이 기기에서 열어주세요.',
        );
        return;
      }

      final isVerified = await _authService.isStudentVerified(uid);
      if (!isVerified) {
        if (!mounted) return;
        setState(() => _statusMessage = '❗ 아직 이메일 인증이 완료되지 않았습니다');
        return;
      }

      await _storageService.saveAppUserId(uid);
      await _storageService.setStudentVerified(uid, true);

      if (!mounted) return;
      setState(() => _statusMessage = '학생 인증이 확인되었습니다!');
      HapticFeedback.mediumImpact();
      await _continueAfterPrimaryAuth(uid);
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
      navigationBar: const CupertinoNavigationBar(middle: Text('연세 이메일 로그인')),
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
                      '연세대학교 이메일로\n로그인해 주세요',
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
                      '@yonsei.ac.kr 메일로 로그인 링크를 보내드릴게요.\n메일의 링크를 이 기기에서 열면 로그인이 완료돼요.',
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
                              '로그인 링크 보내기',
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
