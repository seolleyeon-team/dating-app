// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 폭탄 돌리기 테스트 (컨트롤러 + 화면)
// 경로: test/features/meeting_icebreaker/bomb_pass_timer_test.dart
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/application/bomb_pass_timer_controller.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/bomb_pass_timer.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/bomb_pass_timer_screen.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/meeting_icebreaker_keys.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/services/meeting_icebreaker_audio_service.dart';

import 'meeting_icebreaker_test_support.dart';

void main() {
  group('폭탄 타이머 컨트롤러', () {
    testWidgets('시작 전에는 대기 상태다', (tester) async {
      final controller = BombPassTimerController(random: FixedRandom(<int>[4]));
      expect(controller.phase, BombPassPhase.ready);
      expect(controller.isReady, isTrue);
      expect(controller.isRunning, isFalse);
      expect(controller.hasExploded, isFalse);
      controller.dispose();
    });

    testWidgets('숨겨진 시간이 지나면 폭발한다', (tester) async {
      // nextInt(15) -> 4 이므로 숨겨진 시간은 5초
      final controller = BombPassTimerController(random: FixedRandom(<int>[4]));
      var exploded = 0;
      controller.onExploded = () => exploded += 1;

      controller.start();
      expect(controller.isRunning, isTrue);

      await tester.pump(const Duration(seconds: 4));
      expect(controller.hasExploded, isFalse);
      expect(exploded, 0);

      await tester.pump(const Duration(seconds: 1));
      expect(controller.hasExploded, isTrue);
      expect(exploded, 1);

      controller.dispose();
    });

    testWidgets('최소 1초 / 최대 15초 값에서도 동작한다', (tester) async {
      final shortest = BombPassTimerController(random: FixedRandom(<int>[0]));
      shortest.start();
      await tester.pump(const Duration(milliseconds: 999));
      expect(shortest.hasExploded, isFalse);
      await tester.pump(const Duration(milliseconds: 2));
      expect(shortest.hasExploded, isTrue);
      shortest.dispose();

      final longest = BombPassTimerController(random: FixedRandom(<int>[14]));
      longest.start();
      await tester.pump(const Duration(seconds: 14, milliseconds: 900));
      expect(longest.hasExploded, isFalse);
      await tester.pump(const Duration(milliseconds: 200));
      expect(longest.hasExploded, isTrue);
      longest.dispose();
    });

    testWidgets('중복 시작을 막는다', (tester) async {
      final controller = BombPassTimerController(random: FixedRandom(<int>[2]));
      var tickingStarts = 0;
      controller.onTickingStart = () => tickingStarts += 1;

      controller.start();
      controller.start();
      controller.start();

      expect(tickingStarts, 1);
      expect(controller.isRunning, isTrue);

      await tester.pump(const Duration(seconds: 4));
      expect(controller.hasExploded, isTrue);

      // 폭발 후 start()는 아무 일도 하지 않는다.
      controller.start();
      expect(tickingStarts, 1);

      controller.dispose();
    });

    testWidgets('폭발하면 째깍째깍을 멈춘다', (tester) async {
      final controller = BombPassTimerController(random: FixedRandom(<int>[1]));
      var stops = 0;
      controller.onTickingStop = () => stops += 1;

      controller.start();
      expect(stops, 0);
      await tester.pump(const Duration(seconds: 3));
      expect(controller.hasExploded, isTrue);
      expect(stops, 1);

      controller.dispose();
      // dispose도 소리를 멈춘다.
      expect(stops, 2);
    });

    testWidgets('background에서 돌아오면 deadline을 다시 확인한다', (tester) async {
      final clock = FakeClock(DateTime.utc(2026, 7, 31, 21, 0, 0));
      // 숨겨진 시간 11초
      final controller = BombPassTimerController(
        random: FixedRandom(<int>[10]),
        clock: clock.call,
      );

      controller.start();
      // 화면이 background에 있는 동안 timer가 늦게 도착한 상황을 만든다.
      clock.advance(const Duration(seconds: 12));
      expect(controller.hasExploded, isFalse);

      controller.handleAppResumed();
      expect(controller.hasExploded, isTrue);

      // deadline 처리 후 예약된 timer는 취소된다.
      await tester.pump(const Duration(seconds: 20));
      controller.dispose();
    });

    testWidgets('deadline 전에 돌아오면 계속 진행한다', (tester) async {
      final clock = FakeClock(DateTime.utc(2026, 7, 31, 21, 0, 0));
      final controller = BombPassTimerController(
        random: FixedRandom(<int>[10]),
        clock: clock.call,
      );

      controller.start();
      clock.advance(const Duration(seconds: 3));
      controller.handleAppResumed();
      expect(controller.isRunning, isTrue);
      expect(controller.hasExploded, isFalse);

      controller.dispose();
    });

    testWidgets('다시 시작하면 새 숨겨진 시간을 뽑는다', (tester) async {
      // 첫 게임 3초(nextInt->2), 두 번째 게임 9초(nextInt->8)
      final controller = BombPassTimerController(
        random: FixedRandom(<int>[2, 8]),
      );

      controller.start();
      await tester.pump(const Duration(seconds: 3));
      expect(controller.hasExploded, isTrue);

      controller.restart();
      expect(controller.phase, BombPassPhase.ready);

      controller.start();
      // 이전 값(3초)을 재사용했다면 여기서 이미 터졌어야 한다.
      await tester.pump(const Duration(seconds: 4));
      expect(controller.hasExploded, isFalse);

      await tester.pump(const Duration(seconds: 6));
      expect(controller.hasExploded, isTrue);

      controller.dispose();
    });

    testWidgets('dispose하면 timer가 남지 않는다', (tester) async {
      final controller = BombPassTimerController(random: FixedRandom(<int>[9]));
      var exploded = 0;
      controller.onExploded = () => exploded += 1;

      controller.start();
      controller.dispose();

      await tester.pump(const Duration(seconds: 30));
      expect(exploded, 0);
    });

    testWidgets('화면 이탈 시 소리를 멈춘다', (tester) async {
      final controller = BombPassTimerController(random: FixedRandom(<int>[6]));
      var stops = 0;
      controller.onTickingStop = () => stops += 1;

      controller.start();
      controller.stopForNavigation();
      expect(stops, 1);

      await tester.pump(const Duration(seconds: 20));
      controller.dispose();
    });
  });

  group('폭탄 화면', () {
    Future<SilentMeetingIcebreakerAudioService> pumpScreen(
      WidgetTester tester, {
      List<int> draws = const <int>[4],
      bool failingAudio = false,
      double textScale = 1.0,
      Size size = const Size(400, 800),
      bool disableAnimations = false,
    }) async {
      final audio = SilentMeetingIcebreakerAudioService(failing: failingAudio);
      await tester.pumpWidget(
        icebreakerScreenHost(
          BombPassTimerScreen(audioService: audio, random: FixedRandom(draws)),
          size: size,
          textScale: textScale,
          disableAnimations: disableAnimations,
        ),
      );
      await tester.pump();
      return audio;
    }

    testWidgets('숨겨진 타이머를 ??:?? 로만 보여준다', (tester) async {
      await pumpScreen(tester);

      expect(find.byKey(MeetingIcebreakerKeys.bombScreen), findsOneWidget);
      expect(find.text(kBombPassHiddenTimerMask), findsOneWidget);
      expect(find.text('폭탄 돌리기'), findsOneWidget);
      expect(find.text('누구에게서 터질지는 아무도 몰라요!'), findsOneWidget);

      // 화면 어디에도 초 단위 숫자가 노출되지 않는다.
      final texts = tester
          .widgetList<Text>(find.byType(Text))
          .map((t) => t.data ?? '')
          .toList();
      for (final text in texts) {
        expect(RegExp(r'\d').hasMatch(text), isFalse, reason: '숫자가 노출됨: $text');
      }

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('시작 버튼을 누르면 진행 상태가 되고 소리가 시작된다', (tester) async {
      final audio = await pumpScreen(tester, draws: <int>[4]);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();

      expect(find.text('게임 진행 중…'), findsOneWidget);
      expect(find.text(kBombPassHiddenTimerMask), findsOneWidget);
      expect(audio.startTickingCalls, 1);

      // 진행 중에는 버튼이 비활성이라 중복 입력이 불가능하다.
      final button = tester.widget<FilledButton>(
        find.byKey(MeetingIcebreakerKeys.bombStartButton),
      );
      expect(button.onPressed, isNull);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('숨겨진 시간이 지나면 폭발 문구와 다시 시작 버튼이 나온다', (tester) async {
      final audio = await pumpScreen(tester, draws: <int>[4]);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 800));

      expect(find.byKey(MeetingIcebreakerKeys.bombExplosion), findsOneWidget);
      expect(find.text(kBombPassExplodedTitle), findsOneWidget);
      expect(find.text(kBombPassExplodedBody), findsOneWidget);
      expect(
        find.byKey(MeetingIcebreakerKeys.bombRestartButton),
        findsOneWidget,
      );
      expect(find.byKey(MeetingIcebreakerKeys.bombStartButton), findsNothing);

      expect(audio.explosionCalls, 1);
      expect(audio.stopTickingCalls, greaterThanOrEqualTo(1));

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('다시 시작하면 대기 상태로 돌아간다', (tester) async {
      await pumpScreen(tester, draws: <int>[0, 9]);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(milliseconds: 800));
      expect(
        find.byKey(MeetingIcebreakerKeys.bombRestartButton),
        findsOneWidget,
      );

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombRestartButton));
      await tester.pump();

      expect(find.byKey(MeetingIcebreakerKeys.bombStartButton), findsOneWidget);
      expect(find.text('게임 시작하기'), findsOneWidget);
      expect(find.text(kBombPassExplodedTitle), findsNothing);
      expect(find.text(kBombPassHiddenTimerMask), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('소리 재생이 실패해도 게임은 진행되고 안내를 보여준다', (tester) async {
      await pumpScreen(tester, draws: <int>[0], failingAudio: true);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(milliseconds: 800));

      // 시각적 게임은 정상 진행된다.
      expect(find.text(kBombPassExplodedBody), findsOneWidget);
      expect(find.text('소리를 재생할 수 없어 화면으로만 진행돼요.'), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('semantics에 실제 시간을 노출하지 않는다', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpScreen(tester, draws: <int>[7]);

      final semantics = tester.getSemantics(
        find.byKey(MeetingIcebreakerKeys.bombHiddenTimer),
      );
      expect(semantics.label, kBombPassHiddenTimerSemanticLabel);
      expect(RegExp(r'\d').hasMatch(semantics.label), isFalse);
      expect(RegExp(r'\d').hasMatch(semantics.value), isFalse);

      await tester.pumpWidget(const SizedBox());
      handle.dispose();
    });

    testWidgets('큰 글씨에서도 버튼이 넘치지 않는다', (tester) async {
      await pumpScreen(tester, textScale: 2.0, size: const Size(360, 690));
      expect(tester.takeException(), isNull);
      expect(find.byKey(MeetingIcebreakerKeys.bombStartButton), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('작은 화면에서도 레이아웃이 깨지지 않는다', (tester) async {
      await pumpScreen(tester, size: const Size(320, 560));
      expect(tester.takeException(), isNull);
      expect(find.text(kBombPassHiddenTimerMask), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('reduce motion에서도 폭발까지 진행된다', (tester) async {
      await pumpScreen(tester, draws: <int>[0], disableAnimations: true);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(milliseconds: 800));

      expect(find.text(kBombPassExplodedBody), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('화면을 벗어나면 오디오를 정리한다', (tester) async {
      final audio = await pumpScreen(tester, draws: <int>[9]);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.bombStartButton));
      await tester.pump();
      expect(audio.startTickingCalls, 1);

      await tester.pumpWidget(const SizedBox());
      await tester.pump();

      expect(audio.disposeCalls, greaterThanOrEqualTo(1));
      expect(audio.stopTickingCalls, greaterThanOrEqualTo(1));

      // dispose 후 남은 timer가 폭발을 일으키지 않는다.
      await tester.pump(const Duration(seconds: 30));
      expect(audio.explosionCalls, 0);
    });
  });
}
