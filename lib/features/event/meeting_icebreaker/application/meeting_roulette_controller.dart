// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 회전 컨트롤러
// 경로: lib/features/event/meeting_icebreaker/application/meeting_roulette_controller.dart
//
// 결과는 애니메이션이 아니라 난수가 먼저 정한다.
// 애니메이션은 이미 정해진 index에 맞춰 각도를 계산해 감속 정지할 뿐이다.
//
// 안전장치
//  - 회전 중 재회전 차단 (중복 tap 방지)
//  - AnimationController는 한 번만 만들고 dispose에서 정리
//  - 2초 지연은 dispose 후에 실행되지 않도록 취소한다
// =============================================================================

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../domain/meeting_icebreaker_game.dart';
import '../domain/meeting_roulette_spin.dart';

/// 룰렛 진행 단계.
enum MeetingRoulettePhase {
  /// 회전 대기.
  idle,

  /// 회전 중. 버튼은 비활성.
  spinning,

  /// 당첨 조명 표시 중 (약 2초).
  celebrating,

  /// 설명 창을 열 준비가 끝난 상태.
  revealed,
}

class MeetingRouletteController extends ChangeNotifier {
  MeetingRouletteController({
    required TickerProvider vsync,
    required List<MeetingRouletteGame> games,
    math.Random? random,
    bool reduceMotion = false,
    Duration? spinDuration,
    int? fullTurns,
    Duration? celebrationDelay,
  }) : assert(games.length == kMeetingRouletteSegmentCount),
       _games = List<MeetingRouletteGame>.unmodifiable(games),
       _random = random ?? math.Random.secure(),
       _reduceMotion = reduceMotion,
       _spinDuration =
           spinDuration ??
           (reduceMotion
               ? kMeetingRouletteReducedSpinDuration
               : kMeetingRouletteSpinDuration),
       _fullTurns =
           fullTurns ??
           (reduceMotion
               ? kMeetingRouletteReducedFullTurns
               : kMeetingRouletteFullTurns),
       _celebrationDelay =
           celebrationDelay ??
           (reduceMotion
               ? kMeetingRouletteReducedCelebrationDelay
               : kMeetingRouletteCelebrationDelay) {
    _animation = AnimationController(vsync: vsync, duration: _spinDuration);
    _curved = CurvedAnimation(parent: _animation, curve: Curves.easeOutCubic);
    _animation.addListener(_onAnimationTick);
    _animation.addStatusListener(_onAnimationStatus);
  }

  final List<MeetingRouletteGame> _games;
  final math.Random _random;
  final bool _reduceMotion;
  final Duration _spinDuration;
  final int _fullTurns;
  final Duration _celebrationDelay;

  late final AnimationController _animation;
  late final Animation<double> _curved;

  Timer? _revealTimer;
  bool _disposed = false;

  MeetingRoulettePhase _phase = MeetingRoulettePhase.idle;
  double _rotation = 0;
  double _targetRotation = 0;
  double _startRotation = 0;
  int? _winningIndex;
  int _tickCount = 0;

  /// 칸 경계를 지날 때마다 호출된다 (haptic / 바늘 흔들림).
  ///
  /// 플랫폼 채널을 직접 부르지 않아 테스트에서 호출 횟수를 셀 수 있다.
  void Function()? onSegmentTick;

  /// 당첨 조명이 끝나 설명 창을 열 수 있을 때 호출된다.
  void Function(MeetingRouletteGame game)? onRevealReady;

  List<MeetingRouletteGame> get games => _games;

  MeetingRoulettePhase get phase => _phase;

  /// 현재 원판 회전 각도 (라디안, 시계 방향).
  double get rotation => _rotation;

  bool get reduceMotion => _reduceMotion;

  Duration get spinDuration => _spinDuration;

  Duration get celebrationDelay => _celebrationDelay;

  int? get winningIndex => _winningIndex;

  MeetingRouletteGame? get winningGame {
    final index = _winningIndex;
    if (index == null) return null;
    return _games[index];
  }

  /// 회전 중에는 false. 중복 tap을 막는다.
  bool get canSpin =>
      !_disposed &&
      (_phase == MeetingRoulettePhase.idle ||
          _phase == MeetingRoulettePhase.revealed);

  bool get isSpinning => _phase == MeetingRoulettePhase.spinning;

  /// 조명이 켜져 있는 상태 (당첨 강조 + 전구 점등).
  bool get isHighlighting =>
      _phase == MeetingRoulettePhase.celebrating ||
      _phase == MeetingRoulettePhase.revealed;

  /// 경계 통과 횟수 (테스트·디버그용).
  @visibleForTesting
  int get segmentTickCount => _tickCount;

  /// 룰렛을 돌린다.
  ///
  /// 회전 중이면 아무 일도 하지 않는다.
  void spin() {
    if (!canSpin) return;

    _revealTimer?.cancel();
    _revealTimer = null;

    // 1) 결과를 먼저 정한다 (각 칸 1/8 균등 확률).
    final index = drawMeetingRouletteIndex(_random);
    _winningIndex = index;

    // 2) 그 칸이 상단 바늘 아래에 오도록 최종 각도를 만든다.
    //
    // 이전 회전이 남긴 각도에서 이어서 돌리므로, 현재 각도의 "완성된 바퀴 수"를
    // 기준으로 목표 각도를 잡는다. 목표 각도의 2π 나머지는 항상 당첨 칸을
    // 가리키기 때문에 결과 index와 시각적 위치가 어긋나지 않는다.
    _startRotation = _rotation;
    final alignedRemainder = meetingRouletteAlignedRemainder(index);
    final completedTurns = (_rotation / (2 * math.pi)).floorToDouble();
    _targetRotation =
        (completedTurns + _fullTurns + 1) * 2 * math.pi + alignedRemainder;

    _phase = MeetingRoulettePhase.spinning;
    _tickCount = 0;
    notifyListeners();

    _animation
      ..reset()
      ..forward();
  }

  /// 다시 돌릴 수 있는 상태로 되돌린다 (각도는 유지).
  void reset() {
    if (_disposed) return;
    _revealTimer?.cancel();
    _revealTimer = null;
    _animation.stop();
    _phase = MeetingRoulettePhase.idle;
    notifyListeners();
  }

  void _onAnimationTick() {
    final previous = _rotation;
    _rotation =
        _startRotation + (_targetRotation - _startRotation) * _curved.value;

    final crossings = meetingRouletteBoundaryCrossings(
      fromRotation: previous,
      toRotation: _rotation,
    );
    if (crossings > 0 && !_reduceMotion) {
      _tickCount += crossings;
      onSegmentTick?.call();
    }
    notifyListeners();
  }

  void _onAnimationStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed) return;
    if (_disposed) return;

    // 애니메이션이 끝난 각도와 사전에 정한 index가 어긋나지 않는지 확인한다.
    _rotation = _targetRotation;
    assert(
      meetingRouletteWinningIndex(_rotation) == _winningIndex,
      'roulette rotation and winning index diverged',
    );

    _phase = MeetingRoulettePhase.celebrating;
    notifyListeners();

    _revealTimer = Timer(_celebrationDelay, () {
      _revealTimer = null;
      if (_disposed) return;
      if (_phase != MeetingRoulettePhase.celebrating) return;
      _phase = MeetingRoulettePhase.revealed;
      notifyListeners();
      final game = winningGame;
      if (game != null) onRevealReady?.call(game);
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _revealTimer?.cancel();
    _revealTimer = null;
    onSegmentTick = null;
    onRevealReady = null;
    _animation.removeListener(_onAnimationTick);
    _animation.removeStatusListener(_onAnimationStatus);
    _animation.dispose();
    super.dispose();
  }
}
