// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 폭탄 돌리기 숨겨진 시간
// 경로: lib/features/event/meeting_icebreaker/domain/bomb_pass_timer.dart
//
// 숨겨진 시간은 1초 ~ 15초 사이의 정수 하나를 균등 확률로 뽑는다.
// 참가자에게는 절대 노출하지 않는다.
//   - 화면에는 `??:??` 만 표시
//   - progress bar 등으로 남은 시간을 추정할 수 있게 만들지 않는다
//   - accessibility semantics / analytics / 로그에도 실제 초를 남기지 않는다
//
// 이 파일은 "값을 만드는 함수"만 공개한다.
// 현재 게임에 뽑힌 값은 컨트롤러 내부에만 있고 밖으로 나가지 않는다.
// =============================================================================

import 'dart:math' as math;

/// 숨겨진 시간 최소값 (초). 포함된다.
const int kBombPassHiddenMinSeconds = 1;

/// 숨겨진 시간 최대값 (초). 포함된다.
const int kBombPassHiddenMaxSeconds = 15;

/// 화면에 항상 보여주는 마스킹 문자열.
const String kBombPassHiddenTimerMask = '??:??';

/// screen reader가 읽는 문자열. 실제 초를 노출하지 않는다.
const String kBombPassHiddenTimerSemanticLabel = '숨겨진 타이머';

/// 폭탄이 터진 뒤 보여주는 문구.
const String kBombPassExplodedTitle = '펑!';
const String kBombPassExplodedBody = '폭탄이 터졌어요';

/// 폭탄 상태.
enum BombPassPhase {
  /// 시작 전. `게임 시작하기` 버튼 노출.
  ready,

  /// 진행 중. 남은 시간은 표시하지 않는다.
  running,

  /// 폭발.
  exploded,
}

/// 1초 ~ 15초 중 하나를 균등 확률로 뽑는다.
///
/// production에서는 `Random.secure()`를, 테스트에서는 고정 난수를 주입한다.
Duration drawBombPassHiddenDuration(math.Random random) {
  const span = kBombPassHiddenMaxSeconds - kBombPassHiddenMinSeconds + 1;
  return Duration(seconds: kBombPassHiddenMinSeconds + random.nextInt(span));
}

/// [startedAt] 기준 폭발 시각.
///
/// 1초씩 감소하는 화면 timer가 아니라 deadline을 저장해두고 비교한다.
/// frame drop이나 background 진입이 있어도 정확한 시점에 종료된다.
DateTime computeBombPassDeadline({
  required DateTime startedAt,
  required Duration hiddenDuration,
}) {
  return startedAt.add(hiddenDuration);
}

/// deadline이 지났는지.
bool hasBombPassDeadlinePassed({
  required DateTime now,
  required DateTime deadline,
}) {
  return !now.isBefore(deadline);
}
