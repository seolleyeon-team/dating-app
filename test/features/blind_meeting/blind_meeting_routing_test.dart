// 라우트 및 legacy deep link 호환 테스트

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_feedback_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_follow_up_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_result_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart';
import 'package:seolleyeon/features/onboarding/onboarding_route_args.dart';
import 'package:seolleyeon/features/onboarding/screens/interests_selection_screen.dart';
import 'package:seolleyeon/router/app_router.dart';
import 'package:seolleyeon/router/route_names.dart';

Future<void> pumpRoute(
  WidgetTester tester,
  String route, {
  Object? arguments,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      // route별로 새 앱 트리를 만들어야 initialRoute가 다시 평가된다.
      key: ValueKey('route-$route-${arguments.hashCode}'),
      onGenerateRoute: AppRouter.generateRoute,
      initialRoute: route,
      onGenerateInitialRoutes: (initialRoute) => [
        AppRouter.generateRoute(
          RouteSettings(name: initialRoute, arguments: arguments),
        ),
      ],
    ),
  );
  await tester.pump();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  group('블라인드 취향 미팅 라우트', () {
    testWidgets('신규 route가 각 화면으로 연결된다', (tester) async {
      await pumpRoute(tester, RouteNames.blindTasteMeeting);
      expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);

      await pumpRoute(tester, RouteNames.blindTasteMeetingWaiting);
      expect(find.byType(BlindMeetingWaitingScreen), findsOneWidget);

      await pumpRoute(
        tester,
        RouteNames.blindTasteMeetingResult,
        arguments: const BlindMeetingMeetingArgs(meetingId: 'm1'),
      );
      expect(find.byType(BlindMeetingResultScreen), findsOneWidget);

      await pumpRoute(
        tester,
        RouteNames.blindTasteMeetingFollowUp,
        arguments: const BlindMeetingMeetingArgs(meetingId: 'm1'),
      );
      expect(find.byType(BlindMeetingFollowUpScreen), findsOneWidget);

      await pumpRoute(
        tester,
        RouteNames.blindTasteMeetingFeedback,
        arguments: const BlindMeetingMeetingArgs(meetingId: 'm1'),
      );
      expect(find.byType(BlindMeetingFeedbackScreen), findsOneWidget);
    });

    testWidgets('인자가 없으면 소개 화면으로 안전하게 되돌린다', (tester) async {
      for (final route in [
        RouteNames.blindTasteMeetingResult,
        RouteNames.blindTasteMeetingDna,
        RouteNames.blindTasteMeetingSchedule,
        RouteNames.blindTasteMeetingFollowUp,
        RouteNames.blindTasteMeetingFeedback,
      ]) {
        await pumpRoute(tester, route);
        expect(
          find.byType(BlindMeetingIntroScreen),
          findsOneWidget,
          reason: route,
        );
      }
    });
  });

  group('관심사 보충 라우트', () {
    testWidgets('typed 보충 인자는 기존 관심사 화면을 repair 모드로 연다', (tester) async {
      await pumpRoute(
        tester,
        RouteNames.onboardingInterestsSelection,
        arguments: const InterestsSelectionRouteArgs.prerequisiteRepair(),
      );
      await tester.pumpAndSettle();

      expect(find.byType(InterestsSelectionScreen), findsOneWidget);
      expect(
        find.byKey(const ValueKey('interests-selection-progress')),
        findsNothing,
      );
      expect(find.text('관심사 등록 완료'), findsOneWidget);
    });

    testWidgets('인자가 없는 기존 관심사 route는 onboarding 모드로 유지된다', (tester) async {
      await pumpRoute(tester, RouteNames.onboardingInterestsSelection);
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('interests-selection-progress')),
        findsOneWidget,
      );
      expect(find.text('다음'), findsOneWidget);
    });
  });

  group('legacy 랜덤 미팅 deep link 호환', () {
    test('기존 route 경로 문자열이 그대로 유지된다', () {
      expect(RouteNames.legacyRandomMatching, '/event/random-matching');
      expect(RouteNames.legacyRandomMeeting, '/event/random-meeting');
      expect(RouteNames.legacyMeetingApplication, '/meeting/application');
      expect(RouteNames.legacyBlindMeetingAliases.length, 3);
    });

    testWidgets('기존 route가 블라인드 취향 미팅으로 redirect 된다', (tester) async {
      for (final alias in RouteNames.legacyBlindMeetingAliases) {
        await pumpRoute(tester, alias);
        expect(
          find.byType(BlindMeetingIntroScreen),
          findsOneWidget,
          reason: alias,
        );
      }
    });
  });

  group('시즌 미팅 회귀', () {
    test('시즌 미팅 경로 문자열이 바뀌지 않았다', () {
      expect(RouteNames.teamSetup, '/event/team-setup');
      expect(
        RouteNames.seasonMeetingRoulette,
        '/event/season-meeting-roulette',
      );
      expect(RouteNames.matchResult, '/event/match-result');
      expect(RouteNames.event, '/event');
      expect(RouteNames.threeVsThreeMatch, '/event/three-vs-three-match');
    });

    testWidgets('알 수 없는 route는 블라인드 미팅으로 흡수되지 않는다', (tester) async {
      await pumpRoute(tester, '/does-not-exist');
      expect(find.byType(BlindMeetingIntroScreen), findsNothing);
      expect(find.textContaining('Route not found'), findsOneWidget);
    });
  });
}
