import 'package:flutter/material.dart';

import '../../../router/route_names.dart';

/// 로그인 안내 화면 (연세 이메일 로그인으로 이동). Kakao 는 인증 수단이 아니다.
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Spacer(),
              // Logo
              const Text(
                '설레연',
                style: TextStyle(
                  fontSize: 48,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFFFF6B8A),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '설레는 연애의 시작',
                style: TextStyle(fontSize: 16, color: Color(0xFF666666)),
              ),
              const Spacer(),
              // 연세 이메일 로그인 화면으로 이동 (primary 인증)
              ElevatedButton(
                onPressed: () {
                  Navigator.of(context).pushReplacementNamed(RouteNames.login);
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFFF6B8A),
                  foregroundColor: Colors.white,
                  minimumSize: const Size(double.infinity, 56),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.mail_outline, size: 20),
                    SizedBox(width: 8),
                    Text(
                      '연세 메일로 시작하기',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 48),
            ],
          ),
        ),
      ),
    );
  }
}
