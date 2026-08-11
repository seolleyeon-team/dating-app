import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_dna.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_dna_wizard_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/widgets/blind_meeting_common.dart';
import 'package:seolleyeon/router/app_router.dart';
import 'package:seolleyeon/router/route_names.dart';

class _FakeWaitingRepository extends BlindMeetingRepository {
  _FakeWaitingRepository({required this.application});

  final BlindMeetingApplication application;

  @override
  Stream<BlindMeetingApplication?> watchMyApplication() =>
      Stream<BlindMeetingApplication?>.value(application);

  @override
  Future<BlindMeetingApplication?> loadMyApplication() async => application;

  @override
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async =>
      BlindMeetingProfileSnapshot(
        userId: application.userId,
        nickname: '민지',
        department: '컴퓨터과학과',
        mbti: 'ENFP',
        interests: const ['커피', '영화'],
        drinkingLevel: DrinkingLevel.sometimes,
        smokingStatus: SmokingStatus.nonSmoker,
        schoolVerified: true,
        onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
      );
}

class _EditRepository extends BlindMeetingRepository {
  _EditRepository({required this.application, required this.storedDna});

  BlindMeetingApplication? application;
  BlindMeetingDna? storedDna;
  int submitCalls = 0;
  int updateCalls = 0;

  @override
  Stream<BlindMeetingApplication?> watchMyApplication() =>
      Stream<BlindMeetingApplication?>.value(application);

  @override
  Future<BlindMeetingApplication?> loadMyApplication() async => application;

  @override
  Future<BlindMeetingDna?> loadMyDna() async => storedDna;

  @override
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async =>
      testProfile();

  @override
  Future<BlindMeetingApplicationResult> submitApplication(
    BlindMeetingDna dna,
  ) async {
    submitCalls++;
    return const BlindMeetingApplicationResult(
      accepted: true,
      stage: BlindMeetingMatchingStage.searchingCandidates,
    );
  }

  @override
  Future<BlindMeetingApplicationResult> updateApplication(
    BlindMeetingDna dna,
  ) async {
    updateCalls++;
    storedDna = dna;
    return const BlindMeetingApplicationResult(
      accepted: true,
      stage: BlindMeetingMatchingStage.searchingCandidates,
    );
  }
}

BlindMeetingApplication editableApplication() => BlindMeetingApplication(
  userId: 'u1',
  status: BlindMeetingParticipantStatus.applied,
  stage: BlindMeetingMatchingStage.searchingCandidates,
  requestedDateKeys: const ['2026-08-11'],
);

BlindMeetingProfileSnapshot testProfile() => BlindMeetingProfileSnapshot(
  userId: 'u1',
  nickname: '민지',
  department: '컴퓨터과학과',
  mbti: 'ENFP',
  interests: const ['커피', '영화'],
  drinkingLevel: DrinkingLevel.sometimes,
  smokingStatus: SmokingStatus.nonSmoker,
  schoolVerified: true,
  onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
);

Future<void> pumpFrames(WidgetTester tester, {int frames = 12}) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  test('typed DNA route args preserve edit mode', () {
    final args = BlindMeetingDnaRouteArgs(
      profile: testProfile(),
      mode: BlindMeetingDnaMode.editExistingApplication,
    );

    expect(args.mode, BlindMeetingDnaMode.editExistingApplication);
  });

  test(
    'AppRouter preserves named routes needed by Waiting back navigation',
    () {
      final routeSettings = [
        const RouteSettings(name: RouteNames.main),
        const RouteSettings(name: RouteNames.event),
        const RouteSettings(name: RouteNames.blindTasteMeeting),
        RouteSettings(
          name: RouteNames.blindTasteMeetingDna,
          arguments: testProfile(),
        ),
        RouteSettings(
          name: RouteNames.blindTasteMeetingSchedule,
          arguments: BlindMeetingDnaDraft(
            profile: testProfile(),
            atmosphere: ConversationAtmosphere.calm,
            initiative: ConversationInitiative.adaptive,
            purpose: MeetingPurpose.both,
            alcoholPreference: AlcoholCompanionPreference.lightOkay,
            smokingPreference: SmokingCompanionPreference.noPreference,
          ),
        ),
        const RouteSettings(name: RouteNames.blindTasteMeetingWaiting),
      ];
      for (final settings in routeSettings) {
        final route = AppRouter.generateRoute(settings);
        expect(route.settings.name, settings.name);
      }
    },
  );

  testWidgets('editable Waiting shows cancel before DNA edit CTA', (
    tester,
  ) async {
    final repository = _FakeWaitingRepository(
      application: editableApplication(),
    );
    await tester.pumpWidget(
      MaterialApp(home: BlindMeetingWaitingScreen(repository: repository)),
    );
    await tester.pump();

    final cancel = find.text('신청 취소하기');
    final edit = find.text('DNA 수정하기');
    expect(cancel, findsOneWidget);
    expect(edit, findsOneWidget);
    expect(tester.getCenter(edit).dy, greaterThan(tester.getCenter(cancel).dy));
  });

  testWidgets('Waiting back removes transient DNA and schedule routes', (
    tester,
  ) async {
    final repository = _FakeWaitingRepository(
      application: editableApplication(),
    );
    await tester.pumpWidget(
      MaterialApp(
        initialRoute: RouteNames.main,
        routes: {
          RouteNames.main: (_) => const Scaffold(body: Text('main')),
          RouteNames.blindTasteMeeting: (_) =>
              BlindMeetingIntroScreen(repository: repository),
          '/test/dna': (_) => const Scaffold(body: Text('DNA sentinel')),
          '/test/schedule': (_) =>
              const Scaffold(body: Text('Schedule sentinel')),
          RouteNames.blindTasteMeetingWaiting: (_) =>
              BlindMeetingWaitingScreen(repository: repository),
        },
      ),
    );
    await tester.pumpAndSettle();
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pushNamed(RouteNames.blindTasteMeeting);
    navigator.pushNamed('/test/dna');
    navigator.pushNamed('/test/schedule');
    navigator.pushNamed(RouteNames.blindTasteMeetingWaiting);
    await pumpFrames(tester);

    await tester.tap(find.byTooltip('뒤로'));
    await tester.pumpAndSettle();

    expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);
    expect(find.text('DNA sentinel'), findsNothing);
    expect(find.text('Schedule sentinel'), findsNothing);
    expect(find.byType(BlindMeetingWaitingScreen), findsNothing);
  });

  testWidgets('system back uses the same canonical Intro destination', (
    tester,
  ) async {
    final repository = _FakeWaitingRepository(
      application: editableApplication(),
    );
    await tester.pumpWidget(
      MaterialApp(
        initialRoute: RouteNames.main,
        routes: {
          RouteNames.main: (_) => const Scaffold(body: Text('main')),
          RouteNames.blindTasteMeeting: (_) =>
              BlindMeetingIntroScreen(repository: repository),
          RouteNames.blindTasteMeetingWaiting: (_) =>
              BlindMeetingWaitingScreen(repository: repository),
        },
      ),
    );
    await tester.pumpAndSettle();
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pushNamed(RouteNames.blindTasteMeeting);
    navigator.pushNamed(RouteNames.blindTasteMeetingWaiting);
    await pumpFrames(tester);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);
  });

  testWidgets('edit DNA wizard preloads the authoritative first-step value', (
    tester,
  ) async {
    final storedDna = BlindMeetingDna(
      userId: 'u1',
      conversationAtmosphere: ConversationAtmosphere.lively,
      conversationInitiative: ConversationInitiative.initiator,
      meetingPurpose: MeetingPurpose.romance,
      alcoholCompanionPreference: AlcoholCompanionPreference.lightOkay,
      smokingCompanionPreference: SmokingCompanionPreference.nonSmokersOnly,
      interestIds: const ['커피', '영화'],
      drinkingLevelSnapshot: DrinkingLevel.sometimes,
      smokingStatusSnapshot: SmokingStatus.nonSmoker,
      mbtiSnapshot: 'ENFP',
      availableDateKeys: const ['2026-08-11'],
    );
    final repository = _EditRepository(
      application: editableApplication(),
      storedDna: storedDna,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: BlindMeetingDnaWizardScreen(
          profile: testProfile(),
          mode: BlindMeetingDnaMode.editExistingApplication,
          repository: repository,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('1/4'), findsOneWidget);
    final selected = tester
        .widgetList<BlindMeetingOptionTile>(find.byType(BlindMeetingOptionTile))
        .where((tile) => tile.selected)
        .single;
    expect(selected.label, ConversationAtmosphere.lively.label);
  });

  testWidgets('DNA edit CTA opens the canonical wizard in edit mode', (
    tester,
  ) async {
    final repository = _EditRepository(
      application: editableApplication(),
      storedDna: BlindMeetingDna(
        userId: 'u1',
        conversationAtmosphere: ConversationAtmosphere.lively,
        conversationInitiative: ConversationInitiative.initiator,
        meetingPurpose: MeetingPurpose.romance,
        alcoholCompanionPreference: AlcoholCompanionPreference.lightOkay,
        smokingCompanionPreference: SmokingCompanionPreference.nonSmokersOnly,
        interestIds: const ['커피'],
        drinkingLevelSnapshot: DrinkingLevel.sometimes,
        smokingStatusSnapshot: SmokingStatus.nonSmoker,
        availableDateKeys: const ['2026-08-11'],
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: BlindMeetingWaitingScreen(repository: repository),
        onGenerateRoute: (settings) {
          final args = settings.arguments! as BlindMeetingDnaRouteArgs;
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => BlindMeetingDnaWizardScreen(
              profile: args.profile,
              mode: args.mode,
              repository: repository,
            ),
          );
        },
      ),
    );
    await pumpFrames(tester);

    await tester.ensureVisible(find.text('DNA 수정하기'));
    await tester.tap(find.text('DNA 수정하기'));
    await pumpFrames(tester);

    expect(find.byType(BlindMeetingDnaWizardScreen), findsOneWidget);
    expect(find.text('1/4'), findsOneWidget);
    final selected = tester
        .widgetList<BlindMeetingOptionTile>(find.byType(BlindMeetingOptionTile))
        .where((tile) => tile.selected)
        .single;
    expect(selected.label, ConversationAtmosphere.lively.label);
  });

  testWidgets(
    'edit schedule updates the existing application without submit duplication',
    (tester) async {
      final originalApplication = editableApplication();
      final repository = _EditRepository(
        application: originalApplication,
        storedDna: null,
      );
      final draft = BlindMeetingDnaDraft(
        profile: testProfile(),
        atmosphere: ConversationAtmosphere.calm,
        initiative: ConversationInitiative.adaptive,
        purpose: MeetingPurpose.both,
        alcoholPreference: AlcoholCompanionPreference.lightOkay,
        smokingPreference: SmokingCompanionPreference.noPreference,
        mode: BlindMeetingDnaMode.editExistingApplication,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: BlindMeetingScheduleScreen(
            draft: draft,
            repository: repository,
            now: DateTime.utc(2026, 8, 1),
            restoreExistingSelection: false,
          ),
          routes: {
            RouteNames.blindTasteMeetingWaiting: (_) =>
                const Scaffold(body: Text('waiting')),
          },
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel(RegExp(r'^8월 2일 일요일')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('선택한 1개 날짜로 신청하기'));
      await tester.pumpAndSettle();

      expect(repository.updateCalls, 1);
      expect(repository.submitCalls, 0);
      expect(repository.application, same(originalApplication));
    },
  );
}
