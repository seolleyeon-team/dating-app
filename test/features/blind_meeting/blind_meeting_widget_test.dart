// 블라인드 취향 미팅 UI 위젯 테스트

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_feedback.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_public_profile.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_slot.dart';
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

  group('일정 선택', () {
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

    testWidgets('시간을 고르기 전에는 제출할 수 없다', (tester) async {
      await tester.pumpWidget(
        host(
          BlindMeetingScheduleScreen(
            draft: draft(),
            now: DateTime.utc(2026, 8, 1),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('가능한 시간을 선택해주세요'), findsOneWidget);
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });

    testWidgets('시간을 고르면 선택 개수가 표시된다', (tester) async {
      await tester.pumpWidget(
        host(
          BlindMeetingScheduleScreen(
            draft: draft(),
            now: DateTime.utc(2026, 8, 1),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('저녁').first);
      await tester.pumpAndSettle();

      expect(find.text('참가 신청하기 (1개 선택)'), findsOneWidget);
    });

    testWidgets('전원 비음주를 고른 사용자에게 무알코올 안내를 보여준다', (tester) async {
      await tester.pumpWidget(
        host(
          BlindMeetingScheduleScreen(
            draft: draft(alcohol: AlcoholCompanionPreference.allSober),
            now: DateTime.utc(2026, 8, 1),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('무알코올 미팅으로 신청돼요'), findsOneWidget);
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
                    candidateSlots: const [
                      BlindMeetingSlot(
                        dateKey: '2026-08-01',
                        timeBlock: BlindMeetingTimeBlock.evening,
                      ),
                    ],
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

      final disabled = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '투표하기'),
      );
      expect(disabled.onPressed, isNull);

      await tester.tap(find.text('8월 1일 저녁'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('보드게임 카페 · 무알코올'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('투표하기'));
      await tester.pumpAndSettle();

      expect(result, isNotNull);
      expect(result!.preferredSlotIds, ['2026-08-01#evening']);
      expect(result!.preferredPlaceId, 'p1');
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
