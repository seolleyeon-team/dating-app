import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';

import '../../router/route_names.dart';
import '../../services/account_setup_flow.dart';
import '../../services/auth_service.dart';
import '../../shared/widgets/seolleyeon_splash_view.dart';
import '../auth/utils/email_link_continue_url.dart';

/// 스플래시 화면 (Yonsei-email-primary)
/// - 이메일 액션 링크 진입: StudentVerificationScreen 이 링크를 소비한다.
/// - Firebase 세션 없음: 약관(terms) → 성인인증 → 연세 이메일 로그인.
/// - Firebase 세션 있음(canonical / grandfathered legacy): users/{uid} 서버
///   진실로 설정 사다리(성인인증/카카오 친구 연결/온보딩/튜토리얼/메인)를 라우팅.
///   카카오 기반 세션 복구는 존재하지 않는다.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  final _authService = AuthService();
  final _setupFlow = AccountSetupFlow();

  bool _isEmailLink(String link) {
    if (link.trim().isEmpty) return false;
    try {
      return _authService.isSignInWithEmailLink(link);
    } catch (_) {
      return false;
    }
  }

  bool _isEmailLinkEntryPoint(Uri? uri) {
    if (uri == null) return false;
    return _isEmailLink(uri.toString()) || isStudentEmailLinkContinuation(uri);
  }

  Future<Uri?> _readInitialUri() async {
    // On web the browser URL is the source of truth. AppLinks may return a
    // normalized root URL instead of the original Firebase action link.
    final browserUri = Uri.base;
    if (_isEmailLinkEntryPoint(browserUri)) {
      return browserUri;
    }

    try {
      final appLink = await AppLinks().getInitialLink();
      if (appLink != null) return appLink;
    } catch (e) {
      debugPrint(
        '[Splash] initial link read failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }

    return browserUri;
  }

  @override
  void initState() {
    super.initState();
    _navigateToNext();
  }

  Future<void> _navigateToNext() async {
    await Future.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;

    try {
      final initialUri = await _readInitialUri();

      // Firebase email links must be handled by StudentVerificationScreen
      // before the normal app-session gate: the action code is single-use
      // and completes the PRIMARY authentication there.
      if (_isEmailLinkEntryPoint(initialUri)) {
        if (!mounted) return;
        Navigator.of(context).pushNamedAndRemoveUntil(
          RouteNames.studentVerification,
          (route) => false,
        );
        return;
      }

      // Only an attached Firebase session counts as a session. A cached
      // local id or a Kakao SDK session never authenticates.
      final firebaseUser = FirebaseAuth.instance.currentUser;
      if (firebaseUser == null) {
        if (!mounted) return;
        Navigator.of(context).pushReplacementNamed(RouteNames.terms);
        return;
      }

      // 운영 제재 계정은 세션과 로컬 식별자를 정리하고 약관으로 보낸다.
      if (await _setupFlow.handleRejoinRestriction()) {
        if (!mounted) return;
        Navigator.of(context).pushReplacementNamed(RouteNames.terms);
        return;
      }

      final route = await _setupFlow.resolveNextRoute();
      if (!mounted) return;
      if (route == RouteNames.main) {
        Navigator.of(
          context,
        ).pushNamedAndRemoveUntil(RouteNames.main, (r) => false);
        return;
      }
      if (route == RouteNames.terms) {
        Navigator.of(context).pushReplacementNamed(RouteNames.terms);
        return;
      }
      Navigator.of(context).pushNamedAndRemoveUntil(route, (r) => false);
    } catch (e) {
      debugPrint('⚠️ Splash 네비게이션 오류: ${PrivacyLogUtils.errorSummary(e)}');
      if (!mounted) return;
      // 오류 발생 시 안전하게 terms 화면으로 이동
      Navigator.of(context).pushReplacementNamed(RouteNames.terms);
    }
  }

  @override
  Widget build(BuildContext context) {
    return const CupertinoPageScaffold(
      backgroundColor: SeolleyeonSplashView.backgroundColor,
      child: SeolleyeonSplashView(),
    );
  }
}
