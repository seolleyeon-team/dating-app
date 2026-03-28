// =============================================================================
// 스와이프 카드 덱 (Tinder-Style)
// 경로: lib/shared/widgets/seol_swipe_deck.dart
//
// 사용 예시:
// final controller = SeolSwipeDeckController();
// SeolSwipeDeck(
//   cards: profileWidgets,
//   controller: controller,
//   onSwiped: (index, dir) => print('$index → $dir'),
// )
// =============================================================================

import 'dart:math' as math;
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 스와이프 방향
// =============================================================================
enum SwipeDirection { left, right }

// =============================================================================
// 컨트롤러 (프로그래밍 방식 스와이프)
// =============================================================================
class SeolSwipeDeckController extends ChangeNotifier {
  void Function()? _swipeLeftFn;
  void Function()? _swipeRightFn;

  void _attach({
    required void Function() swipeLeft,
    required void Function() swipeRight,
  }) {
    _swipeLeftFn = swipeLeft;
    _swipeRightFn = swipeRight;
  }

  void _detach() {
    _swipeLeftFn = null;
    _swipeRightFn = null;
  }

  void swipeLeft() => _swipeLeftFn?.call();
  void swipeRight() => _swipeRightFn?.call();
}

// =============================================================================
// 메인 위젯
// =============================================================================
class SeolSwipeDeck extends StatefulWidget {
  final List<Widget> cards;
  final void Function(int index, SwipeDirection direction)? onSwiped;
  final VoidCallback? onEmpty;
  final SeolSwipeDeckController? controller;

  const SeolSwipeDeck({
    super.key,
    required this.cards,
    this.onSwiped,
    this.onEmpty,
    this.controller,
  });

  @override
  State<SeolSwipeDeck> createState() => _SeolSwipeDeckState();
}

class _SeolSwipeDeckState extends State<SeolSwipeDeck>
    with TickerProviderStateMixin {
  // ── 상태 ──
  int _topIndex = 0;
  Offset _dragOffset = Offset.zero;
  bool _isAnimating = false;

  // ── 애니메이션 ──
  late AnimationController _flyController;
  late AnimationController _snapController;
  Animation<Offset>? _flyAnimation;
  Animation<Offset>? _snapAnimation;

  // ── 상수 ──
  static const double _maxRotationDeg = 15.0;
  static const double _distanceThresholdRatio = 0.22;
  static const double _velocityThreshold = 800.0;
  static const Duration _flyDuration = Duration(milliseconds: 300);
  static const Duration _snapDuration = Duration(milliseconds: 400);
  static const double _backCardBaseScale = 0.95;

  @override
  void initState() {
    super.initState();
    _flyController = AnimationController(vsync: this, duration: _flyDuration);
    _snapController = AnimationController(vsync: this, duration: _snapDuration);

    _flyController.addStatusListener(_onFlyComplete);
    _snapController.addStatusListener(_onSnapComplete);

    widget.controller?._attach(
      swipeLeft: () => _programmaticSwipe(SwipeDirection.left),
      swipeRight: () => _programmaticSwipe(SwipeDirection.right),
    );
  }

  @override
  void didUpdateWidget(covariant SeolSwipeDeck oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.controller != oldWidget.controller) {
      oldWidget.controller?._detach();
      widget.controller?._attach(
        swipeLeft: () => _programmaticSwipe(SwipeDirection.left),
        swipeRight: () => _programmaticSwipe(SwipeDirection.right),
      );
    }
  }

  @override
  void dispose() {
    widget.controller?._detach();
    _flyController.removeStatusListener(_onFlyComplete);
    _snapController.removeStatusListener(_onSnapComplete);
    _flyController.dispose();
    _snapController.dispose();
    super.dispose();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 제스처 핸들러
  // ═══════════════════════════════════════════════════════════════════════════

  void _onPanStart(DragStartDetails _) {
    if (_isAnimating) return;
    _snapController.stop();
    _flyController.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_isAnimating) return;
    setState(() {
      _dragOffset += details.delta;
    });
  }

  void _onPanEnd(DragEndDetails details) {
    if (_isAnimating) return;

    final screenWidth = MediaQuery.of(context).size.width;
    final threshold = screenWidth * _distanceThresholdRatio;
    final velocity = details.velocity.pixelsPerSecond.dx;

    if (_dragOffset.dx.abs() > threshold ||
        velocity.abs() > _velocityThreshold) {
      // ── 스와이프 확정 ──
      final direction = _dragOffset.dx > 0
          ? SwipeDirection.right
          : SwipeDirection.left;
      _animateFlyOff(direction);
    } else {
      // ── 스냅백 ──
      _animateSnapBack();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 애니메이션
  // ═══════════════════════════════════════════════════════════════════════════

  void _animateFlyOff(SwipeDirection direction) {
    _isAnimating = true;
    HapticFeedback.mediumImpact();

    final screenWidth = MediaQuery.of(context).size.width;
    final targetX = direction == SwipeDirection.right
        ? screenWidth * 1.5
        : -screenWidth * 1.5;

    _flyAnimation = Tween<Offset>(
      begin: _dragOffset,
      end: Offset(targetX, _dragOffset.dy + 80),
    ).animate(CurvedAnimation(parent: _flyController, curve: Curves.easeIn));

    _flyAnimation!.addListener(() {
      if (mounted) setState(() => _dragOffset = _flyAnimation!.value);
    });

    _flyController.forward(from: 0);
  }

  void _animateSnapBack() {
    _isAnimating = true;

    _snapAnimation = Tween<Offset>(begin: _dragOffset, end: Offset.zero)
        .animate(
          CurvedAnimation(parent: _snapController, curve: Curves.elasticOut),
        );

    _snapAnimation!.addListener(() {
      if (mounted) setState(() => _dragOffset = _snapAnimation!.value);
    });

    _snapController.forward(from: 0);
  }

  void _onFlyComplete(AnimationStatus status) {
    if (status == AnimationStatus.completed) {
      final direction = _dragOffset.dx > 0
          ? SwipeDirection.right
          : SwipeDirection.left;
      final swipedIndex = _topIndex;

      if (mounted) {
        setState(() {
          _topIndex++;
          _dragOffset = Offset.zero;
          _isAnimating = false;
        });
      }

      widget.onSwiped?.call(swipedIndex, direction);

      if (_topIndex >= widget.cards.length) {
        widget.onEmpty?.call();
      }
    }
  }

  void _onSnapComplete(AnimationStatus status) {
    if (status == AnimationStatus.completed) {
      if (mounted) {
        setState(() {
          _dragOffset = Offset.zero;
          _isAnimating = false;
        });
      }
    }
  }

  void _programmaticSwipe(SwipeDirection direction) {
    if (_isAnimating) return;
    if (_topIndex >= widget.cards.length) return;

    // 시작 오프셋을 살짝 설정하고 fly-off
    setState(() {
      _dragOffset = Offset(direction == SwipeDirection.right ? 40 : -40, 0);
    });
    _animateFlyOff(direction);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 빌드
  // ═══════════════════════════════════════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    if (_topIndex >= widget.cards.length) {
      return const _EmptyDeck();
    }

    final screenWidth = MediaQuery.of(context).size.width;
    final dragProgress = (_dragOffset.dx / (screenWidth * 0.5)).clamp(
      -1.0,
      1.0,
    );
    final absDragProgress = dragProgress.abs();
    final rotationAngle = dragProgress * _maxRotationDeg * (math.pi / 180);

    return Stack(
      children: [
        // ── 다음 카드 (아래) ──
        if (_topIndex + 1 < widget.cards.length)
          Positioned.fill(
            child: Transform.scale(
              scale: _backCardBaseScale + (0.05 * absDragProgress),
              child: widget.cards[_topIndex + 1],
            ),
          ),

        // ── 현재 카드 (위) ──
        Positioned.fill(
          child: GestureDetector(
            onPanStart: _onPanStart,
            onPanUpdate: _onPanUpdate,
            onPanEnd: _onPanEnd,
            child: Transform.translate(
              offset: _dragOffset,
              child: Transform.rotate(
                angle: rotationAngle,
                child: Stack(
                  children: [
                    // 카드 본체
                    Positioned.fill(child: widget.cards[_topIndex]),

                    // ── LIKE 배지 (오른쪽으로 드래그) ──
                    if (dragProgress > 0.05)
                      Positioned(
                        top: 40,
                        left: 24,
                        child: Transform.rotate(
                          angle: -0.3,
                          child: Opacity(
                            opacity: (dragProgress * 2).clamp(0.0, 1.0),
                            child: const _SwipeBadge(
                              text: 'LIKE',
                              color: Color(0xFF10B981),
                            ),
                          ),
                        ),
                      ),

                    // ── NOPE 배지 (왼쪽으로 드래그) ──
                    if (dragProgress < -0.05)
                      Positioned(
                        top: 40,
                        right: 24,
                        child: Transform.rotate(
                          angle: 0.3,
                          child: Opacity(
                            opacity: (absDragProgress * 2).clamp(0.0, 1.0),
                            child: const _SwipeBadge(
                              text: 'NOPE',
                              color: Color(0xFFF43F5E),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// LIKE / NOPE 배지
// =============================================================================
class _SwipeBadge extends StatelessWidget {
  final String text;
  final Color color;

  const _SwipeBadge({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        border: Border.all(color: color, width: 3.5),
        borderRadius: BorderRadius.circular(12),
        color: color.withValues(alpha: 0.15),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 36,
          fontWeight: FontWeight.w900,
          color: color,
          letterSpacing: 2,
        ),
      ),
    );
  }
}

// =============================================================================
// 빈 덱
// =============================================================================
class _EmptyDeck extends StatelessWidget {
  const _EmptyDeck();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            CupertinoIcons.heart_slash,
            size: 56,
            color: CupertinoColors.systemGrey3,
          ),
          const SizedBox(height: 16),
          const Text(
            '오늘의 추천이 끝났어요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: CupertinoColors.systemGrey,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '내일 새로운 인연을 만나보세요 💕',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: CupertinoColors.systemGrey2,
            ),
          ),
        ],
      ),
    );
  }
}
