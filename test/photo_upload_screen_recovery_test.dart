// needs_review recovery, server-authoritative retry, and source_selecting
// resume for PhotoUploadScreen.
//
// Kept in its own file so it does not overlap the concurrently edited
// photo_upload_screen_avatar_flow_test.dart.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/screens/photo_upload_screen.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_resume_policy.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_error_banner.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';
import 'package:seolleyeon/shared/utils/avatar_lock_policy.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _RecoveryClient extends AvatarGenerationClient {
  _RecoveryClient({
    this.pollStatus = AvatarJobStatus.needsReview,
    this.pollErrorCode = 'qa_requires_review',
    this.serverStatus,
    this.serverRetryAllowed = false,
    this.useRealPollingLoop = false,
  });

  final AvatarJobStatus pollStatus;
  final String pollErrorCode;
  final String? serverStatus;
  final bool serverRetryAllowed;

  /// true 면 실제 폴링 루프(getCandidates 반복)를 쓴다. 서버가 아직 진행 중인
  /// 상태를 재현할 때 사용한다.
  final bool useRealPollingLoop;
  int replaceCalls = 0;
  int retryCalls = 0;
  int pollCount = 0;

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    pollCount += 1;
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.queued,
      candidates: const [],
    );
  }

  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    if (useRealPollingLoop) {
      return super.pollUntilPreviewReady(
        jobId: jobId,
        pollInterval: pollInterval,
        timeout: timeout,
        shouldContinue: shouldContinue,
        maxConsecutiveErrors: maxConsecutiveErrors,
      );
    }
    pollCount += 1;
    return AvatarCandidatesResult(
      jobId: jobId,
      status: pollStatus,
      candidates: const [],
      errorCode: pollErrorCode,
    );
  }

  @override
  Future<AvatarGenerationStatusSnapshot?> getCurrentGenerationStatus() async {
    if (serverStatus == null) return null;
    return AvatarGenerationStatusSnapshot.fromMap({
      'sourceLocked': true,
      'jobId': 'avatar_job_recovery_1',
      'sourceSelectionVersion': 1,
      'status': serverStatus,
      'candidateAvailability': 'none',
      'retryAllowed': serverRetryAllowed,
      'approved': false,
      'safeReasonCode': null,
    });
  }

  @override
  Future<AvatarGenerationStatusSnapshot?> retryCurrentGeneration({
    required String clientRequestId,
  }) async {
    retryCalls += 1;
    return AvatarGenerationStatusSnapshot.fromMap({
      'sourceLocked': true,
      'jobId': 'avatar_job_recovery_1',
      'sourceSelectionVersion': 1,
      'status': 'queued',
      'candidateAvailability': 'none',
      'retryAllowed': false,
      'approved': false,
      'safeReasonCode': null,
    });
  }

  @override
  Future<bool> replaceCurrentGeneration({
    required String clientRequestId,
  }) async {
    replaceCalls += 1;
    return true;
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async =>
      throw UnimplementedError();
}

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 1100);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Widget _harness(AvatarGenerationClient client) {
  return MaterialApp(
    home: PhotoUploadScreen(
      avatarGenerationClient: client,
      initialPhotosForTesting: [
        AvatarSourcePhotoService.queuedSlotToken('avatar_job_recovery_1'),
        AvatarSourcePhotoService.queuedSlotToken('avatar_job_recovery_1'),
      ],
      onNext: (_) {},
    ),
  );
}

Finder _nextButton() => find.byType(ElevatedButton).last;

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('needs_review recovery', () {
    testWidgets('shows review copy, no retry, and offers start over', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _RecoveryClient();
      await tester.pumpWidget(_harness(client));
      await tester.pump();

      await tester.tap(_nextButton());
      await _settle(tester);

      expect(find.text(avatarNeedsReviewMessage), findsWidgets);
      expect(find.text(avatarGenerationFailedMessage), findsNothing);
      expect(find.text(avatarGenericNoPreviewMessage), findsNothing);
      expect(find.text('다시 시도'), findsNothing);
      expect(find.text(avatarStartOverButtonLabel), findsOneWidget);
      // 같은 generation 재시도 금지: 소스는 여전히 잠겨 있다.
      expect(find.byIcon(Icons.close_rounded), findsNothing);
    });

    testWidgets(
      'start over ends the generation server-side and unlocks the screen',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _RecoveryClient();
        await tester.pumpWidget(_harness(client));
        await tester.pump();
        await tester.tap(_nextButton());
        await _settle(tester);
        expect(find.text(avatarStartOverButtonLabel), findsOneWidget);

        await tester.tap(find.text(avatarStartOverButtonLabel));
        await _settle(tester);

        expect(client.replaceCalls, 1);
        expect(find.byType(AvatarGenerationErrorBanner), findsNothing);
        expect(find.text(sourceLockedAvatarMessage), findsNothing);
        // 잠금이 풀리고 새 사진 세트를 받을 준비가 된 빈 화면.
        expect(find.text('최소 2장 필요'), findsOneWidget);
      },
    );

    testWidgets('double tap on start over releases exactly once', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _RecoveryClient();
      await tester.pumpWidget(_harness(client));
      await tester.pump();
      await tester.tap(_nextButton());
      await _settle(tester);

      await tester.tap(find.text(avatarStartOverButtonLabel));
      await tester.tap(
        find.text(avatarStartOverButtonLabel),
        warnIfMissed: false,
      );
      await _settle(tester);

      expect(client.replaceCalls, 1);
    });
  });

  group('server-authoritative retry', () {
    testWidgets('retry goes through the server when it allows a retry', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _RecoveryClient(
        pollStatus: AvatarJobStatus.failed,
        pollErrorCode: 'azure_rate_limit_timeout',
        serverStatus: 'retryable_failed',
        serverRetryAllowed: true,
      );
      await tester.pumpWidget(_harness(client));
      await tester.pump();
      await tester.tap(_nextButton());
      await _settle(tester);
      expect(find.text('다시 시도'), findsOneWidget);

      await tester.tap(find.text('다시 시도'));
      await _settle(tester);

      expect(
        client.retryCalls,
        1,
        reason: 'the server re-dispatches the same job',
      );
    });

    testWidgets(
      'retry is refused without a server call when the server says terminal',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _RecoveryClient(
          pollStatus: AvatarJobStatus.failed,
          pollErrorCode: 'no_safe_avatar_candidates',
          serverStatus: 'terminal_failed',
        );
        await tester.pumpWidget(_harness(client));
        await tester.pump();
        await tester.tap(_nextButton());
        await _settle(tester);
        // In-session failure still shows the retry button (server not consulted yet).
        expect(find.text('다시 시도'), findsOneWidget);

        await tester.tap(find.text('다시 시도'));
        await _settle(tester);

        expect(client.retryCalls, 0);
        expect(find.text(avatarTerminalFailureMessage), findsWidgets);
        expect(find.text('다시 시도'), findsNothing);
        expect(find.text(avatarStartOverButtonLabel), findsOneWidget);
      },
    );

    testWidgets('reconciliation_required offers neither retry nor start over', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _RecoveryClient(
        pollStatus: AvatarJobStatus.failed,
        serverStatus: 'reconciliation_required',
      );
      await tester.pumpWidget(_harness(client));
      await tester.pump();
      await tester.tap(_nextButton());
      await _settle(tester);
      await tester.tap(find.text('다시 시도'));
      await _settle(tester);

      expect(client.retryCalls, 0);
      expect(client.replaceCalls, 0);
      expect(find.text(avatarReconciliationRequiredMessage), findsWidgets);
      expect(find.text('다시 시도'), findsNothing);
      expect(find.text(avatarStartOverButtonLabel), findsNothing);
    });
  });

  group('source_selecting resume', () {
    testWidgets(
      'restart while the server is selecting the source keeps waiting',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _RecoveryClient(
          serverStatus: 'source_selecting',
          useRealPollingLoop: true,
        );
        await tester.pumpWidget(_harness(client));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        expect(find.byType(AvatarGenerationErrorBanner), findsNothing);
        expect(client.pollCount, greaterThan(0));

        // 폴링 루프 정리.
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump(const Duration(seconds: 3));
      },
    );
  });

  test('resume policy treats source_selecting as active work', () {
    final plan = planAvatarResume(
      AvatarGenerationStatusSnapshot.fromMap({
        'sourceLocked': true,
        'jobId': 'avatar_job_recovery_1',
        'sourceSelectionVersion': 1,
        'status': 'source_selecting',
        'candidateAvailability': 'none',
        'retryAllowed': false,
        'approved': false,
      }),
    );
    expect(plan.action, AvatarResumeAction.resumeGenerating);
    expect(plan.retryAllowed, isFalse);
    expect(plan.allowsNewGeneration, isFalse);
  });
}
