// =============================================================================
// AI 로직 튜토리얼 화면 (AI 추천 플로우 다이어그램)
// 경로: lib/features/tutorial/screens/ai_logic_tutorial_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const AiLogicTutorialScreen()),
// );
// =============================================================================

import 'dart:math' as math;
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5C8D);
  static const Color secondary = Color(0xFF1A1C29);
  static const Color backgroundLight = Color(0xFFFFFDFE);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1A1C29);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color pinkSoft = Color(0xFFFFF0F5);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color yellow300 = Color(0xFFFCD34D);
}

// =============================================================================
// 메인 화면
// =============================================================================
class AiLogicTutorialScreen extends StatefulWidget {
  final VoidCallback? onNext;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;

  const AiLogicTutorialScreen({
    super.key,
    this.onNext,
    this.onSkip,
    this.currentStep = 2,
    this.totalSteps = 3,
  });

  @override
  State<AiLogicTutorialScreen> createState() => _AiLogicTutorialScreenState();
}

class _AiLogicTutorialScreenState extends State<AiLogicTutorialScreen>
    with TickerProviderStateMixin {
  late AnimationController _floatController;
  late AnimationController _spinController;
  late AnimationController _dashController;

  @override
  void initState() {
    super.initState();
    _floatController = AnimationController(
      duration: const Duration(seconds: 6),
      vsync: this,
    )..repeat(reverse: true);

    _spinController = AnimationController(
      duration: const Duration(seconds: 4),
      vsync: this,
    )..repeat();

    _dashController = AnimationController(
      duration: const Duration(seconds: 20),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _floatController.dispose();
    _spinController.dispose();
    _dashController.dispose();
    super.dispose();
  }

  void _onNext() {
    HapticFeedback.mediumImpact();
    widget.onNext?.call();
  }

  void _onSkip() {
    HapticFeedback.lightImpact();
    widget.onSkip?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 블러 원
          Positioned(
            top: -50,
            left: -100,
            child: Container(
              width: 500,
              height: 500,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.pink100.withValues(alpha: 0.6),
              ),
            ),
          ),
          Positioned(
            bottom: 100,
            right: -100,
            child: Container(
              width: 400,
              height: 400,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.pinkSoft.withValues(alpha: 0.6),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onSkip: _onSkip),
                // 콘텐츠
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    child: Column(
                      children: [
                        const SizedBox(height: 24),
                        // 타이틀 섹션
                        const _TitleSection(),
                        const SizedBox(height: 40),
                        // 플로우 다이어그램
                        _FlowDiagram(
                          floatController: _floatController,
                          spinController: _spinController,
                          dashController: _dashController,
                        ),
                      ],
                    ),
                  ),
                ),
                // 하단 버튼
                Padding(
                  padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 24),
                  child: Column(
                    children: [
                      // 페이지 인디케이터
                      _PageIndicator(
                        currentStep: widget.currentStep,
                        totalSteps: widget.totalSteps,
                      ),
                      const SizedBox(height: 24),
                      // 다음 버튼
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _onNext,
                        child: Container(
                          width: double.infinity,
                          height: 56,
                          decoration: BoxDecoration(
                            color: _AppColors.secondary,
                            borderRadius: BorderRadius.circular(18),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.gray200,
                                blurRadius: 20,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                '다음으로',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: CupertinoColors.white,
                                ),
                              ),
                              SizedBox(width: 8),
                              Icon(
                                CupertinoIcons.arrow_right,
                                size: 20,
                                color: CupertinoColors.white,
                              ),
                            ],
                          ),
                        ),
                      ),
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
  final VoidCallback onSkip;

  const _Header({required this.onSkip});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 로고
          const Row(
            children: [
              Icon(
                CupertinoIcons.heart_fill,
                color: _AppColors.primary,
                size: 28,
              ),
              SizedBox(width: 8),
              Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.secondary,
                ),
              ),
            ],
          ),
          // Skip 버튼
          CupertinoButton(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            onPressed: onSkip,
            child: const Text(
              'Skip',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 타이틀 섹션
// =============================================================================
class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          // AI LOGIC 배지
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: _AppColors.pinkSoft,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _AppColors.pink100),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.sparkles,
                  size: 14,
                  color: _AppColors.primary,
                ),
                SizedBox(width: 6),
                Text(
                  'AI LOGIC',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    color: _AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // 타이틀
          ShaderMask(
            shaderCallback: (bounds) => const LinearGradient(
              colors: [_AppColors.primary, Color(0xFFFF8FA3)],
            ).createShader(bounds),
            child: RichText(
              textAlign: TextAlign.center,
              text: const TextSpan(
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 28,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                ),
                children: [
                  TextSpan(
                    text: '사진 취향 + 라이프스타일의\n',
                    style: TextStyle(color: _AppColors.textMain),
                  ),
                  TextSpan(
                    text: '완벽한 조화',
                    style: TextStyle(color: CupertinoColors.white),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          // 서브타이틀
          Text(
            '데이터가 쌓일수록\n내일의 추천은 더 정확해집니다.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 15,
              fontWeight: FontWeight.w500,
              height: 1.5,
              color: _AppColors.textSecondary.withValues(alpha: 0.9),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 플로우 다이어그램
// =============================================================================
class _FlowDiagram extends StatelessWidget {
  final AnimationController floatController;
  final AnimationController spinController;
  final AnimationController dashController;

  const _FlowDiagram({
    required this.floatController,
    required this.spinController,
    required this.dashController,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 320,
      height: 400,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 연결선
          CustomPaint(
            size: const Size(320, 400),
            painter: _FlowLinePainter(dashController),
          ),
          // 상단 카드 (AI Swipe)
          Positioned(
            top: 0,
            child: AnimatedBuilder(
              animation: floatController,
              builder: (_, child) {
                return Transform.translate(
                  offset: Offset(0, -10 * floatController.value),
                  child: child,
                );
              },
              child: const _SwipeCard(),
            ),
          ),
          // 중앙 아이콘
          Positioned(
            top: 170,
            child: AnimatedBuilder(
              animation: spinController,
              builder: (_, child) {
                return Transform.rotate(
                  angle: spinController.value * 2 * math.pi,
                  child: child,
                );
              },
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight,
                  shape: BoxShape.circle,
                  border: Border.all(color: _AppColors.pink100),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.1),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Icon(
                  CupertinoIcons.gear_alt_fill,
                  size: 20,
                  color: _AppColors.primary,
                ),
              ),
            ),
          ),
          // 하단 카드 (1:1 Recommendations)
          Positioned(
            bottom: 0,
            child: AnimatedBuilder(
              animation: floatController,
              builder: (_, child) {
                // 3초 딜레이 효과
                final delayedValue = (floatController.value + 0.5) % 1.0;
                return Transform.translate(
                  offset: Offset(0, -10 * delayedValue),
                  child: child,
                );
              },
              child: const _MatchCard(),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 플로우 라인 페인터
// =============================================================================
class _FlowLinePainter extends CustomPainter {
  final Animation<double> animation;

  _FlowLinePainter(this.animation) : super(repaint: animation);

  @override
  void paint(Canvas canvas, Size size) {
    final centerX = size.width / 2;
    final startY = 100.0;
    final endY = 290.0;

    // 배경 라인
    final bgPaint = Paint()
      ..color = _AppColors.primary.withValues(alpha: 0.1)
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    canvas.drawLine(Offset(centerX, startY), Offset(centerX, endY), bgPaint);

    // 애니메이션 대시 라인
    final dashPaint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0x4DFF5C8D), _AppColors.primary, Color(0x4DFF5C8D)],
      ).createShader(Rect.fromLTRB(centerX - 2, startY, centerX + 2, endY))
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // 대시 효과
    final dashLength = 6.0;
    final gapLength = 6.0;
    final totalLength = endY - startY;
    final offset = animation.value * (dashLength + gapLength) * 50;

    for (
      double i = -offset % (dashLength + gapLength);
      i < totalLength;
      i += dashLength + gapLength
    ) {
      final start = startY + i;
      final end = (start + dashLength).clamp(startY, endY);
      if (start < endY && end > startY) {
        canvas.drawLine(
          Offset(centerX, start.clamp(startY, endY)),
          Offset(centerX, end),
          dashPaint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant _FlowLinePainter oldDelegate) => true;
}

// =============================================================================
// Swipe 카드
// =============================================================================
class _SwipeCard extends StatelessWidget {
  const _SwipeCard();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 96,
          height: 128,
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: _AppColors.pink100),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // 아바타
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  CupertinoIcons.person_fill,
                  size: 32,
                  color: _AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 12),
              // 스와이프 아이콘
              const Icon(
                CupertinoIcons.hand_draw,
                size: 24,
                color: _AppColors.secondary,
              ),
              const SizedBox(height: 8),
              // 인디케이터
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 4,
                    height: 4,
                    decoration: const BoxDecoration(
                      color: CupertinoColors.systemRed,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Container(
                    width: 4,
                    height: 4,
                    decoration: const BoxDecoration(
                      color: CupertinoColors.systemGreen,
                      shape: BoxShape.circle,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.8),
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Text(
            'AI Swipe',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: _AppColors.secondary,
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// Match 카드
// =============================================================================
class _MatchCard extends StatelessWidget {
  const _MatchCard();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 96,
          height: 128,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [_AppColors.secondary, Color(0xFF111827)],
            ),
            borderRadius: BorderRadius.circular(18),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.2),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Stack(
            children: [
              // 스파클
              const Positioned(
                top: 8,
                right: 8,
                child: Icon(
                  CupertinoIcons.sparkles,
                  size: 12,
                  color: _AppColors.yellow300,
                ),
              ),
              // 하트
              const Center(
                child: Icon(
                  CupertinoIcons.heart_fill,
                  size: 40,
                  color: CupertinoColors.white,
                ),
              ),
              // MATCH 라벨
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  decoration: BoxDecoration(
                    color: CupertinoColors.black.withValues(alpha: 0.2),
                    borderRadius: const BorderRadius.only(
                      bottomLeft: Radius.circular(18),
                      bottomRight: Radius.circular(18),
                    ),
                  ),
                  child: const Text(
                    'MATCH',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2,
                      color: CupertinoColors.white,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.8),
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Text(
            '1:1 Recommendations',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: _AppColors.secondary,
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 페이지 인디케이터
// =============================================================================
class _PageIndicator extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _PageIndicator({required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(totalSteps, (index) {
        final isActive = index + 1 == currentStep;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          width: isActive ? 32 : 8,
          height: 8,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            color: isActive ? _AppColors.primary : _AppColors.gray200,
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }
}
