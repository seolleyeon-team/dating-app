// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 폭탄 돌리기 타이머 컨트롤러
// 경로: lib/features/event/meeting_icebreaker/application/bomb_pass_timer_controller.dart
//
// 숨겨진 시간(1~15초)은 화면이 만들어질 때 한 번 뽑고 밖으로 노출하지 않는다.
// 남은 시간을 1초씩 깎아 화면에 그리지 않고 deadline을 저장해두고 비교하므로
// frame drop이나 background 전환이 있어도 정확한 시점에 종료된다.
//
// 앱이 완전히 종료된 뒤 알람을 울리는 기능은 만들지 않는다.
// 폭탄은 사용자가 현재 화면에서 진행하는 짧은 인앱 게임이다.
// =============================================================================

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../domain/bomb_pass_timer.dart';

typedef BombPassClock = DateTime Function();

class BombPassTimerController extends ChangeNotifier {
  BombPassTimerController({math.Random? random, BombPassClock? clock})
    : _random = random ?? math.Random.secure(),
      _clock = clock ?? DateTime.now {
    _hiddenDuration = drawBombPassHiddenDuration(_random);
  }

  final math.Random _random;
  final BombPassClock _clock;

  /// 사용자에게 절대 보여주지 않는 값. getter를 만들지 않는다.
  late Duration _hiddenDuration;
  DateTime? _deadline;
  Timer? _deadlineTimer;
  bool _disposed = false;

  BombPassPhase _phase = BombPassPhase.ready;

  /// 째깍째깍 소리를 시작해야 할 때 호출된다.
  VoidCallback? onTickingStart;

  /// 째깍째깍 소리를 멈춰야 할 때 호출된다 (폭발, 이탈, 재시작).
  VoidCallback? onTickingStop;

  /// 폭발 순간 호출된다 (폭발음 + 애니메이션).
  VoidCallback? onExploded;

  BombPassPhase get phase => _phase;

  bool get isReady => _phase == BombPassPhase.ready;

  bool get isRunning => _phase == BombPassPhase.running;

  bool get hasExploded => _phase == BombPassPhase.exploded;

  /// 게임을 시작한다. 이미 시작했으면 무시한다 (중복 입력 방지).
  void start() {
    if (_disposed) return;
    if (_phase != BombPassPhase.ready) return;

    final startedAt = _clock();
    _deadline = computeBombPassDeadline(
      startedAt: startedAt,
      hiddenDuration: _hiddenDuration,
    );
    _phase = BombPassPhase.running;
    notifyListeners();

    onTickingStart?.call();

    _deadlineTimer?.cancel();
    _deadlineTimer = Timer(_hiddenDuration, _handleDeadlineReached);
  }

  /// deadline이 지났는지 확인한다.
  ///
  /// 화면이 잠시 background에 들어갔다 돌아왔을 때 호출한다.
  void checkDeadline() {
    if (_disposed) return;
    if (_phase != BombPassPhase.running) return;
    final deadline = _deadline;
    if (deadline == null) return;
    if (hasBombPassDeadlinePassed(now: _clock(), deadline: deadline)) {
      _handleDeadlineReached();
    }
  }

  /// 앱이 다시 foreground로 돌아왔을 때 호출한다.
  void handleAppResumed() => checkDeadline();

  /// 새로운 숨겨진 시간으로 다시 시작할 수 있게 되돌린다.
  ///
  /// 이전 값을 재사용하지 않는다.
  void restart() {
    if (_disposed) return;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    _deadline = null;
    onTickingStop?.call();
    _hiddenDuration = drawBombPassHiddenDuration(_random);
    _phase = BombPassPhase.ready;
    notifyListeners();
  }

  /// 화면을 떠날 때 소리를 멈춘다.
  void stopForNavigation() {
    if (_disposed) return;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    onTickingStop?.call();
  }

  void _handleDeadlineReached() {
    if (_disposed) return;
    if (_phase != BombPassPhase.running) return;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    _phase = BombPassPhase.exploded;
    notifyListeners();
    onTickingStop?.call();
    onExploded?.call();
  }

  @override
  void dispose() {
    _disposed = true;
    _deadlineTimer?.cancel();
    _deadlineTimer = null;
    // 화면이 사라질 때 소리가 남아 있지 않게 한다.
    onTickingStop?.call();
    onTickingStart = null;
    onTickingStop = null;
    onExploded = null;
    super.dispose();
  }
}
