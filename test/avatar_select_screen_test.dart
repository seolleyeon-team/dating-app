import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/screens/avatar_select_screen.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_generation_session_controller.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_resume_policy.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_selection_dialog.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_tile.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';

class _SelectClient extends AvatarGenerationClient {
  _SelectClient({required this.status, this.retryAllowed = false});

  String status;
  bool retryAllowed;
  String candidateAvailability = 'none';
  String? approvedCandidateId;
  int retryCalls = 0;
  int replaceCalls = 0;
  int candidateCalls = 0;
  bool replaceResult = true;
  bool failApproval = false;
  String approvalStatus = 'approved';

  /// approve → complete → finished 순서 검증용.
  final List<String> events = <String>[];

  @override
  Future<AvatarGenerationStatusSnapshot?> getCurrentGenerationStatus() async {
    if (status == '<null>') return null;
    return AvatarGenerationStatusSnapshot.fromMap({
      'sourceLocked': status != 'none',
      'jobId': 'avatar_job_select_0001',
      'sourceSelectionVersion': 1,
      'status': status,
      'candidateAvailability': candidateAvailability,
      'retryAllowed': retryAllowed,
      'approved': status == 'approved',
    });
  }

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    candidateCalls += 1;
    return AvatarCandidatesResult(
      jobId: jobId,
      status: status == 'needs_review'
          ? AvatarJobStatus.needsReview
          : AvatarJobStatus.previewReady,
      candidates: List<AvatarCandidate>.generate(
        2,
        (index) => AvatarCandidate(
          candidateId: 'cand_$index',
          previewUrl: 'https://example.invalid/avatar_$index.png',
        ),
      ),
    );
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    events.add('approve');
    approvedCandidateId = candidateId;
    if (failApproval) throw Exception('approve_failed');
    return AvatarApprovalResult(
      avatarStatus: approvalStatus,
      approvedAvatarUrl: 'https://cdn.example/avatar.png',
      selectedCandidateId: candidateId,
      duplicate: false,
    );
  }

  @override
  Future<AvatarGenerationStatusSnapshot?> retryCurrentGeneration({
    required String clientRequestId,
  }) async {
    retryCalls += 1;
    status = 'queued';
    retryAllowed = false;
    return getCurrentGenerationStatus();
  }

  @override
  Future<bool> replaceCurrentGeneration({
    required String clientRequestId,
  }) async {
    replaceCalls += 1;
    if (replaceResult) status = 'none';
    return replaceResult;
  }
}

class _Harness {
  _Harness(this.client) {
    controller = AvatarGenerationSessionController(
      client: client,
      uidResolver: () async => null,
      profileStreamFactory: (_) => const Stream.empty(),
      authUidStream: const Stream.empty(),
    );
  }

  final _SelectClient client;
  late final AvatarGenerationSessionController controller;
  int completeCalls = 0;
  int finishedCalls = 0;
  int startOverCalls = 0;

  Widget build() {
    return MaterialApp(
      home: AvatarSelectScreen(
        controller: controller,
        completeOnboarding: () async {
          completeCalls += 1;
          client.events.add('complete');
        },
        onFinished: () {
          finishedCalls += 1;
          client.events.add('finished');
        },
        onStartOver: () => startOverCalls += 1,
      ),
    );
  }

  bool _disposed = false;

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    controller.dispose();
  }
}

/// 위젯을 내리고 컨트롤러를 정리한다. 폴링 타이머가 남으면 테스트가 실패한다.
Future<void> _finish(WidgetTester tester, _Harness h) async {
  await tester.pumpWidget(const SizedBox.shrink());
  h.dispose();
}

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 1100);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void _drainImageErrors(WidgetTester tester) {
  tester.takeException();
}

void main() {
  testWidgets(
    'generating shows the waiting overlay, then switches to selection',
    (tester) async {
      await _useMobileSurface(tester);
      final client = _SelectClient(status: 'queued');
      final h = _Harness(client);
      addTearDown(h.dispose);

      await tester.pumpWidget(h.build());
      await _settle(tester);

      expect(find.text('아바타 생성중...'), findsOneWidget);
      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);

      client.status = 'preview_ready';
      client.candidateAvailability = 'preview_safe';
      await h.controller.refresh();
      await _settle(tester);
      _drainImageErrors(tester);

      expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);
      expect(find.byType(AvatarCandidateTile), findsNWidgets(2));
      expect(find.text('아바타 생성중...'), findsNothing);
      expect(h.controller.bannerShown, isTrue, reason: '마지막 화면에서는 배너 없이 소비한다');

      await tester.tap(find.byType(AvatarCandidateTile).first);
      await tester.pump();
      await tester.tap(
        find.descendant(
          of: find.byType(AvatarCandidateSelectionDialog),
          matching: find.byType(ElevatedButton),
        ),
      );
      await _settle(tester);
      _drainImageErrors(tester);

      expect(client.approvedCandidateId, 'cand_0');
      expect(h.completeCalls, 1);
      expect(h.finishedCalls, 1);
      expect(client.events, ['approve', 'complete', 'finished']);
      await _finish(tester, h);
    },
  );

  testWidgets('an approval exception never completes onboarding', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'preview_ready')
      ..candidateAvailability = 'preview_safe'
      ..failApproval = true;
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);
    _drainImageErrors(tester);
    expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);

    await tester.tap(find.byType(AvatarCandidateTile).first);
    await tester.pump();
    await tester.tap(
      find.descendant(
        of: find.byType(AvatarCandidateSelectionDialog),
        matching: find.byType(ElevatedButton),
      ),
    );
    await _settle(tester);
    _drainImageErrors(tester);

    expect(client.events, ['approve']);
    expect(h.completeCalls, 0);
    expect(h.finishedCalls, 0);
    expect(find.text(avatarSelectApprovalErrorMessage), findsOneWidget);
    // 선택 UI 는 그대로 남아 다시 시도할 수 있다.
    expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);
    await _finish(tester, h);
  });

  testWidgets('a non-approved server status never completes onboarding', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'preview_ready')
      ..candidateAvailability = 'preview_safe'
      ..approvalStatus = 'approval_copying_failed';
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);
    _drainImageErrors(tester);

    await tester.tap(find.byType(AvatarCandidateTile).first);
    await tester.pump();
    await tester.tap(
      find.descendant(
        of: find.byType(AvatarCandidateSelectionDialog),
        matching: find.byType(ElevatedButton),
      ),
    );
    await _settle(tester);
    _drainImageErrors(tester);

    expect(client.events, ['approve']);
    expect(h.completeCalls, 0);
    expect(h.finishedCalls, 0);
    await _finish(tester, h);
  });

  testWidgets('preview state switches in place without route changes', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'source_selecting');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);
    final screenElement = find.byType(AvatarSelectScreen).evaluate().single;
    expect(find.text('아바타 생성중...'), findsOneWidget);

    client.status = 'preview_ready';
    client.candidateAvailability = 'preview_safe';
    await h.controller.refresh();
    await _settle(tester);
    _drainImageErrors(tester);

    expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);
    // 같은 화면(State) 안에서 전환됐다. push/pop 이 없다.
    expect(
      find.byType(AvatarSelectScreen).evaluate().single,
      same(screenElement),
    );
    await _finish(tester, h);
  });

  testWidgets('needs_review offers start over but no retry', (tester) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'needs_review');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarNeedsReviewMessage), findsOneWidget);
    expect(find.text(avatarSelectRetryLabel), findsNothing);
    expect(find.text(avatarStartOverButtonLabel), findsOneWidget);
    expect(find.text('아바타 생성중...'), findsNothing);

    await tester.tap(find.text(avatarStartOverButtonLabel));
    await _settle(tester);

    expect(client.replaceCalls, 1);
    expect(h.startOverCalls, 1);
    expect(h.controller.phase, AvatarSessionPhase.idle);
    await _finish(tester, h);
  });

  testWidgets('soft needs_review candidates are shown and can be approved', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'needs_review')
      ..candidateAvailability = 'preview_safe';
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);
    _drainImageErrors(tester);

    expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);
    expect(find.byType(AvatarCandidateTile), findsNWidgets(2));
    expect(find.text(avatarNeedsReviewMessage), findsNothing);

    await tester.tap(find.byType(AvatarCandidateTile).first);
    await tester.pump();
    await tester.tap(
      find.descendant(
        of: find.byType(AvatarCandidateSelectionDialog),
        matching: find.byType(ElevatedButton),
      ),
    );
    await _settle(tester);

    expect(client.approvedCandidateId, 'cand_0');
    expect(h.completeCalls, 1);
    expect(h.finishedCalls, 1);
    await _finish(tester, h);
  });

  testWidgets('retryable failure retries through the server and waits again', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(
      status: 'retryable_failed',
      retryAllowed: true,
    );
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarSelectRetryLabel), findsOneWidget);
    expect(find.text(avatarStartOverButtonLabel), findsOneWidget);

    await tester.tap(find.text(avatarSelectRetryLabel));
    await _settle(tester);

    expect(client.retryCalls, 1);
    expect(h.controller.phase, AvatarSessionPhase.generating);
    expect(find.text('아바타 생성중...'), findsOneWidget);
    await _finish(tester, h);
  });

  testWidgets('reconciliation_required offers neither retry nor start over', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'reconciliation_required');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarReconciliationRequiredMessage), findsOneWidget);
    expect(find.text(avatarSelectRetryLabel), findsNothing);
    expect(find.text(avatarStartOverButtonLabel), findsNothing);
    await _finish(tester, h);
  });

  testWidgets('terminal failure offers only start over', (tester) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'terminal_failed');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarTerminalFailureMessage), findsOneWidget);
    expect(find.text(avatarSelectRetryLabel), findsNothing);
    expect(find.text(avatarStartOverButtonLabel), findsOneWidget);
    await _finish(tester, h);
  });

  testWidgets('already approved completes onboarding immediately', (
    tester,
  ) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'approved');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(h.completeCalls, 1);
    expect(h.finishedCalls, 1);
    await _finish(tester, h);
  });

  testWidgets('unreadable status shows a check-again action', (tester) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: '<null>');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarSelectStatusUnavailableMessage), findsOneWidget);
    expect(find.text(avatarSelectCheckAgainLabel), findsOneWidget);

    client.status = 'queued';
    await tester.tap(find.text(avatarSelectCheckAgainLabel));
    await _settle(tester);
    expect(find.text('아바타 생성중...'), findsOneWidget);
    await _finish(tester, h);
  });

  testWidgets('no job at all sends the user back to photos', (tester) async {
    await _useMobileSurface(tester);
    final client = _SelectClient(status: 'none');
    final h = _Harness(client);
    addTearDown(h.dispose);

    await tester.pumpWidget(h.build());
    await _settle(tester);

    expect(find.text(avatarSelectNoJobMessage), findsOneWidget);
    await tester.tap(find.text(avatarSelectGoToPhotosLabel));
    await _settle(tester);
    expect(h.startOverCalls, 1);
    await _finish(tester, h);
  });
}
