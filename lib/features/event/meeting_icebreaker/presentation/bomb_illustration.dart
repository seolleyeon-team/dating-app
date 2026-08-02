// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 폭탄 일러스트
// 경로: lib/features/event/meeting_icebreaker/presentation/bomb_illustration.dart
//
// 설레연 테마에 맞는 부드러운 2.5D 느낌을 CustomPainter로 직접 그린다.
// 외부 이미지를 쓰지 않으므로 라이선스가 명확하고, 어떤 화면 크기에서도 선명하다.
// 광과민성 위험을 줄이기 위해 빠른 반복 점멸을 쓰지 않는다.
// =============================================================================

import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'meeting_icebreaker_palette.dart';

class BombIllustration extends StatelessWidget {
  const BombIllustration({
    super.key,
    required this.palette,
    this.size = 168,
    this.fuseGlow = 0,
    this.explosionProgress = 0,
    this.shake = 0,
  });

  final MeetingIcebreakerPalette palette;
  final double size;

  /// 도화선 불꽃 밝기 (0~1). 진행 중일 때만 켠다.
  final double fuseGlow;

  /// 폭발 진행도 (0~1).
  final double explosionProgress;

  /// 흔들림 offset (논리 픽셀).
  final double shake;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _BombPainter(
          palette: palette,
          fuseGlow: fuseGlow.clamp(0.0, 1.0),
          explosionProgress: explosionProgress.clamp(0.0, 1.0),
          shake: shake,
        ),
      ),
    );
  }
}

class _BombPainter extends CustomPainter {
  _BombPainter({
    required this.palette,
    required this.fuseGlow,
    required this.explosionProgress,
    required this.shake,
  });

  final MeetingIcebreakerPalette palette;
  final double fuseGlow;
  final double explosionProgress;
  final double shake;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2 + shake, size.height * 0.58);
    final bodyRadius = size.shortestSide * 0.29;

    if (explosionProgress > 0) {
      _paintBlast(canvas, center, size.shortestSide * 0.5);
    }

    // 폭발이 진행될수록 폭탄이 살짝 커졌다가 사라진다.
    final scale = 1 + explosionProgress * 0.22;
    final bodyOpacity = (1 - explosionProgress * 0.75).clamp(0.0, 1.0);

    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.scale(scale, scale);
    canvas.translate(-center.dx, -center.dy);

    _paintShadow(canvas, center, bodyRadius);
    _paintBody(canvas, center, bodyRadius, bodyOpacity);
    _paintCap(canvas, center, bodyRadius, bodyOpacity);
    _paintFuse(canvas, center, bodyRadius, bodyOpacity);

    canvas.restore();
  }

  void _paintShadow(Canvas canvas, Offset center, double radius) {
    canvas.drawOval(
      Rect.fromCenter(
        center: center.translate(0, radius * 1.12),
        width: radius * 2.0,
        height: radius * 0.42,
      ),
      Paint()
        ..color = palette.shadow
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8),
    );
  }

  void _paintBody(Canvas canvas, Offset center, double radius, double opacity) {
    final rect = Rect.fromCircle(center: center, radius: radius);
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-0.35, -0.45),
          radius: 1.05,
          colors: <Color>[
            palette.accent.withValues(alpha: opacity),
            palette.accentDeep.withValues(alpha: opacity),
          ],
        ).createShader(rect),
    );

    // 왼쪽 위 하이라이트 (2.5D 광택)
    canvas.drawOval(
      Rect.fromCenter(
        center: center.translate(-radius * 0.33, -radius * 0.42),
        width: radius * 0.72,
        height: radius * 0.46,
      ),
      Paint()..color = Colors.white.withValues(alpha: 0.34 * opacity),
    );
  }

  void _paintCap(Canvas canvas, Offset center, double radius, double opacity) {
    final capRect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: center.translate(0, -radius * 1.02),
        width: radius * 0.62,
        height: radius * 0.34,
      ),
      Radius.circular(radius * 0.1),
    );
    canvas.drawRRect(
      capRect,
      Paint()..color = palette.rimShadow.withValues(alpha: opacity),
    );
    canvas.drawRRect(
      capRect.deflate(radius * 0.05),
      Paint()..color = palette.rim.withValues(alpha: opacity),
    );
  }

  void _paintFuse(Canvas canvas, Offset center, double radius, double opacity) {
    final start = center.translate(0, -radius * 1.16);
    final path = Path()
      ..moveTo(start.dx, start.dy)
      ..cubicTo(
        start.dx + radius * 0.34,
        start.dy - radius * 0.24,
        start.dx + radius * 0.10,
        start.dy - radius * 0.62,
        start.dx + radius * 0.46,
        start.dy - radius * 0.70,
      );

    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = radius * 0.11
        ..strokeCap = StrokeCap.round
        ..color = palette.inkFaint.withValues(alpha: opacity),
    );

    if (fuseGlow <= 0) return;

    final sparkCenter = Offset(
      start.dx + radius * 0.46,
      start.dy - radius * 0.70,
    );
    canvas.drawCircle(
      sparkCenter,
      radius * (0.16 + fuseGlow * 0.08),
      Paint()
        ..color = palette.accent.withValues(alpha: 0.4 * fuseGlow * opacity)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
    );
    canvas.drawCircle(
      sparkCenter,
      radius * (0.08 + fuseGlow * 0.03),
      Paint()..color = const Color(0xFFFFD9A0).withValues(alpha: opacity),
    );
  }

  /// 부드러운 flash + 작은 particle. 화면 전체를 덮는 섬광은 쓰지 않는다.
  void _paintBlast(Canvas canvas, Offset center, double maxRadius) {
    final progress = explosionProgress;
    final flashRadius = maxRadius * (0.35 + progress * 0.75);

    canvas.drawCircle(
      center,
      flashRadius,
      Paint()
        ..color = palette.accent.withValues(alpha: 0.30 * (1 - progress))
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18),
    );
    canvas.drawCircle(
      center,
      flashRadius * 0.62,
      Paint()
        ..color = palette.segmentWinner.withValues(
          alpha: 0.42 * (1 - progress),
        ),
    );

    // 연기 느낌의 작은 원들
    const particleCount = 9;
    for (var i = 0; i < particleCount; i++) {
      final angle = i * (2 * math.pi / particleCount) - math.pi / 2;
      final distance = maxRadius * (0.32 + progress * 0.72);
      final position = Offset(
        center.dx + distance * math.cos(angle),
        center.dy + distance * math.sin(angle) * 0.85,
      );
      canvas.drawCircle(
        position,
        maxRadius * (0.11 - progress * 0.045).clamp(0.02, 0.12),
        Paint()
          ..color = palette.rim.withValues(alpha: 0.5 * (1 - progress))
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5),
      );
    }
  }

  @override
  bool shouldRepaint(_BombPainter oldDelegate) {
    return oldDelegate.fuseGlow != fuseGlow ||
        oldDelegate.explosionProgress != explosionProgress ||
        oldDelegate.shake != shake ||
        oldDelegate.palette != palette;
  }
}
