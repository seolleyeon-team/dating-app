// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 알림 클릭 / deep link 테스트
// 경로: test/features/meeting_icebreaker/meeting_icebreaker_deep_link_test.dart
//
// foreground / background / 완전 종료 상태를 모두 다룬다.
// onMessage, onMessageOpenedApp, getInitialMessage 가 같은 알림을 각각 넘겨도
// 룰렛이 두 번 열리지 않아야 한다.
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/services/meeting_icebreaker_deep_link_handler.dart';
import 'package:seolleyeon/services/navigation_service.dart';

import 'meeting_icebreaker_test_support.dart';

void main() {
  final handler = MeetingIcebreakerDeepLinkHandler.instance;

  late FakeMeetingIcebreakerRepository repository;
  late List<MeetingIcebreakerEntry> opened;
  late List<String> messages;

  Map<String, dynamic> pushData({
    String type = kMeetingIcebreakerNotificationType,
    String sessionId = 'blind_m1',
    String meetingId = 'm1',
    String notificationId = 'meeting_icebreaker_blind_m1_u1_1',
    String sequence = '1',
  }) {
    return <String, dynamic>{
      'type': type,
      'sessionId': sessionId,
      'meetingId': meetingId,
      'meetingType': 'blindTasteMeeting',
      'notificationSequence': sequence,
      'notificationId': notificationId,
    };
  }

  Widget app() => MaterialApp(
    navigatorKey: NavigationService.navigatorKey,
    home: const Scaffold(body: Center(child: Text('home'))),
  );

  setUp(() {
    handler.resetForTest();
    repository = FakeMeetingIcebreakerRepository();
    opened = <MeetingIcebreakerEntry>[];
    messages = <String>[];

    handler.repositoryFactory = () => repository;
    handler.dialogOpener = (context, entry, repo, analytics) async {
      opened.add(entry);
    };
    handler.messagePresenter = (context, message) => messages.add(message);
  });

  tearDown(() {
    handler.resetForTest();
    handler.repositoryFactory = () => throw StateError('not configured');
  });

  testWidgets('foreground: 알림을 누르면 룰렛이 열린다', (tester) async {
    await tester.pumpWidget(app());

    final handled = await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(handled, isTrue);
    expect(repository.loadEntryCalls, 1);
    expect(opened.length, 1);
    expect(opened.single.sessionId, 'blind_m1');
    expect(messages, isEmpty);
  });

  testWidgets('background: onMessageOpenedApp도 같은 경로를 쓴다', (tester) async {
    await tester.pumpWidget(app());

    await handler.handleNotificationData(
      pushData(
        notificationId: 'meeting_icebreaker_blind_m1_u1_2',
        sequence: '2',
      ),
    );
    await tester.pump();

    expect(opened.length, 1);
  });

  testWidgets('같은 알림을 두 번 눌러도 팝업은 한 번만 열린다', (tester) async {
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await handler.handleNotificationData(pushData());
    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened.length, 1);
    expect(repository.loadEntryCalls, 1);
  });

  testWidgets('여러 listener가 같은 알림을 넘겨도 중복 열리지 않는다', (tester) async {
    await tester.pumpWidget(app());

    // onMessage / onMessageOpenedApp / getInitialMessage 가 동시에 전달한 상황
    final futures = <Future<bool>>[
      handler.handleNotificationData(pushData()),
      handler.handleNotificationData(pushData()),
      handler.handleNotificationData(pushData()),
    ];
    await Future.wait(futures);
    await tester.pump();

    expect(opened.length, 1);
  });

  testWidgets('다음 순번 알림은 다시 열 수 있다', (tester) async {
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await handler.handleNotificationData(
      pushData(
        notificationId: 'meeting_icebreaker_blind_m1_u1_2',
        sequence: '2',
      ),
    );
    await tester.pump();

    expect(opened.length, 2);
  });

  testWidgets('완전 종료 상태: 앱이 준비된 뒤 보류된 알림을 이어서 처리한다', (tester) async {
    // navigator가 아직 없는 상태 (Firebase / 라우터 초기화 중)
    final pending = handler.handlePayload(
      MeetingIcebreakerPromptPayload.tryParse(pushData())!,
    );
    // 재시도 대기 시간을 모두 소진시킨다.
    await tester.pump(const Duration(seconds: 12));
    await pending;

    expect(opened, isEmpty);

    await tester.pumpWidget(app());
    await handler.flushPending();
    await tester.pump();

    expect(opened.length, 1);
  });

  testWidgets('종료된 미팅이면 룰렛을 열지 않고 안내만 보여준다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.meetingEnded,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages, <String>['이 미팅은 이미 종료되었어요.']);
  });

  testWidgets('취소된 미팅도 열지 않는다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.meetingCancelled,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '이 미팅은 취소되었어요.');
  });

  testWidgets('다른 사람의 미팅이면 접근을 막는다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.notParticipant,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData(sessionId: 'blind_other'));
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '참가 중인 미팅이 아니에요.');
  });

  testWidgets('시작 안전도장 전이면 열리지 않는다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.notStarted,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '미팅 시작 안전도장을 찍은 뒤에 열 수 있어요.');
  });

  testWidgets('로그아웃 상태면 로그인 안내를 보여준다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.unauthenticated,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '로그인이 필요해요.');
  });

  testWidgets('feature flag가 꺼져 있으면 안전하게 안내한다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.featureDisabled,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '지금은 미팅 룰렛을 사용할 수 없어요.');
  });

  testWidgets('네트워크 오류는 dedupe에 남기지 않아 다시 시도할 수 있다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.unavailable,
    );
    await tester.pumpWidget(app());

    await handler.handleNotificationData(pushData());
    await tester.pump();
    expect(opened, isEmpty);
    expect(handler.hasHandled('meeting_icebreaker_blind_m1_u1_1'), isFalse);

    // 복구된 뒤 같은 알림을 다시 눌러 성공
    repository.entry = const MeetingIcebreakerEntry(
      decision: MeetingIcebreakerEntryDecision.allowed,
      sessionId: 'blind_m1',
      meetingId: 'm1',
    );
    await handler.handleNotificationData(pushData());
    await tester.pump();
    expect(opened.length, 1);
  });

  testWidgets('룰렛 알림이 아니면 처리하지 않는다', (tester) async {
    await tester.pumpWidget(app());

    expect(
      await handler.handleNotificationData(pushData(type: 'chat')),
      isFalse,
    );
    expect(
      await handler.handleNotificationData(
        pushData(type: 'blind_meeting_checkin'),
      ),
      isFalse,
    );
    expect(repository.loadEntryCalls, 0);
    expect(opened, isEmpty);
  });

  testWidgets('식별자가 없는 payload는 무시한다', (tester) async {
    await tester.pumpWidget(app());

    expect(
      await handler.handleNotificationData(
        pushData(sessionId: '', meetingId: ''),
      ),
      isFalse,
    );
    expect(repository.loadEntryCalls, 0);
  });

  testWidgets('앱 내 진입 경로도 같은 서버 검증을 거친다', (tester) async {
    await tester.pumpWidget(app());
    final context = NavigationService.navigatorKey.currentContext!;

    await handler.openFromApp(context: context, sessionId: 'blind_m1');
    await tester.pump();

    expect(repository.loadEntryCalls, 1);
    expect(opened.length, 1);
  });

  testWidgets('앱 내 진입도 종료된 미팅은 막는다', (tester) async {
    repository.entry = const MeetingIcebreakerEntry.denied(
      MeetingIcebreakerEntryDecision.meetingEnded,
    );
    await tester.pumpWidget(app());
    final context = NavigationService.navigatorKey.currentContext!;

    await handler.openFromApp(context: context, sessionId: 'blind_m1');
    await tester.pump();

    expect(opened, isEmpty);
    expect(messages.single, '이 미팅은 이미 종료되었어요.');
  });
}
