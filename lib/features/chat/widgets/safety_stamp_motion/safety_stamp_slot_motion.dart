import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_3d_controller/flutter_3d_controller.dart';

const String safetyStampModelAsset = 'assets/models/stamp_scene_animated.glb';

String safetyStampModelSource({bool isWeb = kIsWeb}) =>
    isWeb ? 'assets/$safetyStampModelAsset' : safetyStampModelAsset;

String? selectSafetyStampAnimationName(List<String> animations) {
  if (animations.isEmpty) return null;
  if (animations.contains('Stamp')) return 'Stamp';
  for (final animation in animations) {
    if (animation.toLowerCase() == 'stamp') return animation;
  }
  for (final animation in animations) {
    if (animation.toLowerCase().contains('stamp')) return animation;
  }
  return animations.first;
}

abstract final class SafetyStampMotionTiming {
  static const total = Duration(milliseconds: 4000);
  static const petalStartMs = 0;
  static const petalEndMs = 2400;
  static const stampStartMs = 2550;
  static const impactMs = 3050;
  static const stampExitMs = 3650;

  static double interval(
    double value, {
    required int beginMs,
    required int endMs,
  }) {
    final milliseconds = value * total.inMilliseconds;
    return ((milliseconds - beginMs) / (endMs - beginMs)).clamp(0.0, 1.0);
  }
}

/// The complete safety-stamp motion used inside one half of the two-person
/// board. The GLB is kept mounted while idle so it is ready when Firestore
/// reports a newly completed stamp.
class SafetyStampSlotMotion extends StatefulWidget {
  const SafetyStampSlotMotion({
    super.key,
    required this.timeline,
    required this.isVisible,
    required this.forceSettled,
    required this.stickerSize,
    required this.settledRotationDeg,
    this.enable3d = true,
  });

  final double timeline;
  final bool isVisible;
  final bool forceSettled;
  final double stickerSize;
  final double settledRotationDeg;
  final bool enable3d;

  @override
  State<SafetyStampSlotMotion> createState() => _SafetyStampSlotMotionState();
}

class _SafetyStampSlotMotionState extends State<SafetyStampSlotMotion> {
  final Flutter3DController _modelController = Flutter3DController();

  bool _modelLoaded = false;
  bool _playedModel = false;
  bool _impactFired = false;
  String? _animationName;
  String? _modelError;

  @override
  void didUpdateWidget(covariant SafetyStampSlotMotion oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.timeline < oldWidget.timeline || !widget.isVisible) {
      _playedModel = false;
      _impactFired = false;
      if (_modelLoaded && widget.enable3d) {
        _modelController.stopAnimation();
        _modelController.resetAnimation();
      }
    }
    _synchronizeEffects();
  }

  void _synchronizeEffects() {
    if (!widget.isVisible || widget.forceSettled) return;
    final milliseconds =
        widget.timeline * SafetyStampMotionTiming.total.inMilliseconds;
    if (!_playedModel &&
        milliseconds >= SafetyStampMotionTiming.stampStartMs &&
        milliseconds < SafetyStampMotionTiming.stampExitMs) {
      _playedModel = true;
      unawaited(_playModelAnimation());
    }
    if (!_impactFired && milliseconds >= SafetyStampMotionTiming.impactMs) {
      _impactFired = true;
      unawaited(HapticFeedback.mediumImpact());
    }
  }

  Future<void> _handleModelLoaded() async {
    if (!mounted) return;
    setState(() {
      _modelLoaded = true;
      _modelError = null;
    });
    try {
      final animations = await _modelController.getAvailableAnimations();
      _animationName = selectSafetyStampAnimationName(animations);
      _modelController.setCameraTarget(0, 0, 0);
      _modelController.setCameraOrbit(0, 0, 180);

      final milliseconds =
          widget.timeline * SafetyStampMotionTiming.total.inMilliseconds;
      if (widget.isVisible &&
          !widget.forceSettled &&
          milliseconds >= SafetyStampMotionTiming.stampStartMs &&
          milliseconds < SafetyStampMotionTiming.stampExitMs) {
        _playedModel = true;
        await _playModelAnimation();
      }
    } catch (error) {
      if (!mounted) return;
      setState(() => _modelError = error.toString());
    }
  }

  Future<void> _playModelAnimation() async {
    if (!_modelLoaded || !widget.enable3d) return;
    try {
      _modelController.stopAnimation();
      await Future<void>.delayed(const Duration(milliseconds: 40));
      _modelController.resetAnimation();
      await Future<void>.delayed(const Duration(milliseconds: 16));
      _modelController.playAnimation(
        animationName: _animationName,
        loopCount: 1,
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _modelError = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final timeline = widget.forceSettled ? 1.0 : widget.timeline;
    return IgnorePointer(
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          if (widget.isVisible)
            _PetalLayer(
              timeline: timeline,
              stickerSize: widget.stickerSize,
              settledRotationDeg: widget.settledRotationDeg,
            ),
          if (widget.isVisible && !widget.forceSettled)
            _ImpactLayer(
              timeline: timeline,
              diameter: widget.stickerSize * .83,
            ),
          LayoutBuilder(
            builder: (context, constraints) => OverflowBox(
              alignment: Alignment.center,
              minWidth: constraints.maxWidth,
              maxWidth: constraints.maxWidth,
              minHeight: 900,
              maxHeight: 900,
              child: _StampLayer(
                timeline: timeline,
                controller: _modelController,
                modelLoaded: _modelLoaded,
                enable3d: widget.enable3d,
                modelFailed: _modelError != null,
                suppressMotion: widget.forceSettled || !widget.isVisible,
                onLoaded: _handleModelLoaded,
                onError: (error) {
                  if (!mounted) return;
                  setState(() {
                    _modelLoaded = false;
                    _modelError = error;
                  });
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PetalLayer extends StatelessWidget {
  const _PetalLayer({
    required this.timeline,
    required this.stickerSize,
    required this.settledRotationDeg,
  });

  final double timeline;
  final double stickerSize;
  final double settledRotationDeg;

  @override
  Widget build(BuildContext context) {
    final fallProgress = SafetyStampMotionTiming.interval(
      timeline,
      beginMs: SafetyStampMotionTiming.petalStartMs,
      endMs: SafetyStampMotionTiming.petalEndMs,
    );
    final pressProgress = SafetyStampMotionTiming.interval(
      timeline,
      beginMs: SafetyStampMotionTiming.impactMs,
      endMs: SafetyStampMotionTiming.impactMs + 280,
    );
    return _AnimatedCherrySticker(
      progress: fallProgress,
      stickerSize: stickerSize,
      settledRotationDeg: settledRotationDeg,
      pressedProgress: pressProgress,
    );
  }
}

class _StickerPose {
  const _StickerPose({
    required this.dx,
    required this.dy,
    required this.rotDeg,
    this.scaleX = 1,
    this.scaleY = 1,
    this.opacity = 1,
  });

  final double dx;
  final double dy;
  final double rotDeg;
  final double scaleX;
  final double scaleY;
  final double opacity;
}

// These are the original dowon0901 single-petal poses and timings.
List<_StickerPose> _buildPoses(double stickerSize, double finalRotDeg) {
  final s = stickerSize;
  return [
    _StickerPose(dx: -34, dy: -s * 1.28, rotDeg: -18, opacity: 0),
    _StickerPose(
      dx: 24,
      dy: -s * .82,
      rotDeg: 10,
      scaleX: 1.015,
      scaleY: 1.015,
    ),
    _StickerPose(dx: -18, dy: -s * .22, rotDeg: -7),
    _StickerPose(dx: 0, dy: 0, rotDeg: finalRotDeg, scaleX: 1.04, scaleY: .96),
  ];
}

class _AnimatedCherrySticker extends StatelessWidget {
  const _AnimatedCherrySticker({
    required this.progress,
    required this.stickerSize,
    required this.settledRotationDeg,
    required this.pressedProgress,
  });

  final double progress;
  final double stickerSize;
  final double settledRotationDeg;
  final double pressedProgress;

  @override
  Widget build(BuildContext context) {
    final p = progress.clamp(0.0, 1.0).toDouble();
    final poses = _buildPoses(stickerSize, settledRotationDeg);
    final motionProgress = Curves.easeInOut.transform(p);
    final pose = _poseAt(poses, motionProgress);
    final trailProgresses = [
      math.max(0.0, motionProgress - .08),
      math.max(0.0, motionProgress - .16),
    ];
    final pressed = Curves.easeOutCubic.transform(
      pressedProgress.clamp(0.0, 1.0).toDouble(),
    );
    final impactSquash = math.sin(pressed * math.pi);

    return Transform.scale(
      scaleX: 1 + impactSquash * .14,
      scaleY: 1 - impactSquash * .12,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          for (var i = trailProgresses.length - 1; i >= 0; i--)
            _buildStickerLayer(
              _poseAt(poses, trailProgresses[i]),
              extraOpacity: (i == 0 ? .16 : .08) * (1 - pressed),
            ),
          _buildStickerLayer(pose, extraOpacity: 1 - pressed),
          if (pressed > 0)
            _buildStickerLayer(
              pose,
              key: const ValueKey('pressed-petal'),
              assetPath: 'cherrysticker-pressed.png',
              extraOpacity: pressed,
            ),
        ],
      ),
    );
  }

  Widget _buildStickerLayer(
    _StickerPose pose, {
    Key? key,
    String assetPath = 'cherrysticker.png',
    double extraOpacity = 1,
  }) {
    return Transform.translate(
      key: key,
      offset: Offset(pose.dx, pose.dy),
      child: Transform.rotate(
        angle: pose.rotDeg * (math.pi / 180),
        child: Transform.scale(
          scaleX: pose.scaleX,
          scaleY: pose.scaleY,
          child: Opacity(
            opacity: (pose.opacity * extraOpacity).clamp(0.0, 1.0).toDouble(),
            child: Image.asset(
              assetPath,
              width: stickerSize,
              height: stickerSize,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.high,
              errorBuilder: (_, __, ___) => const SizedBox.shrink(),
            ),
          ),
        ),
      ),
    );
  }

  _StickerPose _poseAt(List<_StickerPose> poses, double progress) {
    final interpolated = _interpolatePose(poses, progress);
    final sway =
        math.sin(progress * math.pi * 3.2) *
        (stickerSize * .045) *
        (1 - progress);
    return _StickerPose(
      dx: interpolated.dx + sway,
      dy: interpolated.dy,
      rotDeg: interpolated.rotDeg,
      scaleX: interpolated.scaleX,
      scaleY: interpolated.scaleY,
      opacity: interpolated.opacity,
    );
  }

  _StickerPose _interpolatePose(List<_StickerPose> poses, double progress) {
    if (progress >= 1) return poses.last;
    final segmentProgress = progress * (poses.length - 1);
    final lowerIndex = segmentProgress.floor().clamp(0, poses.length - 1);
    final upperIndex = math.min(lowerIndex + 1, poses.length - 1);
    if (lowerIndex == upperIndex) return poses[lowerIndex];
    final localT = Curves.easeInOutCubic.transform(
      segmentProgress - lowerIndex,
    );
    final from = poses[lowerIndex];
    final to = poses[upperIndex];
    return _StickerPose(
      dx: ui.lerpDouble(from.dx, to.dx, localT) ?? to.dx,
      dy: ui.lerpDouble(from.dy, to.dy, localT) ?? to.dy,
      rotDeg: ui.lerpDouble(from.rotDeg, to.rotDeg, localT) ?? to.rotDeg,
      scaleX: ui.lerpDouble(from.scaleX, to.scaleX, localT) ?? to.scaleX,
      scaleY: ui.lerpDouble(from.scaleY, to.scaleY, localT) ?? to.scaleY,
      opacity: ui.lerpDouble(from.opacity, to.opacity, localT) ?? to.opacity,
    );
  }
}

class _ImpactLayer extends StatelessWidget {
  const _ImpactLayer({required this.timeline, required this.diameter});

  final double timeline;
  final double diameter;

  @override
  Widget build(BuildContext context) {
    final pulse = SafetyStampMotionTiming.interval(
      timeline,
      beginMs: SafetyStampMotionTiming.impactMs,
      endMs: SafetyStampMotionTiming.impactMs + 360,
    );
    if (pulse <= 0 || pulse >= 1) return const SizedBox.shrink();
    final eased = Curves.easeOutCubic.transform(pulse);
    return Opacity(
      opacity: 1 - eased,
      child: Transform.scale(
        scale: .55 + eased * .72,
        child: Container(
          key: const ValueKey('safety-stamp-impact-pulse'),
          width: diameter,
          height: diameter,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: const Color(0xFFD34F70).withValues(alpha: .46),
              width: 4,
            ),
          ),
        ),
      ),
    );
  }
}

class _StampLayer extends StatelessWidget {
  const _StampLayer({
    required this.timeline,
    required this.controller,
    required this.modelLoaded,
    required this.enable3d,
    required this.modelFailed,
    required this.suppressMotion,
    required this.onLoaded,
    required this.onError,
  });

  final double timeline;
  final Flutter3DController controller;
  final bool modelLoaded;
  final bool enable3d;
  final bool modelFailed;
  final bool suppressMotion;
  final VoidCallback onLoaded;
  final ValueChanged<String> onError;

  @override
  Widget build(BuildContext context) {
    final milliseconds =
        timeline * SafetyStampMotionTiming.total.inMilliseconds;
    final visible =
        !suppressMotion &&
        milliseconds >= SafetyStampMotionTiming.stampStartMs &&
        milliseconds < SafetyStampMotionTiming.stampExitMs;

    return Stack(
      alignment: Alignment.center,
      children: [
        if (!modelLoaded || !enable3d || modelFailed)
          Opacity(opacity: visible ? 1 : 0, child: const _FallbackStamp()),
        if (enable3d && !modelFailed)
          Positioned.fill(
            child: Opacity(
              // Keep the platform view mounted at the same imperceptible
              // opacity used by the standalone prototype so the GLB is fully
              // prepared before this slot begins its motion.
              opacity: visible ? 1 : .01,
              child: Align(
                child: FractionallySizedBox(
                  widthFactor: .58,
                  heightFactor: 1,
                  child: Flutter3DViewer(
                    src: safetyStampModelSource(),
                    controller: controller,
                    enableTouch: false,
                    activeGestureInterceptor: true,
                    progressBarColor: Colors.transparent,
                    onLoad: (_) => onLoaded(),
                    onError: onError,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _FallbackStamp extends StatelessWidget {
  const _FallbackStamp();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: const Size(150, 190),
      painter: _FallbackStampPainter(),
    );
  }
}

class _FallbackStampPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final centerX = size.width / 2;
    final shadow = Paint()..color = const Color(0x4250343D);
    canvas.drawOval(
      Rect.fromCenter(center: Offset(centerX + 8, 174), width: 118, height: 21),
      shadow,
    );

    canvas.save();
    canvas.translate(centerX, 4);
    canvas.rotate(-.10);
    canvas.skew(-.09, 0);

    final bodySide = Path()
      ..moveTo(-29, 22)
      ..quadraticBezierTo(-30, 9, -17, 5)
      ..quadraticBezierTo(0, -2, 18, 5)
      ..quadraticBezierTo(30, 10, 31, 22)
      ..lineTo(39, 111)
      ..quadraticBezierTo(37, 124, 25, 129)
      ..quadraticBezierTo(2, 137, -25, 128)
      ..quadraticBezierTo(-38, 123, -38, 111)
      ..close();
    canvas.drawShadow(bodySide, const Color(0x46000000), 7, false);
    canvas.drawPath(bodySide, Paint()..color = const Color(0xFFC4BDB7));
    canvas.drawOval(
      Rect.fromCenter(center: const Offset(0, 14), width: 58, height: 22),
      Paint()..color = const Color(0xFFE4DFDA),
    );

    final highlight = Path()
      ..moveTo(-22, 28)
      ..quadraticBezierTo(-16, 18, -10, 26)
      ..lineTo(-5, 110)
      ..quadraticBezierTo(-12, 117, -19, 111)
      ..close();
    canvas.drawPath(highlight, Paint()..color = const Color(0xAAFFFFFF));

    final baseSide = Path()
      ..moveTo(-50, 105)
      ..quadraticBezierTo(0, 86, 51, 105)
      ..lineTo(58, 151)
      ..quadraticBezierTo(4, 172, -55, 151)
      ..close();
    canvas.drawShadow(baseSide, const Color(0x3D000000), 6, false);
    canvas.drawPath(baseSide, Paint()..color = const Color(0xFFB7AEA8));
    canvas.drawOval(
      Rect.fromCenter(center: const Offset(0, 107), width: 102, height: 29),
      Paint()..color = const Color(0xFFD8D1CB),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
