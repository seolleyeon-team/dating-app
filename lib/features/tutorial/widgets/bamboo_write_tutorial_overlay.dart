// =============================================================================
// 대나무숲 글쓰기 튜토리얼 오버레이
// 경로: lib/features/tutorial/widgets/bamboo_write_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => BambooWriteTutorialOverlay(
//     onClose: () => Navigator.pop(context),
//     currentStep: 4,
//     totalSteps: 6,
//   ),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF43F85);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink100 = Color(0xFFFCE7F3);
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class BambooWriteTutorialOverlay extends StatefulWidget {
  final VoidCallback onClose;
  final int currentStep;
  final int totalSteps;

  const BambooWriteTutorialOverlay({
    super.key,
    required this.onClose,
    this.currentStep = 4,
    this.totalSteps = 6,
  });

  @override
  State<BambooWriteTutorialOverlay> createState() =>
      _BambooWriteTutorialOverlayState();
}

class _BambooWriteTutorialOverlayState extends State<BambooWriteTutorialOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.15),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _fadeAnimation,
      child: Container(
        color: const Color(0x99000000),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
          child: Stack(
            alignment: Alignment.center,
            children: [
              // 글쓰기 모달
              SlideTransition(
                position: _slideAnimation,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Transform.translate(
                    offset: const Offset(0, -40),
                    child: const _WriteModal(),
                  ),
                ),
              ),
              // 하단 설명
              Positioned(
                bottom: 180,
                left: 32,
                right: 32,
                child: _TutorialInfo(
                  currentStep: widget.currentStep,
                  totalSteps: widget.totalSteps,
                ),
              ),
              // 하단 우측 FAB 하이라이트
              Positioned(
                bottom: 100,
                right: 24,
                child: _HighlightedFAB(onTap: widget.onClose),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 글쓰기 모달
// =============================================================================
class _WriteModal extends StatelessWidget {
  const _WriteModal();

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
            children: [
              const Icon(
                CupertinoIcons.xmark,
                color: _AppColors.textMain,
                size: 22,
              ),
              const Text(
                '대나무숲 글쓰기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
              Text(
                '임시저장',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.textSecondary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // 태그 섹션
          const Text(
            '어떤 마음인가요?',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _TagChip(label: '#두근두근', isSelected: true),
              _TagChip(label: '#첫미팅', isSelected: false),
              _TagChip(label: '#짝사랑', isSelected: false),
            ],
          ),
          const SizedBox(height: 20),
          // 입력 영역
          Container(
            height: 120,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: _AppColors.gray50,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: _AppColors.gray100),
            ),
            child: Stack(
              children: [
                const Text(
                  '솔직한 마음을 익명으로 남겨보세요...\n아무도 모를 거예요.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    color: _AppColors.gray400,
                  ),
                ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            CupertinoIcons.lock_fill,
                            size: 14,
                            color: _AppColors.gray400,
                          ),
                          const SizedBox(width: 4),
                          const Text(
                            '익명 보장',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              color: _AppColors.gray400,
                            ),
                          ),
                        ],
                      ),
                      const Text(
                        '0/300자',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          color: _AppColors.gray400,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // 등록 버튼
          Container(
            width: double.infinity,
            height: 52,
            decoration: BoxDecoration(
              color: _AppColors.primary,
              borderRadius: BorderRadius.circular(14),
              boxShadow: [
                BoxShadow(
                  color: _AppColors.pink100,
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '등록하기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: CupertinoColors.white,
                  ),
                ),
                SizedBox(width: 6),
                Icon(
                  CupertinoIcons.paperplane_fill,
                  size: 16,
                  color: CupertinoColors.white,
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
// 태그 칩
// =============================================================================
class _TagChip extends StatelessWidget {
  final String label;
  final bool isSelected;

  const _TagChip({required this.label, required this.isSelected});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: isSelected ? _AppColors.primary : _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: isSelected ? null : Border.all(color: _AppColors.gray200),
        boxShadow: isSelected
            ? [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
              ]
            : null,
      ),
      child: Text(
        label,
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 14,
          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
          color: isSelected ? CupertinoColors.white : _AppColors.textSecondary,
        ),
      ),
    );
  }
}

// =============================================================================
// 튜토리얼 안내
// =============================================================================
class _TutorialInfo extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _TutorialInfo({required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Text(
          '글쓰기',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: CupertinoColors.white,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '익명으로 글을 쓸 수 있어요.\n개인정보(연락처/실명)는 올리지 마세요.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            height: 1.5,
            color: CupertinoColors.white.withValues(alpha: 0.8),
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Text(
            '$currentStep / $totalSteps',
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              letterSpacing: 1,
              color: CupertinoColors.white,
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 하이라이트 FAB
// =============================================================================
class _HighlightedFAB extends StatefulWidget {
  final VoidCallback onTap;

  const _HighlightedFAB({required this.onTap});

  @override
  State<_HighlightedFAB> createState() => _HighlightedFABState();
}

class _HighlightedFABState extends State<_HighlightedFAB>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.mediumImpact();
        widget.onTap();
      },
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 글로우 효과
          AnimatedBuilder(
            animation: _pulseController,
            builder: (_, __) {
              return Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _AppColors.primary.withValues(
                    alpha: 0.3 * (1 - _pulseController.value),
                  ),
                ),
              );
            },
          ),
          // 버튼
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: _AppColors.primary,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.4),
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: const Icon(
              CupertinoIcons.pencil,
              color: CupertinoColors.white,
              size: 24,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showBambooWriteTutorial(
  BuildContext context, {
  int currentStep = 4,
  int totalSteps = 6,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => BambooWriteTutorialOverlay(
      onClose: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
