import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../core/constants/app_colors.dart';
import '../../core/constants/app_typography.dart';
import '../../providers/auth_provider.dart';
import '../../router/route_names.dart';
import '../../services/adult_verification_service.dart';

/// Legacy stub. Kakao NEVER authenticates the Seolleyeon account anymore:
/// the PRIMARY credential is the verified Yonsei email link. This stub only
/// forwards to the adult-verification gate / email login screen.
class KakaoLoginScreen extends StatelessWidget {
  const KakaoLoginScreen({super.key});

  Future<void> _handleContinue(BuildContext context) async {
    final adultVerificationService = AdultVerificationService();

    if (!await adultVerificationService.hasPendingKakaoLoginSession()) {
      if (!context.mounted) return;
      Navigator.of(context).pushReplacementNamed(RouteNames.adultVerification);
      return;
    }

    if (!context.mounted) return;
    context.go('/student-verification');
  }

  @override
  Widget build(BuildContext context) {
    final isLoading = context.watch<AuthProvider>().isLoading;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('로그인'),
        backgroundColor: AppColors.background,
        elevation: 0,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 12),
              const Text('설레연 시작하기', style: AppTypography.h2),
              const SizedBox(height: 8),
              const Text(
                '약관 동의가 완료됐어요.\n연세 이메일로 로그인해 주세요.',
                style: AppTypography.bodyLarge,
              ),
              const SizedBox(height: 24),
              Expanded(
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [Color(0xFFFFEFF3), Color(0xFFFFF7FA)],
                    ),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 8,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.heartLight,
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: const Text(
                            '안전한 가입을 위해 1회만 진행해요',
                            style: AppTypography.labelMedium,
                          ),
                        ),
                        const SizedBox(height: 14),
                        const Text('연세 메일로 계속하기', style: AppTypography.h3),
                        const SizedBox(height: 6),
                        const Text(
                          '연세 메일 인증으로 로그인한 뒤 기본 정보를 입력하게 됩니다.',
                          style: AppTypography.bodyMedium,
                        ),
                        const Spacer(),
                        SizedBox(
                          width: double.infinity,
                          height: 52,
                          child: ElevatedButton(
                            onPressed: isLoading
                                ? null
                                : () => _handleContinue(context),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppColors.primary,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14),
                              ),
                            ),
                            child: isLoading
                                ? const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Text('연세 메일로 로그인'),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Center(
                          child: TextButton(
                            onPressed: isLoading
                                ? null
                                : () => context.go('/welcome'),
                            child: const Text(
                              '처음으로',
                              style: TextStyle(color: AppColors.textSecondary),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );
  }
}
