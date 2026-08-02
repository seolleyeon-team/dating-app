// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 위젯 테스트용 Key
// 경로: lib/features/event/meeting_icebreaker/presentation/meeting_icebreaker_keys.dart
//
// 문구가 바뀌어도 테스트가 깨지지 않도록 주요 요소에 Key를 붙인다.
// =============================================================================

import 'package:flutter/widgets.dart';

class MeetingIcebreakerKeys {
  MeetingIcebreakerKeys._();

  static const Key rouletteDialog = Key('meeting_roulette_dialog');
  static const Key rouletteWheel = Key('meeting_roulette_wheel');
  static const Key spinButton = Key('meeting_roulette_spin_button');
  static const Key winnerBanner = Key('meeting_roulette_winner_banner');
  static const Key optOutButton = Key('meeting_roulette_opt_out_button');
  static const Key alcoholNotice = Key('meeting_roulette_alcohol_notice');

  static const Key resultSheet = Key('meeting_game_result_sheet');
  static const Key resultTitle = Key('meeting_game_result_title');
  static const Key resultNumber = Key('meeting_game_result_number');
  static const Key resultCloseButton = Key('meeting_game_result_close');
  static const Key resultSpinAgainButton = Key(
    'meeting_game_result_spin_again',
  );
  static const Key resultBombTimerButton = Key(
    'meeting_game_result_bomb_timer',
  );

  static const Key bombScreen = Key('bomb_pass_timer_screen');
  static const Key bombHiddenTimer = Key('bomb_pass_hidden_timer');
  static const Key bombStartButton = Key('bomb_pass_start_button');
  static const Key bombRestartButton = Key('bomb_pass_restart_button');
  static const Key bombExplosion = Key('bomb_pass_explosion');
  static const Key bombStatusText = Key('bomb_pass_status_text');

  /// 각 룰렛 칸의 semantic 노드 (screen reader 전용).
  static Key segmentSemantics(int index) =>
      Key('meeting_roulette_segment_$index');
}
