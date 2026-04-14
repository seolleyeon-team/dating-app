import 'dart:ui';

import 'package:flutter/cupertino.dart';

import 'slot_machine_lever.dart';
import 'slot_reel_controller.dart';

class EventSlotMachine extends StatelessWidget {
  const EventSlotMachine({
    super.key,
    required this.reel1,
    required this.reel2,
    required this.reel3,
    required this.reel1Items,
    required this.reel2Items,
    required this.reel3Items,
    required this.onLeverPull,
    required this.spinning,
  });

  final SlotReelController reel1;
  final SlotReelController reel2;
  final SlotReelController reel3;
  final List<Widget> reel1Items;
  final List<Widget> reel2Items;
  final List<Widget> reel3Items;
  final VoidCallback onLeverPull;
  final bool spinning;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(36),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFFFFFFFF).withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(36),
                border: Border.all(
                  color: const Color(0xFFFFFFFF).withValues(alpha: 0.75),
                  width: 2.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF7C5BA0).withValues(alpha: 0.10),
                    blurRadius: 40,
                    offset: const Offset(0, 16),
                  ),
                  BoxShadow(
                    color: const Color(0xFFFFFFFF).withValues(alpha: 0.6),
                    blurRadius: 2,
                    offset: const Offset(0, -1),
                  ),
                ],
              ),
              padding: const EdgeInsets.all(14),
              child: _InnerFrame(
                reel1: reel1,
                reel2: reel2,
                reel3: reel3,
                reel1Items: reel1Items,
                reel2Items: reel2Items,
                reel3Items: reel3Items,
              ),
            ),
          ),
        ),
        Positioned(
          right: -18,
          top: 0,
          bottom: 0,
          child: Center(
            child: SlotMachineLever(
              onPull: onLeverPull,
              disabled: spinning,
            ),
          ),
        ),
      ],
    );
  }
}

class _InnerFrame extends StatelessWidget {
  const _InnerFrame({
    required this.reel1,
    required this.reel2,
    required this.reel3,
    required this.reel1Items,
    required this.reel2Items,
    required this.reel3Items,
  });

  final SlotReelController reel1;
  final SlotReelController reel2;
  final SlotReelController reel3;
  final List<Widget> reel1Items;
  final List<Widget> reel2Items;
  final List<Widget> reel3Items;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFFF5F0FA),
            Color(0xFFFFFFFF),
            Color(0xFFF0EAF5),
          ],
        ),
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFFFFFFF).withValues(alpha: 0.9),
            offset: const Offset(0, 2),
            blurRadius: 3,
          ),
          BoxShadow(
            color: const Color(0xFF000000).withValues(alpha: 0.04),
            offset: const Offset(0, 8),
            blurRadius: 16,
          ),
        ],
      ),
      padding: const EdgeInsets.all(8),
      child: _ReelViewport(
        reel1: reel1,
        reel2: reel2,
        reel3: reel3,
        reel1Items: reel1Items,
        reel2Items: reel2Items,
        reel3Items: reel3Items,
      ),
    );
  }
}

class _ReelViewport extends StatelessWidget {
  const _ReelViewport({
    required this.reel1,
    required this.reel2,
    required this.reel3,
    required this.reel1Items,
    required this.reel2Items,
    required this.reel3Items,
  });

  final SlotReelController reel1;
  final SlotReelController reel2;
  final SlotReelController reel3;
  final List<Widget> reel1Items;
  final List<Widget> reel2Items;
  final List<Widget> reel3Items;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: Container(
        color: const Color(0xFFFCFAFD),
        child: Row(
          children: [
            Expanded(
              child: SlotReelWidget(
                controller: reel1,
                items: reel1Items,
                itemExtent: 130,
                visibleCount: 2,
                initialIndex: 0,
              ),
            ),
            Container(
              width: 1,
              color: const Color(0xFFE8E0EF).withValues(alpha: 0.5),
            ),
            Expanded(
              child: SlotReelWidget(
                controller: reel2,
                items: reel2Items,
                itemExtent: 130,
                visibleCount: 2,
                initialIndex: 0,
              ),
            ),
            Container(
              width: 1,
              color: const Color(0xFFE8E0EF).withValues(alpha: 0.5),
            ),
            Expanded(
              child: SlotReelWidget(
                controller: reel3,
                items: reel3Items,
                itemExtent: 130,
                visibleCount: 2,
                initialIndex: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
