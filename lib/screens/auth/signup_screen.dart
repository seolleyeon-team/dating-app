import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../services/auth_service.dart';
import '../../providers/auth_provider.dart';

class SignupScreen extends StatelessWidget {
  const SignupScreen({super.key});

  Future<void> _handleKakaoLogin(BuildContext context) async {
    final authService = AuthService();
    final authProvider = context.read<AuthProvider>();

    try {
      final userInfo = await authService.loginWithKakao();

      final kakaoUserId = userInfo['id']?.toString();
      if (kakaoUserId != null) {
        await authProvider.setKakaoLogin(kakaoUserId, userInfo: userInfo);
      }

      debugPrint('Kakao login success');

      if (!context.mounted) return;
      if (!authProvider.isStudentVerified) {
        context.go('/student-verification');
      } else if (!authProvider.isInitialSetupComplete) {
        context.go('/initial-setup');
      } else {
        context.go('/home');
      }
    } catch (e) {
      final message = e.toString().replaceFirst('Exception: ', '');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('계정 생성')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '카카오 계정으로 로그인해주세요',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => _handleKakaoLogin(context),
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(double.infinity, 50),
              ),
              child: const Text('카카오로 로그인'),
            ),
          ],
        ),
      ),
    );
  }
}
