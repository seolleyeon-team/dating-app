// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 회전 컨트롤러 테스트
// 경로: test/features/meeting_icebreaker/meeting_roulette_controller_test.dart
// =============================================================================

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/application/meeting_roulette_controller.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_game.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_roulette_spin.dart';

import 'meeting_icebreaker_test_support.dart';

void main() {
  MeetingRouletteController build({
    required List<int> draws,
    bool reduceMotion = false,
    bool alcoholFreeCopy = false,
  }) {
    return MeetingRouletteController(
      vsync: const TestVSync(),
      games: buildMeetingRouletteGames(alcoholFreeCopy: alcoholFreeCopy),
      random: FixedRandom(draws),
      reduceMotion: reduceMotion,
    );
  }

  /// 회전 애니메이션이 끝날 때까지 프레임을 진행한다.
  Future<void> runSpin(
    WidgetTester tester,
    MeetingRouletteController controller,
  ) async {
    await tester.pump();
    for (var i = 0; i < 400; i++) {
      if (controller.phase != MeetingRoulettePhase.spinning) break;
      await tester.pump(const Duration(milliseconds: 32));
    }
  }

  /// 당첨 조명 2초를 지나 설명 창 단계까지 진행한다.
  Future<void> runReveal(
    WidgetTester tester,
    MeetingRouletteController controller,
  ) async {
    await tester.pump(controller.celebrationDelay);
    await tester.pump();
  }

  testWidgets('주입한 난수의 칸에서 정확히 멈춘다', (tester) async {
    for (
      var expected = 0;
      expected < kMeetingRouletteSegmentCount;
      expected++
    ) {
      final controller = build(draws: <int>[expected]);

      controller.spin();
      expect(controller.winningIndex, expected);
      expect(controller.phase, MeetingRoulettePhase.spinning);

      await runSpin(tester, controller);

      expect(controller.phase, MeetingRoulettePhase.celebrating);
      // 결과 index와 시각적 위치(회전 각도)가 어긋나지 않는다.
      expect(meetingRouletteWinningIndex(controller.rotation), expected);
      expect(controller.winningGame!.number, expected + 1);

      await runReveal(tester, controller);
      expect(controller.phase, MeetingRoulettePhase.revealed);

      controller.dispose();
    }
  });

  testWidgets('회전 중에는 다시 돌릴 수 없다 (중복 tap 방지)', (tester) async {
    final random = FixedRandom(<int>[2, 5]);
    final controller = MeetingRouletteController(
      vsync: const TestVSync(),
      games: buildMeetingRouletteGames(),
      random: random,
    );

    controller.spin();
    controller.spin();
    controller.spin();

    expect(random.drawCount, 1);
    expect(controller.winningIndex, 2);
    expect(controller.canSpin, isFalse);

    await runSpin(tester, controller);
    // 조명 표시 중에도 다시 돌릴 수 없다.
    expect(controller.canSpin, isFalse);

    await runReveal(tester, controller);
    expect(controller.canSpin, isTrue);

    controller.dispose();
  });

  testWidgets('설명 창은 당첨 2초 뒤에 열린다', (tester) async {
    final controller = build(draws: <int>[3]);

    MeetingRouletteGame? revealed;
    controller.onRevealReady = (game) => revealed = game;

    controller.spin();
    await runSpin(tester, controller);

    expect(revealed, isNull);
    await tester.pump(const Duration(milliseconds: 1900));
    expect(revealed, isNull, reason: '2초 전에는 설명 창을 열지 않는다');

    await tester.pump(const Duration(milliseconds: 200));
    expect(revealed, isNotNull);
    expect(revealed!.type, MeetingRouletteGameType.bombPass);
    expect(revealed!.opensBombTimer, isTrue);

    controller.dispose();
  });

  testWidgets('dispose 이후에는 설명 창 콜백이 실행되지 않는다', (tester) async {
    final controller = build(draws: <int>[1]);

    var revealCalls = 0;
    controller.onRevealReady = (_) => revealCalls += 1;

    controller.spin();
    await runSpin(tester, controller);
    expect(controller.phase, MeetingRoulettePhase.celebrating);

    // 2초 지연 도중 화면이 닫힌 상황
    controller.dispose();
    await tester.pump(const Duration(seconds: 3));

    expect(revealCalls, 0);
  });

  testWidgets('reset 후에는 다시 돌릴 수 있다', (tester) async {
    final random = FixedRandom(<int>[0, 6]);
    final controller = MeetingRouletteController(
      vsync: const TestVSync(),
      games: buildMeetingRouletteGames(),
      random: random,
    );

    controller.spin();
    await runSpin(tester, controller);
    await runReveal(tester, controller);

    controller.reset();
    expect(controller.phase, MeetingRoulettePhase.idle);
    expect(controller.isHighlighting, isFalse);

    controller.spin();
    expect(random.drawCount, 2);
    expect(controller.winningIndex, 6);

    await runSpin(tester, controller);
    expect(meetingRouletteWinningIndex(controller.rotation), 6);

    await runReveal(tester, controller);
    controller.dispose();
  });

  testWidgets('이전 회전 각도가 남아 있어도 결과 위치가 맞는다', (tester) async {
    final controller = MeetingRouletteController(
      vsync: const TestVSync(),
      games: buildMeetingRouletteGames(),
      random: FixedRandom(<int>[4, 7, 1]),
    );

    for (final expected in <int>[4, 7, 1]) {
      controller.spin();
      await runSpin(tester, controller);
      expect(meetingRouletteWinningIndex(controller.rotation), expected);
      await runReveal(tester, controller);
      controller.reset();
    }

    controller.dispose();
  });

  testWidgets('회전 중 칸 경계를 지날 때 tick이 발생한다', (tester) async {
    final controller = build(draws: <int>[5]);

    var ticks = 0;
    controller.onSegmentTick = () => ticks += 1;

    controller.spin();
    await runSpin(tester, controller);

    // 5바퀴 = 40칸을 지나므로 tick이 충분히 발생한다.
    expect(ticks, greaterThan(20));
    expect(controller.segmentTickCount, ticks);

    await runReveal(tester, controller);
    controller.dispose();
  });

  testWidgets('reduce motion에서는 회전을 단순화하고 tick을 쓰지 않는다', (tester) async {
    final controller = build(draws: <int>[2], reduceMotion: true);

    var ticks = 0;
    controller.onSegmentTick = () => ticks += 1;

    expect(controller.reduceMotion, isTrue);
    expect(controller.spinDuration, kMeetingRouletteReducedSpinDuration);
    expect(
      controller.celebrationDelay,
      kMeetingRouletteReducedCelebrationDelay,
    );

    controller.spin();
    await runSpin(tester, controller);

    expect(ticks, 0);
    expect(meetingRouletteWinningIndex(controller.rotation), 2);

    await runReveal(tester, controller);
    expect(controller.phase, MeetingRoulettePhase.revealed);

    controller.dispose();
  });

  testWidgets('무알코올 문구로 만든 룰렛도 8칸을 유지한다', (tester) async {
    final controller = build(draws: <int>[5], alcoholFreeCopy: true);

    expect(controller.games.length, kMeetingRouletteSegmentCount);
    expect(controller.games[5].title, kMeetingRouletteNonAlcoholPenaltyTitle);

    controller.spin();
    await runSpin(tester, controller);
    expect(controller.winningGame!.number, 6);
    expect(controller.winningGame!.mentionsAlcohol, isFalse);

    await runReveal(tester, controller);
    controller.dispose();
  });
}
