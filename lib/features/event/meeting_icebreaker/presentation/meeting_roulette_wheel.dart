// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 원판 위젯
// 경로: lib/features/event/meeting_icebreaker/presentation/meeting_roulette_wheel.dart
//
// 구조
//   고정 rim + 외곽 전구  (회전하지 않는다)
//   회전하는 8칸 원판
//   고정 중앙 허브
//   고정 상단 바늘
//
// 바늘은 고정하고 원판만 돌리므로 결과 index와 시각적 위치가 어긋나지 않는다.
// asset 이미지를 쓰지 않고 CustomPainter로 직접 그린다 (라이선스 명확 + 선명함).
// =============================================================================

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../domain/meeting_icebreaker_game.dart';
import '../domain/meeting_roulette_spin.dart';
import 'meeting_icebreaker_palette.dart';

/// rim에 배치되는 전구 수.
const int kMeetingRouletteBulbCount = 16;

class MeetingRouletteWheel extends StatelessWidget {
  const MeetingRouletteWheel({
    super.key,
    required this.games,
    required this.rotation,
    required this.palette,
    this.winningIndex,
    this.isHighlighting = false,
    this.hubPulse = 0,
    this.pointerNudge = 0,
    this.diameter = 268,
  });

  final List<MeetingRouletteGame> games;

  /// 원판 회전 각도 (라디안, 시계 방향).
  final double rotation;

  final MeetingIcebreakerPalette palette;

  /// 당첨 칸 index. 조명을 켤 때만 쓴다.
  final int? winningIndex;

  /// 당첨 강조(칸 glow + 전구 점등 + 허브 pulse) 표시 여부.
  final bool isHighlighting;

  /// 허브 pulse 진행도 (0~1). 부드러운 숨쉬기 표현에만 쓴다.
  final double hubPulse;

  /// 바늘의 미세한 흔들림 (라디안).
  final double pointerNudge;

  final double diameter;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: diameter,
      height: diameter,
      child: CustomPaint(
        painter: _MeetingRouletteWheelPainter(
          games: games,
          rotation: rotation,
          palette: palette,
          winningIndex: isHighlighting ? winningIndex : null,
          hubPulse: hubPulse,
          pointerNudge: pointerNudge,
          textDirection: Directionality.of(context),
        ),
      ),
    );
  }
}

class _MeetingRouletteWheelPainter extends CustomPainter {
  _MeetingRouletteWheelPainter({
    required this.games,
    required this.rotation,
    required this.palette,
    required this.winningIndex,
    required this.hubPulse,
    required this.pointerNudge,
    required this.textDirection,
  });

  final List<MeetingRouletteGame> games;
  final double rotation;
  final MeetingIcebreakerPalette palette;
  final int? winningIndex;
  final double hubPulse;
  final double pointerNudge;
  final TextDirection textDirection;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final outerRadius = math.min(size.width, size.height) / 2;
    final rimWidth = outerRadius * 0.13;
    final discRadius = outerRadius - rimWidth;

    _paintRim(canvas, center, outerRadius, rimWidth);
    _paintBulbs(canvas, center, outerRadius - rimWidth / 2);
    _paintDisc(canvas, center, discRadius);
    _paintHub(canvas, center, discRadius);
    _paintPointer(canvas, center, outerRadius, rimWidth);
  }

  // ── 고정 rim (두꺼운 외곽, 부드러운 입체감) ──────────────────────────────
  void _paintRim(
    Canvas canvas,
    Offset center,
    double outerRadius,
    double rimWidth,
  ) {
    final rimRect = Rect.fromCircle(
      center: center,
      radius: outerRadius - rimWidth / 2,
    );

    // 바닥 그림자
    canvas.drawCircle(
      center.translate(0, outerRadius * 0.035),
      outerRadius - rimWidth * 0.2,
      Paint()
        ..color = palette.shadow
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10),
    );

    canvas.drawArc(
      rimRect,
      0,
      2 * math.pi,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = rimWidth
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[palette.rimHighlight, palette.rim, palette.rimShadow],
          stops: const <double>[0.0, 0.55, 1.0],
        ).createShader(rimRect),
    );

    // rim 안쪽 경계선
    canvas.drawCircle(
      center,
      outerRadius - rimWidth,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..color = palette.rimShadow.withValues(alpha: 0.55),
    );
  }

  // ── 고정 전구. 당첨 시 상단(바늘 주변) 전구가 밝아진다 ────────────────────
  void _paintBulbs(Canvas canvas, Offset center, double radius) {
    final bulbRadius = radius * 0.035;
    final winner = winningIndex;

    for (var i = 0; i < kMeetingRouletteBulbCount; i++) {
      final angle =
          -math.pi / 2 + i * (2 * math.pi / kMeetingRouletteBulbCount);
      final position = Offset(
        center.dx + radius * math.cos(angle),
        center.dy + radius * math.sin(angle),
      );

      // 상단 바늘 기준 각거리. 당첨 칸 폭 안에 있는 전구만 밝게 켠다.
      final normalized = _angleDistanceFromTop(angle);
      final isNearWinner =
          winner != null && normalized <= kMeetingRouletteSegmentSweep * 0.75;

      if (isNearWinner) {
        canvas.drawCircle(
          position,
          bulbRadius * 2.6,
          Paint()
            ..color = palette.accent.withValues(alpha: 0.35)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
        );
      }

      canvas.drawCircle(
        position,
        bulbRadius,
        Paint()
          ..color = isNearWinner
              ? palette.bulbOn
              : (winner != null
                    ? palette.bulbOff.withValues(alpha: 0.9)
                    : palette.bulbOff),
      );
      canvas.drawCircle(
        position,
        bulbRadius,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.8
          ..color = palette.rimShadow.withValues(alpha: 0.35),
      );
    }
  }

  /// 상단(12시)에서의 각거리 (0 ~ π).
  double _angleDistanceFromTop(double angle) {
    var delta = (angle + math.pi / 2) % (2 * math.pi);
    if (delta > math.pi) delta = 2 * math.pi - delta;
    return delta;
  }

  // ── 회전하는 8칸 원판 ──────────────────────────────────────────────────
  void _paintDisc(Canvas canvas, Offset center, double radius) {
    final rect = Rect.fromCircle(center: center, radius: radius);

    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(rotation);
    canvas.translate(-center.dx, -center.dy);

    for (var i = 0; i < games.length; i++) {
      // canvas 0rad = 3시. 원판 기준 0rad = 12시이므로 -π/2 보정한다.
      final startAngle = -math.pi / 2 + meetingRouletteSegmentStartAngle(i);
      final isWinner = winningIndex == i;
      final fill = isWinner
          ? palette.segmentWinner
          : (i.isEven ? palette.segmentLight : palette.segmentPink);

      canvas.drawArc(
        rect,
        startAngle,
        kMeetingRouletteSegmentSweep,
        true,
        Paint()..color = fill,
      );

      if (isWinner) {
        // 당첨 칸 외곽 glow
        canvas.drawArc(
          rect.deflate(radius * 0.02),
          startAngle,
          kMeetingRouletteSegmentSweep,
          true,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = radius * 0.05
            ..color = palette.accent.withValues(alpha: 0.75)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5),
        );
      }

      // 칸 구분선
      canvas.drawLine(
        center,
        Offset(
          center.dx + radius * math.cos(startAngle),
          center.dy + radius * math.sin(startAngle),
        ),
        Paint()
          ..strokeWidth = 1.0
          ..color = palette.border.withValues(alpha: 0.8),
      );

      _paintSegmentLabel(
        canvas,
        center: center,
        radius: radius,
        index: i,
        game: games[i],
        isWinner: isWinner,
      );
    }

    canvas.restore();
  }

  void _paintSegmentLabel(
    Canvas canvas, {
    required Offset center,
    required double radius,
    required int index,
    required MeetingRouletteGame game,
    required bool isWinner,
  }) {
    final lines = meetingRouletteSegmentLabelLines(game);
    final angle = -math.pi / 2 + meetingRouletteSegmentCenterAngle(index);

    final painter = TextPainter(
      text: TextSpan(
        text: lines.join('\n'),
        style: MeetingIcebreakerText.segment(
          isWinner ? palette.accentDeep : palette.ink,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: textDirection,
      maxLines: 2,
      // 큰 글씨 설정에서도 칸을 넘지 않도록 배율을 고정한다.
      textScaler: TextScaler.noScaling,
    )..layout(maxWidth: radius * 0.62);

    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(angle + math.pi / 2);
    canvas.translate(0, -radius * 0.63);
    painter.paint(canvas, Offset(-painter.width / 2, -painter.height / 2));
    canvas.restore();
  }

  // ── 고정 중앙 허브 ────────────────────────────────────────────────────
  void _paintHub(Canvas canvas, Offset center, double discRadius) {
    final baseRadius = discRadius * 0.19;
    final pulse = winningIndex != null ? hubPulse : 0.0;

    if (pulse > 0) {
      canvas.drawCircle(
        center,
        baseRadius * (1.25 + pulse * 0.45),
        Paint()
          ..color = palette.accent.withValues(alpha: 0.28 * (1 - pulse))
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8),
      );
    }

    canvas.drawCircle(
      center,
      baseRadius * 1.16,
      Paint()..color = palette.rimHighlight,
    );
    canvas.drawCircle(center, baseRadius, Paint()..color = palette.surface);
    canvas.drawCircle(
      center,
      baseRadius,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = baseRadius * 0.16
        ..color = palette.accent,
    );
    canvas.drawCircle(
      center,
      baseRadius * 0.34,
      Paint()..color = palette.accentDeep,
    );
  }

  // ── 고정 상단 바늘 ────────────────────────────────────────────────────
  void _paintPointer(
    Canvas canvas,
    Offset center,
    double outerRadius,
    double rimWidth,
  ) {
    final tipY = center.dy - outerRadius + rimWidth * 0.35;
    final baseY = center.dy - outerRadius + rimWidth * 2.5;
    final halfWidth = outerRadius * 0.055;

    canvas.save();
    canvas.translate(center.dx, baseY);
    canvas.rotate(pointerNudge);
    canvas.translate(-center.dx, -baseY);

    final path = Path()
      ..moveTo(center.dx, tipY)
      ..lineTo(center.dx - halfWidth, baseY)
      ..quadraticBezierTo(
        center.dx,
        baseY + halfWidth * 0.8,
        center.dx + halfWidth,
        baseY,
      )
      ..close();

    canvas.drawPath(
      path,
      Paint()
        ..color = palette.shadow
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3),
    );
    canvas.drawPath(path, Paint()..color = palette.accentDeep);
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..color = palette.rimHighlight.withValues(alpha: 0.9),
    );

    canvas.restore();
  }

  @override
  bool shouldRepaint(_MeetingRouletteWheelPainter oldDelegate) {
    return oldDelegate.rotation != rotation ||
        oldDelegate.winningIndex != winningIndex ||
        oldDelegate.hubPulse != hubPulse ||
        oldDelegate.pointerNudge != pointerNudge ||
        oldDelegate.palette != palette ||
        !identical(oldDelegate.games, games);
  }
}
