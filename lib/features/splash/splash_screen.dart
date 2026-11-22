import 'dart:async';

import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart' show FirebaseAuth;
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../router/route_names.dart';
import '../../services/account_setup_flow.dart';
import '../../services/auth_service.dart';
import '../../shared/widgets/seolleyeon_splash_view.dart';
import '../auth/utils/email_link_continue_url.dart';

/// What Splash asks of the outside world. Production reads Firebase and the
/// platform link; widget tests inject a fake.
abstract class SplashEnvironment {
  Future<Uri?> readInitialUri();
  bool isEmailLinkEntryPoint(Uri? uri);

  /// Only an attached Firebase session counts as a session. A cached local
  /// id or a Kakao SDK session never authenticates.
  bool get hasFirebaseSession;

  /// 운영 제재 계정은 세션과 로컬 식별자를 정리한다. true 면 약관으로 보낸다.
  Future<bool> handleRejoinRestriction();
  Future<String> resolveSetupRoute();
}

class _FirebaseSplashEnvironment implements SplashEnvironment {
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

  @override
  bool isEmailLinkEntryPoint(Uri? uri) {
    if (uri == null) return false;
    return _isEmailLink(uri.toString()) || isStudentEmailLinkContinuation(uri);
  }

  @override
  Future<Uri?> readInitialUri() async {
    // On web the browser URL is the source of truth. AppLinks may return a
    // normalized root URL instead of the original Firebase action link.
    final browserUri = Uri.base;
    if (isEmailLinkEntryPoint(browserUri)) {
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
  bool get hasFirebaseSession => FirebaseAuth.instance.currentUser != null;

  @override
  Future<bool> handleRejoinRestriction() {
    return _setupFlow.handleRejoinRestriction();
  }

  @override
  Future<String> resolveSetupRoute() => _setupFlow.resolveNextRoute();
}

/// 스플래시 화면 (Yonsei-email-primary)
/// - 이메일 액션 링크 진입: StudentVerificationScreen 이 링크를 소비한다.
/// - Firebase 세션 없음: 약관(terms) → 성인인증 → 연세 이메일 로그인.
/// - Firebase 세션 있음(canonical / grandfathered legacy): users/{uid} 서버
///   진실로 설정 사다리(성인인증/카카오 친구 연결/온보딩/튜토리얼/메인)를 라우팅.
///   카카오 기반 세션 복구는 존재하지 않는다.
///
/// Launch order (B-17): Splash waits for AuthProvider's first session
/// resolution before it routes, so the two never act on the session
/// concurrently (the provider may sign a non-canonical session out).
///
/// Transient failures (AUD-16): a signed-in user is never dropped onto the
/// login funnel because the network or the backend failed at launch. Splash
/// shows a retry state instead and continues by itself once the provider's
/// bounded retry resolves the session.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key, this.environment});

  @visibleForTesting
  final SplashEnvironment? environment;

  /// Longest Splash waits for AuthProvider's first resolution.
  @visibleForTesting
  static const Duration bootstrapWaitLimit = Duration(seconds: 10);

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  late final SplashEnvironment _environment =
      widget.environment ?? _FirebaseSplashEnvironment();

  AuthProvider? _auth;
  bool _showRetry = false;
  bool _routing = false;
  bool _navigated = false;

  @override
  void initState() {
    super.initState();
    try {
      _auth = Provider.of<AuthProvider>(context, listen: false);
    } catch (_) {
      _auth = null;
    }
    _auth?.addListener(_onAuthChanged);
    _navigateToNext();
  }

  @override
  void dispose() {
    _auth?.removeListener(_onAuthChanged);
    super.dispose();
  }

  /// While the retry state is shown, continue as soon as the provider's own
  /// retry (or an app resume) has resolved the session.
  void _onAuthChanged() {
    if (!mounted || !_showRetry || _routing || _navigated) return;
    if (_auth?.bootstrapPhase == AuthBootstrapPhase.ready) {
      unawaited(_route());
    }
  }

  Future<void> _waitForAuthBootstrap() async {
    final auth = _auth;
    if (auth == null) return;
    await auth.bootstrapSettled.timeout(
      SplashScreen.bootstrapWaitLimit,
      onTimeout: () {},
    );
  }

  Future<void> _navigateToNext() async {
    await Future.wait<void>([
      Future<void>.delayed(const Duration(milliseconds: 1500)),
      _waitForAuthBootstrap(),
    ]);
    if (!mounted) return;
    await _route();
  }

  void _replaceWith(String route) {
    _navigated = true;
    Navigator.of(context).pushReplacementNamed(route);
  }

  void _resetTo(String route) {
    _navigated = true;
    Navigator.of(context).pushNamedAndRemoveUntil(route, (r) => false);
  }

  void _enterRetryState() {
    if (!mounted) return;
    setState(() => _showRetry = true);
  }

  Future<void> _route() async {
    if (_routing || _navigated) return;
    _routing = true;
    try {
      final initialUri = await _environment.readInitialUri();
      if (!mounted) return;

      // Firebase email links must be handled by StudentVerificationScreen
      // before the normal app-session gate: the action code is single-use
      // and completes the PRIMARY authentication there.
      if (_environment.isEmailLinkEntryPoint(initialUri)) {
        _resetTo(RouteNames.studentVerification);
        return;
      }

      if (!_environment.hasFirebaseSession) {
        _replaceWith(RouteNames.terms);
        return;
      }

      // A session is attached but the provider could not resolve it yet
      // (offline, timeout, backend error). Do not guess a route.
      if (_auth?.bootstrapPhase == AuthBootstrapPhase.retryableError) {
        _enterRetryState();
        return;
      }

      // 운영 제재 계정은 세션과 로컬 식별자를 정리하고 약관으로 보낸다.
      if (await _environment.handleRejoinRestriction()) {
        if (!mounted) return;
        _replaceWith(RouteNames.terms);
        return;
      }

      final route = await _environment.resolveSetupRoute();
      if (!mounted) return;

      // The setup ladder answers "re-verify the email" when it cannot read
      // the users doc. If the provider has just hydrated this very account
      // as student-verified from the server, that answer is a failed read,
      // not a fact: retry instead of sending the user to log in again.
      final auth = _auth;
      if (route == RouteNames.studentVerification &&
          auth != null &&
          auth.isAuthenticated &&
          auth.isStudentVerified) {
        _enterRetryState();
        return;
      }

      if (route == RouteNames.main) {
        _resetTo(RouteNames.main);
        return;
      }
      if (route == RouteNames.terms) {
        _replaceWith(RouteNames.terms);
        return;
      }
      _resetTo(route);
    } catch (e) {
      debugPrint('⚠️ Splash 네비게이션 오류: ${PrivacyLogUtils.errorSummary(e)}');
      if (!mounted) return;
      if (_hasSessionSafely()) {
        // Signed in, and something failed while resolving the route. The
        // terms screen is the logged-OUT entry; never strand a signed-in
        // user there because of an error.
        _enterRetryState();
        return;
      }
      // 세션이 없으면 안전하게 terms 화면으로 이동
      _replaceWith(RouteNames.terms);
    } finally {
      _routing = false;
    }
  }

  bool _hasSessionSafely() {
    try {
      return _environment.hasFirebaseSession;
    } catch (_) {
      return false;
    }
  }

  Future<void> _retry() async {
    if (_routing) return;
    setState(() => _showRetry = false);
    final auth = _auth;
    if (auth != null &&
        auth.bootstrapPhase == AuthBootstrapPhase.retryableError) {
      await auth.retryBootstrap();
    }
    if (!mounted || _navigated) return;
    await _route();
  }

  /// The explicit way out of the retry state: the user chooses to sign out.
  Future<void> _signOutAndRestart() async {
    final auth = _auth;
    if (auth == null || _routing) return;
    await auth.logout();
    if (!mounted || _navigated) return;
    _replaceWith(RouteNames.terms);
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: SeolleyeonSplashView.backgroundColor,
      child: Stack(
        fit: StackFit.expand,
        children: [
          const SeolleyeonSplashView(),
          if (_showRetry)
            SafeArea(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        '연결이 원활하지 않아요.\n네트워크를 확인한 뒤 다시 시도해 주세요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'NanumSquareRound',
                          fontSize: 14,
                          height: 1.4,
                          color: Color(0xFF475569),
                          decoration: TextDecoration.none,
                        ),
                      ),
                      const SizedBox(height: 12),
                      CupertinoButton.filled(
                        key: const ValueKey('splash-retry'),
                        onPressed: _retry,
                        child: const Text('다시 시도'),
                      ),
                      if (_auth != null)
                        CupertinoButton(
                          key: const ValueKey('splash-sign-out'),
                          onPressed: _signOutAndRestart,
                          child: const Text(
                            '로그아웃',
                            style: TextStyle(fontSize: 13),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
