// =============================================================================
// 카카오 인증 에러 화면
// 경로: lib/features/auth/screens/kakao_auth_error_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const KakaoAuthErrorScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEE2B5B);
  static const Color backgroundLight = Color(0xFFFCF8F9);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1B0D11);
  static const Color textSecondary = Color(0xFF1B0D11);
  static const Color red500 = Color(0xFFEF4444);
}

// =============================================================================
// 메인 화면
// =============================================================================
class KakaoAuthErrorScreen extends StatelessWidget {
  final VoidCallback? onRetry;
  final VoidCallback? onBack;
  final VoidCallback? onContactSupport;
  final VoidCallback? onAlternativeLogin;

  const KakaoAuthErrorScreen({
    super.key,
    this.onRetry,
    this.onBack,
    this.onContactSupport,
    this.onAlternativeLogin,
  });

  void _onRetry(BuildContext context) {
    HapticFeedback.mediumImpact();
    onRetry?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Column(
        children: [
          // 헤더
          _Header(onBack: onBack),
          // 메인 콘텐츠
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // 에러 비주얼
                  const _ErrorVisual(),
                  const SizedBox(height: 32),
                  // 텍스트 콘텐츠
                  const _TextContent(),
                  const SizedBox(height: 48),
                  // 재시도 버튼
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => _onRetry(context),
                    child: Container(
                      width: double.infinity,
                      height: 56,
                      decoration: BoxDecoration(
                        color: _AppColors.primary,
                        borderRadius: BorderRadius.circular(28),
                        boxShadow: [
                          BoxShadow(
                            color: _AppColors.primary.withValues(alpha: 0.15),
                            blurRadius: 40,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: const Center(
                        child: Text(
                          '다시 시도',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.5,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 푸터
          Padding(
            padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 32),
            child: Column(
              children: [
                // 안심 카드
                const _TrustCard(),
                const SizedBox(height: 32),
                // 도움말 링크
                _HelpLinks(
                  onContactSupport: onContactSupport,
                  onAlternativeLogin: onAlternativeLogin,
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
    return SafeArea(
      bottom: false,
      child: Padding(
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
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: CupertinoColors.black.withValues(alpha: 0.05),
                ),
                child: const Icon(
                  CupertinoIcons.back,
                  size: 24,
                  color: _AppColors.textMain,
                ),
              ),
            ),
            Expanded(
              child: Text(
                'Seolleyeon',
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
            const SizedBox(width: 48),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 에러 비주얼
// =============================================================================
class _ErrorVisual extends StatelessWidget {
  const _ErrorVisual();

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        // 배경 글로우
        Positioned.fill(
          child: Transform.scale(
            scale: 0.75,
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.primary.withValues(alpha: 0.2),
              ),
            ),
          ),
        ),
        // 메인 아이콘
        Container(
          width: 128,
          height: 128,
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
            border: Border.all(
              color: CupertinoColors.black.withValues(alpha: 0.05),
            ),
          ),
          child: const Center(
            child: Icon(
              CupertinoIcons.heart_slash_fill,
              size: 48,
              color: _AppColors.primary,
            ),
          ),
        ),
        // 경고 배지
        Positioned(
          bottom: 4,
          right: 4,
          child: Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: _AppColors.red500,
              shape: BoxShape.circle,
              border: Border.all(color: _AppColors.backgroundLight, width: 4),
            ),
            child: const Center(
              child: Icon(
                CupertinoIcons.exclamationmark,
                size: 14,
                color: CupertinoColors.white,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 텍스트 콘텐츠
// =============================================================================
class _TextContent extends StatelessWidget {
  const _TextContent();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Text(
          '인증에 실패했어요',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 28,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.5,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          '일시적인 오류일 수 있어요.\n잠시 후 다시 시도해 주세요.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            height: 1.5,
            color: _AppColors.textSecondary.withValues(alpha: 0.6),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 안심 카드
// =============================================================================
class _TrustCard extends StatelessWidget {
  const _TrustCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: CupertinoColors.black.withValues(alpha: 0.05),
        ),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.02),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 아이콘
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              CupertinoIcons.shield_fill,
              size: 20,
              color: _AppColors.primary,
            ),
          ),
          const SizedBox(width: 16),
          // 텍스트
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '안심하세요',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '회원님의 카카오톡 타임라인에\n절대 기록을 남기지 않아요.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    height: 1.5,
                    color: _AppColors.textSecondary.withValues(alpha: 0.6),
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
// 도움말 링크
// =============================================================================
class _HelpLinks extends StatelessWidget {
  final VoidCallback? onContactSupport;
  final VoidCallback? onAlternativeLogin;

  const _HelpLinks({this.onContactSupport, this.onAlternativeLogin});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: onContactSupport,
          child: Text(
            '고객센터 문의',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSecondary.withValues(alpha: 0.4),
            ),
          ),
        ),
        Container(
          margin: const EdgeInsets.symmetric(horizontal: 12),
          width: 1,
          height: 12,
          color: _AppColors.textSecondary.withValues(alpha: 0.1),
        ),
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: onAlternativeLogin,
          child: Text(
            '다른 방법으로 로그인',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSecondary.withValues(alpha: 0.4),
            ),
          ),
        ),
      ],
    );
  }
}
