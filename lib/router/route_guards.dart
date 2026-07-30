import 'package:flutter/cupertino.dart';

/// 라우트 가드
class RouteGuards {
  RouteGuards._();

  /// 인증 필요 여부 확인
  static bool requiresAuth(String routeName) {
    const publicRoutes = ['/', '/login', '/kakao-auth', '/terms'];
    return !publicRoutes.contains(routeName);
  }

  /// 온보딩 완료 필요 여부 확인
  static bool requiresOnboarding(String routeName) {
    const onboardingRoutes = [
      '/onboarding/basic-info',
      '/onboarding/interests-selection',
      '/onboarding/lifestyle',
      '/onboarding/major',
      '/onboarding/department',
      '/onboarding/interests',
      '/onboarding/keywords',
      '/onboarding/photo',
      '/onboarding/self-intro',
      '/onboarding/profile-qa',
      '/onboarding/ideal/age',
      '/onboarding/ideal/height',
      '/onboarding/ideal/mbti',
      '/onboarding/ideal/department',
      '/onboarding/ideal/personality',
      '/onboarding/ideal/lifestyle',
    ];
    return onboardingRoutes.contains(routeName);
  }

  /// 메인 탭 라우트인지 확인
  static bool isMainTabRoute(String routeName) {
    const mainRoutes = [
      '/main',
      '/matching',
      '/community',
      '/event',
      '/chat',
      '/profile',
    ];
    return mainRoutes.contains(routeName);
  }
}

/// 인증 상태 체크 위젯 (라우트 가드로 사용)
class AuthGuard extends StatelessWidget {
  final Widget child;
  final Widget fallback;
  final bool isAuthenticated;

  const AuthGuard({
    super.key,
    required this.child,
    required this.fallback,
    required this.isAuthenticated,
  });

  @override
  Widget build(BuildContext context) {
    return isAuthenticated ? child : fallback;
  }
}
