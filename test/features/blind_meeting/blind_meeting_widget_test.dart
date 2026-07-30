// 블라인드 취향 미팅 UI 위젯 테스트

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_feedback.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_public_profile.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/widgets/blind_meeting_action_sheets.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_dna_wizard_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/widgets/blind_meeting_event_card.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/widgets/blind_meeting_profile_card.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/widgets/blind_meeting_recommendation_banner.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/theme/blind_meeting_palette.dart';

Widget host(Widget child) => MaterialApp(home: Scaffold(body: child));

BlindMeetingProfileSnapshot profile({
  DrinkingLevel? drinking = DrinkingLevel.sometimes,
  SmokingStatus? smoking = SmokingStatus.nonSmoker,
  List<String> interests = const ['커피', '영화', '농구'],
  String? mbti = 'ENFP',
}) {
  return BlindMeetingProfileSnapshot(
    userId: 'u1',
    nickname: '민지',
    department: '컴퓨터과학과',
    mbti: mbti,
    interests: interests,
    drinkingLevel: drinking,
    smokingStatus: smoking,
    schoolVerified: true,
    onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
  );
}

void main() {
  group('이벤트 탭 카드', () {
    testWidgets('블라인드 취향 미팅 문구와 CTA를 보여준다', (tester) async {
      await tester.pumpWidget(host(const BlindMeetingEventCard()));
      await tester.pumpAndSettle();

      expect(find.text('블라인드 취향 미팅'), findsOneWidget);
      expect(find.text('취향 미팅 참가하기'), findsOneWidget);
      expect(find.textContaining('혼자 신청해도 설레연이 3:3 팀을 구성해드려요'), findsOneWidget);
    });

    testWidgets('랜덤 매칭 문구와 슬롯머신 요소가 없다', (tester) async {
      await tester.pumpWidget(host(const BlindMeetingEventCard()));
      await tester.pumpAndSettle();

      expect(find.textContaining('랜덤'), findsNothing);
      expect(find.text('RANDOM MATCHING'), findsNothing);
      expect(find.byIcon(Icons.shuffle), findsNothing);
      expect(find.byIcon(Icons.casino), findsNothing);
    });
  });

  group('DNA wizard', () {
    testWidgets('1/4 대화 분위기부터 시작한다', (tester) async {
      await tester.pumpWidget(
        host(BlindMeetingDnaWizardScreen(profile: profile())),
      );
      await tester.pumpAndSettle();

      expect(find.text('1/4'), findsOneWidget);
      expect(find.text('어떤 분위기의 대화를 선호하나요?'), findsOneWidget);
      expect(find.text('차분하게 이야기하는 분위기'), findsOneWidget);
    });

    testWidgets('선택 전에는 다음으로 넘어갈 수 없다', (tester) async {
      await tester.pumpWidget(
        host(BlindMeetingDnaWizardScreen(profile: profile())),
      );
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });

    testWidgets('네 단계를 지나면 온보딩 값을 보여준다', (tester) async {
      await tester.pumpWidget(
        host(BlindMeetingDnaWizardScreen(profile: profile())),
      );
      await tester.pumpAndSettle();

      Future<void> pickFirstAndNext(String label) async {
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
        await tester.tap(find.text('다음'));
        await tester.pumpAndSettle();
      }

      await pickFirstAndNext('차분하게 이야기하는 분위기');
      expect(find.text('2/4'), findsOneWidget);
      await pickFirstAndNext('먼저 대화를 시작하는 편이에요');
      expect(find.text('3/4'), findsOneWidget);
      await pickFirstAndNext('연애와 친구 모두 열려 있어요');
      expect(find.text('4/4'), findsOneWidget);

      // 온보딩에서 이미 받은 값은 다시 묻지 않고 요약으로 보여준다.
      expect(find.text('이미 등록한 프로필을 사용해요'), findsOneWidget);
      expect(find.text('가끔'), findsOneWidget);
      expect(find.text('비흡연'), findsOneWidget);
      expect(find.text('ENFP'), findsOneWidget);
      expect(find.textContaining('커피'), findsWidgets);
    });

    testWidgets('비음주가 아니면 전원 비음주 조건을 선택할 수 없다', (tester) async {
      await tester.pumpWidget(
        host(
          BlindMeetingDnaWizardScreen(
            profile: profile(drinking: DrinkingLevel.often),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('차분하게 이야기하는 분위기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('먼저 대화를 시작하는 편이에요'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('연애와 친구 모두 열려 있어요'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('음주 정도가 \'전혀 안 함\'일 때 선택할 수 있어요'),
        findsOneWidget,
      );

      // 비활성 옵션을 눌러도 선택되지 않는다.
      await tester.tap(
        find.text(AlcoholCompanionPreference.allSober.label),
        warnIfMissed: false,
      );
      await tester.pumpAndSettle();
      // '상관없어요'는 음주·흡연 두 곳에 있으므로 흡연(마지막) 항목을 고른다.
      await tester.tap(
        find.text(SmokingCompanionPreference.noPreference.label).last,
      );
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });

    testWidgets('라이프스타일 값이 없으면 보완 안내를 보여준다', (tester) async {
      await tester.pumpWidget(
        host(
          BlindMeetingDnaWizardScreen(
            profile: profile(drinking: null, smoking: null),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('차분하게 이야기하는 분위기'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('상황에 따라 달라요'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('새로운 친구'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();

      expect(find.text('라이프스타일 수정하기'), findsOneWidget);
    });
  });

  group('참여 날짜 선택 캘린더', () {
    // KST 2026-08-01 기준 → 선택 가능: 2026-08-02 ~ 2026-08-22
    final now = DateTime.utc(2026, 8, 1);

    BlindMeetingDnaDraft draft({
      AlcoholCompanionPreference alcohol =
          AlcoholCompanionPreference.noPreference,
    }) {
      return BlindMeetingDnaDraft(
        profile: profile(),
        atmosphere: ConversationAtmosphere.calm,
        initiative: ConversationInitiative.adaptive,
        purpose: MeetingPurpose.both,
        alcoholPreference: alcohol,
        smokingPreference: SmokingCompanionPreference.noPreference,
      );
    }

    Widget screen({
      AlcoholCompanionPreference alcohol =
          AlcoholCompanionPreference.noPreference,
    }) {
      return host(
        BlindMeetingScheduleScreen(
          draft: draft(alcohol: alcohol),
          now: now,
          restoreExistingSelection: false,
        ),
      );
    }

    /// 날짜 셀을 semantics label로 찾는다 (같은 숫자가 여러 곳에 있어도 안전).
    Finder dayCell(int day, {required String weekday}) =>
        find.bySemanticsLabel(RegExp('^8월 $day일 $weekday요일'));

    testWidgets('캘린더와 안내 문구를 보여준다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      expect(find.text('2026년 8월'), findsOneWidget);
      expect(find.text('참여 가능한 날짜를\n골라주세요'), findsOneWidget);
      expect(find.textContaining('앞으로 21일'), findsOneWidget);
      expect(find.textContaining('단체 채팅방에서 함께 정해요'), findsOneWidget);
      // 요일 헤더
      expect(find.text('월'), findsOneWidget);
      expect(find.text('일'), findsOneWidget);
    });

    testWidgets('아침·오후·저녁 시간대 선택 UI가 없다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      expect(find.text('아침'), findsNothing);
      expect(find.text('오후'), findsNothing);
      expect(find.text('저녁'), findsNothing);
      expect(find.text('늦은 저녁'), findsNothing);
    });

    testWidgets('날짜를 고르기 전에는 제출할 수 없다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      expect(find.text('가능한 날짜를 선택해주세요'), findsOneWidget);
      expect(find.text('선택한 날짜 없음'), findsOneWidget);
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });

    testWidgets('오늘은 선택할 수 없고 내일은 선택할 수 있다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      // 8월 1일(토)은 오늘 → 비활성
      expect(find.text('오늘'), findsOneWidget);
      await tester.tap(dayCell(1, weekday: '토'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 없음'), findsOneWidget);

      // 8월 2일(일)은 내일 → 활성
      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);
    });

    testWidgets('범위 마지막 날짜(8월 22일)는 선택 가능, 범위 밖(8월 23일)은 불가', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      await tester.tap(dayCell(22, weekday: '토'));
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);

      await tester.tap(dayCell(23, weekday: '일'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);
    });

    testWidgets('날짜를 복수 선택하고 다시 눌러 해제한다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();
      await tester.tap(dayCell(5, weekday: '수'));
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 2개'), findsOneWidget);
      expect(find.text('선택한 2개 날짜로 신청하기'), findsOneWidget);

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNotNull);

      // 같은 날짜를 다시 누르면 해제된다.
      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);
    });

    testWidgets('선택 요약을 정렬된 형태로 보여준다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      await tester.tap(dayCell(5, weekday: '수'));
      await tester.pumpAndSettle();
      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();

      expect(find.text('8월 2일(일), 8월 5일(수)'), findsOneWidget);
    });

    testWidgets('선택 날짜가 많으면 요약으로 줄인다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      for (final day in [2, 3, 4, 5]) {
        await tester.tap(find.bySemanticsLabel(RegExp('^8월 $day일 ')));
        await tester.pumpAndSettle();
      }

      expect(find.textContaining('외 2일'), findsOneWidget);
      expect(find.text('선택한 날짜 4개'), findsOneWidget);
    });

    testWidgets('범위가 한 달 안이면 월 이동이 모두 막힌다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      final previous = tester.widget<IconButton>(
        find.widgetWithIcon(IconButton, Icons.chevron_left),
      );
      final next = tester.widget<IconButton>(
        find.widgetWithIcon(IconButton, Icons.chevron_right),
      );
      expect(previous.onPressed, isNull);
      expect(next.onPressed, isNull);
    });

    testWidgets('범위가 두 달에 걸치면 다음 달만 탐색할 수 있다', (tester) async {
      // KST 2026-08-20 기준 → 선택 가능: 2026-08-21 ~ 2026-09-10
      await tester.pumpWidget(
        host(
          BlindMeetingScheduleScreen(
            draft: draft(),
            now: DateTime.utc(2026, 8, 20),
            restoreExistingSelection: false,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('2026년 8월'), findsOneWidget);
      final previous = tester.widget<IconButton>(
        find.widgetWithIcon(IconButton, Icons.chevron_left),
      );
      expect(previous.onPressed, isNull);

      await tester.tap(find.widgetWithIcon(IconButton, Icons.chevron_right));
      await tester.pumpAndSettle();
      expect(find.text('2026년 8월'), findsNothing);
      expect(find.text('2026년 9월'), findsOneWidget);

      // 9월 10일은 선택 가능, 9월 11일은 범위 밖
      await tester.tap(find.bySemanticsLabel(RegExp('^9월 10일 ')));
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);
      await tester.tap(
        find.bySemanticsLabel(RegExp('^9월 11일 ')),
        warnIfMissed: false,
      );
      await tester.pumpAndSettle();
      expect(find.text('선택한 날짜 1개'), findsOneWidget);

      // 다음 달로는 더 이상 못 가고, 이전 달로는 되돌아갈 수 있다.
      final next = tester.widget<IconButton>(
        find.widgetWithIcon(IconButton, Icons.chevron_right),
      );
      expect(next.onPressed, isNull);
      await tester.tap(find.widgetWithIcon(IconButton, Icons.chevron_left));
      await tester.pumpAndSettle();
      expect(find.text('2026년 8월'), findsOneWidget);
    });

    testWidgets('전원 비음주를 고른 사용자에게 무알코올 안내를 보여준다', (tester) async {
      await tester.pumpWidget(
        screen(alcohol: AlcoholCompanionPreference.allSober),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('무알코올 미팅으로 신청돼요'), findsOneWidget);
    });

    testWidgets('권장 개수 미달이면 안내하고, 채우면 사라진다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      // 0개일 때는 권장 안내를 띄우지 않는다 (아직 아무것도 안 골랐으므로).
      expect(find.textContaining('개 이상 고르면'), findsNothing);

      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();
      expect(find.textContaining('개 이상 고르면'), findsOneWidget);

      await tester.tap(dayCell(3, weekday: '월'));
      await tester.pumpAndSettle();
      await tester.tap(dayCell(4, weekday: '화'));
      await tester.pumpAndSettle();

      // 3개를 채우면 안내가 사라지고, 그래도 제출은 계속 가능하다.
      expect(find.textContaining('개 이상 고르면'), findsNothing);
      expect(find.text('선택한 3개 날짜로 신청하기'), findsOneWidget);
    });

    testWidgets('권장 개수 미달이어도 제출을 막지 않는다', (tester) async {
      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();

      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNotNull);
    });

    testWidgets('작은 화면(320x568)에서도 overflow가 없다', (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(screen());
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.tap(dayCell(2, weekday: '일'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('글자 크기를 키워도 overflow가 없다', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(1.6)),
            child: Scaffold(
              body: BlindMeetingScheduleScreen(
                draft: draft(),
                now: now,
                restoreExistingSelection: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  });

  group('추천 안내 배너', () {
    testWidgets('일반 미팅 문구를 잠시 보여준 뒤 사라진다', (tester) async {
      await tester.pumpWidget(
        host(const BlindMeetingRecommendationBanner(alcoholFree: false)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.text(blindMeetingRecommendationMessage), findsOneWidget);

      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();

      final opacity = tester.widget<AnimatedOpacity>(
        find.byType(AnimatedOpacity),
      );
      expect(opacity.opacity, 0);
    });

    testWidgets('무알코올 미팅은 전용 문구를 쓴다', (tester) async {
      await tester.pumpWidget(
        host(const BlindMeetingRecommendationBanner(alcoholFree: true)),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(
        find.text(blindMeetingAlcoholFreeRecommendationMessage),
        findsOneWidget,
      );

      // 예약된 숨김 타이머를 소진한다.
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
    });

    testWidgets('과장 표현을 쓰지 않는다', (tester) async {
      expect(blindMeetingRecommendationMessage, isNot(contains('최적')));
      expect(
        blindMeetingAlcoholFreeRecommendationMessage,
        isNot(contains('최적')),
      );
    });

    testWidgets('모션 감소 설정에서는 애니메이션 없이 표시한다', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: const Scaffold(
              body: BlindMeetingRecommendationBanner(alcoholFree: false),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(AnimatedOpacity), findsNothing);
      expect(find.text(blindMeetingRecommendationMessage), findsOneWidget);

      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
      expect(find.text(blindMeetingRecommendationMessage), findsNothing);
    });
  });

  group('공개 프로필 카드', () {
    const sample = BlindMeetingPublicProfile(
      userId: 'b1',
      nickname: '하늘',
      department: '경영학과',
      mbti: 'INFJ',
      topInterestIds: ['커피', '전시회', '러닝'],
      avatarSeed: 'b1',
      schoolVerified: true,
      safetyStampSummary: SafetyStampSummary(
        completedMeetings: 3,
        allCheckinsCompleted: true,
        allCheckoutsCompleted: true,
      ),
      oneLineIntro: '조용한 카페를 좋아해요',
    );

    testWidgets('닉네임·학과·MBTI·관심사·인증 배지를 보여준다', (tester) async {
      await tester.pumpWidget(
        host(const BlindMeetingProfileCard(profile: sample)),
      );
      await tester.pumpAndSettle();

      expect(find.text('하늘'), findsOneWidget);
      expect(find.text('경영학과 · INFJ'), findsOneWidget);
      expect(find.text('커피'), findsOneWidget);
      expect(find.text('학교 인증'), findsOneWidget);
      expect(find.text('안전도장 3회 모두 완료'), findsOneWidget);
      expect(find.text('조용한 카페를 좋아해요'), findsOneWidget);
    });

    testWidgets('실제 사진 대신 비식별 실루엣만 렌더링한다', (tester) async {
      await tester.pumpWidget(
        host(const BlindMeetingProfileCard(profile: sample)),
      );
      await tester.pumpAndSettle();

      expect(find.byType(Image), findsNothing);
      expect(find.byType(BlindMeetingSilhouetteAvatar), findsOneWidget);
    });

    testWidgets('같은 seed는 항상 같은 색을 쓴다', (tester) async {
      final first = BlindMeetingSilhouetteAvatar.tintFor(
        'b1',
        BlindMeetingPalette.light,
      );
      final second = BlindMeetingSilhouetteAvatar.tintFor(
        'b1',
        BlindMeetingPalette.light,
      );
      expect(first, second);
    });
  });

  group('약속잡기 투표 시트', () {
    testWidgets('시간을 고르지 않으면 투표할 수 없다', (tester) async {
      BlindMeetingScheduleVote? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  result = await showBlindMeetingScheduleVoteSheet(
                    context,
                    candidateDateKeys: const ['2026-08-01', '2026-08-03'],
                    venueOptions: const [
                      BlindMeetingVenueOption(
                        placeId: 'p1',
                        name: '보드게임 카페',
                        category: '카페',
                        alcoholFreeFriendly: true,
                      ),
                    ],
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('약속잡기'), findsOneWidget);
      expect(find.text('보드게임 카페 · 무알코올'), findsOneWidget);
      // 공통 가능 날짜만 후보로 보여준다.
      expect(find.text('8월 1일(토)'), findsOneWidget);
      expect(find.text('8월 3일(월)'), findsOneWidget);
      // 날짜를 고르기 전에는 시간대가 나오지 않는다.
      expect(find.text('날짜를 먼저 선택하면 시간을 고를 수 있어요.'), findsOneWidget);

      final disabled = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '투표하기'),
      );
      expect(disabled.onPressed, isNull);

      await tester.tap(find.text('8월 1일(토)'));
      await tester.pumpAndSettle();

      // 날짜를 고르면 시간대를 선택할 수 있다.
      final stillDisabled = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '투표하기'),
      );
      expect(stillDisabled.onPressed, isNull);

      await tester.tap(find.text('저녁 18:00~20:00'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('보드게임 카페 · 무알코올'));
      await tester.pumpAndSettle();

      final voteButton = find.widgetWithText(FilledButton, '투표하기');
      await tester.ensureVisible(voteButton);
      await tester.pumpAndSettle();
      await tester.tap(voteButton);
      await tester.pumpAndSettle();

      expect(result, isNotNull);
      expect(result!.preferredSlotIds, ['2026-08-01#evening']);
      expect(result!.preferredPlaceId, 'p1');
    });
  });

  group('가능한 날짜 추가 시트 (조건 완화)', () {
    // 서버가 빈 날짜 목록을 거부하므로, 이 시트 없이 완화를 요청하면 항상 실패한다.
    testWidgets('이미 신청한 날짜는 후보에서 빠지고 선택 후 결과를 돌려준다', (tester) async {
      List<String>? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  result = await showBlindMeetingExtraDatesSheet(
                    context,
                    alreadySelected: const {'2026-08-02'},
                    now: DateTime.utc(2026, 8, 1),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('가능한 날짜 추가'), findsOneWidget);
      // 이미 신청한 8월 2일은 후보에 없다.
      expect(find.text('8월 2일(일)'), findsNothing);
      expect(find.text('8월 3일(월)'), findsOneWidget);

      final disabled = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '추가할 날짜를 선택해주세요'),
      );
      expect(disabled.onPressed, isNull);

      await tester.tap(find.text('8월 3일(월)'));
      await tester.pumpAndSettle();
      final confirm = find.widgetWithText(FilledButton, '1개 날짜 추가하기');
      await tester.ensureVisible(confirm);
      await tester.pumpAndSettle();
      await tester.tap(confirm);
      await tester.pumpAndSettle();

      expect(result, ['2026-08-03']);
    });
  });

  group('안전도장 확인', () {
    testWidgets('도착/종료 안내 문구가 다르다', (tester) async {
      bool? checkin;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  checkin = await confirmBlindMeetingSafetyStamp(
                    context,
                    isCheckout: false,
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.text('도착 안전도장'), findsOneWidget);
      expect(find.textContaining('전원이 완료되면 미팅이 시작돼요'), findsOneWidget);

      await tester.tap(find.text('안전도장 찍기'));
      await tester.pumpAndSettle();
      expect(checkin, isTrue);
    });
  });

  group('만족도 문항', () {
    test('필수 문항 4개와 선택 사유가 정의되어 있다', () {
      expect(BlindMeetingFeedbackQuestion.values.length, 4);
      expect(BlindMeetingFeedbackReason.values.length, 6);
      expect(
        BlindMeetingFeedbackQuestion.ownTeamComfort.label,
        '우리 팀 분위기가 편했나요?',
      );
    });

    test('모든 문항이 채워져야 완료 상태가 된다', () {
      final incomplete = BlindMeetingFeedback(
        meetingId: 'm1',
        userId: 'u1',
        ratings: {BlindMeetingFeedbackQuestion.ownTeamComfort: 4},
      );
      expect(incomplete.isComplete, isFalse);

      final complete = BlindMeetingFeedback(
        meetingId: 'm1',
        userId: 'u1',
        ratings: {for (final q in BlindMeetingFeedbackQuestion.values) q: 4},
      );
      expect(complete.isComplete, isTrue);
    });
  });
}
