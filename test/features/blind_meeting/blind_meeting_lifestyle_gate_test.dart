import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_dna.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_dna_progress.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart';
import 'package:seolleyeon/router/route_names.dart';

class _MissingLifestyleRepository extends BlindMeetingRepository {
  int submitCalls = 0;
  int startDnaCalls = 0;

  @override
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async =>
      BlindMeetingProfileSnapshot(
        userId: 'u1',
        nickname: '민지',
        interests: const ['커피', '영화'],
        drinkingLevel: null,
        smokingStatus: SmokingStatus.nonSmoker,
        schoolVerified: true,
        campusLifeZones: const ['sinchon'],
        onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
      );

  @override
  Future<bool> loadCampusLifeZoneEnforced() async => true;

  @override
  Future<BlindMeetingApplication?> loadMyApplication() async => null;

  @override
  Future<BlindMeetingDnaProgress?> loadMyDnaProgress() async => null;

  @override
  Future<BlindMeetingDnaStartResult> startBlindMeetingDna() async {
    startDnaCalls++;
    return const BlindMeetingDnaStartResult(
      charged: true,
      heartBalance: 70,
      heartChargeCount: 1,
    );
  }

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
}

BlindMeetingProfileSnapshot _completeProfile() => BlindMeetingProfileSnapshot(
  userId: 'u1',
  nickname: '민지',
  interests: const ['커피', '영화'],
  drinkingLevel: DrinkingLevel.sometimes,
  smokingStatus: SmokingStatus.nonSmoker,
  schoolVerified: true,
  onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
);

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  testWidgets('paid DNA start is blocked before any heart charge', (
    tester,
  ) async {
    final repository = _MissingLifestyleRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: BlindMeetingIntroScreen(
          repository: repository,
          enablePaidDnaStart: true,
        ),
        routes: {
          RouteNames.profileEdit: (_) =>
              const Scaffold(body: Text('프로필 편집 화면')),
        },
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('미팅 DNA 작성하기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('미팅 DNA 작성하기'));
    await tester.pumpAndSettle();

    expect(find.text('음주·흡연 정보가 필요해요'), findsOneWidget);
    expect(repository.startDnaCalls, 0);
  });

  testWidgets(
    'missing drinking or smoking blocks submit and opens profile edit guidance',
    (tester) async {
      final repository = _MissingLifestyleRepository();
      final draft = BlindMeetingDnaDraft(
        profile: _completeProfile(),
        atmosphere: ConversationAtmosphere.calm,
        initiative: ConversationInitiative.adaptive,
        purpose: MeetingPurpose.both,
        alcoholPreference: AlcoholCompanionPreference.lightOkay,
        smokingPreference: SmokingCompanionPreference.noPreference,
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
            RouteNames.profileEdit: (_) =>
                const Scaffold(body: Text('프로필 편집 화면')),
          },
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel(RegExp(r'^8월 2일 일요일')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('선택한 1개 날짜로 신청하기'));
      await tester.pumpAndSettle();

      expect(find.text('음주·흡연 정보가 필요해요'), findsOneWidget);
      expect(find.textContaining('내 페이지 → 프로필 편집 맨 아래'), findsOneWidget);
      expect(find.text('채우러 가기'), findsOneWidget);
      expect(find.text('취소'), findsOneWidget);
      expect(repository.submitCalls, 0);

      await tester.tap(find.text('채우러 가기'));
      await tester.pumpAndSettle();
      expect(find.text('프로필 편집 화면'), findsOneWidget);
      expect(repository.submitCalls, 0);
    },
  );
}
