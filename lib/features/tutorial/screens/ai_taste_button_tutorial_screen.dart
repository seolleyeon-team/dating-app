// =============================================================================
// AI 취향 버튼 튜토리얼 화면
// 경로: lib/features/tutorial/screens/ai_taste_button_tutorial_screen.dart
//
// 디자인: 메인 화면 백그라운드 + AI 취향 버튼 하이라이트 + 튜토리얼 카드
// 네비게이션: "AI에게 내 취향 알려주기" 버튼 → aiTasteTrainingTutorial
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수 (mystery_card_screen 톤 맞춤)
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D88);
  static const Color backgroundLight = Color(0xFFFFF5F8);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF111827);
  static const Color textSub = Color(0xFF6B7280);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink500 = Color(0xFFEC4899);
}

// =============================================================================
// 메인 화면
// =============================================================================
class AiTasteButtonTutorialScreen extends StatefulWidget {
  const AiTasteButtonTutorialScreen({super.key});

  @override
  State<AiTasteButtonTutorialScreen> createState() =>
      _AiTasteButtonTutorialScreenState();
}

class _AiTasteButtonTutorialScreenState
    extends State<AiTasteButtonTutorialScreen>
    with TickerProviderStateMixin {
  // 진입 페이드+슬라이드
  late AnimationController _entryController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  // 글로우 펄스
  late AnimationController _glowController;

  // 동심원 리플
  late AnimationController _rippleController;

  @override
  void initState() {
    super.initState();

    // 1) 진입 애니메이션
    _entryController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _entryController, curve: Curves.easeOut));
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.05),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _entryController, curve: Curves.easeOut));

    // 2) 글로우 펄스 (2초 주기)
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);

    // 3) 리플 (3초 주기, 반복)
    _rippleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3000),
    )..repeat();

    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _entryController.forward();
    });
  }

  @override
  void dispose() {
    _entryController.dispose();
    _glowController.dispose();
    _rippleController.dispose();
    super.dispose();
  }

  void _onButtonPressed() {
    // 기존 "다음" 버튼의 네비게이션 로직
    Navigator.of(context).pushNamed(RouteNames.aiTasteTrainingTutorial);
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 1. 백그라운드 (가상 메인 화면)
          const _FakeMainScreen(),

          // 2. 어두운 오버레이
          Positioned.fill(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 2, sigmaY: 2),
                child: Container(
                  color: CupertinoColors.black.withValues(alpha: 0.75),
                ),
              ),
            ),
          ),

          // 3. 하이라이트된 버튼 (원본 위치에 겹침) + 리플 + 글로우
          SafeArea(
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned(
                  top: 16,
                  right: 60,
                  child: FadeTransition(
                    opacity: _fadeAnimation,
                    child: _AnimatedHighlightButton(
                      glowController: _glowController,
                      rippleController: _rippleController,
                      onPressed: _onButtonPressed,
                    ),
                  ),
                ),
              ],
            ),
          ),

          // 4. 튜토리얼 컨텐츠 (카드 + 화살표 + 페이지 인디케이터)
          Center(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: SlideTransition(
                position: _slideAnimation,
                child: _TutorialContent(onButtonPressed: _onButtonPressed),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 리플 페인터 (동심원 파동)
// =============================================================================
class _RipplePainter extends CustomPainter {
  final double progress; // 0.0 ~ 1.0

  _RipplePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width * 0.9;

    // 2개의 링을 시간차로 그리기
    for (int i = 0; i < 2; i++) {
      final phase = (progress + i * 0.5) % 1.0;
      final radius = maxRadius * phase;
      final opacity = (1.0 - phase).clamp(0.0, 0.6);

      final paint = Paint()
        ..color = _AppColors.primary.withValues(alpha: opacity * 0.5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0 * (1.0 - phase);

      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(_RipplePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

// =============================================================================
// 애니메이션 하이라이트 버튼 (글로우 + 리플 + 터치 가능)
// =============================================================================
class _AnimatedHighlightButton extends StatelessWidget {
  final AnimationController glowController;
  final AnimationController rippleController;
  final VoidCallback onPressed;

  const _AnimatedHighlightButton({
    required this.glowController,
    required this.rippleController,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      clipBehavior: Clip.none,
      children: [
        // 리플 레이어
        Positioned(
          child: IgnorePointer(
            child: AnimatedBuilder(
              animation: rippleController,
              builder: (context, child) {
                return CustomPaint(
                  size: const Size(220, 100),
                  painter: _RipplePainter(progress: rippleController.value),
                );
              },
            ),
          ),
        ),
        // 글로우 + 버튼
        AnimatedBuilder(
          animation: glowController,
          builder: (context, child) {
            final glowValue = 0.3 + 0.4 * glowController.value;
            return CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: onPressed,
              child: Container(
                constraints: BoxConstraints(
                  maxWidth: MediaQuery.of(context).size.width - 180,
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.pink50,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: _AppColors.primary.withValues(alpha: 0.8),
                    width: 1.5,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: glowValue),
                      blurRadius: 15 + 10 * glowController.value,
                      spreadRadius: 2 * glowController.value,
                    ),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: const [
                    Icon(
                      CupertinoIcons.sparkles,
                      size: 16,
                      color: _AppColors.pink500,
                    ),
                    SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        'AI에게 내 취향 알려주기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textMain,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

// =============================================================================
// 튜토리얼 컨텐츠 (카드, 화살표, 페이지 인디케이터)
// =============================================================================
class _TutorialContent extends StatelessWidget {
  final VoidCallback onButtonPressed;

  const _TutorialContent({required this.onButtonPressed});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // 화살표 (SVG 대체 - CustomPaint)
        CustomPaint(size: const Size(80, 80), painter: _ArrowPainter()),
        const SizedBox(height: 20),

        // 카드 (mystery_card_screen 스타일 맞춤)
        Container(
          width: 320,
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: CupertinoColors.white.withValues(alpha: 0.3),
            ),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.15),
                blurRadius: 40,
                offset: const Offset(0, 10),
              ),
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.08),
                blurRadius: 60,
                offset: const Offset(0, 20),
              ),
            ],
          ),
          child: Column(
            children: [
              // 아이콘
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [_AppColors.pink100, _AppColors.pink50],
                  ),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.15),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.psychology_rounded,
                  color: _AppColors.primary,
                  size: 30,
                ),
              ),
              const SizedBox(height: 20),

              // 타이틀
              const Text(
                'AI에게 당신의 취향을\n학습시켜 보세요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                  height: 1.35,
                  letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 10),

              // 보조 설명
              const Text(
                '위 버튼을 눌러 AI 취향 학습을 시작하면\n매칭 추천이 더욱 정확해집니다.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w400,
                  color: _AppColors.textSub,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 24),

              // 인라인 CTA 버튼
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onButtonPressed,
                child: Container(
                  width: double.infinity,
                  height: 48,
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(24),
                    boxShadow: [
                      BoxShadow(
                        color: _AppColors.primary.withValues(alpha: 0.35),
                        blurRadius: 16,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Text(
                      '시작하기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 32),

        // 페이지 인디케이터
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _Dot(isActive: true),
            const SizedBox(width: 8),
            _Dot(isActive: false),
            const SizedBox(width: 8),
            _Dot(isActive: false),
          ],
        ),
      ],
    );
  }
}

// =============================================================================
// 페이지 인디케이터 점
// =============================================================================
class _Dot extends StatelessWidget {
  final bool isActive;

  const _Dot({required this.isActive});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: isActive ? 20 : 6,
      height: 6,
      decoration: BoxDecoration(
        color: isActive
            ? CupertinoColors.white
            : CupertinoColors.white.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(3),
      ),
    );
  }
}

// =============================================================================
// 화살표 Painter
// =============================================================================
class _ArrowPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color =
          const Color(0xFFF9A8D4) // pink-300
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final path = Path();
    // 커브 그리기 (우측 상단 -> 좌측 하단 방향)
    path.moveTo(size.width, 0);
    path.quadraticBezierTo(
      size.width * 0.8,
      size.height * 0.5,
      size.width * 0.2,
      size.height,
    );

    // 화살표 머리 (좌측 하단 끝점 기준)
    final endX = size.width * 0.2;
    final endY = size.height;

    path.moveTo(endX, endY);
    path.lineTo(endX + 10, endY - 10);

    path.moveTo(endX, endY);
    path.lineTo(endX + 15, endY - 2);

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// =============================================================================
// 가짜 메인 화면 (배경용)
// =============================================================================
class _FakeMainScreen extends StatelessWidget {
  const _FakeMainScreen();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Column(
        children: [
          // 헤더
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: const [
                      Icon(
                        CupertinoIcons.heart_fill,
                        color: _AppColors.primary,
                        size: 24,
                      ),
                      SizedBox(width: 8),
                      Text(
                        '설레연',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 21,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                          letterSpacing: -0.3,
                        ),
                      ),
                    ],
                  ),
                  Flexible(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // 버튼 자리 (실제로는 비워둠, 오버레이가 덮음)
                        Flexible(
                          child: Opacity(
                            opacity: 0.3,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: _AppColors.pink50,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: _AppColors.pink100),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: const [
                                  Icon(
                                    CupertinoIcons.sparkles,
                                    size: 16,
                                    color: _AppColors.pink500,
                                  ),
                                  SizedBox(width: 6),
                                  Flexible(
                                    child: Text(
                                      'AI에게 내 취향 알려주기',
                                      style: TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontSize: 12,
                                        fontWeight: FontWeight.w500,
                                        color: _AppColors.textMain,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Icon(
                          CupertinoIcons.bell,
                          size: 24,
                          color: _AppColors.gray400,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),

          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Column(
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFEDE9FE), // purple-100
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'AI CURATED',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF9333EA), // purple-600
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      const Text(
                        'Nov 14',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          color: _AppColors.gray400,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: const [
                      Text(
                        '오늘의 설레연',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 28,
                          fontWeight: FontWeight.bold,
                          color: _AppColors.textMain,
                        ),
                      ),
                      Icon(
                        CupertinoIcons.slider_horizontal_3,
                        color: _AppColors.gray400,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // 메인 카드 (이미지)
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                        color: _AppColors.gray100,
                        borderRadius: BorderRadius.circular(32),
                        boxShadow: [
                          BoxShadow(
                            color: CupertinoColors.black.withValues(
                              alpha: 0.08,
                            ),
                            blurRadius: 40,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(32),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            Container(color: const Color(0xFFE5E7EB)),

                            // 텍스트 정보
                            Positioned(
                              left: 24,
                              right: 24,
                              bottom: 24,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        'Ji-min',
                                        style: TextStyle(
                                          fontFamily: 'Pretendard',
                                          fontSize: 32,
                                          fontWeight: FontWeight.bold,
                                          color: _AppColors.textMain.withValues(
                                            alpha: 0.4,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 8,
                                          vertical: 2,
                                        ),
                                        decoration: BoxDecoration(
                                          color: CupertinoColors.black
                                              .withValues(alpha: 0.08),
                                          borderRadius: BorderRadius.circular(
                                            10,
                                          ),
                                        ),
                                        child: const Text(
                                          '94%',
                                          style: TextStyle(
                                            fontFamily: 'Pretendard',
                                            fontSize: 10,
                                            color: _AppColors.textSub,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 100),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
