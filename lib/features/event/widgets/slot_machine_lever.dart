// =============================================================================
// 슬롯머신 레버 위젯
// 경로: lib/features/event/widgets/slot_machine_lever.dart
//
// 탭 또는 아래로 드래그 시 레버가 내려갔다가 spring-back.
// threshold 이상 당기면 onPull 콜백을 트리거한다.
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

class SlotMachineLever extends StatefulWidget {
  const SlotMachineLever({
    super.key,
    required this.onPull,
    this.disabled = false,
  });

  final VoidCallback onPull;
  final bool disabled;

  @override
  State<SlotMachineLever> createState() => _SlotMachineLeverState();
}

class _SlotMachineLeverState extends State<SlotMachineLever>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late Animation<double> _animation;

  /// 0.0 = 원위치, 1.0 = 최대로 당긴 상태
  double _dragValue = 0.0;
  bool _isDragging = false;

  static const double _maxPullPx = 48.0;
  static const double _threshold = 0.45; // 45% 이상 당기면 spin

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
    _animation = Tween<double>(begin: 0.0, end: 0.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.elasticOut),
    );
    _controller.addListener(() {
      if (!_isDragging) {
        setState(() => _dragValue = _animation.value);
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onTap() {
    if (widget.disabled) return;
    // 짧은 pull-and-release 애니메이션
    _animatePull(0.8, triggerSpin: true);
  }

  void _animatePull(double peak, {required bool triggerSpin}) {
    _animation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: _dragValue, end: peak)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 30,
      ),
      TweenSequenceItem(
        tween: Tween(begin: peak, end: 0.0)
            .chain(CurveTween(curve: Curves.elasticOut)),
        weight: 70,
      ),
    ]).animate(_controller);
    _controller.forward(from: 0.0);

    if (triggerSpin) {
      HapticFeedback.mediumImpact();
      widget.onPull();
    }
  }

  void _onDragUpdate(DragUpdateDetails details) {
    if (widget.disabled) return;
    _isDragging = true;
    setState(() {
      _dragValue = (_dragValue + details.delta.dy / _maxPullPx).clamp(0.0, 1.0);
    });
  }

  void _onDragEnd(DragEndDetails details) {
    _isDragging = false;
    if (_dragValue >= _threshold) {
      _animatePull(_dragValue, triggerSpin: true);
    } else {
      _animatePull(0.0, triggerSpin: false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final offset = _dragValue * _maxPullPx;

    return GestureDetector(
      onTap: _onTap,
      onVerticalDragUpdate: _onDragUpdate,
      onVerticalDragEnd: _onDragEnd,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: 44,
        height: 160,
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.topCenter,
          children: [
            // 트랙 (실버 바디)
            Positioned(
              top: 36 + offset * 0.3,
              child: Container(
                width: 10,
                height: 72,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(5),
                  gradient: const LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: [
                      Color(0xFF9CA3AF),
                      Color(0xFFE4E4E7),
                      Color(0xFFD4D4D8),
                      Color(0xFFFFFFFF),
                      Color(0xFFD4D4D8),
                      Color(0xFFE4E4E7),
                      Color(0xFF9CA3AF),
                    ],
                    stops: [0.0, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0],
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF000000).withValues(alpha: 0.15),
                      blurRadius: 4,
                      offset: const Offset(1, 2),
                    ),
                  ],
                ),
              ),
            ),
            // 베이스 마운트
            Positioned(
              top: 100 + offset * 0.15,
              child: Container(
                width: 22,
                height: 24,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(6),
                  gradient: const LinearGradient(
                    colors: [
                      Color(0xFFB0B0B8),
                      Color(0xFFE8E8EC),
                      Color(0xFFB0B0B8),
                    ],
                  ),
                  border: Border.all(
                    color: const Color(0xFFFFFFFF).withValues(alpha: 0.5),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF000000).withValues(alpha: 0.1),
                      blurRadius: 3,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
              ),
            ),
            // 루비 볼 (drag에 따라 offset)
            Positioned(
              top: offset,
              child: _RubyBall(scale: widget.disabled ? 0.9 : 1.0),
            ),
          ],
        ),
      ),
    );
  }
}

// 글로시 레드 구체
class _RubyBall extends StatelessWidget {
  const _RubyBall({this.scale = 1.0});
  final double scale;

  @override
  Widget build(BuildContext context) {
    return Transform.scale(
      scale: scale,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: const RadialGradient(
            center: Alignment(-0.3, -0.35),
            radius: 0.8,
            colors: [
              Color(0xFFFF8A8A),
              Color(0xFFEF4444),
              Color(0xFFDC2626),
              Color(0xFFB91C1C),
            ],
            stops: [0.0, 0.35, 0.65, 1.0],
          ),
          border: Border.all(
            color: const Color(0xFFFFFFFF).withValues(alpha: 0.25),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFFDC2626).withValues(alpha: 0.4),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
            BoxShadow(
              color: const Color(0xFF000000).withValues(alpha: 0.15),
              blurRadius: 6,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          children: [
            // 하이라이트
            Positioned(
              top: 5,
              left: 6,
              child: Container(
                width: 14,
                height: 9,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(7),
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      const Color(0xFFFFFFFF).withValues(alpha: 0.8),
                      const Color(0xFFFFFFFF).withValues(alpha: 0.0),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
