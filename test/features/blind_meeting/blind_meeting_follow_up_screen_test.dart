// 3:3 블라인드 취향 미팅 — 후속 선택 화면.
//
// 선택 대상은 "상대 팀 전원"이 아니라 서버가 고를 수 있다고 판정한 상대다.
// 서버가 값으로 돌려준 거절과 callable 오류가 화면 상태에 반영되는지도 고정한다.

import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_followup.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_public_profile.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_session.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_follow_up_screen.dart';

const _meetingId = 'meeting-1';
const _me = 'a1';
final _now = DateTime.utc(2026, 11, 21, 12);

BlindMeetingPublicProfile _profile(String uid, String nickname) =>
    BlindMeetingPublicProfile(userId: uid, nickname: nickname, avatarSeed: uid);

class _FollowUpRepository extends BlindMeetingRepository {
  /// Server-selectable opponents. `null` makes the targets call fail.
  List<String>? targets = const ['b1', 'b2', 'b3'];
  int targetCalls = 0;

  BlindMeetingFollowUpChoice? storedChoice;
  List<BlindMeetingMutualMatch> matches = const [];

  /// What the next submit does. Defaults to storing the choice.
  Future<void> Function(List<String> selectedUids)? onSubmit;
  final submissions = <List<String>>[];

  @override
  Future<String?> currentUserId() async => _me;

  @override
  Future<BlindMeetingRecommendationView?> loadRecommendation(
    String meetingId,
  ) async {
    return BlindMeetingRecommendationView(
      session: BlindMeetingSession(
        meetingId: meetingId,
        status: BlindMeetingStatus.followupOpen,
        teamAUserIds: const [_me, 'a2', 'a3'],
        teamBUserIds: const ['b1', 'b2', 'b3'],
        participantIds: const [_me, 'a2', 'a3', 'b1', 'b2', 'b3'],
        followupClosesAt: _now.add(const Duration(hours: 20)),
      ),
      viewerTeam: BlindMeetingTeam.teamA,
      myTeam: [_profile(_me, '민지'), _profile('a2', '서연')],
      opponentTeam: [
        _profile('b1', '하늘'),
        _profile('b2', '도윤'),
        _profile('b3', '지호'),
      ],
      me: const BlindMeetingParticipant(
        userId: _me,
        team: BlindMeetingTeam.teamA,
        status: BlindMeetingParticipantStatus.completed,
        checkedIn: true,
        checkedOut: true,
      ),
    );
  }

  @override
  Future<List<String>> loadFollowUpTargets(String meetingId) async {
    targetCalls += 1;
    final value = targets;
    if (value == null) {
      throw FirebaseFunctionsException(
        code: 'unavailable',
        message: 'UNAVAILABLE',
      );
    }
    return value;
  }

  @override
  Future<BlindMeetingFollowUpChoice?> loadMyFollowUpChoice(
    String meetingId,
  ) async => storedChoice;

  @override
  Future<List<BlindMeetingMutualMatch>> loadMutualMatches(
    String meetingId,
  ) async => matches;

  @override
  Future<void> submitFollowUpChoice({
    required String meetingId,
    required List<String> selectedUids,
  }) async {
    submissions.add(List<String>.of(selectedUids));
    final handler = onSubmit;
    if (handler != null) return handler(selectedUids);
    storeChoice(selectedUids);
  }

  void storeChoice(List<String> selectedUids) {
    storedChoice = BlindMeetingFollowUpChoice(
      meetingId: _meetingId,
      chooserUid: _me,
      selectedUids: selectedUids,
      submittedAt: _now,
    );
  }
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _open(WidgetTester tester, _FollowUpRepository repository) async {
  tester.view.physicalSize = const Size(1080, 4200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: BlindMeetingFollowUpScreen(
        args: const BlindMeetingMeetingArgs(meetingId: _meetingId),
        repository: repository,
        now: _now,
      ),
    ),
  );
  await _settle(tester);
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
  });

  testWidgets('서버가 선택 가능하다고 한 상대만 선택 대상으로 보인다', (tester) async {
    final repository = _FollowUpRepository()..targets = const ['b1', 'b3'];
    await _open(tester, repository);

    expect(repository.targetCalls, 1);
    expect(find.text('하늘'), findsOneWidget);
    expect(find.text('지호'), findsOneWidget);
    expect(find.text('도윤'), findsNothing, reason: '서버가 거절할 상대');
    expect(find.text('민지'), findsNothing, reason: '같은 팀');

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(repository.submissions, [
      ['b1'],
    ]);
    expect(find.textContaining('선택을 제출했어요'), findsOneWidget);
  });

  testWidgets('선택 가능한 상대가 없어도 선택 없이 마칠 수 있다', (tester) async {
    final repository = _FollowUpRepository()..targets = const [];
    await _open(tester, repository);

    expect(find.text('하늘'), findsNothing);
    expect(find.text('지금 선택할 수 있는 상대가 없어요.'), findsOneWidget);

    await tester.tap(find.text('선택하지 않고 마치기'));
    await _settle(tester);

    expect(repository.submissions, [<String>[]]);
  });

  testWidgets('선택 대상 조회가 실패하면 상대 팀 전체로 되돌아간다 (서버가 제출을 검증한다)', (tester) async {
    final repository = _FollowUpRepository()..targets = null;
    await _open(tester, repository);

    expect(find.text('하늘'), findsOneWidget);
    expect(find.text('도윤'), findsOneWidget);
    expect(find.text('지호'), findsOneWidget);
    expect(find.text('잠시 문제가 생겼어요'), findsNothing);
  });

  testWidgets('제출 중 두 번째 탭은 다시 제출하지 않고, 카드도 바뀌지 않는다', (tester) async {
    final gate = Completer<void>();
    final repository = _FollowUpRepository();
    repository.onSubmit = (selected) async {
      await gate.future;
      repository.storeChoice(selected);
    };
    await _open(tester, repository);

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await tester.pump();
    // The button shows a spinner while submitting; tap where it is.
    await tester.tap(
      find.byType(BlindMeetingFollowUpScreen),
      warnIfMissed: false,
    );
    await tester.tap(find.text('도윤'), warnIfMissed: false);
    await tester.pump();

    expect(repository.submissions, hasLength(1));

    gate.complete();
    await _settle(tester);

    expect(repository.submissions, [
      ['b1'],
    ]);
    expect(repository.storedChoice!.selectedUids, ['b1']);
  });

  testWidgets('already_submitted 거절은 저장된 선택으로 화면을 다시 맞춘다', (tester) async {
    final repository = _FollowUpRepository();
    repository.onSubmit = (selected) async {
      // The first attempt committed on the server before failing; the retry
      // is answered with the stored choice.
      repository.storeChoice(const ['b3']);
      repository.matches = [
        BlindMeetingMutualMatch(
          partnerUid: 'b3',
          chatRoomId: 'dm_b3_a1',
          matchedAt: _now,
        ),
      ];
      throw const BlindMeetingFollowUpRejectedException('already_submitted');
    };
    await _open(tester, repository);

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(find.textContaining('선택을 제출했어요'), findsOneWidget);
    expect(find.text('1:1 채팅 열기'), findsOneWidget);
    expect(find.textContaining('이미 선택을 제출했어요'), findsNothing);

    // The cards and the button are locked on the stored choice.
    await tester.tap(find.text('도윤'), warnIfMissed: false);
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'), warnIfMissed: false);
    await _settle(tester);
    expect(repository.submissions, hasLength(1));
  });

  testWidgets('not_open 거절은 선택을 지우지 않고 다시 누를 수 있게 둔다', (tester) async {
    final repository = _FollowUpRepository();
    var attempts = 0;
    repository.onSubmit = (selected) async {
      attempts += 1;
      if (attempts == 1) {
        throw const BlindMeetingFollowUpRejectedException('not_open');
      }
      repository.storeChoice(selected);
    };
    await _open(tester, repository);

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(find.textContaining('아직 후속 선택이 열리지 않았어요'), findsOneWidget);

    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(repository.submissions, [
      ['b1'],
      ['b1'],
    ]);
    expect(find.textContaining('선택을 제출했어요'), findsOneWidget);
  });

  testWidgets('callable 오류는 SDK 접두어 없이 서버 문구로 보인다', (tester) async {
    final repository = _FollowUpRepository();
    repository.onSubmit = (_) async {
      throw FirebaseFunctionsException(
        code: 'invalid-argument',
        message: '선택할 수 없는 상대예요.',
      );
    };
    await _open(tester, repository);

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(find.text('선택할 수 없는 상대예요.'), findsOneWidget);
    expect(find.textContaining('firebase_functions'), findsNothing);
    expect(find.textContaining('invalid-argument'), findsNothing);
  });

  testWidgets('SDK 가 만든 상태 이름은 그대로 노출하지 않는다', (tester) async {
    final repository = _FollowUpRepository();
    repository.onSubmit = (_) async {
      throw FirebaseFunctionsException(
        code: 'unavailable',
        message: 'UNAVAILABLE',
      );
    };
    await _open(tester, repository);

    await tester.tap(find.text('하늘'));
    await tester.pump();
    await tester.tap(find.text('선택 제출하기'));
    await _settle(tester);

    expect(find.textContaining('UNAVAILABLE'), findsNothing);
    expect(find.textContaining('선택을 제출하지 못했어요'), findsOneWidget);
    // The selection survives and the button works again.
    expect(find.text('선택 제출하기'), findsOneWidget);
    expect(repository.submissions, hasLength(1));
  });
}
