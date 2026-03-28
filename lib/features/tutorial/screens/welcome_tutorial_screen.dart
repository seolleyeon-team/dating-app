// =============================================================================
// 환영 튜토리얼 화면 (온보딩 첫 화면)
// 경로: lib/features/tutorial/screens/welcome_tutorial_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/tutorial/screens/welcome_tutorial_screen.dart';
// ...
// home: const WelcomeTutorialScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5A78);
  static const Color backgroundLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color purple300 = Color(0xFFC4B5FD);
  static const Color pink200 = Color(0xFFFBCFE8);
}

// =============================================================================
// 메인 화면
// =============================================================================
class WelcomeTutorialScreen extends StatefulWidget {
  final VoidCallback? onNext;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;

  const WelcomeTutorialScreen({
    super.key,
    this.onNext,
    this.onSkip,
    this.currentStep = 1,
    this.totalSteps = 3,
  });

  @override
  State<WelcomeTutorialScreen> createState() => _WelcomeTutorialScreenState();
}

class _WelcomeTutorialScreenState extends State<WelcomeTutorialScreen>
    with TickerProviderStateMixin {
  late AnimationController _bounceController;
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _bounceController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);

    _pulseController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _bounceController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _onNext() {
    HapticFeedback.mediumImpact();
    if (widget.onNext != null) {
      widget.onNext!.call();
    } else {
      Navigator.of(context).pushNamed(RouteNames.tutorial);
    }
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
          // 라벤더 글로우 배경
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: MediaQuery.of(context).size.height * 0.6,
            child: Container(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: const Alignment(0, -0.3),
                  radius: 1.2,
                  colors: [
                    const Color(0xFFEBD7FF).withValues(alpha: 0.6),
                    _AppColors.backgroundLight.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // Skip 버튼
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 8, 24, 0),
                  child: Align(
                    alignment: Alignment.topRight,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: _onSkip,
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
                  ),
                ),
                // 중앙 콘텐츠
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // 아이콘
                      _HeartIcon(
                        bounceController: _bounceController,
                        pulseController: _pulseController,
                      ),
                      const SizedBox(height: 40),
                      // 타이틀
                      RichText(
                        textAlign: TextAlign.center,
                        text: const TextSpan(
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            height: 1.3,
                            color: _AppColors.textMain,
                          ),
                          children: [
                            TextSpan(text: '설레연에 오신 걸\n'),
                            TextSpan(
                              text: '환영해요',
                              style: TextStyle(color: _AppColors.primary),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                      // 서브타이틀
                      const Text(
                        '연애를 못 하는 이유는\n개인 문제가 아니라, 환경 문제.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          height: 1.5,
                          color: _AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                // 하단 영역
                Padding(
                  padding: EdgeInsets.fromLTRB(32, 0, 32, bottomPadding + 24),
                  child: Column(
                    children: [
                      // 다음 버튼
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _onNext,
                        child: Container(
                          width: double.infinity,
                          height: 56,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(18),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.3,
                                ),
                                blurRadius: 20,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                '다음',
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
// 하트 아이콘
// =============================================================================
class _HeartIcon extends StatelessWidget {
  final AnimationController bounceController;
  final AnimationController pulseController;

  const _HeartIcon({
    required this.bounceController,
    required this.pulseController,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 150,
      height: 150,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 글로우 효과
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _AppColors.pink100.withValues(alpha: 0.6),
            ),
          ),
          // 메인 아이콘 컨테이너
          Container(
            width: 112,
            height: 112,
            decoration: BoxDecoration(
              color: CupertinoColors.white,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.15),
                  blurRadius: 40,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: const Icon(
              CupertinoIcons.heart_fill,
              size: 48,
              color: _AppColors.primary,
            ),
          ),
          // 스파클 아이콘 (우상단)
          Positioned(
            top: 0,
            right: 10,
            child: AnimatedBuilder(
              animation: bounceController,
              builder: (_, child) {
                return Transform.translate(
                  offset: Offset(0, -5 * bounceController.value),
                  child: child,
                );
              },
              child: const Icon(
                CupertinoIcons.sparkles,
                size: 20,
                color: _AppColors.purple300,
              ),
            ),
          ),
          // 작은 하트 (좌하단)
          Positioned(
            bottom: 20,
            left: 5,
            child: AnimatedBuilder(
              animation: pulseController,
              builder: (_, child) {
                return Opacity(
                  opacity: 0.5 + (0.5 * pulseController.value),
                  child: child,
                );
              },
              child: const Icon(
                CupertinoIcons.heart_fill,
                size: 16,
                color: _AppColors.pink200,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
