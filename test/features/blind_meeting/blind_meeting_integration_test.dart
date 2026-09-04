// 블라인드 취향 미팅 전체 흐름 통합 테스트
//
// 신청 → DNA → 팀 구성 → (수락 단계 없음) 즉시 확정 + 3:3 채팅방 → 참석 확인
// → 안전도장 → 만족도 → 후속 선택 → 상호 선택 → 1:1 채팅
// + 매칭 전 신청 취소(하트 환불) / 취소 후 재신청 / DNA·날짜 prefill
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

  /// rollout activation 은 서버 값이다. fake 는 적용된 상태를 기본으로 둔다.
  bool campusLifeZoneEnforced = true;

  @override
  Future<bool> loadCampusLifeZoneEnforced() async => campusLifeZoneEnforced;

  final StreamController<BlindMeetingApplication?> _applications =
      StreamController<BlindMeetingApplication?>.broadcast();
  final StreamController<BlindMeetingSession?> _sessions =
      StreamController<BlindMeetingSession?>.broadcast();

  BlindMeetingApplication? application;

  /// 매칭 = 확정. 서버는 미팅을 confirmed/chatOpen 으로 만들고 같은 트랜잭션에서
  /// 채팅방을 연다. 수락 대기 상태의 미팅은 신규 흐름에 존재하지 않는다.
  BlindMeetingSession session = BlindMeetingSession(
    meetingId: kMeetingId,
    status: BlindMeetingStatus.chatOpen,
    groupChatId: 'blind_$kMeetingId',
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
    status: BlindMeetingParticipantStatus.confirmed,
  );
  BlindMeetingFollowUpChoice? followUpChoice;
  List<BlindMeetingMutualMatch> mutualMatches =
      const <BlindMeetingMutualMatch>[];

  BlindMeetingDna? submittedDna;
  int cancelCalls = 0;

  /// 서버에서 매칭 tx 가 먼저 commit 된 상황을 흉내낸다: 취소가 거부된다.
  bool cancelRefusedAsMatched = false;
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
      // 생활권도 hard eligibility 다 (정상 사용자 fixture).
      campusLifeZones: const ['sinchon'],
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
    // 서버는 최종 신청 시 재사용 DNA(답변 + 날짜)를 Firestore 에 저장한다.
    storedDna = dna;
    application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.searchingCandidates,
      requestedDateKeys: dna.availableDateKeys,
      prefersAlcoholFree: dna.belongsToAlcoholFreePool,
      heartCost: 30,
      heartChargeCount: 1,
    );
    _pushApplication();
    return const BlindMeetingApplicationResult(
      accepted: true,
      stage: BlindMeetingMatchingStage.searchingCandidates,
    );
  }

  /// 서버가 매칭 tx 를 commit 한 상황을 흉내낸다: 신청서는 곧바로 confirmed,
  /// 미팅은 chatOpen + 채팅방. 수락 단계는 없다.
  void completeMatching() {
    application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.confirmed,
      stage: BlindMeetingMatchingStage.matched,
      meetingId: kMeetingId,
      heartCost: 30,
      heartChargeCount: 1,
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

  /// 미팅 취소 상태를 흉내낸다.
  void cancelMeeting() {
    me = const BlindMeetingParticipant(
      userId: kMe,
      team: BlindMeetingTeam.teamA,
      status: BlindMeetingParticipantStatus.cancelled,
    );
    session = BlindMeetingSession(
      meetingId: kMeetingId,
      status: BlindMeetingStatus.cancelled,
      teamAUserIds: const [kMe, 'a2', 'a3'],
      teamBUserIds: const ['b1', 'b2', 'b3'],
      participantIds: const [kMe, 'a2', 'a3', 'b1', 'b2', 'b3'],
    );
    _pushSession();
  }

  /// 안전도장 2단계와 미팅 종료를 흉내낸다.
  void completeMeetingAndOpenFollowUp() {
    me = BlindMeetingParticipant(
      userId: kMe,
      team: BlindMeetingTeam.teamA,
      status: BlindMeetingParticipantStatus.completed,
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

  /// 서버 계약: 매칭 전 취소는 문서를 cancelled 로 옮기고(삭제 아님) 하트를
  /// 정확히 한 번 돌려준다. 매칭 후에는 CANNOT_CANCEL_ALREADY_MATCHED.
  @override
  Future<BlindMeetingCancelResult> cancelApplication() async {
    cancelCalls++;
    if (cancelRefusedAsMatched) {
      completeMatching();
      throw const BlindMeetingAlreadyMatchedException(meetingId: kMeetingId);
    }
    final current = application;
    if (current == null || current.isCancelled) {
      return const BlindMeetingCancelResult(outcome: 'already_cancelled');
    }
    application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.cancelled,
      stage: BlindMeetingMatchingStage.cancelled,
      requestedDateKeys: current.requestedDateKeys,
      heartCost: current.heartCost,
      heartChargeCount: current.heartChargeCount,
      heartRefundedAmount: current.heartCost,
    );
    _pushApplication();
    return BlindMeetingCancelResult(
      outcome: 'cancelled',
      heartRefunded: current.heartCost,
      heartBalance: 100,
    );
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
          repository: repository,
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
        page = BlindMeetingWaitingScreen(
          repository: repository,
          analytics: analytics,
        );
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

    // 대기 화면: 매칭 전이라 신청 취소만 있고, 수락/거절은 없다.
    expect(find.text('신청 취소하기'), findsOneWidget);
    expect(find.text('참가자 확정을 기다리고 있어요'), findsNothing);

    // 5) 서버가 매칭 tx 를 commit 하면 (수락 단계 없이) 곧바로 매칭 결과로 이동
    repository.completeMatching();
    await pumpFrames(tester);
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingResultScreen), findsOneWidget);
    expect(find.text('우리 팀 3명'), findsOneWidget);
    expect(find.text('상대 팀 3명'), findsOneWidget);
    expect(find.text('하늘'), findsOneWidget);
    // 얼굴 사진은 노출되지 않는다.
    expect(find.byType(Image), findsNothing);

    // 6) 매칭 = 확정. 수락/거절 UI 없이 "매칭됐어요" 안내와 채팅방 진입만 있다.
    expect(find.text('3:3 미팅이 매칭됐어요!'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('blind-meeting-open-group-chat')),
      findsOneWidget,
    );
    expect(find.text('채팅방으로 이동'), findsOneWidget);
    expect(find.text('참가할게요'), findsNothing);
    expect(find.text('이번에는 참가하지 않을게요'), findsNothing);
    expect(find.textContaining('수락'), findsNothing);
    expect(find.textContaining('거절'), findsNothing);
    expect(find.text('신청 취소하기'), findsNothing);
    expect(repository.cancelCalls, 0);
    expect(find.textContaining('보증금'), findsNothing);
    expect(find.textContaining('결제'), findsNothing);
    expect(find.textContaining('환급'), findsNothing);

    // 8) 미팅 종료 + 후속 선택 개방
    repository.completeMeetingAndOpenFollowUp();
    await tester.pumpAndSettle();
    expect(find.text('미팅이 마무리됐어요'), findsOneWidget);
    expect(find.textContaining('환급'), findsNothing);
    expect(find.textContaining('보증금'), findsNothing);

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
    expect(sink.events, isNot(contains('blind_meeting_invitation_accepted')));
    expect(sink.events, isNot(contains('blind_meeting_deposit_completed')));
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

  testWidgets('매칭 전 신청 취소: 취소 → 하트 환불 안내 → 소개 화면은 다시 신청 가능 상태', (tester) async {
    // RED(수정 전): 대기 화면에서 취소하고 돌아와도 소개 화면 메모리가 신청 중으로
    // 남아 "이미 신청이 진행 중이에요" → 확인 → "매칭 준비 중" 이 다시 보였다.
    repository.application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.searchingCandidates,
      requestedDateKeys: const ['2026-08-02'],
      heartCost: 30,
      heartChargeCount: 1,
    );

    await pumpApp(tester);
    expect(find.text('이미 신청이 진행 중이에요'), findsOneWidget);
    await tester.tap(find.text('진행 상황 보기'));
    await pumpFrames(tester);
    expect(find.byType(BlindMeetingWaitingScreen), findsOneWidget);
    expect(find.text('매칭 준비 중'), findsOneWidget);

    // 취소 확인 시트 → 취소
    await tester.tap(
      find.byKey(const ValueKey('blind-meeting-cancel-application')),
    );
    await pumpFrames(tester);
    expect(find.text('신청을 취소할까요?'), findsOneWidget);
    expect(find.textContaining('하트 30개는 바로 환불'), findsOneWidget);
    await tester.tap(find.text('신청 취소'));
    await pumpFrames(tester);

    expect(repository.cancelCalls, 1);
    expect(find.text('신청이 취소됐어요.'), findsOneWidget);
    expect(find.textContaining('하트 30개를 환불했어요'), findsOneWidget);
    // 취소 상태에서는 대기 UI/취소 버튼이 다시 보이지 않는다.
    expect(find.text('매칭 준비 중'), findsNothing);
    expect(
      find.byKey(const ValueKey('blind-meeting-cancel-application')),
      findsNothing,
    );
    expect(sink.events, contains('blind_meeting_application_cancelled'));

    // 재신청 CTA → 소개 화면은 canonical 문서(cancelled)를 다시 읽는다.
    await tester.tap(find.byKey(const ValueKey('blind-meeting-reapply')));
    await pumpFrames(tester);
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingIntroScreen), findsOneWidget);
    expect(find.text('이미 신청이 진행 중이에요'), findsNothing);
    expect(find.text('진행 상황 보기'), findsNothing);
    expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    expect(find.textContaining('이전 신청은 취소됐어요'), findsOneWidget);

    // 두 번째 취소(재시도)는 환불을 다시 만들지 않는다 (fake 는 서버 계약을 반영).
    final again = await repository.cancelApplication();
    expect(again.outcome, 'already_cancelled');
    expect(again.heartRefunded, 0);
  });

  testWidgets('취소 버튼을 눌렀지만 서버에서 매칭이 먼저 commit 되면 매칭 결과로 복구한다', (tester) async {
    repository.application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.applied,
      stage: BlindMeetingMatchingStage.checkingCrossTeam,
      requestedDateKeys: const ['2026-08-02'],
      heartCost: 30,
      heartChargeCount: 1,
    );
    repository.cancelRefusedAsMatched = true;

    await pumpApp(
      tester,
      initialRoute: RouteNames.blindTasteMeetingWaiting,
      settle: false,
    );
    await tester.tap(
      find.byKey(const ValueKey('blind-meeting-cancel-application')),
    );
    await pumpFrames(tester);
    await tester.tap(find.text('신청 취소'));
    await pumpFrames(tester);
    await tester.pumpAndSettle();

    // 거짓 "취소 성공" 없이 canonical 상태(매칭됨 → 채팅)로 간다.
    expect(find.text('신청이 취소됐어요.'), findsNothing);
    expect(find.byType(BlindMeetingResultScreen), findsOneWidget);
    expect(find.text('3:3 미팅이 매칭됐어요!'), findsOneWidget);
    expect(find.text('참가할게요'), findsNothing);
    // 매칭 직후 진입이라 추천 배너의 자동 숨김 타이머가 돈다 — 흘려보낸다.
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('취소 후 재신청: 이전 DNA 답변과 날짜가 전부 prefill 된다', (tester) async {
    // 이전 신청(취소됨)의 재사용 DNA 가 Firestore 에 남아 있다.
    repository.storedDna = BlindMeetingDna(
      userId: kMe,
      conversationAtmosphere: ConversationAtmosphere.lively,
      conversationInitiative: ConversationInitiative.listener,
      meetingPurpose: MeetingPurpose.friendship,
      alcoholCompanionPreference: AlcoholCompanionPreference.lightOkay,
      smokingCompanionPreference: SmokingCompanionPreference.noIndoorSmoking,
      interestIds: const ['커피', '영화'],
      drinkingLevelSnapshot: DrinkingLevel.none,
      smokingStatusSnapshot: SmokingStatus.nonSmoker,
      availableDateKeys: const ['2026-08-02', '2026-08-05'],
      waitlistOptIn: false,
    );
    repository.application = BlindMeetingApplication(
      userId: kMe,
      status: BlindMeetingParticipantStatus.cancelled,
      stage: BlindMeetingMatchingStage.cancelled,
      requestedDateKeys: const ['2026-08-02', '2026-08-05'],
    );

    await pumpApp(tester);
    expect(find.text('이미 신청이 진행 중이에요'), findsNothing);
    await tester.tap(find.text('미팅 DNA 작성하기'));
    await tester.pumpAndSettle();

    // 1/4 부터 이전 답변이 선택돼 있어 바로 다음으로 넘어갈 수 있다.
    expect(find.text('1/4'), findsOneWidget);
    await tester.tap(find.text('다음'));
    await tester.pumpAndSettle();
    expect(find.text('2/4'), findsOneWidget);
    await tester.tap(find.text('다음'));
    await tester.pumpAndSettle();
    expect(find.text('3/4'), findsOneWidget);
    await tester.tap(find.text('다음'));
    await tester.pumpAndSettle();
    expect(find.text('4/4'), findsOneWidget);
    // 값은 수정할 수 있다: 흡연 조건을 바꾼다.
    await tester.tap(
      find.text(SmokingCompanionPreference.nonSmokersOnly.label),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('일정 선택하기'));
    await tester.pumpAndSettle();

    // 이전 날짜 2개가 그대로 선택돼 있다 (기준 시각 2026-08-01).
    expect(find.byType(BlindMeetingScheduleScreen), findsOneWidget);
    expect(find.text('선택한 2개 날짜로 신청하기'), findsOneWidget);
    await tester.tap(find.text('선택한 2개 날짜로 신청하기'));
    await pumpFrames(tester);

    final dna = repository.submittedDna!;
    expect(dna.conversationAtmosphere, ConversationAtmosphere.lively);
    expect(dna.conversationInitiative, ConversationInitiative.listener);
    expect(dna.meetingPurpose, MeetingPurpose.friendship);
    expect(
      dna.alcoholCompanionPreference,
      AlcoholCompanionPreference.lightOkay,
    );
    expect(
      dna.smokingCompanionPreference,
      SmokingCompanionPreference.nonSmokersOnly,
    );
    expect(dna.availableDateKeys, ['2026-08-02', '2026-08-05']);
    expect(find.byType(BlindMeetingWaitingScreen), findsOneWidget);
  });

  testWidgets('앱 재진입: 매칭된 신청은 수락 화면 없이 매칭 결과(채팅 진입)로 복구된다', (tester) async {
    repository.completeMatching();
    await pumpApp(tester);
    expect(find.text('3:3 미팅이 매칭됐어요!'), findsOneWidget);
    expect(find.text('이미 신청이 진행 중이에요'), findsNothing);
    await tester.tap(find.text('매칭 결과 보기'));
    await tester.pumpAndSettle();
    expect(find.byType(BlindMeetingResultScreen), findsOneWidget);
    expect(find.text('채팅방으로 이동'), findsOneWidget);
    expect(find.text('참가할게요'), findsNothing);
    expect(find.text('이번에는 참가하지 않을게요'), findsNothing);
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
