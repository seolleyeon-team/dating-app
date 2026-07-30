import 'dart:math' as math;

import 'package:flutter/material.dart';

@immutable
class LeafSpec {
  const LeafSpec({
    required this.normalizedStartX,
    required this.normalizedStartY,
    required this.horizontalDrift,
    required this.swayAmplitude,
    required this.swayFrequency,
    required this.phase,
    required this.size,
    required this.baseRotation,
    required this.rotationSpeed,
    required this.flipFrequency,
    required this.color,
    required this.opacity,
    required this.fallSpeed,
    this.mirrored = false,
    this.zigzagAmplitude = 0,
    this.zigzagSegments = 0,
    this.zigzagCornerSlowdown = 0,
  });

  final double normalizedStartX;
  final double normalizedStartY;
  final double horizontalDrift;
  final double swayAmplitude;
  final double swayFrequency;
  final double phase;
  final double size;
  final double baseRotation;
  final double rotationSpeed;
  final double flipFrequency;
  final Color color;
  final double opacity;
  final double fallSpeed;
  final bool mirrored;
  final double zigzagAmplitude;
  final int zigzagSegments;
  final double zigzagCornerSlowdown;
}

class FallingLeavesOverlay extends StatefulWidget {
  const FallingLeavesOverlay({super.key, required this.isDark});

  static const Duration animationDuration = Duration(seconds: 22);
  static const double leafSizeScale = 0.84;
  static const double leafThicknessScale = 1.30;

  final bool isDark;

  @override
  State<FallingLeavesOverlay> createState() => _FallingLeavesOverlayState();
}

class _FallingLeavesOverlayState extends State<FallingLeavesOverlay>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  static const List<LeafSpec> _leaves = [
    LeafSpec(
      normalizedStartX: -0.06,
      normalizedStartY: -0.17,
      horizontalDrift: 0.34,
      swayAmplitude: 0.045,
      swayFrequency: 1.15,
      phase: 0.04,
      size: 28,
      baseRotation: -0.45,
      rotationSpeed: 8.2,
      flipFrequency: 1.05,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.72,
      zigzagAmplitude: 0.075,
      zigzagSegments: 3,
      zigzagCornerSlowdown: 0.42,
    ),
    LeafSpec(
      normalizedStartX: 0.80,
      normalizedStartY: -0.23,
      horizontalDrift: -0.24,
      swayAmplitude: 0.032,
      swayFrequency: 1.72,
      phase: 0.17,
      size: 23,
      baseRotation: 0.30,
      rotationSpeed: -12.4,
      flipFrequency: 1.38,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.78,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 0.24,
      normalizedStartY: -0.14,
      horizontalDrift: 0.27,
      swayAmplitude: 0.061,
      swayFrequency: 0.88,
      phase: 0.29,
      size: 31,
      baseRotation: 0.75,
      rotationSpeed: 14.1,
      flipFrequency: 0.82,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.74,
    ),
    LeafSpec(
      normalizedStartX: 1.08,
      normalizedStartY: -0.20,
      horizontalDrift: -0.36,
      swayAmplitude: 0.052,
      swayFrequency: 1.44,
      phase: 0.42,
      size: 26,
      baseRotation: -0.18,
      rotationSpeed: -9.7,
      flipFrequency: 1.22,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.80,
      mirrored: true,
      zigzagAmplitude: 0.068,
      zigzagSegments: 4,
      zigzagCornerSlowdown: 0.38,
    ),
    LeafSpec(
      normalizedStartX: 0.08,
      normalizedStartY: -0.19,
      horizontalDrift: 0.39,
      swayAmplitude: 0.038,
      swayFrequency: 1.27,
      phase: 0.55,
      size: 20,
      baseRotation: -0.72,
      rotationSpeed: 11.3,
      flipFrequency: 1.58,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.76,
    ),
    LeafSpec(
      normalizedStartX: 0.66,
      normalizedStartY: -0.16,
      horizontalDrift: -0.21,
      swayAmplitude: 0.068,
      swayFrequency: 1.02,
      phase: 0.68,
      size: 25,
      baseRotation: 0.52,
      rotationSpeed: -15.2,
      flipFrequency: 0.94,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.70,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 0.39,
      normalizedStartY: -0.22,
      horizontalDrift: -0.18,
      swayAmplitude: 0.047,
      swayFrequency: 1.61,
      phase: 0.80,
      size: 27,
      baseRotation: -0.28,
      rotationSpeed: 10.6,
      flipFrequency: 1.31,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.78,
      zigzagAmplitude: 0.082,
      zigzagSegments: 3,
      zigzagCornerSlowdown: 0.44,
    ),
    LeafSpec(
      normalizedStartX: 0.94,
      normalizedStartY: -0.15,
      horizontalDrift: -0.30,
      swayAmplitude: 0.057,
      swayFrequency: 0.96,
      phase: 0.92,
      size: 22,
      baseRotation: 0.64,
      rotationSpeed: -13.5,
      flipFrequency: 1.47,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.72,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 0.57,
      normalizedStartY: -0.18,
      horizontalDrift: 0.16,
      swayAmplitude: 0.029,
      swayFrequency: 1.36,
      phase: 0.10,
      size: 24,
      baseRotation: -0.36,
      rotationSpeed: 9.4,
      flipFrequency: 1.12,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.76,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 0.02,
      normalizedStartY: -0.21,
      horizontalDrift: 0.28,
      swayAmplitude: 0.036,
      swayFrequency: 1.08,
      phase: 0.23,
      size: 29,
      baseRotation: 0.18,
      rotationSpeed: -11.8,
      flipFrequency: 1.26,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.70,
      zigzagAmplitude: 0.070,
      zigzagSegments: 3,
      zigzagCornerSlowdown: 0.36,
    ),
    LeafSpec(
      normalizedStartX: 0.88,
      normalizedStartY: -0.16,
      horizontalDrift: -0.19,
      swayAmplitude: 0.051,
      swayFrequency: 1.53,
      phase: 0.35,
      size: 21,
      baseRotation: -0.62,
      rotationSpeed: 13.1,
      flipFrequency: 0.86,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.80,
    ),
    LeafSpec(
      normalizedStartX: 0.31,
      normalizedStartY: -0.24,
      horizontalDrift: 0.31,
      swayAmplitude: 0.043,
      swayFrequency: 0.92,
      phase: 0.48,
      size: 26,
      baseRotation: 0.43,
      rotationSpeed: -14.6,
      flipFrequency: 1.55,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.74,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 1.04,
      normalizedStartY: -0.19,
      horizontalDrift: -0.33,
      swayAmplitude: 0.031,
      swayFrequency: 1.24,
      phase: 0.61,
      size: 28,
      baseRotation: -0.12,
      rotationSpeed: 8.8,
      flipFrequency: 1.18,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.80,
      zigzagAmplitude: 0.065,
      zigzagSegments: 4,
      zigzagCornerSlowdown: 0.40,
    ),
    LeafSpec(
      normalizedStartX: 0.18,
      normalizedStartY: -0.17,
      horizontalDrift: 0.23,
      swayAmplitude: 0.059,
      swayFrequency: 1.67,
      phase: 0.74,
      size: 19,
      baseRotation: 0.81,
      rotationSpeed: -10.2,
      flipFrequency: 1.42,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.68,
    ),
    LeafSpec(
      normalizedStartX: 0.73,
      normalizedStartY: -0.20,
      horizontalDrift: -0.26,
      swayAmplitude: 0.034,
      swayFrequency: 1.11,
      phase: 0.86,
      size: 25,
      baseRotation: -0.48,
      rotationSpeed: 12.7,
      flipFrequency: 0.98,
      color: Color(0xFFFFB4D8),
      opacity: 0.92,
      fallSpeed: 0.78,
      mirrored: true,
    ),
    LeafSpec(
      normalizedStartX: 0.44,
      normalizedStartY: -0.15,
      horizontalDrift: 0.20,
      swayAmplitude: 0.041,
      swayFrequency: 1.39,
      phase: 0.98,
      size: 23,
      baseRotation: 0.27,
      rotationSpeed: -9.1,
      flipFrequency: 1.34,
      color: Color(0xFFFDE7F1),
      opacity: 0.88,
      fallSpeed: 0.72,
      zigzagAmplitude: 0.080,
      zigzagSegments: 3,
      zigzagCornerSlowdown: 0.45,
    ),
  ];

  late final AnimationController _controller;
  bool _isAppActive = true;
  bool _tickerEnabled = true;
  bool _reduceMotion = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final lifecycleState = WidgetsBinding.instance.lifecycleState;
    _isAppActive =
        lifecycleState == null || lifecycleState == AppLifecycleState.resumed;
    _controller = AnimationController(
      vsync: this,
      duration: FallingLeavesOverlay.animationDuration,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final mediaQuery = MediaQuery.maybeOf(context);
    _reduceMotion =
        (mediaQuery?.disableAnimations ?? false) ||
        (mediaQuery?.accessibleNavigation ?? false);
    _tickerEnabled = TickerMode.valuesOf(context).enabled;
    _syncController();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _isAppActive = state == AppLifecycleState.resumed;
    _syncController();
  }

  void _syncController() {
    if (!mounted) {
      return;
    }

    final shouldAnimate = _isAppActive && _tickerEnabled && !_reduceMotion;
    if (shouldAnimate && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!shouldAnimate && _controller.isAnimating) {
      _controller.stop(canceled: false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: IgnorePointer(
        child: RepaintBoundary(
          child: ExcludeSemantics(
            child: CustomPaint(
              painter: _FallingLeavesPainter(
                animation: _controller,
                leaves: _leaves,
                isDark: widget.isDark,
                staticMode: _reduceMotion,
              ),
              child: const SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
  }
}

class _FallingLeavesPainter extends CustomPainter {
  _FallingLeavesPainter({
    required this.animation,
    required this.leaves,
    required this.isDark,
    required this.staticMode,
  }) : super(repaint: animation);

  static final Path _unitLeafPath = Path()
    ..moveTo(-0.52, 0.02)
    ..cubicTo(-0.29, -0.35, 0.15, -0.41, 0.52, -0.06)
    ..cubicTo(0.21, 0.29, -0.24, 0.35, -0.52, 0.02)
    ..close();
  static const List<Color> _lightSpringColors = [
    Color(0xFFBDE7FF),
    Color(0xFFD8F1FF),
    Color(0xFFF9FDFF),
    Color(0xFFCBEAFF),
  ];
  static const List<Color> _darkSpringColors = [
    Color(0xFF1B3142),
    Color(0xFF233C4E),
    Color(0xFF1F2A3C),
    Color(0xFF172B3A),
  ];

  final Animation<double> animation;
  final List<LeafSpec> leaves;
  final bool isDark;
  final bool staticMode;
  final Paint _paint = Paint()..style = PaintingStyle.fill;
  final Paint _gradientPaint = Paint()..style = PaintingStyle.fill;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }

    final leafCount = staticMode
        ? math.min(4, leaves.length)
        : size.width < 350
        ? math.min(14, leaves.length)
        : leaves.length;
    final animationValue = staticMode ? 0.0 : animation.value;
    _paintAnimatedSpringGradient(canvas, size, animationValue);

    for (var index = 0; index < leafCount; index++) {
      final leaf = leaves[staticMode ? index * 2 + 1 : index];

      // Phase staggers leaves; wrapping happens beyond the viewport edges.
      final cycle = (animationValue + leaf.phase) % 1.0;
      final progress = math
          .pow(cycle, 1 / leaf.fallSpeed)
          .toDouble()
          .clamp(0.0, 1.0);

      var motionProgress = progress;
      var zigzagOffset = 0.0;
      var zigzagTilt = 0.0;
      if (leaf.zigzagSegments > 0 && leaf.zigzagAmplitude > 0) {
        final segmentPosition = (progress * leaf.zigzagSegments).clamp(
          0.0,
          leaf.zigzagSegments - 0.000001,
        );
        final segmentIndex = segmentPosition.floor();
        final segmentProgress = segmentPosition - segmentIndex;

        // Cosine easing reaches zero horizontal speed at every direction change.
        final cornerEase = 0.5 - 0.5 * math.cos(math.pi * segmentProgress);
        final movesRight = segmentIndex.isEven;
        final sidePosition = movesRight
            ? -1 + 2 * cornerEase
            : 1 - 2 * cornerEase;
        zigzagOffset = sidePosition * leaf.zigzagAmplitude;
        zigzagTilt =
            (movesRight ? 1 : -1) * math.sin(math.pi * segmentProgress) * 0.28;

        // Vertical speed also eases near each corner, then recovers mid-segment.
        final slowdownWave = math.sin(
          2 * math.pi * leaf.zigzagSegments * progress,
        );
        motionProgress =
            (progress -
                    leaf.zigzagCornerSlowdown *
                        slowdownWave /
                        (2 * math.pi * leaf.zigzagSegments))
                .clamp(0.0, 1.0);
      }

      final normalizedY =
          leaf.normalizedStartY +
          (1.18 - leaf.normalizedStartY) * motionProgress;
      final sway =
          math.sin(
            (motionProgress * leaf.swayFrequency + leaf.phase) * 2 * math.pi,
          ) *
          leaf.swayAmplitude;
      final normalizedX =
          leaf.normalizedStartX +
          leaf.horizontalDrift * motionProgress +
          sway +
          zigzagOffset;

      final leafSize =
          (leaf.size * (size.width / 390) * FallingLeavesOverlay.leafSizeScale)
              .clamp(15.12, 30.24)
              .toDouble();
      final x = normalizedX * size.width;
      final y = normalizedY * size.height;
      final cullMargin = leafSize * 1.5;
      if (x < -cullMargin ||
          x > size.width + cullMargin ||
          y < -cullMargin ||
          y > size.height + cullMargin) {
        continue;
      }

      // Separate frequencies keep sway, rotation, and flipping out of sync.
      final flip = math
          .cos(
            (progress * leaf.flipFrequency + leaf.phase * 0.73) * 2 * math.pi,
          )
          .abs();
      final scaleX = 0.32 + 0.68 * flip;
      final scaleY =
          0.96 +
          0.04 *
              math.sin(
                (progress * (leaf.flipFrequency + 0.31) + leaf.phase) *
                    2 *
                    math.pi,
              );
      final wobble =
          math.sin(
            (progress * (leaf.swayFrequency + 0.43) + leaf.phase) * 2 * math.pi,
          ) *
          0.24;
      final rotation =
          leaf.baseRotation +
          leaf.rotationSpeed * progress +
          wobble +
          zigzagTilt;

      if (!staticMode) {
        final trailingX =
            leaf.horizontalDrift * leafSize * 0.7 +
            math.sin(rotation) * leafSize * 0.18;
        _drawPetal(
          canvas,
          x: x - trailingX * 2.6,
          y: y - leafSize * 4.8,
          rotation: rotation - 0.28,
          leafSize: leafSize,
          scaleX: scaleX,
          scaleY: scaleY,
          leaf: leaf,
          opacity: leaf.opacity * 0.10,
          sizeScale: 0.76,
          blurSigma: 3.4,
        );
        _drawPetal(
          canvas,
          x: x - trailingX * 1.8,
          y: y - leafSize * 3.2,
          rotation: rotation - 0.20,
          leafSize: leafSize,
          scaleX: scaleX,
          scaleY: scaleY,
          leaf: leaf,
          opacity: leaf.opacity * 0.18,
          sizeScale: 0.83,
          blurSigma: 2.4,
        );
        _drawPetal(
          canvas,
          x: x - trailingX,
          y: y - leafSize * 1.8,
          rotation: rotation - 0.12,
          leafSize: leafSize,
          scaleX: scaleX,
          scaleY: scaleY,
          leaf: leaf,
          opacity: leaf.opacity * 0.28,
          sizeScale: 0.90,
          blurSigma: 1.4,
        );
        _drawPetal(
          canvas,
          x: x - trailingX * 0.45,
          y: y - leafSize * 0.7,
          rotation: rotation - 0.05,
          leafSize: leafSize,
          scaleX: scaleX,
          scaleY: scaleY,
          leaf: leaf,
          opacity: leaf.opacity * 0.42,
          sizeScale: 0.96,
          blurSigma: 0.7,
        );
      }
      _drawPetal(
        canvas,
        x: x,
        y: y,
        rotation: rotation,
        leafSize: leafSize,
        scaleX: scaleX,
        scaleY: scaleY,
        leaf: leaf,
        opacity: leaf.opacity,
      );
    }
  }

  void _drawPetal(
    Canvas canvas, {
    required double x,
    required double y,
    required double rotation,
    required double leafSize,
    required double scaleX,
    required double scaleY,
    required LeafSpec leaf,
    required double opacity,
    double sizeScale = 1,
    double blurSigma = 0,
  }) {
    _paint
      ..color = leaf.color.withValues(alpha: opacity)
      ..maskFilter = blurSigma == 0
          ? null
          : MaskFilter.blur(BlurStyle.normal, blurSigma);

    canvas.save();
    canvas.translate(x, y);
    canvas.rotate(rotation);
    canvas.scale(
      (leaf.mirrored ? -1 : 1) * leafSize * scaleX * sizeScale,
      leafSize *
          0.48 *
          FallingLeavesOverlay.leafThicknessScale *
          scaleY *
          sizeScale,
    );
    canvas.drawPath(_unitLeafPath, _paint);
    canvas.restore();
    _paint.maskFilter = null;
  }

  void _paintAnimatedSpringGradient(
    Canvas canvas,
    Size size,
    double animationValue,
  ) {
    final radians = animationValue * 2 * math.pi;
    final begin = Alignment(
      -1.12 + math.sin(radians) * 0.48,
      -1.08 + math.cos(radians) * 0.34,
    );
    final end = Alignment(
      1.08 + math.cos(radians) * 0.42,
      1.04 + math.sin(radians * 2) * 0.28,
    );
    final bounds = Offset.zero & size;

    _gradientPaint.shader = LinearGradient(
      begin: begin,
      end: end,
      colors: isDark ? _darkSpringColors : _lightSpringColors,
      stops: const [0, 0.3, 0.66, 1],
    ).createShader(bounds);
    canvas.drawRect(bounds, _gradientPaint);
    _gradientPaint.shader = null;
  }

  @override
  bool shouldRepaint(covariant _FallingLeavesPainter oldDelegate) {
    return oldDelegate.animation != animation ||
        oldDelegate.leaves != leaves ||
        oldDelegate.isDark != isDark ||
        oldDelegate.staticMode != staticMode;
  }
}
