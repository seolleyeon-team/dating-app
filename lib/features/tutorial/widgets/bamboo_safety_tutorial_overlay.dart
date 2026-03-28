// =============================================================================
// 대나무숲 안전 튜토리얼 오버레이 (신고/차단 메뉴)
// 경로: lib/features/tutorial/widgets/bamboo_safety_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => BambooSafetyTutorialOverlay(
//     onStart: () => Navigator.pop(context),
//     onBack: () => Navigator.pop(context),
//   ),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF4438F);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color red500 = Color(0xFFEF4444);
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class BambooSafetyTutorialOverlay extends StatefulWidget {
  final VoidCallback onStart;
  final VoidCallback? onBack;
  final int currentStep;
  final int totalSteps;

  const BambooSafetyTutorialOverlay({
    super.key,
    required this.onStart,
    this.onBack,
    this.currentStep = 6,
    this.totalSteps = 6,
  });

  @override
  State<BambooSafetyTutorialOverlay> createState() =>
      _BambooSafetyTutorialOverlayState();
}

class _BambooSafetyTutorialOverlayState
    extends State<BambooSafetyTutorialOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onStart() {
    HapticFeedback.mediumImpact();
    widget.onStart();
  }

  void _onBack() {
    HapticFeedback.lightImpact();
    widget.onBack?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return FadeTransition(
      opacity: _fadeAnimation,
      child: Container(
        color: const Color(0x99000000), // 60% black overlay
        child: Stack(
          children: [
            // 하이라이트 영역 (상단 우측 메뉴 버튼)
            Positioned(top: 180, right: 28, child: _HighlightedMenuArea()),
            // 플로팅 이모지
            const Positioned(
              top: 180,
              left: 32,
              child: _FloatingEmoji(emoji: '🛡️'),
            ),
            const Positioned(
              top: 250,
              right: 48,
              child: _FloatingEmoji(emoji: '✨', delay: Duration(seconds: 1)),
            ),
            // 하단 카드
            Positioned(
              left: 16,
              right: 16,
              bottom: bottomPadding + 32,
              child: SlideTransition(
                position: _slideAnimation,
                child: _SafetyCard(
                  currentStep: widget.currentStep,
                  totalSteps: widget.totalSteps,
                  onStart: _onStart,
                  onBack: _onBack,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하이라이트 메뉴 영역
// =============================================================================
class _HighlightedMenuArea extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        // 펄싱 원
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: _AppColors.primary, width: 2),
          ),
        ),
        const SizedBox(height: 8),
        // 드롭다운 메뉴
        Container(
          width: 160,
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(14),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.15),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            children: [
              const SizedBox(height: 8),
              // 신고하기
              _MenuItem(
                icon: CupertinoIcons.exclamationmark_bubble,
                label: '신고하기 (Report)',
                iconColor: _AppColors.red500,
                textColor: _AppColors.red500,
              ),
              Container(
                height: 1,
                margin: const EdgeInsets.symmetric(vertical: 4),
                color: _AppColors.gray100,
              ),
              // 차단하기
              _MenuItem(
                icon: CupertinoIcons.nosign,
                label: '차단하기 (Block)',
                iconColor: _AppColors.textSecondary,
                textColor: _AppColors.textMain,
              ),
              // 숨기기
              _MenuItem(
                icon: CupertinoIcons.eye_slash,
                label: '숨기기 (Hide)',
                iconColor: _AppColors.textSecondary,
                textColor: _AppColors.textMain,
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ],
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color iconColor;
  final Color textColor;

  const _MenuItem({
    required this.icon,
    required this.label,
    required this.iconColor,
    required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Icon(icon, size: 18, color: iconColor),
          const SizedBox(width: 10),
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: textColor,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 플로팅 이모지
// =============================================================================
class _FloatingEmoji extends StatefulWidget {
  final String emoji;
  final Duration delay;

  const _FloatingEmoji({required this.emoji, this.delay = Duration.zero});

  @override
  State<_FloatingEmoji> createState() => _FloatingEmojiState();
}

class _FloatingEmojiState extends State<_FloatingEmoji>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(seconds: 3),
      vsync: this,
    );
    Future.delayed(widget.delay, () {
      if (mounted) _controller.repeat();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (_, child) {
        return Transform.translate(
          offset: Offset(0, 8 * (0.5 - (_controller.value - 0.5).abs())),
          child: child,
        );
      },
      child: Text(widget.emoji, style: const TextStyle(fontSize: 24)),
    );
  }
}

// =============================================================================
// 안전 카드
// =============================================================================
class _SafetyCard extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback onStart;
  final VoidCallback onBack;

  const _SafetyCard({
    required this.currentStep,
    required this.totalSteps,
    required this.onStart,
    required this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.2),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 헤더
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Expanded(
                child: Text(
                  '안전하고 깨끗한\n대나무숲 만들기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                    height: 1.3,
                    color: _AppColors.textMain,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '$currentStep/$totalSteps',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // 설명
          const Text(
            '불쾌한 글은 신고/숨김할 수 있어요.\n설레는 분위기를 해치는 글은 노출이 줄어들 수 있어요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              height: 1.6,
              color: _AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '✨ 서로 배려하는 따뜻한 공간을 만들어주세요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.primary,
            ),
          ),
          const SizedBox(height: 24),
          // 버튼
          Row(
            children: [
              // 뒤로 버튼
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onBack,
                child: Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: _AppColors.gray100,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(
                    CupertinoIcons.back,
                    color: _AppColors.textSecondary,
                    size: 22,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // 시작하기 버튼
              Expanded(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onStart,
                  child: Container(
                    height: 52,
                    decoration: BoxDecoration(
                      color: _AppColors.primary,
                      borderRadius: BorderRadius.circular(16),
                      boxShadow: [
                        BoxShadow(
                          color: _AppColors.primary.withValues(alpha: 0.3),
                          blurRadius: 16,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '시작하기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: CupertinoColors.white,
                          ),
                        ),
                        SizedBox(width: 6),
                        Icon(
                          CupertinoIcons.arrow_right,
                          size: 16,
                          color: CupertinoColors.white,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showBambooSafetyTutorial(
  BuildContext context, {
  int currentStep = 6,
  int totalSteps = 6,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => BambooSafetyTutorialOverlay(
      onStart: () => Navigator.of(context).pop(),
      onBack: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
