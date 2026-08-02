// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 팝업 / 설명 창 위젯 테스트
// 경로: test/features/meeting_icebreaker/meeting_roulette_widget_test.dart
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/core/constants/app_colors.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/data/meeting_icebreaker_analytics.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_game.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_roulette_spin.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/meeting_icebreaker_keys.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/meeting_icebreaker_palette.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/meeting_roulette_dialog.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/presentation/meeting_roulette_wheel.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/services/meeting_icebreaker_audio_service.dart';

import 'meeting_icebreaker_test_support.dart';

void main() {
  MeetingIcebreakerEntry entry({
    bool alcoholFreeCopy = false,
    bool optedOut = false,
    bool bombPassEnabled = true,
    String? sessionId = 'blind_m1',
  }) {
    return MeetingIcebreakerEntry(
      decision: MeetingIcebreakerEntryDecision.allowed,
      sessionId: sessionId,
      meetingId: 'm1',
      meetingKind: MeetingIcebreakerMeetingKind.blindTasteMeeting,
      alcoholFreeCopy: alcoholFreeCopy,
      optedOut: optedOut,
      bombPassEnabled: bombPassEnabled,
    );
  }

  Future<({FakeMeetingIcebreakerRepository repo, RecordingAnalyticsSink sink})>
  openDialog(
    WidgetTester tester, {
    List<int> draws = const <int>[3],
    MeetingIcebreakerEntry? withEntry,
    Size size = const Size(400, 1000),
    double textScale = 1.0,
    bool disableAnimations = false,
    ThemeData? theme,
    bool withRepository = true,
  }) async {
    final repo = FakeMeetingIcebreakerRepository();
    final sink = RecordingAnalyticsSink();
    final analytics = MeetingIcebreakerAnalytics(sink: sink);

    // 실제 렌더 표면 크기를 바꿔야 dialog route에도 적용된다.
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        theme: theme,
        // dialog route는 Navigator 아래에 push되므로 builder로 감싸야
        // 큰 글씨 / reduce motion 설정이 dialog에도 적용된다.
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.linear(textScale),
            disableAnimations: disableAnimations,
          ),
          child: child!,
        ),
        home: Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: ElevatedButton(
                onPressed: () => showMeetingRouletteDialog(
                  context: context,
                  entry: withEntry ?? entry(),
                  repository: withRepository ? repo : null,
                  analytics: analytics,
                  random: FixedRandom(draws),
                  audioService: SilentMeetingIcebreakerAudioService(),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    return (repo: repo, sink: sink);
  }

  /// 회전이 끝나 당첨 배너가 보일 때까지 프레임을 진행한다.
  Future<void> awaitWinner(WidgetTester tester) async {
    for (var i = 0; i < 500; i++) {
      if (find
          .byKey(MeetingIcebreakerKeys.winnerBanner)
          .evaluate()
          .isNotEmpty) {
        return;
      }
      await tester.pump(const Duration(milliseconds: 32));
    }
    fail('당첨 배너가 표시되지 않았다');
  }

  /// 설명 창(bottom sheet)이 열릴 때까지 프레임을 진행한다.
  Future<void> awaitResultSheet(WidgetTester tester) async {
    for (var i = 0; i < 120; i++) {
      if (find.byKey(MeetingIcebreakerKeys.resultSheet).evaluate().isNotEmpty) {
        await tester.pump(const Duration(milliseconds: 400));
        return;
      }
      await tester.pump(const Duration(milliseconds: 100));
    }
    fail('설명 창이 열리지 않았다');
  }

  Future<void> spin(WidgetTester tester) async {
    await tester.ensureVisible(find.byKey(MeetingIcebreakerKeys.spinButton));
    await tester.pump();
    await tester.tap(find.byKey(MeetingIcebreakerKeys.spinButton));
    await tester.pump();
  }

  group('룰렛 팝업', () {
    testWidgets('제목·설명·룰렛·안전 안내·CTA를 보여준다', (tester) async {
      await openDialog(tester);

      expect(find.byKey(MeetingIcebreakerKeys.rouletteDialog), findsOneWidget);
      expect(find.text('어색할 땐 룰렛 한 번!'), findsOneWidget);
      expect(find.text('여섯 명이 함께 할 게임을 골라드려요.'), findsOneWidget);
      expect(find.byType(MeetingRouletteWheel), findsOneWidget);
      expect(find.text(kMeetingRouletteParticipationNotice), findsOneWidget);
      expect(find.text('룰렛 돌리기'), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('8개 칸이 모두 표시된다', (tester) async {
      await openDialog(tester);

      for (var i = 0; i < kMeetingRouletteSegmentCount; i++) {
        expect(
          find.byKey(MeetingIcebreakerKeys.segmentSemantics(i)),
          findsOneWidget,
          reason: '$i번 칸 없음',
        );
      }
      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.games.length, kMeetingRouletteSegmentCount);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('회전 전에는 버튼이 활성, 회전 중에는 비활성이다', (tester) async {
      await openDialog(tester);

      var button = tester.widget<FilledButton>(
        find.byKey(MeetingIcebreakerKeys.spinButton),
      );
      expect(button.onPressed, isNotNull);

      await spin(tester);

      button = tester.widget<FilledButton>(
        find.byKey(MeetingIcebreakerKeys.spinButton),
      );
      expect(button.onPressed, isNull);
      expect(find.text('돌아가고 있어요…'), findsOneWidget);

      await awaitWinner(tester);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('회전이 끝나면 당첨 칸을 강조하고 조명을 켠다', (tester) async {
      await openDialog(tester, draws: <int>[2]);
      await spin(tester);
      await awaitWinner(tester);

      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.winningIndex, 2);
      expect(wheel.isHighlighting, isTrue);
      expect(meetingRouletteWinningIndex(wheel.rotation), 2);
      expect(find.textContaining('당첨 3번'), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('2초 뒤 설명 창에 게임명과 번호를 보여준다', (tester) async {
      await openDialog(tester, draws: <int>[0]);
      await spin(tester);
      await awaitWinner(tester);

      // 당첨 직후에는 설명 창이 없다.
      expect(find.byKey(MeetingIcebreakerKeys.resultSheet), findsNothing);

      await awaitResultSheet(tester);

      expect(find.byKey(MeetingIcebreakerKeys.resultSheet), findsOneWidget);
      final title = tester.widget<Text>(
        find.byKey(MeetingIcebreakerKeys.resultTitle),
      );
      final number = tester.widget<Text>(
        find.byKey(MeetingIcebreakerKeys.resultNumber),
      );
      expect(title.data, '귓속말게임');
      expect(number.data, '1');

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('폭탄 돌리기 당첨 시에만 타이머 CTA가 나온다', (tester) async {
      await openDialog(tester, draws: <int>[3]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      expect(
        tester.widget<Text>(find.byKey(MeetingIcebreakerKeys.resultTitle)).data,
        '폭탄 돌리기',
      );
      expect(
        find.byKey(MeetingIcebreakerKeys.resultBombTimerButton),
        findsOneWidget,
      );
      expect(find.text('타이머 열기'), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('다른 게임 설명 창에는 타이머 CTA가 없다', (tester) async {
      for (final draw in <int>[0, 1, 2, 4, 5, 6, 7]) {
        await openDialog(tester, draws: <int>[draw]);
        await spin(tester);
        await awaitWinner(tester);
        await awaitResultSheet(tester);

        expect(
          find.byKey(MeetingIcebreakerKeys.resultBombTimerButton),
          findsNothing,
          reason: '$draw번 칸에 타이머 CTA가 노출됨',
        );
        expect(find.text('타이머 열기'), findsNothing);

        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('타이머 열기를 누르면 폭탄 화면으로 이동한다', (tester) async {
      await openDialog(tester, draws: <int>[3]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.resultBombTimerButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(MeetingIcebreakerKeys.bombScreen), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('폭탄 게임 feature flag가 꺼지면 CTA를 숨긴다', (tester) async {
      await openDialog(
        tester,
        draws: <int>[3],
        withEntry: entry(bombPassEnabled: false),
      );
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      expect(
        find.byKey(MeetingIcebreakerKeys.resultBombTimerButton),
        findsNothing,
      );
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('닫기를 누르면 팝업이 사라진다', (tester) async {
      await openDialog(tester, draws: <int>[4]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.resultCloseButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(MeetingIcebreakerKeys.rouletteDialog), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('다시 돌리기를 누르면 룰렛으로 돌아간다', (tester) async {
      await openDialog(tester, draws: <int>[1, 5]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      await tester.tap(find.byKey(MeetingIcebreakerKeys.resultSpinAgainButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(MeetingIcebreakerKeys.rouletteDialog), findsOneWidget);
      final button = tester.widget<FilledButton>(
        find.byKey(MeetingIcebreakerKeys.spinButton),
      );
      expect(button.onPressed, isNotNull);

      await spin(tester);
      await awaitWinner(tester);
      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.winningIndex, 5);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('회전 중에는 바깥을 눌러도 닫히지 않는다', (tester) async {
      await openDialog(tester);
      await spin(tester);

      await tester.tapAt(const Offset(6, 6));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byKey(MeetingIcebreakerKeys.rouletteDialog), findsOneWidget);
      expect(find.text('회전이 끝나면 닫을 수 있어요.'), findsOneWidget);

      await awaitWinner(tester);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('음주 안내', () {
    testWidgets('기본 문구에는 음주 선택 안내가 함께 나온다', (tester) async {
      await openDialog(tester);

      expect(find.byKey(MeetingIcebreakerKeys.alcoholNotice), findsOneWidget);
      expect(find.text(kMeetingRouletteAlcoholNotice), findsOneWidget);
      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.games[5].title, kMeetingRouletteAlcoholPenaltyTitle);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('무알코올 미팅에서는 비음주 문구로 대체한다', (tester) async {
      await openDialog(
        tester,
        draws: <int>[5],
        withEntry: entry(alcoholFreeCopy: true),
      );

      expect(find.byKey(MeetingIcebreakerKeys.alcoholNotice), findsNothing);
      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.games.length, kMeetingRouletteSegmentCount);
      expect(wheel.games[5].title, kMeetingRouletteNonAlcoholPenaltyTitle);

      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      expect(
        tester.widget<Text>(find.byKey(MeetingIcebreakerKeys.resultTitle)).data,
        kMeetingRouletteNonAlcoholPenaltyTitle,
      );
      // 결과 창에도 음주 안내를 넣지 않는다.
      expect(find.text(kMeetingRouletteAlcoholNotice), findsNothing);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('음주 칸 결과 창에는 음주 선택 안내가 붙는다', (tester) async {
      await openDialog(tester, draws: <int>[5]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      expect(find.text(kMeetingRouletteAlcoholNotice), findsWidgets);
      expect(find.text(kMeetingRouletteParticipationNotice), findsWidgets);

      await tester.pumpWidget(const SizedBox());
    });
  });

  group('알림 opt-out', () {
    testWidgets('이번 미팅 알림만 끌 수 있다', (tester) async {
      final handles = await openDialog(tester);

      expect(find.text(kMeetingIcebreakerOptOutLabel), findsOneWidget);
      expect(find.text(kMeetingIcebreakerOptOutHint), findsOneWidget);

      await tester.ensureVisible(
        find.byKey(MeetingIcebreakerKeys.optOutButton),
      );
      await tester.pump();
      await tester.tap(find.byKey(MeetingIcebreakerKeys.optOutButton));
      await tester.pump();
      await tester.pump();

      expect(handles.repo.setOptOutCalls, 1);
      expect(handles.repo.lastOptOutRequested, isTrue);
      expect(find.text(kMeetingIcebreakerOptInLabel), findsOneWidget);
      expect(
        handles.sink.names,
        contains('meeting_icebreaker_prompt_opted_out'),
      );

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('이미 끈 상태면 다시 켜기 문구를 보여준다', (tester) async {
      await openDialog(tester, withEntry: entry(optedOut: true));
      expect(find.text(kMeetingIcebreakerOptInLabel), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('저장소가 없으면 opt-out 버튼을 숨긴다', (tester) async {
      await openDialog(tester, withRepository: false);
      expect(find.byKey(MeetingIcebreakerKeys.optOutButton), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('레이아웃과 테마', () {
    testWidgets('작은 화면에서도 오류 없이 그려진다', (tester) async {
      await openDialog(tester, size: const Size(320, 560));
      expect(tester.takeException(), isNull);
      expect(find.byType(MeetingRouletteWheel), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('큰 글씨에서도 버튼이 넘치지 않는다', (tester) async {
      await openDialog(tester, size: const Size(360, 690), textScale: 2.0);
      expect(tester.takeException(), isNull);
      expect(find.byKey(MeetingIcebreakerKeys.spinButton), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('reduce motion에서는 회전을 단순화한다', (tester) async {
      await openDialog(tester, draws: <int>[6], disableAnimations: true);

      await spin(tester);
      // 짧은 회전이라 1초 안에 끝난다.
      await tester.pump(const Duration(milliseconds: 900));
      expect(find.byKey(MeetingIcebreakerKeys.winnerBanner), findsOneWidget);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('설레연 테마 토큰을 사용한다 (카지노 톤 아님)', (tester) async {
      final theme = ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: AppColors.primary),
        extensions: const <ThemeExtension<dynamic>>[SeolThemeColors.light],
      );
      await openDialog(tester, theme: theme);

      final dialog = tester.widget<Dialog>(
        find.byKey(MeetingIcebreakerKeys.rouletteDialog),
      );
      expect(dialog.backgroundColor, SeolThemeColors.light.cardSurface);

      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.palette.background, SeolThemeColors.light.eventBackground);
      expect(wheel.palette.surfaceMuted, SeolThemeColors.light.pink50);
      // 검정 배경이나 어두운 네온 톤을 쓰지 않는다.
      expect(wheel.palette.segmentLight, isNot(Colors.black));
      expect(wheel.palette.segmentPink.computeLuminance(), greaterThan(0.5));

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('테마 확장이 없어도 기본 팔레트로 그려진다', (tester) async {
      await openDialog(tester);
      final wheel = tester.widget<MeetingRouletteWheel>(
        find.byType(MeetingRouletteWheel),
      );
      expect(wheel.palette.accent, MeetingIcebreakerPalette.light.accent);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('접근성', () {
    testWidgets('룰렛 semantics가 8칸 이름과 상태를 알린다', (tester) async {
      final handle = tester.ensureSemantics();
      await openDialog(tester, draws: <int>[7]);

      final semantics = tester.getSemantics(
        find.byKey(MeetingIcebreakerKeys.rouletteWheel),
      );
      for (final game in buildMeetingRouletteGames()) {
        expect(
          semantics.label.contains(game.title),
          isTrue,
          reason: '${game.title} semantic label 없음',
        );
      }
      expect(semantics.value, contains('돌릴 준비'));

      await spin(tester);
      await awaitWinner(tester);

      final after = tester.getSemantics(
        find.byKey(MeetingIcebreakerKeys.rouletteWheel),
      );
      expect(after.value, contains('두부 게임'));

      await tester.pumpWidget(const SizedBox());
      handle.dispose();
    });

    testWidgets('칸 번호마다 semantic label이 있다', (tester) async {
      final handle = tester.ensureSemantics();
      await openDialog(tester);

      final games = buildMeetingRouletteGames();
      for (var i = 0; i < games.length; i++) {
        final node = tester.getSemantics(
          find.byKey(MeetingIcebreakerKeys.segmentSemantics(i)),
        );
        expect(node.label, '${games[i].number}번 ${games[i].title}');
      }

      await tester.pumpWidget(const SizedBox());
      handle.dispose();
    });
  });

  group('analytics', () {
    testWidgets('노출·회전·결과 이벤트를 민감정보 없이 기록한다', (tester) async {
      final handles = await openDialog(tester, draws: <int>[3]);
      await spin(tester);
      await awaitWinner(tester);
      await awaitResultSheet(tester);

      expect(handles.sink.names, contains('meeting_roulette_shown'));
      expect(handles.sink.names, contains('meeting_roulette_spin_started'));
      expect(handles.sink.names, contains('meeting_roulette_spin_completed'));
      expect(handles.sink.names, contains('meeting_game_result_shown'));

      final completed = handles.sink.paramsFor(
        'meeting_roulette_spin_completed',
      )!;
      expect(completed['game_type'], 'bombPass');
      expect(completed['spin_duration_bucket'], '3_5s');

      for (final event in handles.sink.events) {
        expect(event.$2.containsKey('userId'), isFalse);
        expect(event.$2.containsKey('participantIds'), isFalse);
        expect(event.$2.containsKey('hiddenSeconds'), isFalse);
      }

      await tester.pumpWidget(const SizedBox());
    });
  });
}
