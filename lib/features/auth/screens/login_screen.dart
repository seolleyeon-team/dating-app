import 'package:flutter/material.dart';

import '../../../router/route_names.dart';

/// 로그인 화면 (카카오톡으로 시작하기 → 카카오 인증 화면으로 이동)
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
              // 카카오 로그인 버튼 → 카카오 인증 화면(연세메일/홈 분기)
              ElevatedButton(
                onPressed: () {
                  Navigator.of(
                    context,
                  ).pushReplacementNamed(RouteNames.kakaoAuth);
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFFEE500),
                  foregroundColor: Colors.black87,
                  minimumSize: const Size(double.infinity, 56),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.chat_bubble, size: 20),
                    SizedBox(width: 8),
                    Text(
                      '카카오톡으로 시작하기',
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
