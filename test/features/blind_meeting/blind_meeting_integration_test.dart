// 블라인드 취향 미팅 전체 흐름 통합 테스트
//
// 신청 → DNA → 팀 구성 → 수락 → 보증금 → 채팅 → 참석 확인 → 안전도장
// → 만족도 → 후속 선택 → 상호 선택 → 1:1 채팅
//
// 서버 대신 FakeBlindMeetingRepository가 상태 전환을 시뮬레이션한다.

import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_analytics.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_dna.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_feedback.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_followup.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_public_profile.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_session.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_dna_wizard_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_feedback_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_follow_up_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_result_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart';
import 'package:seolleyeon/router/route_names.dart';

const String kMeetingId = 'meeting-1';
const String kMe = 'me';

/// 매칭 기준 날짜 (KST). 세부 시간은 단체 채팅방에서 정한다.
const String kDateKey = '2026-08-01';

class RecordingAnalyticsSink implements BlindMeetingAnalyticsSink {
  final List<String> events = <String>[];
  final List<Map<String, dynamic>> params = <Map<String, dynamic>>[];

  @override
  Future<void> send(String event, Map<String, dynamic> payload) async {
    events.add(event);
    params.add(payload);
  }
}

/// 서버 흐름을 흉내내는 fake repository.
class FakeBlindMeetingRepository extends BlindMeetingRepository {
  FakeBlindMeetingRepository();

  final StreamController<BlindMeetingApplication?> _applications =
      StreamController<BlindMeetingApplication?>.broadcast();
  final StreamController<BlindMeetingSession?> _sessions =
      StreamController<BlindMeetingSession?>.broadcast();

  BlindMeetingApplication? application;
  BlindMeetingSession session = BlindMeetingSession(
    meetingId: kMeetingId,
    status: BlindMeetingStatus.awaitingAcceptance,
    algorithmVersion: 'blind_taste_v1',
    matchedDateKey: kDateKey,
    commonAvailableDateKeys: const [kDateKey, '2026-08-02'],
    teamAUserIds: const [kMe, 'a2', 'a3'],
    teamBUserIds: const ['b1', 'b2', 'b3'],
    participantIds: const [kMe, 'a2', 'a3', 'b1', 'b2', 'b3'],
  );
  BlindMeetingParticipant me = const BlindMeetingParticipant(
    userId: kMe,
    team: BlindMeetingTeam.teamA,
    status: BlindMeetingParticipantStatus.invited,
  );
  BlindMeetingFollowUpChoice? followUpChoice;
  List<BlindMeetingMutualMatch> mutualMatches =
      const <BlindMeetingMutualMatch>[];

  BlindMeetingDna? submittedDna;
  int acceptCalls = 0;
  int depositCalls = 0;
  BlindMeetingFeedback? submittedFeedback;
  List<String>? submittedFollowUp;

  void _pushApplication() => _applications.add(application);
  void _pushSession() => _sessions.add(session);

  @override
  Future<String?> currentUserId() async => kMe;

  @override
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async {
    return BlindMeetingProfileSnapshot(
      userId: kMe,
      nickname: '민지',
      department: '컴퓨터과학과',
      mbti: 'ENFP',
      interests: const ['커피', '영화', '농구'],
      drinkingLevel: DrinkingLevel.none,
      smokingStatus: SmokingStatus.nonSmoker,
      schoolVerified: true,
      onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
    );
  }

  /// 설정하면 신청 상태 조회가 이 오류로 실패한다.
  Object? applicationReadError;

  /// 일정 화면이 복구할 기존 DNA. null이면 이전 신청이 없는 상태.
  BlindMeetingDna? storedDna;

  /// 설정하면 기존 DNA 조회가 이 오류로 실패한다.
  Object? dnaReadError;

  @override
  Future<BlindMeetingDna?> loadMyDna() async {
    final error = dnaReadError;
    if (error != null) throw error;
    return storedDna;
  }

  @override
  Stream<BlindMeetingApplication?> watchMyApplication() {
    final error = applicationReadError;
    if (error != null) {
      return Stream<BlindMeetingApplication?>.error(error);
    }
    Future.microtask(_pushApplication);
    return _applications.stream;
  }

  @override
  Future<BlindMeetingApplication?> loadMyApplication() async {
    final error = applicationReadError;
    if (error != null) throw error;
    return application;
  }

  @override
  Future<BlindMeetingApplicationResult> submitApplication(
    BlindMeetingDna dna,
  ) async {
    submittedDna = dna;
    application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.searchingCandidates,
      requestedDateKeys: dna.availableDateKeys,
      prefersAlcoholFree: dna.belongsToAlcoholFreePool,
    );
    _pushApplication();
    return const BlindMeetingApplicationResult(
      accepted: true,
      stage: BlindMeetingMatchingStage.searchingCandidates,
    );
  }

  /// 서버가 팀 구성을 마친 상황을 흉내낸다.
  void completeMatching() {
    application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.invited,
      stage: BlindMeetingMatchingStage.matched,
      meetingId: kMeetingId,
    );
    _pushApplication();
  }

  @override
  Stream<BlindMeetingSession?> watchMeeting(String meetingId) {
    Future.microtask(_pushSession);
    return _sessions.stream;
  }

  @override
  Future<BlindMeetingRecommendationView?> loadRecommendation(
    String meetingId,
  ) async {
    BlindMeetingPublicProfile profile(String id, String nickname) =>
        BlindMeetingPublicProfile(
          userId: id,
          nickname: nickname,
          department: '경영학과',
          mbti: 'INFJ',
          topInterestIds: const ['커피', '전시회'],
          avatarSeed: id,
          schoolVerified: true,
        );

    return BlindMeetingRecommendationView(
      session: session,
      viewerTeam: BlindMeetingTeam.teamA,
      myTeam: [profile(kMe, '민지'), profile('a2', '수현'), profile('a3', '지우')],
      opponentTeam: [
        profile('b1', '하늘'),
        profile('b2', '태오'),
        profile('b3', '유진'),
      ],
      me: me,
    );
  }

  @override
  Future<void> acceptInvitation(String meetingId) async {
    acceptCalls++;
    me = const BlindMeetingParticipant(
      userId: kMe,
      team: BlindMeetingTeam.teamA,
      status: BlindMeetingParticipantStatus.depositPending,
      depositStatus: BlindMeetingDepositStatus.pending,
    );
    session = BlindMeetingSession(
      meetingId: kMeetingId,
      status: BlindMeetingStatus.awaitingDeposits,
      matchedDateKey: kDateKey,
      commonAvailableDateKeys: const [kDateKey, '2026-08-02'],
      teamAUserIds: const [kMe, 'a2', 'a3'],
      teamBUserIds: const ['b1', 'b2', 'b3'],
      participantIds: const [kMe, 'a2', 'a3', 'b1', 'b2', 'b3'],
    );
    _pushSession();
  }

  @override
  Future<BlindMeetingDepositIntent> startDeposit(String meetingId) async {
    depositCalls++;
    me = const BlindMeetingParticipant(
      userId: kMe,
      team: BlindMeetingTeam.teamA,
      status: BlindMeetingParticipantStatus.confirmed,
      depositStatus: BlindMeetingDepositStatus.paid,
    );
    session = BlindMeetingSession(
      meetingId: kMeetingId,
      status: BlindMeetingStatus.chatOpen,
      groupChatId: 'blind_$kMeetingId',
      matchedDateKey: kDateKey,
      commonAvailableDateKeys: const [kDateKey, '2026-08-02'],
      teamAUserIds: const [kMe, 'a2', 'a3'],
      teamBUserIds: const ['b1', 'b2', 'b3'],
      participantIds: const [kMe, 'a2', 'a3', 'b1', 'b2', 'b3'],
    );
    _pushSession();
    return const BlindMeetingDepositIntent(
      status: BlindMeetingDepositStatus.paid,
      provider: 'sandbox',
      amount: 5000,
      sandbox: true,
      message: 'sandbox 결제로 처리했어요. 운영 결제가 아닙니다.',
    );
  }

  /// 안전도장 2단계와 미팅 종료를 흉내낸다.
  void completeMeetingAndOpenFollowUp() {
    me = BlindMeetingParticipant(
      userId: kMe,
      team: BlindMeetingTeam.teamA,
      status: BlindMeetingParticipantStatus.completed,
      depositStatus: BlindMeetingDepositStatus.refunded,
      checkedIn: true,
      checkedOut: true,
    );
    session = BlindMeetingSession(
      meetingId: kMeetingId,
      status: BlindMeetingStatus.followupOpen,
      groupChatId: 'blind_$kMeetingId',
      teamAUserIds: const [kMe, 'a2', 'a3'],
      teamBUserIds: const ['b1', 'b2', 'b3'],
      participantIds: const [kMe, 'a2', 'a3', 'b1', 'b2', 'b3'],
      followupClosesAt: DateTime.now().add(const Duration(hours: 20)),
    );
    _pushSession();
  }

  @override
  Stream<BlindMeetingFollowUpChoice?> watchMyFollowUpChoice(String meetingId) {
    return Stream<BlindMeetingFollowUpChoice?>.value(followUpChoice);
  }

  @override
  Future<void> submitFollowUpChoice({
    required String meetingId,
    required List<String> selectedUids,
  }) async {
    submittedFollowUp = selectedUids;
    followUpChoice = BlindMeetingFollowUpChoice(
      meetingId: meetingId,
      chooserUid: kMe,
      selectedUids: selectedUids,
      submittedAt: DateTime.now(),
    );
    // 상대도 나를 선택한 상황: 서버가 1:1 채팅을 만든다.
    if (selectedUids.contains('b1')) {
      mutualMatches = [
        BlindMeetingMutualMatch(
          partnerUid: 'b1',
          chatRoomId: 'dm_b1_me',
          matchedAt: DateTime.now(),
        ),
      ];
    }
  }

  @override
  Future<BlindMeetingFollowUpChoice?> loadMyFollowUpChoice(
    String meetingId,
  ) async => followUpChoice;

  @override
  Future<List<BlindMeetingMutualMatch>> loadMutualMatches(
    String meetingId,
  ) async => mutualMatches;

  @override
  Future<void> submitFeedback(BlindMeetingFeedback feedback) async {
    submittedFeedback = feedback;
  }

  @override
  Future<void> cancelApplication() async {
    application = null;
    _pushApplication();
  }

  Future<void> dispose() async {
    await _applications.close();
    await _sessions.close();
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  late FakeBlindMeetingRepository repository;
  late RecordingAnalyticsSink sink;
  late BlindMeetingAnalytics analytics;

  setUp(() {
    repository = FakeBlindMeetingRepository();
    sink = RecordingAnalyticsSink();
    analytics = BlindMeetingAnalytics(sink: sink);
  });

  tearDown(() async {
    await repository.dispose();
  });

  Route<dynamic> generate(RouteSettings settings) {
    Widget page;
    switch (settings.name) {
      case RouteNames.blindTasteMeeting:
        page = BlindMeetingIntroScreen(
          repository: repository,
          analytics: analytics,
        );
      case RouteNames.blindTasteMeetingDna:
        page = BlindMeetingDnaWizardScreen(
          profile: settings.arguments as BlindMeetingProfileSnapshot,
          analytics: analytics,
        );
      case RouteNames.blindTasteMeetingSchedule:
        page = BlindMeetingScheduleScreen(
          draft: settings.arguments as BlindMeetingDnaDraft,
          repository: repository,
          analytics: analytics,
          now: DateTime.utc(2026, 8, 1),
        );
      case RouteNames.blindTasteMeetingWaiting:
        page = BlindMeetingWaitingScreen(repository: repository);
      case RouteNames.blindTasteMeetingResult:
        page = BlindMeetingResultScreen(
          args: settings.arguments as BlindMeetingMeetingArgs,
          repository: repository,
          analytics: analytics,
        );
      case RouteNames.blindTasteMeetingFollowUp:
        page = BlindMeetingFollowUpScreen(
          args: settings.arguments as BlindMeetingMeetingArgs,
          repository: repository,
          analytics: analytics,
        );
      case RouteNames.blindTasteMeetingFeedback:
        page = BlindMeetingFeedbackScreen(
          args: settings.arguments as BlindMeetingMeetingArgs,
          repository: repository,
          analytics: analytics,
        );
      default:
        page = const Scaffold(body: Text('unknown'));
    }
    return MaterialPageRoute<dynamic>(builder: (_) => page, settings: settings);
  }

  /// 대기 화면에는 진행 표시 spinner가 계속 돌기 때문에 pumpAndSettle을 쓸 수 없다.
  Future<void> pumpFrames(WidgetTester tester, {int frames = 10}) async {
    for (var i = 0; i < frames; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  Future<void> pumpApp(
    WidgetTester tester, {
    String? initialRoute,
    bool settle = true,
  }) async {
    // 긴 화면이 잘려서 탭이 빗나가지 않도록 큰 뷰포트를 사용한다.
    tester.view.physicalSize = const Size(1000, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await tester.pumpWidget(
      MaterialApp(
        onGenerateRoute: generate,
        initialRoute: initialRoute ?? RouteNames.blindTasteMeeting,
      ),
    );
    if (settle) {
      await tester.pumpAndSettle();
    } else {
      await pumpFrames(tester);
    }
  }

  Future<void> tapNext(WidgetTester tester, String option) async {
    await tester.tap(find.text(option));
    await tester.pumpAndSettle();
    await tester.tap(find.text('다음'));
    await tester.pumpAndSettle();
  }

  testWidgets('신청부터 1:1 채팅 생성까지 전체 흐름', (tester) async {
    // 1) 소개 화면
    await pumpApp(tester);
    expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);
    expect(find.text('미팅 DNA 작성하기'), findsOneWidget);

    // 2) DNA wizard 4단계
    await tester.tap(find.text('미팅 DNA 작성하기'));
    await tester.pumpAndSettle();
    expect(find.text('1/4'), findsOneWidget);

    await tapNext(tester, '차분하게 이야기하는 분위기');
    await tapNext(tester, '먼저 대화를 시작하는 편이에요');
    await tapNext(tester, '연애와 친구 모두 열려 있어요');

    // 4/4: 프로필이 비음주이므로 전원 비음주 조건을 고를 수 있다.
    expect(find.text('4/4'), findsOneWidget);
    await tester.tap(find.text(AlcoholCompanionPreference.allSober.label));
    await tester.pumpAndSettle();
    await tester.tap(
      find.text(SmokingCompanionPreference.nonSmokersOnly.label),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('일정 선택하기'));
    await tester.pumpAndSettle();

    // 3) 참여 가능 날짜 선택 + 신청 (시간대 선택은 없다)
    expect(find.byType(BlindMeetingScheduleScreen), findsOneWidget);
    expect(find.textContaining('무알코올 미팅으로 신청돼요'), findsOneWidget);
    expect(find.textContaining('단체 채팅방에서 함께 정해요'), findsOneWidget);
    expect(find.text('저녁'), findsNothing);
    // 기준 시각이 KST 2026-08-01이므로 8월 2일부터 선택할 수 있다.
    await tester.tap(find.text('2'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('선택한 1개 날짜로 신청하기'));
    await pumpFrames(tester);

    expect(repository.submittedDna, isNotNull);
    expect(repository.submittedDna!.belongsToAlcoholFreePool, isTrue);
    expect(repository.submittedDna!.availableDateKeys, ['2026-08-02']);
    expect(repository.submittedDna!.interestIds, contains('커피'));

    // 4) 대기 화면에서 단계가 보인다
    expect(find.byType(BlindMeetingWaitingScreen), findsOneWidget);
    // 제목과 단계 목록 양쪽에 현재 단계가 표시된다.
    expect(find.text('조건에 맞는 참가자를 찾고 있어요'), findsWidgets);

    // 5) 서버가 팀 구성을 마치면 추천 결과로 이동
    repository.completeMatching();
    await pumpFrames(tester);
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingResultScreen), findsOneWidget);
    expect(find.text('우리 팀 3명'), findsOneWidget);
    expect(find.text('상대 팀 3명'), findsOneWidget);
    expect(find.text('하늘'), findsOneWidget);
    // 얼굴 사진은 노출되지 않는다.
    expect(find.byType(Image), findsNothing);

    // 6) 참가 수락
    await tester.tap(find.text('참가할게요'));
    await tester.pumpAndSettle();
    expect(repository.acceptCalls, 1);
    expect(find.text('개인별 보증금을 결제해주세요'), findsOneWidget);

    // 7) 개인별 보증금 결제
    await tester.tap(find.text('보증금 결제하기'));
    await tester.pumpAndSettle();
    expect(repository.depositCalls, 1);
    expect(find.text('단체 채팅에서 약속을 정해주세요'), findsOneWidget);
    expect(find.text('단체 채팅방 열기'), findsOneWidget);

    // 8) 미팅 종료 + 후속 선택 개방
    repository.completeMeetingAndOpenFollowUp();
    await tester.pumpAndSettle();
    expect(find.text('미팅이 마무리됐어요'), findsOneWidget);

    // 9) 만족도
    await tester.tap(find.text('만족도 남기기'));
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingFeedbackScreen), findsOneWidget);
    for (final question in BlindMeetingFeedbackQuestion.values) {
      expect(find.text(question.label), findsOneWidget);
    }
    // 각 문항에 4점 부여
    final scoreButtons = find.text('4');
    expect(scoreButtons, findsNWidgets(4));
    for (var i = 0; i < 4; i++) {
      await tester.tap(find.text('4').at(i));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('만족도 제출하기'));
    await tester.pumpAndSettle();
    expect(repository.submittedFeedback, isNotNull);
    expect(repository.submittedFeedback!.isComplete, isTrue);
    expect(find.text('소중한 의견 고맙습니다'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new).last);
    await tester.pumpAndSettle();

    // 10) 비공개 후속 선택 (상대 팀만, 최대 2명)
    await tester.tap(find.text('후속 대화 선택하기'));
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingFollowUpScreen), findsOneWidget);
    expect(find.textContaining('최대 2명까지 선택할 수 있어요'), findsOneWidget);
    expect(find.text('민지'), findsNothing); // 같은 팀은 선택 대상이 아니다

    await tester.tap(find.text('하늘'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('선택 제출하기'));
    await tester.pumpAndSettle();

    expect(repository.submittedFollowUp, ['b1']);

    // 11) 상호 선택 → 1:1 채팅 열림
    expect(find.text('서로 다시 대화해보고 싶어 했어요.'), findsOneWidget);
    expect(find.text('1:1 채팅 열기'), findsOneWidget);

    // analytics: 개인정보 없이 주요 이벤트가 기록된다
    expect(sink.events, contains('blind_meeting_intro_viewed'));
    expect(sink.events, contains('blind_meeting_dna_started'));
    expect(sink.events, contains('blind_meeting_dna_completed'));
    expect(sink.events, contains('blind_meeting_schedule_viewed'));
    expect(sink.events, contains('blind_meeting_date_selected'));
    expect(sink.events, contains('blind_meeting_schedule_submitted'));
    expect(sink.events, contains('blind_meeting_invitation_accepted'));
    expect(sink.events, contains('blind_meeting_deposit_completed'));
    expect(sink.events, contains('blind_meeting_feedback_submitted'));
    expect(sink.events, contains('blind_meeting_followup_prompt_opened'));
    expect(sink.events, contains('blind_meeting_followup_submitted'));
    expect(sink.events, contains('blind_meeting_mutual_match'));
    for (final payload in sink.params) {
      expect(payload.keys, isNot(contains('nickname')));
      expect(payload.keys, isNot(contains('interests')));
      expect(payload.keys, isNot(contains('userId')));
      // 실제 선택 날짜는 analytics로 나가지 않는다.
      expect(payload.keys, isNot(contains('availableDateKeys')));
      expect(payload.keys, isNot(contains('dateKey')));
      for (final value in payload.values) {
        expect('$value', isNot(matches(RegExp(r'^\d{4}-\d{2}-\d{2}$'))));
      }
    }
  });

  testWidgets('진행 중인 신청이 있으면 대기 상태를 복구한다', (tester) async {
    repository.application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.formingOwnTeam,
    );

    await pumpApp(tester);
    expect(find.text('이미 신청이 진행 중이에요'), findsOneWidget);
    expect(find.text('우리 팀을 구성하고 있어요'), findsOneWidget);

    await tester.tap(find.text('진행 상황 보기'));
    await pumpFrames(tester);
    expect(find.byType(BlindMeetingWaitingScreen), findsOneWidget);
  });

  testWidgets('신청 상태를 읽을 수 없어도 소개 화면은 열린다', (tester) async {
    repository.applicationReadError = FirebaseException(
      plugin: 'cloud_firestore',
      code: 'permission-denied',
      message: 'Missing or insufficient permissions.',
    );

    await pumpApp(tester);
    expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);
    expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    expect(find.text('잠시 문제가 생겼어요'), findsNothing);
  });

  testWidgets('무알코올 후보 부족 시 사용자가 직접 조건을 선택한다', (tester) async {
    repository.application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.insufficientCandidates,
      prefersAlcoholFree: true,
    );

    await pumpApp(
      tester,
      initialRoute: RouteNames.blindTasteMeetingWaiting,
      settle: false,
    );
    expect(find.text('아직 조건에 맞는 참가자가 충분하지 않아요.'), findsOneWidget);
    expect(find.text('다음 무알코올 미팅까지 기다릴게요'), findsOneWidget);
    expect(find.text('다른 날짜도 괜찮아요'), findsOneWidget);
    expect(find.text('다른 사람의 가벼운 음주는 괜찮도록 조건을 변경할게요'), findsOneWidget);
  });
}
