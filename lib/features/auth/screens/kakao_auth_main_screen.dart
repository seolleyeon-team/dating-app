// =============================================================================
// 카카오 인증 메인 화면
// 경로: lib/features/auth/screens/kakao_auth_main_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const KakaoAuthMainScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEE2B5B);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1B0D11);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray700 = Color(0xFF374151);
  static const Color kakao = Color(0xFFFEE500);
  static const Color kakaoLabel = Color(0xFF191919);
  static const Color green100 = Color(0xFFDCFCE7);
  static const Color green600 = Color(0xFF16A34A);
  static const Color red50 = Color(0xFFFEF2F2);
  static const Color red500 = Color(0xFFEF4444);
}

// =============================================================================
// 메인 화면
// =============================================================================
class KakaoAuthMainScreen extends StatelessWidget {
  final VoidCallback? onBack;
  final VoidCallback? onKakaoLogin;
  final VoidCallback? onTerms;
  final VoidCallback? onPrivacy;

  const KakaoAuthMainScreen({
    super.key,
    this.onBack,
    this.onKakaoLogin,
    this.onTerms,
    this.onPrivacy,
  });

  void _onKakaoLogin() {
    HapticFeedback.mediumImpact();
    onKakaoLogin?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 글로우
          Positioned(
            top: MediaQuery.of(context).size.height * 0.3,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: 300,
                height: 300,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      _AppColors.primary.withValues(alpha: 0.15),
                      _AppColors.primary.withValues(alpha: 0.05),
                      _AppColors.primary.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBack: onBack),
                // 히어로 섹션
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // 아이콘
                      Container(
                        padding: const EdgeInsets.all(24),
                        decoration: BoxDecoration(
                          color: _AppColors.surfaceLight,
                          shape: BoxShape.circle,
                          border: Border.all(color: _AppColors.gray100),
                          boxShadow: [
                            BoxShadow(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.04,
                              ),
                              blurRadius: 30,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: const Icon(
                          CupertinoIcons.heart_fill,
                          size: 48,
                          color: _AppColors.primary,
                        ),
                      ),
                      const SizedBox(height: 32),
                      // 타이틀
                      const Text(
                        '안전한 캠퍼스 인증을\n시작할게요',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 26,
                          fontWeight: FontWeight.w700,
                          height: 1.3,
                          letterSpacing: -0.5,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        '철저한 신원 확인으로 믿을 수 있는\n만남을 약속해요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 16,
                          height: 1.5,
                          color: _AppColors.gray500,
                        ),
                      ),
                    ],
                  ),
                ),
                // 하단 액션
                Padding(
                  padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 32),
                  child: Column(
                    children: [
                      // 카카오 버튼
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _onKakaoLogin,
                        child: Container(
                          width: double.infinity,
                          height: 56,
                          decoration: BoxDecoration(
                            color: _AppColors.kakao,
                            borderRadius: BorderRadius.circular(28),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.kakao.withValues(alpha: 0.3),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                CupertinoIcons.chat_bubble_fill,
                                size: 24,
                                color: _AppColors.kakaoLabel,
                              ),
                              SizedBox(width: 12),
                              Text(
                                '카카오로 계속하기',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                  color: _AppColors.kakaoLabel,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      // 약관 안내
                      _LegalText(onTerms: onTerms, onPrivacy: onPrivacy),
                      const SizedBox(height: 24),
                      // 정보 카드
                      const _InfoCard(),
                      const SizedBox(height: 24),
                      // 보안 배지
                      const _SecureBadge(),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onBack;

  const _Header({this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.lightImpact();
              onBack?.call();
            },
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: CupertinoColors.black.withValues(alpha: 0.05),
              ),
              child: const Icon(
                CupertinoIcons.back,
                size: 20,
                color: _AppColors.textMain,
              ),
            ),
          ),
          const Expanded(
            child: Text(
              '카카오톡 인증',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.3,
                color: _AppColors.textMain,
              ),
            ),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

// =============================================================================
// 약관 텍스트
// =============================================================================
class _LegalText extends StatelessWidget {
  final VoidCallback? onTerms;
  final VoidCallback? onPrivacy;

  const _LegalText({this.onTerms, this.onPrivacy});

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 12,
          height: 1.5,
          color: _AppColors.gray400,
        ),
        children: [
          const TextSpan(text: '계속 진행 시 '),
          TextSpan(
            text: '이용약관',
            style: const TextStyle(decoration: TextDecoration.underline),
            recognizer: TapGestureRecognizer()..onTap = onTerms,
          ),
          const TextSpan(text: ' 및 '),
          TextSpan(
            text: '개인정보 처리방침',
            style: const TextStyle(decoration: TextDecoration.underline),
            recognizer: TapGestureRecognizer()..onTap = onPrivacy,
          ),
          const TextSpan(text: '에\n동의하게 됩니다.'),
        ],
      ),
      textAlign: TextAlign.center,
    );
  }
}

// =============================================================================
// 정보 카드
// =============================================================================
class _InfoCard extends StatelessWidget {
  const _InfoCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.gray100),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.02),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 헤더
          const Row(
            children: [
              Icon(
                CupertinoIcons.info_circle_fill,
                size: 18,
                color: _AppColors.primary,
              ),
              SizedBox(width: 8),
              Text(
                '카카오에서 제공받는 정보',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // 허용 항목
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _AppColors.gray50,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: const BoxDecoration(
                    color: _AppColors.green100,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    CupertinoIcons.checkmark,
                    size: 16,
                    color: _AppColors.green600,
                  ),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    '이름, 전화번호',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.gray700,
                    ),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    border: Border.all(color: _AppColors.gray100),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    '본인확인용',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.gray400,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // 차단 항목
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _AppColors.gray50,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: const BoxDecoration(
                    color: _AppColors.red50,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    CupertinoIcons.xmark,
                    size: 16,
                    color: _AppColors.red500,
                  ),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    '카카오톡 친구 목록',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.gray700,
                    ),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    '수집안함',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.primary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 보안 배지
// =============================================================================
class _SecureBadge extends StatelessWidget {
  const _SecureBadge();

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.6,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            CupertinoIcons.shield_fill,
            size: 16,
            color: _AppColors.gray400,
          ),
          const SizedBox(width: 6),
          Text(
            'SEOLLEYEON SECURE SYSTEM',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 1,
              color: _AppColors.gray400,
            ),
          ),
        ],
      ),
    );
  }
}
