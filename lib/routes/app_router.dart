import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';

import '../screens/auth/welcome_screen.dart';
import '../screens/auth/terms_screen.dart';
import '../screens/auth/signup_screen.dart';
import '../screens/auth/kakao_login_screen.dart';
import '../screens/auth/student_verification_screen.dart';
import '../screens/auth/initial_setup_screen.dart';
import '../screens/auth/kakao_callback_screen.dart';
import '../screens/main/main_screen.dart';
import '../screens/matching/matching_screen.dart';
import '../screens/chat/chat_list_screen.dart';
import '../screens/event/event_screen.dart';
import '../screens/community/community_screen.dart';
import '../screens/profile/profile_screen.dart';
import '../screens/tutorial/tutorial_screen.dart';

class AppRouter {
  static GoRouter router(AuthProvider authProvider) => GoRouter(
    initialLocation: '/splash', // ✅ 변경
    refreshListenable: authProvider,
    redirect: (context, state) {
      final loc = state.matchedLocation;

      debugPrint(
        '[Router] loc=$loc '
        'init=${authProvider.isInitialized} '
        'loading=${authProvider.isLoading} '
        'authed=${authProvider.isAuthenticated} '
        'verified=${authProvider.isStudentVerified} '
        'setup=${authProvider.isInitialSetupComplete} '
        'tutorial=${authProvider.hasSeenTutorial}',
      );

      // ✅ 0) 초기화/로딩 중엔 splash 고정
      if (!authProvider.isInitialized || authProvider.isLoading) {
        return loc == '/splash' ? null : '/splash';
      }

      // ✅ 0-1) 이메일 링크 인증은 무조건 허용 (중요)
      if (loc == '/auth/email-link') {
        return null;
      }

      // ✅ 0-2) 카카오 로그인 플로우 화면은 항상 허용
      // (기존 상태값에 의해 /initial-setup 등으로 강제 redirect 되는 것을 방지)
      if (loc == '/auth/kakao' || loc == '/auth/kakao/callback') {
        return null;
      }

      final isLoggedIn = authProvider.isAuthenticated;
      final isStudentVerified = authProvider.isStudentVerified;
      final isInitialSetupComplete = authProvider.isInitialSetupComplete;
      final hasSeenTutorial = authProvider.hasSeenTutorial;

      final isPublic =
          loc == '/welcome' ||
          loc == '/terms' ||
          loc == '/login' ||
          loc == '/signup' ||
          loc == '/auth/kakao' ||
          loc == '/auth/kakao/callback';

      // 1) 로그인 전
      if (!isLoggedIn) {
        return isPublic ? null : '/welcome';
      }

      // 2) 학생 인증 전
      if (!isStudentVerified) {
        return loc == '/student-verification' ? null : '/student-verification';
      }

      // 3) 초기 설정
      if (!isInitialSetupComplete) {
        return loc == '/initial-setup' ? null : '/initial-setup';
      }

      // 4) 튜토리얼
      if (!hasSeenTutorial) {
        return loc == '/tutorial' ? null : '/tutorial';
      }

      // 5) 다 끝났으면 홈
      if (isPublic ||
          loc == '/tutorial' ||
          loc == '/initial-setup' ||
          loc == '/student-verification') {
        return '/home';
      }

      // 🔥 최종 안전망: 다 끝났는데 splash에 있으면 홈으로
      if (authProvider.isInitialized &&
          !authProvider.isLoading &&
          authProvider.isAuthenticated &&
          authProvider.isStudentVerified &&
          authProvider.isInitialSetupComplete &&
          authProvider.hasSeenTutorial &&
          loc == '/splash') {
        return '/home';
      }

      return null;
    },
    routes: [
      // ✅ Splash 추가
      GoRoute(path: '/splash', builder: (_, __) => const _SplashScreen()),

      // Auth Flow
      GoRoute(
        path: '/welcome',
        name: 'welcome',
        builder: (_, __) => const WelcomeScreen(),
      ),
      GoRoute(
        path: '/terms',
        name: 'terms',
        builder: (_, __) => const TermsScreen(),
      ),
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (_, __) => const SignupScreen(),
      ),
      GoRoute(
        path: '/signup',
        name: 'signup',
        builder: (_, __) => const SignupScreen(),
      ),
      GoRoute(
        path: '/auth/kakao/callback',
        name: 'kakao-callback',
        builder: (_, __) => const KakaoCallbackScreen(),
      ),
      GoRoute(
        path: '/auth/kakao',
        name: 'kakao-login',
        builder: (_, __) => const KakaoLoginScreen(),
      ),
      GoRoute(
        path: '/auth/email-link',
        name: 'email-link',
        builder: (_, __) => const StudentVerificationScreen(),
      ),
      GoRoute(
        path: '/student-verification',
        name: 'student-verification',
        builder: (_, __) => const StudentVerificationScreen(),
      ),
      GoRoute(
        path: '/initial-setup',
        name: 'initial-setup',
        builder: (_, __) => const InitialSetupScreen(),
      ),

      // Tutorial
      GoRoute(
        path: '/tutorial',
        name: 'tutorial',
        builder: (_, __) => const TutorialScreen(),
      ),

      // Main
      GoRoute(
        path: '/home',
        name: 'home',
        builder: (_, __) => const MainScreen(),
      ),
      GoRoute(
        path: '/main',
        name: 'main',
        builder: (_, __) => const MainScreen(),
        routes: [
          GoRoute(
            path: 'matching',
            name: 'matching',
            builder: (_, __) => const MatchingScreen(),
          ),
          GoRoute(
            path: 'chat',
            name: 'chat',
            builder: (_, __) => const ChatListScreen(),
          ),
          GoRoute(
            path: 'event',
            name: 'event',
            builder: (_, __) => const EventScreen(),
          ),
          GoRoute(
            path: 'community',
            name: 'community',
            builder: (_, __) => const CommunityScreen(),
          ),
          GoRoute(
            path: 'profile',
            name: 'profile',
            builder: (_, __) => const ProfileScreen(),
          ),
        ],
      ),
    ],
  );
}

class _SplashScreen extends StatefulWidget {
  const _SplashScreen();

  @override
  State<_SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<_SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fade;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 650),
    );

    _fade = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
    _scale = Tween<double>(
      begin: 0.96,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutBack));

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0B0F), // 어두운 배경 (원하면 바꿔)
      body: SafeArea(
        child: Center(
          child: FadeTransition(
            opacity: _fade,
            child: ScaleTransition(
              scale: _scale,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  Text(
                    '설레연',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 40,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                      letterSpacing: 1.0,
                    ),
                  ),
                  SizedBox(height: 10),
                  Text(
                    '만남이 시작되는 곳',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFFB7B7C2),
                    ),
                  ),
                  SizedBox(height: 26),
                  SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
