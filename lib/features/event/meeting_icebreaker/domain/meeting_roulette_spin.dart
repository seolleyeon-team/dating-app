// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 회전 각도 계산
// 경로: lib/features/event/meeting_icebreaker/domain/meeting_roulette_spin.dart
//
// 결과는 애니메이션이 아니라 난수가 먼저 결정한다.
//   1. 안전한 random source로 당첨 index를 뽑는다
//   2. 그 index가 상단 고정 바늘 아래에 오도록 최종 각도를 계산한다
//   3. 여러 바퀴 돌린 뒤 그 각도에서 감속 정지한다
//
// 좌표 규칙
//   - 각도는 라디안, 시계 방향이 +
//   - 0 = 12시(상단 바늘 위치)
//   - 칸 i는 원판 기준 [i*sweep, (i+1)*sweep) 구간을 차지한다
//   - 원판을 rotation 만큼 돌리면 원판 각도 θ는 화면 각도 θ + rotation 에 나타난다
//   - 따라서 바늘(화면 각도 0) 아래에 있는 원판 각도는 (-rotation) mod 2π 이다
// =============================================================================

import 'dart:math' as math;

import 'meeting_icebreaker_game.dart';

/// 한 칸이 차지하는 각도 (2π / 8).
const double kMeetingRouletteSegmentSweep =
    2 * math.pi / kMeetingRouletteSegmentCount;

/// 최소 회전 바퀴 수. 요구사항상 4바퀴 이상 돌아야 한다.
const int kMeetingRouletteMinFullTurns = 4;

/// 기본 회전 바퀴 수.
const int kMeetingRouletteFullTurns = 5;

/// `reduce motion`이 켜진 경우의 회전 바퀴 수.
const int kMeetingRouletteReducedFullTurns = 1;

/// 기본 회전 시간 (3~5초 범위).
const Duration kMeetingRouletteSpinDuration = Duration(milliseconds: 4200);

/// `reduce motion`이 켜진 경우의 회전 시간.
const Duration kMeetingRouletteReducedSpinDuration = Duration(
  milliseconds: 700,
);

/// 당첨 조명을 보여주는 시간. 이후 설명 창을 연다.
const Duration kMeetingRouletteCelebrationDelay = Duration(seconds: 2);

/// `reduce motion`에서도 결과를 읽을 시간은 남긴다.
const Duration kMeetingRouletteReducedCelebrationDelay = Duration(
  milliseconds: 600,
);

const double _kTwoPi = 2 * math.pi;

/// 칸 [index]의 중심 각도 (원판 기준).
double meetingRouletteSegmentCenterAngle(int index) {
  return (index + 0.5) * kMeetingRouletteSegmentSweep;
}

/// 칸 [index]의 시작 각도 (원판 기준).
double meetingRouletteSegmentStartAngle(int index) {
  return index * kMeetingRouletteSegmentSweep;
}

/// 당첨 index가 상단 바늘 아래에 오게 하는 한 바퀴 안의 각도 (0 이상 2π 미만).
///
/// 최종 회전 각도의 2π 나머지가 이 값이면 바늘은 항상 [index] 칸을 가리킨다.
double meetingRouletteAlignedRemainder(int index) {
  assert(index >= 0 && index < kMeetingRouletteSegmentCount);
  return _kTwoPi - meetingRouletteSegmentCenterAngle(index);
}

/// 당첨 index가 상단 바늘 아래에서 멈추게 하는 최종 회전 각도.
///
/// [fullTurns]는 최소 1바퀴 이상이어야 한다.
double meetingRouletteTargetRotation({
  required int index,
  int fullTurns = kMeetingRouletteFullTurns,
}) {
  assert(fullTurns >= 1);
  return fullTurns * _kTwoPi + meetingRouletteAlignedRemainder(index);
}

/// 현재 회전 각도에서 바늘이 가리키는 칸 index.
///
/// 음수 각도와 여러 바퀴(wrap-around)를 모두 처리한다.
int meetingRouletteWinningIndex(double rotation) {
  final local = (-rotation) % _kTwoPi;
  final index = (local / kMeetingRouletteSegmentSweep).floor();
  // 부동소수 오차로 8이 나오는 경우를 방어한다.
  return index % kMeetingRouletteSegmentCount;
}

/// [fromRotation] → [toRotation] 동안 바늘이 지나간 칸 경계 수.
///
/// 회전 중 tick haptic / 바늘 흔들림 트리거로 쓴다.
int meetingRouletteBoundaryCrossings({
  required double fromRotation,
  required double toRotation,
}) {
  if (toRotation <= fromRotation) return 0;
  final from = (fromRotation / kMeetingRouletteSegmentSweep).floor();
  final to = (toRotation / kMeetingRouletteSegmentSweep).floor();
  return to - from;
}

/// 8칸 중 하나를 균등 확률로 뽑는다.
///
/// production에서는 `Random.secure()`를 주입한다. 테스트에서는 고정 난수를 넣는다.
int drawMeetingRouletteIndex(math.Random random) {
  return random.nextInt(kMeetingRouletteSegmentCount);
}

/// 회전 시간을 analytics bucket 문자열로 바꾼다 (원시값 대신 구간만 기록).
String meetingRouletteSpinDurationBucket(Duration duration) {
  final ms = duration.inMilliseconds;
  if (ms < 1000) return 'lt_1s';
  if (ms < 3000) return '1_3s';
  if (ms < 5000) return '3_5s';
  return 'gte_5s';
}
