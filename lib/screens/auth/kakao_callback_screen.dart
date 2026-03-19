import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

import '../../providers/auth_provider.dart';
import '../../router/route_names.dart';
import '../../services/auth_service.dart';

class KakaoCallbackScreen extends StatefulWidget {
  const KakaoCallbackScreen({super.key, this.callbackPathAndQuery});

  /// iOS/Android 딥링크로 열렸을 때 전달되는 경로+쿼리 (예: /?code=xxx)
  final String? callbackPathAndQuery;

  @override
  State<KakaoCallbackScreen> createState() => _KakaoCallbackScreenState();
}

class _KakaoCallbackScreenState extends State<KakaoCallbackScreen> {
  String _statusMessage = '로그인 처리 중...';
  bool _handled = false;

  @override
  void initState() {
    super.initState();
    _handleCallback();
  }

  Future<void> _handleCallback() async {
    if (_handled) return;
    _handled = true;

    final uri = widget.callbackPathAndQuery != null
        ? Uri.parse('https://dummy.com${widget.callbackPathAndQuery}')
        : Uri.base;
    final query = uri.queryParameters;
    final error = query['error'];
    final errorDescription = query['error_description'];

    // 1) 카카오에서 에러로 리다이렉트된 경우
    if (error != null) {
      if (!mounted) return;
      setState(() {
        _statusMessage = '로그인 실패: ${errorDescription ?? error}';
      });
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        RouteNames.kakaoAuth,
        (route) => false,
      );
      return;
    }

    // 2) 앱이 카카오 리다이렉트 URL로 켜졌을 때 네이티브에서 URL을 SDK에 전달 (iOS/Android)
    try {
      await receiveKakaoScheme();
    } catch (_) {}

    // 3) URL에 code가 있으면 토큰 발급 후 저장 (iOS에서 네이티브가 URL을 안 넘겨도 동작하도록)
    final code = query['code'];
    if (code != null && code.isNotEmpty) {
      try {
        final token = await AuthApi.instance.issueAccessToken(
          authCode: code,
          redirectUri: KakaoSdk.redirectUri,
        );
        await TokenManagerProvider.instance.manager.setToken(token);
      } catch (e) {
        debugPrint('[KakaoCallback] issueAccessToken failed: $e');
      }
    }

    try {
      if (!mounted) return;
      setState(() => _statusMessage = '카카오 사용자 정보 확인 중...');

      final user = await UserApi.instance.me();
      final kakaoUserId = user.id.toString();

      final userInfo = {
        'id': kakaoUserId,
        'nickname': user.kakaoAccount?.profile?.nickname,
        'profileImageUrl': user.kakaoAccount?.profile?.profileImageUrl,
        'email': user.kakaoAccount?.email,
      };

      // 4) 로그인 상태 저장 (AuthProvider 갱신)
      if (!mounted) return;
      final authProvider = context.read<AuthProvider>();
      await authProvider.setKakaoLogin(kakaoUserId, userInfo: userInfo);

      if (!mounted) return;
      setState(() => _statusMessage = '로그인 완료! 이동 중...');

      // 5) Firebase에서 최신 상태로 재조회 후 라우팅
      final authService = AuthService();
      final isVerified = await authService.isStudentVerified(kakaoUserId);
      final isSetupComplete =
          await authService.isInitialSetupComplete(kakaoUserId);

      if (!mounted) return;
      if (!isVerified) {
        Navigator.of(context).pushNamedAndRemoveUntil(
          RouteNames.studentVerification,
          (route) => false,
        );
      } else if (!isSetupComplete) {
        // 3단계까지 했으면 4단계로 이어서 채우기
        final nextRoute = await authService.getOnboardingNextRoute(kakaoUserId);
        if (!mounted) return;
        Navigator.of(context).pushNamedAndRemoveUntil(
          nextRoute ?? RouteNames.onboardingBasicInfo,
          (route) => false,
        );
      } else {
        // 연세 인증 + 초기설정 완료 → 튜토리얼 없이 홈(설레연 탭). 재설치 후 약관→카카오 로그인한 기존 사용자 포함
        Navigator.of(context).pushNamedAndRemoveUntil(
          RouteNames.main,
          (route) => false,
        );
      }
    } on KakaoException catch (e) {
      final detail = e.message ?? e.toString();
      if (!mounted) return;
      setState(() => _statusMessage = '카카오 로그인 실패: $detail');
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        RouteNames.kakaoAuth,
        (route) => false,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _statusMessage = '로그인 처리 실패: $e');
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        RouteNames.kakaoAuth,
        (route) => false,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          '카카오 로그인 콜백',
          style: TextStyle(fontFamily: 'Noto Sans KR'),
        ),
      ),
      body: Center(
        child: Text(
          _statusMessage,
          style: const TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 16,
          ),
        ),
      ),
    );
  }
}
