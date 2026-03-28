// =============================================================================
// 카카오 인증 로딩 화면
// 경로: lib/features/auth/screens/kakao_auth_loading_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const KakaoAuthLoadingScreen()),
// );
// =============================================================================

import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEE2B5B);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1B0D11);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color kakao = Color(0xFFFEE500);
  static const Color kakaoLabel = Color(0xFF191919);
}

// =============================================================================
// 메인 화면
// =============================================================================
class KakaoAuthLoadingScreen extends StatefulWidget {
  final VoidCallback? onCancel;

  const KakaoAuthLoadingScreen({super.key, this.onCancel});

  @override
  State<KakaoAuthLoadingScreen> createState() => _KakaoAuthLoadingScreenState();
}

class _KakaoAuthLoadingScreenState extends State<KakaoAuthLoadingScreen>
    with TickerProviderStateMixin {
  late AnimationController _spinController;
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _spinController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    )..repeat();
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _spinController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _onCancel() {
    HapticFeedback.lightImpact();
    widget.onCancel?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 레이어 (이전 화면 흐림)
          const _BlurredBackground(),
          // 오버레이 스크림
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
              child: Container(
                color: _AppColors.surfaceLight.withValues(alpha: 0.4),
              ),
            ),
          ),
          // 로딩 콘텐츠
          SafeArea(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // 스피너
                  _Spinner(
                    spinController: _spinController,
                    pulseController: _pulseController,
                  ),
                  const SizedBox(height: 32),
                  // 텍스트
                  const Text(
                    '인증 중...',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.3,
                      color: _AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    '잠시만 기다려주세요',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 취소 버튼
          Positioned(
            left: 0,
            right: 0,
            bottom: bottomPadding + 48,
            child: Center(
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: _onCancel,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.surfaceLight.withValues(alpha: 0.8),
                    borderRadius: BorderRadius.circular(24),
                    boxShadow: [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.05),
                        blurRadius: 8,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        CupertinoIcons.xmark,
                        size: 18,
                        color: _AppColors.gray500,
                      ),
                      SizedBox(width: 8),
                      Text(
                        '취소',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: _AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 흐린 배경
// =============================================================================
class _BlurredBackground extends StatelessWidget {
  const _BlurredBackground();

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: Opacity(
        opacity: 0.6,
        child: ImageFiltered(
          imageFilter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
          child: IgnorePointer(
            child: Column(
              children: [
                const SizedBox(height: 80),
                // 로고
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        _AppColors.primary,
                        _AppColors.primary.withValues(alpha: 0.6),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: _AppColors.primary.withValues(alpha: 0.2),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: const Icon(
                    CupertinoIcons.heart_fill,
                    size: 36,
                    color: CupertinoColors.white,
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Seolleyeon',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Premium dating for authentic connections.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    color: _AppColors.gray500,
                  ),
                ),
                const Spacer(),
                // 카카오 버튼
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Container(
                    width: double.infinity,
                    height: 56,
                    decoration: BoxDecoration(
                      color: _AppColors.kakao,
                      borderRadius: BorderRadius.circular(28),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          CupertinoIcons.chat_bubble_fill,
                          size: 20,
                          color: _AppColors.kakaoLabel,
                        ),
                        SizedBox(width: 12),
                        Text(
                          'Kakao로 시작하기',
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
                const SizedBox(height: 16),
                // 하단 링크
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '이메일로 로그인',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        color: _AppColors.gray400,
                      ),
                    ),
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 12),
                      width: 1,
                      height: 16,
                      color: _AppColors.gray300,
                    ),
                    Text(
                      '문의하기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        color: _AppColors.gray400,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 48),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 스피너
// =============================================================================
class _Spinner extends StatelessWidget {
  final AnimationController spinController;
  final AnimationController pulseController;

  const _Spinner({required this.spinController, required this.pulseController});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 64,
      height: 64,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 스피너
          AnimatedBuilder(
            animation: spinController,
            builder: (_, __) {
              return CustomPaint(
                size: const Size(64, 64),
                painter: _SpinnerPainter(spinController.value),
              );
            },
          ),
          // 중앙 펄스 도트
          AnimatedBuilder(
            animation: pulseController,
            builder: (_, child) {
              final scale = 1.0 + (0.3 * pulseController.value);
              return Transform.scale(scale: scale, child: child);
            },
            child: Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: _AppColors.primary,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 스피너 페인터
// =============================================================================
class _SpinnerPainter extends CustomPainter {
  final double progress;

  _SpinnerPainter(this.progress);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 4;

    // 트랙
    final trackPaint = Paint()
      ..color = _AppColors.primary.withValues(alpha: 0.2)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawCircle(center, radius, trackPaint);

    // 프로그레스
    final progressPaint = Paint()
      ..color = _AppColors.primary
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final startAngle = -math.pi / 2 + (progress * 2 * math.pi);
    final sweepAngle = math.pi * 0.75;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepAngle,
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _SpinnerPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
