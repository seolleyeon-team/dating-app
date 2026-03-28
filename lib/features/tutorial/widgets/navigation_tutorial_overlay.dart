// =============================================================================
// 하단 탭 네비게이션 튜토리얼 오버레이
// 경로: lib/features/tutorial/widgets/navigation_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => NavigationTutorialOverlay(
//     onContinue: () => Navigator.pop(context),
//     currentStep: 2,
//     totalSteps: 16,
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
  static const Color primary = Color(0xFFFF4E7E);
  static const Color overlayDark = Color(0xB3000000);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
}

// =============================================================================
// 탭 아이템 모델
// =============================================================================
class _TabItem {
  final IconData icon;
  final String label;
  final bool isActive;

  const _TabItem({
    required this.icon,
    required this.label,
    this.isActive = false,
  });
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class NavigationTutorialOverlay extends StatefulWidget {
  final VoidCallback onContinue;
  final int currentStep;
  final int totalSteps;

  const NavigationTutorialOverlay({
    super.key,
    required this.onContinue,
    this.currentStep = 2,
    this.totalSteps = 16,
  });

  @override
  State<NavigationTutorialOverlay> createState() =>
      _NavigationTutorialOverlayState();
}

class _NavigationTutorialOverlayState extends State<NavigationTutorialOverlay>
    with TickerProviderStateMixin {
  late List<AnimationController> _bounceControllers;

  static const List<_TabItem> _tabs = [
    _TabItem(icon: CupertinoIcons.heart_fill, label: '설레연', isActive: true),
    _TabItem(icon: CupertinoIcons.chat_bubble_fill, label: '채팅'),
    _TabItem(icon: CupertinoIcons.calendar, label: '이벤트'),
    _TabItem(icon: CupertinoIcons.tree, label: '대나무숲'),
    _TabItem(icon: CupertinoIcons.person_fill, label: '내 페이지'),
  ];

  @override
  void initState() {
    super.initState();
    _bounceControllers = List.generate(
      _tabs.length,
      (index) => AnimationController(
        duration: const Duration(milliseconds: 1000),
        vsync: this,
      ),
    );

    // 순차적 바운스 시작
    for (var i = 0; i < _bounceControllers.length; i++) {
      Future.delayed(Duration(milliseconds: i * 200), () {
        if (mounted) {
          _bounceControllers[i].repeat(reverse: true);
        }
      });
    }
  }

  @override
  void dispose() {
    for (final controller in _bounceControllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        widget.onContinue();
      },
      child: Container(
        color: _AppColors.overlayDark,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 2, sigmaY: 2),
          child: Stack(
            children: [
              // 중앙 설명
              Positioned(
                left: 24,
                right: 24,
                bottom: 200,
                child: Column(
                  children: [
                    // 페이지 표시
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: CupertinoColors.white.withValues(alpha: 0.1),
                        ),
                      ),
                      child: Text(
                        'Page ${widget.currentStep} of ${widget.totalSteps}',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 10,
                          color: CupertinoColors.white,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '어디로든 빠르게 이동해요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '하단 탭을 눌러 원하는 메뉴로 바로 이동해보세요.',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        color: CupertinoColors.white.withValues(alpha: 0.8),
                      ),
                    ),
                    const SizedBox(height: 24),
                    // 탭 라벨 표시
                    _TabLabels(
                      tabs: _tabs,
                      bounceControllers: _bounceControllers,
                    ),
                  ],
                ),
              ),
              // 하단 탭바
              Positioned(
                left: 16,
                right: 16,
                bottom: bottomPadding + 32,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(28),
                    boxShadow: [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.12),
                        blurRadius: 30,
                        offset: const Offset(0, 8),
                      ),
                    ],
                    border: Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      width: 4,
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: _tabs.map((tab) {
                      return _TabButton(
                        icon: tab.icon,
                        label: tab.label,
                        isActive: tab.isActive,
                      );
                    }).toList(),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 탭 라벨 (바운스 애니메이션)
// =============================================================================
class _TabLabels extends StatelessWidget {
  final List<_TabItem> tabs;
  final List<AnimationController> bounceControllers;

  const _TabLabels({required this.tabs, required this.bounceControllers});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 48,
      child: Stack(
        children: List.generate(tabs.length, (index) {
          final tab = tabs[index];
          final isOddRow = index % 2 == 1;
          final leftPosition = (index / (tabs.length - 1)) * 0.85;

          return Positioned(
            left: MediaQuery.of(context).size.width * leftPosition * 0.7,
            top: isOddRow ? 0 : 20,
            child: AnimatedBuilder(
              animation: bounceControllers[index],
              builder: (_, child) {
                return Transform.translate(
                  offset: Offset(0, -8 * bounceControllers[index].value),
                  child: child,
                );
              },
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: tab.isActive
                          ? _AppColors.primary
                          : CupertinoColors.white,
                      borderRadius: BorderRadius.circular(8),
                      boxShadow: [
                        BoxShadow(
                          color: CupertinoColors.black.withValues(alpha: 0.15),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Text(
                      tab.label,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 10,
                        fontWeight: FontWeight.w500,
                        color: tab.isActive
                            ? CupertinoColors.white
                            : _AppColors.textMain,
                      ),
                    ),
                  ),
                  CustomPaint(
                    size: const Size(8, 6),
                    painter: _TrianglePainter(
                      color: tab.isActive
                          ? _AppColors.primary
                          : CupertinoColors.white,
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
      ),
    );
  }
}

// =============================================================================
// 삼각형 페인터
// =============================================================================
class _TrianglePainter extends CustomPainter {
  final Color color;

  _TrianglePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final path = Path()
      ..moveTo(size.width / 2, size.height)
      ..lineTo(0, 0)
      ..lineTo(size.width, 0)
      ..close();
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _TrianglePainter oldDelegate) =>
      color != oldDelegate.color;
}

// =============================================================================
// 탭 버튼
// =============================================================================
class _TabButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;

  const _TabButton({
    required this.icon,
    required this.label,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          icon,
          size: 24,
          color: isActive ? _AppColors.primary : _AppColors.gray400,
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 10,
            fontWeight: FontWeight.w500,
            color: isActive ? _AppColors.primary : _AppColors.gray500,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showNavigationTutorial(
  BuildContext context, {
  int currentStep = 2,
  int totalSteps = 16,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => NavigationTutorialOverlay(
      onContinue: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
