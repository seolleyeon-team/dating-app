// =============================================================================
// 슬롯 릴 컨트롤러 & 위젯
// 경로: lib/features/event/widgets/slot_reel_controller.dart
//
// 개별 릴(column)의 스핀 애니메이션을 담당하는 컨트롤러와 위젯.
// SlotReelController.spinTo() 로 외부에서 릴 회전을 트리거할 수 있다.
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

/// 릴 하나를 제어하는 컨트롤러
class SlotReelController {
  _SlotReelWidgetState? _state;

  void _attach(_SlotReelWidgetState state) => _state = state;
  void _detach(_SlotReelWidgetState state) {
    if (_state == state) _state = null;
  }

  /// [targetIndex] 위치로 릴을 회전시킨다.
  /// [extraTurns] 만큼 추가 회전 후 정지.
  Future<void> spinTo(
    int targetIndex, {
    Duration duration = const Duration(milliseconds: 1600),
    Curve curve = Curves.easeOutCubic,
    int extraTurns = 4,
  }) async {
    final state = _state;
    if (state == null) return;

    await state._spinTo(
      targetIndex,
      duration: duration,
      curve: curve,
      extraTurns: extraTurns,
    );
  }
}

/// 슬롯 릴 위젯 – 세로 스크롤로 카드들을 돌린다.
/// visibleCount = 2 → 화면에 2장이 보이는 릴.
class SlotReelWidget extends StatefulWidget {
  const SlotReelWidget({
    super.key,
    required this.controller,
    required this.items,
    this.itemExtent = 130,
    this.visibleCount = 2,
    this.initialIndex = 0,
  });

  final SlotReelController controller;
  final List<Widget> items;
  final double itemExtent;
  final int visibleCount;
  final int initialIndex;

  @override
  State<SlotReelWidget> createState() => _SlotReelWidgetState();
}

class _SlotReelWidgetState extends State<SlotReelWidget> {
  late final FixedExtentScrollController _scrollController;

  @override
  void initState() {
    super.initState();
    _scrollController =
        FixedExtentScrollController(initialItem: widget.initialIndex);
    widget.controller._attach(this);
  }

  @override
  void dispose() {
    widget.controller._detach(this);
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _spinTo(
    int targetIndex, {
    required Duration duration,
    required Curve curve,
    required int extraTurns,
  }) async {
    final len = widget.items.length;
    if (len == 0) return;

    final current = _scrollController.selectedItem;
    final currentNormalized = current % len;

    var delta = targetIndex - currentNormalized;
    if (delta < 0) delta += len;

    final landingIndex = current + (extraTurns * len) + delta;

    await _scrollController.animateToItem(
      landingIndex,
      duration: duration,
      curve: curve,
    );

    await HapticFeedback.selectionClick();
  }

  @override
  Widget build(BuildContext context) {
    final height = widget.itemExtent * widget.visibleCount;

    return SizedBox(
      height: height,
      child: ListWheelScrollView.useDelegate(
        controller: _scrollController,
        physics: const NeverScrollableScrollPhysics(),
        itemExtent: widget.itemExtent,
        diameterRatio: 100, // 거의 flat하게
        perspective: 0.001,
        useMagnifier: false,
        overAndUnderCenterOpacity: 1.0,
        childDelegate: ListWheelChildLoopingListDelegate(
          children: widget.items,
        ),
      ),
    );
  }
}
