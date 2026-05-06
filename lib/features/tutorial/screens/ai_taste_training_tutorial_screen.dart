import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../matching/screens/mystery_card_screen.dart';

class AiTasteTrainingTutorialScreen extends StatefulWidget {
  const AiTasteTrainingTutorialScreen({super.key});

  @override
  State<AiTasteTrainingTutorialScreen> createState() =>
      _AiTasteTrainingTutorialScreenState();
}

class _AiTasteTrainingTutorialScreenState
    extends State<AiTasteTrainingTutorialScreen>
    with TickerProviderStateMixin {
  static const _sampleImageAsset = 'aiprofile.png';

  late final AnimationController _entryController;
  late final AnimationController _guideController;
  late final AnimationController _glowController;
  late final AnimationController _rippleController;

  @override
  void initState() {
    super.initState();
    _entryController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _guideController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat(reverse: true);
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);
    _rippleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3000),
    )..repeat();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _entryController.forward();
    });
  }

  @override
  void dispose() {
    _entryController.dispose();
    _guideController.dispose();
    _glowController.dispose();
    _rippleController.dispose();
    super.dispose();
  }

  void _goNext() {
    HapticFeedback.mediumImpact();
    Navigator.of(context).pushNamed(RouteNames.todaysMatchTutorial);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final fade = CurvedAnimation(
      parent: _entryController,
      curve: Curves.easeOutCubic,
    );

    return CupertinoPageScaffold(
      child: Stack(
        children: [
          const IgnorePointer(
            child: MysteryCardScreen(notificationCount: 1, remainingMatches: 2),
          ),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 1.6, sigmaY: 1.6),
              child: Container(
                color: CupertinoColors.black.withValues(alpha: 0.52),
              ),
            ),
          ),
          SafeArea(
            child: Stack(
              children: [
                FadeTransition(
                  opacity: fade,
                  child: const _AlignedAiTasteButtonOverlay(),
                ),
                Padding(
                  padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPadding + 24),
                  child: Column(
                    children: [
                      const Spacer(),
                      FadeTransition(
                        opacity: fade,
                        child: Column(
                          children: [
                            const Text(
                              'AI에게 내 취향을 알려주세요',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                                color: CupertinoColors.white,
                                height: 1.3,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              '왼쪽으로 스와이프해 호감,\n오른쪽으로 스와이프해 비호감을 표시하세요.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                                color: CupertinoColors.white.withValues(
                                  alpha: 0.86,
                                ),
                                height: 1.6,
                              ),
                            ),
                            const SizedBox(height: 26),
                            SizedBox(
                              width: 260,
                              height: 290,
                              child: AnimatedBuilder(
                                animation: _guideController,
                                builder: (context, _) {
                                  final swing =
                                      (_guideController.value - 0.5) * 56;
                                  return Stack(
                                    alignment: Alignment.center,
                                    clipBehavior: Clip.none,
                                    children: [
                                      Transform.translate(
                                        offset: Offset(swing * 0.7, 18),
                                        child: Transform.rotate(
                                          angle: swing / 320,
                                          child: _AiPhotoCard(
                                            imageAssetPath: _sampleImageAsset,
                                          ),
                                        ),
                                      ),
                                      Positioned(
                                        left: 12 + swing,
                                        top: 26,
                                        child: const Icon(
                                          CupertinoIcons.heart_fill,
                                          color: Color(0xFFFF6B95),
                                          size: 30,
                                        ),
                                      ),
                                      Positioned(
                                        right: 12 - swing,
                                        top: 26,
                                        child: const Icon(
                                          CupertinoIcons.xmark_circle_fill,
                                          color: Color(0xFFFFFFFF),
                                          size: 30,
                                        ),
                                      ),
                                      Positioned(
                                        top: 0,
                                        child: Transform.translate(
                                          offset: Offset(swing, 0),
                                          child: Container(
                                            width: 66,
                                            height: 66,
                                            decoration: BoxDecoration(
                                              color: CupertinoColors.white
                                                  .withValues(alpha: 0.16),
                                              shape: BoxShape.circle,
                                              border: Border.all(
                                                color: CupertinoColors.white,
                                                width: 1.6,
                                              ),
                                            ),
                                            child: const Icon(
                                              Icons.pan_tool_rounded,
                                              color: CupertinoColors.white,
                                              size: 30,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Spacer(),
                      FadeTransition(
                        opacity: fade,
                        child: CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: _goNext,
                          child: Container(
                            width: double.infinity,
                            height: 56,
                            decoration: BoxDecoration(
                              color: CupertinoColors.white,
                              borderRadius: BorderRadius.circular(18),
                            ),
                            child: const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(
                                  '다음',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 17,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF211A21),
                                  ),
                                ),
                                SizedBox(width: 8),
                                Icon(
                                  CupertinoIcons.arrow_right,
                                  size: 18,
                                  color: Color(0xFF211A21),
                                ),
                              ],
                            ),
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

class _RipplePainter extends CustomPainter {
  final double progress;

  _RipplePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width * 0.9;

    for (int i = 0; i < 2; i++) {
      final phase = (progress + i * 0.5) % 1.0;
      final radius = maxRadius * phase;
      final opacity = (1.0 - phase).clamp(0.0, 0.6);

      final paint = Paint()
        ..color = const Color(0xFFFF4D88).withValues(alpha: opacity * 0.5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0 * (1.0 - phase);

      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(_RipplePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

class _AlignedAiTasteButtonOverlay extends StatelessWidget {
  const _AlignedAiTasteButtonOverlay();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 32, 8),
      child: Row(
        children: [
          const Opacity(opacity: 0, child: _HeaderBrandPlaceholder()),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              mainAxisSize: MainAxisSize.min,
              children: const [
                _AiTasteHighlightButton(),
                SizedBox(width: 8),
                Opacity(
                  opacity: 0,
                  child: SizedBox(
                    width: 24,
                    height: 24,
                    child: Icon(CupertinoIcons.bell, size: 24),
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

class _HeaderBrandPlaceholder extends StatelessWidget {
  const _HeaderBrandPlaceholder();

  @override
  Widget build(BuildContext context) {
    return const Row(
      children: [
        Icon(CupertinoIcons.heart_fill, size: 24),
        SizedBox(width: 8),
        Text(
          '설레연',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 21,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
      ],
    );
  }
}

class _AiTasteHighlightButton extends StatelessWidget {
  const _AiTasteHighlightButton();

  @override
  Widget build(BuildContext context) {
    final state = context
        .findAncestorStateOfType<_AiTasteTrainingTutorialScreenState>();
    if (state == null) {
      return const SizedBox.shrink();
    }

    return Stack(
      alignment: Alignment.center,
      clipBehavior: Clip.none,
      children: [
        Positioned.fill(
          child: IgnorePointer(
            child: OverflowBox(
              minWidth: 0,
              minHeight: 0,
              maxWidth: 220,
              maxHeight: 100,
              alignment: Alignment.center,
              child: AnimatedBuilder(
                animation: state._rippleController,
                builder: (context, _) {
                  return CustomPaint(
                    size: const Size(220, 100),
                    painter: _RipplePainter(
                      progress: state._rippleController.value,
                    ),
                  );
                },
              ),
            ),
          ),
        ),
        AnimatedBuilder(
          animation: state._glowController,
          builder: (context, _) {
            final glowValue = 0.24 + 0.34 * state._glowController.value;
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFFFDF2F8),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFFBCFE8), width: 1),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFFF4D88).withValues(alpha: glowValue),
                    blurRadius: 15 + 10 * state._glowController.value,
                    spreadRadius: 1.2 + 1.8 * state._glowController.value,
                  ),
                ],
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    CupertinoIcons.sparkles,
                    size: 16,
                    color: Color(0xFFFF4D88),
                  ),
                  SizedBox(width: 4),
                  Text(
                    'AI에게 내 취향 알려주기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFF1F2937),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ],
    );
  }
}

class _AiPhotoCard extends StatelessWidget {
  final String imageAssetPath;

  const _AiPhotoCard({required this.imageAssetPath});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 190,
      height: 236,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        boxShadow: const [
          BoxShadow(
            color: Color(0x26000000),
            blurRadius: 24,
            offset: Offset(0, 14),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.asset(
            imageAssetPath,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0xFFF7D7E3), Color(0xFFE6B9CA)],
                ),
              ),
            ),
          ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0x00000000), Color(0xAA151015)],
                stops: [0.45, 1.0],
              ),
            ),
          ),
          const Positioned(
            left: 18,
            right: 18,
            bottom: 18,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'AI 프로필 예시',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFFFFD7E4),
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  '스와이프로 취향을 학습해요',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: CupertinoColors.white,
                    height: 1.25,
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
