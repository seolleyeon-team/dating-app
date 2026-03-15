import 'package:app_links/app_links.dart';
import 'package:flutter/cupertino.dart';

import '../../router/route_names.dart';
import '../../services/auth_service.dart';
import '../../services/storage_service.dart';

/// 스플래시 화면
/// - 로그인된 계정(저장된 kakaoUserId 있음): 연세+초기설정 완료 시 홈(main), 아니면 약관(terms)
/// - 재설치 등 로그아웃 상태: 약관(terms) → 카카오 로그인. 로그인 시 이미 가입+초기설정 완료면 홈으로 이동
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  final _authService = AuthService();
  final _storageService = StorageService();

  @override
  void initState() {
    super.initState();
    _navigateToNext();
  }

  Future<void> _navigateToNext() async {
    await Future.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;

    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        // 재설치 등 로그아웃 상태: 딥링크로 카카오 콜백이 열렸을 수 있음 → 처리 후 가입+초기설정 완료면 홈으로
        final uri = await AppLinks().getInitialLink();
        final pathAndQuery = uri != null
            ? '${uri.path}${uri.query.isNotEmpty ? '?${uri.query}' : ''}'
            : '';
        if (pathAndQuery.contains('code=')) {
          if (!mounted) return;
          final routeName = pathAndQuery.startsWith('/')
              ? pathAndQuery
              : '/$pathAndQuery';
          Navigator.of(
            context,
          ).pushNamedAndRemoveUntil(routeName, (route) => false);
          return;
        }
        Navigator.of(context).pushReplacementNamed(RouteNames.terms);
        return;
      }

      final exists = await _authService.kakaoUserExists(kakaoUserId);
      if (!exists) {
        Navigator.of(context).pushReplacementNamed(RouteNames.terms);
        return;
      }

      final isVerified = await _authService.isStudentVerified(kakaoUserId);
      final isInitialSetupComplete = await _authService.isInitialSetupComplete(
        kakaoUserId,
      );

      // 이메일 링크로 앱이 열렸을 때 → 학생 인증 화면으로 바로 이동
      final uri = await AppLinks().getInitialLink();
      final path = uri?.path ?? '';
      if (!isVerified && path.contains('auth/email-link')) {
        if (!mounted) return;
        Navigator.of(context).pushNamedAndRemoveUntil(
          RouteNames.studentVerification,
          (route) => false,
        );
        return;
      }

      if (!mounted) return;
      // 연세 인증 + 초기설정 완료 시 튜토리얼 없이 홈(설레연 탭)으로
      if (isVerified && isInitialSetupComplete) {
        Navigator.of(
          context,
        ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
        return;
      }

      // 온보딩 진행 중이면 이어서 시작
      if (isVerified && !isInitialSetupComplete) {
        Navigator.of(context).pushNamedAndRemoveUntil(
          RouteNames.onboardingBasicInfo,
          (route) => false,
        );
        return;
      }

      Navigator.of(context).pushReplacementNamed(RouteNames.terms);
    } catch (e) {
      debugPrint('⚠️ Splash 네비게이션 오류: $e');
      if (!mounted) return;
      // 오류 발생 시 안전하게 terms 화면으로 이동
      Navigator.of(context).pushReplacementNamed(RouteNames.terms);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              '설레연',
              style: TextStyle(
                fontSize: 36,
                fontWeight: FontWeight.bold,
                color: Color(0xFFFF6B8A),
              ),
            ),
            const SizedBox(height: 16),
            const CupertinoActivityIndicator(color: Color(0xFFFF6B8A)),
          ],
        ),
      ),
    );
  }
}
