import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Legacy stub. The Kakao login entrypoint was removed: the PRIMARY
/// authentication is the Yonsei email link (see StudentVerificationScreen).
class SignupScreen extends StatelessWidget {
  const SignupScreen({super.key});

  void _goToEmailLogin(BuildContext context) {
    context.go('/student-verification');
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
              '연세 이메일로 로그인해주세요',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => _goToEmailLogin(context),
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(double.infinity, 50),
              ),
              child: const Text('연세 메일로 로그인'),
            ),
          ],
        ),
      ),
    );
  }
}
