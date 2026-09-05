import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/screens/photo_upload_screen.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_resume_policy.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_selection_dialog.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_tile.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_error_banner.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';
import 'package:seolleyeon/services/onboarding_photo_source_ref.dart';
import 'package:seolleyeon/shared/utils/avatar_lock_policy.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _ReadyAvatarClient extends AvatarGenerationClient {
  _ReadyAvatarClient({this.candidateCount = 2});

  final int candidateCount;
  String? approvedCandidateId;
  final List<String> polledJobIds = <String>[];
  List<OnboardingPhotoSourceRef>? admittedSources;

  @override
  Future<AvatarSourcePhotoUploadResult> beginFromOnboardingPhotos({
    required List<OnboardingPhotoSourceRef> sourcePhotos,
    required String uid,
    String? clientRequestId,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    admittedSources = List<OnboardingPhotoSourceRef>.from(sourcePhotos);
    return const AvatarSourcePhotoUploadResult(
      jobId: 'job_ready',
      photoId: '',
      avatarStatus: 'queued',
      message: 'avatar_generation_queued',
      duplicate: false,
      sourceSelectionVersion: 1,
    );
  }

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    return _readyResult(jobId);
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
    polledJobIds.add(jobId);
    return _readyResult(jobId);
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    approvedCandidateId = candidateId;
    return AvatarApprovalResult(
      avatarStatus: 'approved',
      approvedAvatarUrl: 'https://cdn.example/avatar.png',
      selectedCandidateId: candidateId,
      duplicate: false,
    );
  }

  AvatarCandidatesResult _readyResult(String jobId) {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.previewReady,
      candidates: List<AvatarCandidate>.generate(
        candidateCount,
        (index) => AvatarCandidate(
          candidateId: 'cand_$index',
          previewUrl: 'https://example.invalid/avatar_$index.png',
        ),
      ),
    );
  }
}

class _FailingAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.failed,
      candidates: const [],
    );
  }
}

class _NoPreviewableAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.noPreviewableCandidates,
      candidates: const [],
    );
  }
}

class _SourceRejectedAvatarClient extends _ReadyAvatarClient {
  _SourceRejectedAvatarClient(this.errorCode);

  final String errorCode;

  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.failed,
      candidates: const [],
      errorCode: errorCode,
    );
  }
}

class _TimeoutAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    throw TimeoutException('app_check_token_retry_exhausted');
  }
}

class _CallableErrorAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    throw Exception('firebase_functions unauthenticated');
  }
}

class _FailThenReadyAvatarClient extends _ReadyAvatarClient {
  int pollCount = 0;

  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    pollCount += 1;
    if (pollCount == 1) {
      return AvatarCandidatesResult(
        jobId: jobId,
        status: AvatarJobStatus.failed,
        candidates: const [],
      );
    }
    return _readyResult(jobId);
  }
}

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 1100);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Widget _harness({
  required AvatarGenerationClient client,
  required void Function(List<String>) onNext,
  List<String?>? initialPhotos,
  List<OnboardingPhotoSourceRef?>? initialSourceRefs,
  String? lockedApprovedAvatarUrl,
}) {
  return MaterialApp(
    home: PhotoUploadScreen(
      avatarGenerationClient: client,
      initialPhotosForTesting:
          initialPhotos ??
          [
            AvatarSourcePhotoService.queuedSlotToken('job_ready'),
            AvatarSourcePhotoService.queuedSlotToken('job_second'),
          ],
      initialSourceRefsForTesting: initialSourceRefs,
      lockedApprovedAvatarUrlForTesting: lockedApprovedAvatarUrl,
      onNext: onNext,
    ),
  );
}

Finder _nextButton() => find.byType(ElevatedButton).last;

Finder _candidateDialog() => find.byType(AvatarCandidateSelectionDialog);

Finder _dialogConfirmButton() => find.descendant(
  of: _candidateDialog(),
  matching: find.byType(ElevatedButton),
);

Finder _dialogCandidateTiles() => find.descendant(
  of: _candidateDialog(),
  matching: find.byType(AvatarCandidateTile),
);

void _drainExpectedImageLoadException(WidgetTester tester) {
  tester.takeException();
}

/// 서버 상태만 돌려주는 복구 테스트용 클라이언트.
class _StatusOnlyAvatarClient extends AvatarGenerationClient {
  _StatusOnlyAvatarClient(this.status, {this.retryAllowed = false});

  final String status;
  final bool retryAllowed;
  int pollCount = 0;

  @override
  Future<AvatarGenerationStatusSnapshot?> getCurrentGenerationStatus() async {
    return AvatarGenerationStatusSnapshot.fromMap({
      'sourceLocked': true,
      'jobId': 'avatar_job_resume_1',
      'sourceSelectionVersion': 1,
      'status': status,
      'candidateAvailability': 'none',
      'retryAllowed': retryAllowed,
      'approved': false,
      'safeReasonCode': null,
    });
  }

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
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async =>
      throw UnimplementedError();
}

void main() {
  group('PhotoUploadScreen avatar flow', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    testWidgets('shows candidates, approves one, and advances', (tester) async {
      await _useMobileSurface(tester);
      final client = _ReadyAvatarClient();
      List<String>? advancedPhotos;

      await tester.pumpWidget(
        _harness(client: client, onNext: (photos) => advancedPhotos = photos),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(_candidateDialog(), findsOneWidget);
      expect(_dialogCandidateTiles(), findsNWidgets(2));

      await tester.tap(_dialogCandidateTiles().first);
      await tester.pump();
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);

      await tester.tap(_dialogConfirmButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.approvedCandidateId, 'cand_0');
      expect(advancedPhotos, hasLength(2));
    });

    testWidgets('two verified uploads are sent together for server selection', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _ReadyAvatarClient();
      const refs = <OnboardingPhotoSourceRef?>[
        OnboardingPhotoSourceRef(
          photoId: 'photo_0001',
          slotIndex: 0,
          objectGeneration: '101',
        ),
        OnboardingPhotoSourceRef(
          photoId: 'photo_0002',
          slotIndex: 1,
          objectGeneration: '102',
        ),
      ];
      await tester.pumpWidget(
        _harness(
          client: client,
          onNext: (_) {},
          initialPhotos: const [
            'avatar_generation_queued:display_only_1',
            'avatar_generation_queued:display_only_2',
          ],
          initialSourceRefs: refs,
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.admittedSources?.map((source) => source.photoId), [
        'photo_0001',
        'photo_0002',
      ]);
      expect(_candidateDialog(), findsOneWidget);
    });

    testWidgets('사진 없이는 다음 단계로 넘어갈 수 없다', (tester) async {
      await _useMobileSurface(tester);
      List<String>? advancedPhotos;

      await tester.pumpWidget(
        _harness(
          client: _ReadyAvatarClient(),
          initialPhotos: const [],
          onNext: (photos) => advancedPhotos = photos,
        ),
      );
      await tester.pump();

      final nextButton = tester.widget<ElevatedButton>(_nextButton());
      expect(nextButton.onPressed, isNull);
      expect(find.text('사진은 나중에 추가할 수 있어요'), findsNothing);
      expect(find.text('최소 2장 필요'), findsOneWidget);

      await tester.tap(_nextButton(), warnIfMissed: false);
      await tester.pump();

      expect(advancedPhotos, isNull);
    });

    testWidgets('polls latest queued test job instead of first stale slot', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _ReadyAvatarClient();

      await tester.pumpWidget(
        _harness(
          client: client,
          initialPhotos: [
            AvatarSourcePhotoService.queuedSlotToken('job_stale'),
            AvatarSourcePhotoService.queuedSlotToken('job_latest'),
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.polledJobIds, ['job_latest']);
      expect(_candidateDialog(), findsOneWidget);
    });

    testWidgets(
      'single approved avatar can proceed without another queued source photo',
      (tester) async {
        await _useMobileSurface(tester);
        List<String>? advancedPhotos;

        await tester.pumpWidget(
          _harness(
            client: _ReadyAvatarClient(),
            initialPhotos: const ['https://cdn.example/approved-avatar.png'],
            lockedApprovedAvatarUrl: 'https://cdn.example/approved-avatar.png',
            onNext: (photos) => advancedPhotos = photos,
          ),
        );
        await tester.pump();
        _drainExpectedImageLoadException(tester);

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        _drainExpectedImageLoadException(tester);

        expect(_candidateDialog(), findsNothing);
        expect(advancedPhotos, ['https://cdn.example/approved-avatar.png']);
      },
    );

    testWidgets('approved avatar slot is locked and has no delete button', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _ReadyAvatarClient(),
          initialPhotos: const ['https://cdn.example/approved-avatar.png'],
          lockedApprovedAvatarUrl: 'https://cdn.example/approved-avatar.png',
          onNext: (_) {},
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      expect(find.text(lockedAvatarNotice), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsNothing);
      expect(find.text('잠김'), findsOneWidget);
    });

    testWidgets('queued avatar source is locked and has no delete button', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(client: _ReadyAvatarClient(), onNext: (_) {}),
      );
      await tester.pump();

      expect(find.text(sourceLockedAvatarMessage), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsNothing);
    });

    testWidgets('failed generation leaves retryable error on photo screen', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      var advanced = false;

      await tester.pumpWidget(
        _harness(
          client: _FailingAvatarClient(),
          onNext: (_) => advanced = true,
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(advanced, isFalse);
      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
      expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsNothing);
      expect(find.text(sourceLockedAvatarMessage), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('source multi-face rejection shows exact guidance', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _SourceRejectedAvatarClient('avatar_source_multi_face'),
          onNext: (_) {},
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
      expect(find.text(avatarSourceMultiFaceMessage), findsWidgets);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('no eligible source unlocks photos for replacement', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _SourceRejectedAvatarClient(
            'avatar_no_eligible_source_photo',
          ),
          onNext: (_) {},
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('얼굴이 잘 보이는 사진을 추가하거나 변경해 주세요.'), findsWidgets);
      expect(find.text(sourceLockedAvatarMessage), findsNothing);
      expect(find.byIcon(Icons.close_rounded), findsNWidgets(2));
    });

    testWidgets('no previewable candidates shows safe retryable message', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      var advanced = false;

      await tester.pumpWidget(
        _harness(
          client: _NoPreviewableAvatarClient(),
          onNext: (_) => advanced = true,
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(advanced, isFalse);
      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
      expect(find.textContaining('안전한 아바타 후보'), findsWidgets);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('poll timeout shows delayed generation message', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      var advanced = false;

      await tester.pumpWidget(
        _harness(
          client: _TimeoutAvatarClient(),
          onNext: (_) => advanced = true,
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(advanced, isFalse);
      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
      expect(find.textContaining('아바타 생성이 지연'), findsWidgets);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('callable polling exception shows retryable error', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      var advanced = false;

      await tester.pumpWidget(
        _harness(
          client: _CallableErrorAvatarClient(),
          onNext: (_) => advanced = true,
        ),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(advanced, isFalse);
      expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
      expect(find.textContaining('아바타 생성에 실패'), findsWidgets);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('preview ready with fewer candidates still opens dialog', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(client: _ReadyAvatarClient(candidateCount: 2), onNext: (_) {}),
      );
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(_candidateDialog(), findsOneWidget);
      expect(_dialogCandidateTiles(), findsNWidgets(2));
    });

    testWidgets('retry button polls the queued avatar job again', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _FailThenReadyAvatarClient();

      await tester.pumpWidget(_harness(client: client, onNext: (_) {}));
      await tester.pump();

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);
      expect(client.pollCount, 1);

      await tester.ensureVisible(find.text('다시 시도'));
      await tester.pump();
      await tester.tap(find.text('다시 시도'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.pollCount, 2);
      expect(_candidateDialog(), findsOneWidget);
      expect(_dialogCandidateTiles(), findsNWidgets(2));
    });

    test('queued tokens do not carry source bytes or refs', () {
      final token = AvatarSourcePhotoService.queuedSlotToken('job_ready');
      expect(token, isNotEmpty);
      expect(token, isNot(contains('gs://')));
      expect(token, isNot(contains('gcs://')));
      expect(token, isNot(contains('sourcePhotoRefs')));
    });

    testWidgets('restart while queued resumes generation without a dead end', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _StatusOnlyAvatarClient('queued');

      await tester.pumpWidget(
        _harness(
          client: client,
          initialPhotos: [
            AvatarSourcePhotoService.queuedSlotToken('avatar_job_resume_1'),
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // 서버 작업이 살아 있으므로 실패 배너가 아니라 생성 화면으로 복귀한다.
      expect(find.byType(AvatarGenerationErrorBanner), findsNothing);
      expect(client.pollCount, greaterThan(0));
      _drainExpectedImageLoadException(tester);

      // 폴링 루프를 정리한다(dispose가 취소 플래그를 세운 뒤 대기 타이머 소진).
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('restart while needs_review shows review copy and no retry', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _StatusOnlyAvatarClient('needs_review'),
          initialPhotos: [
            AvatarSourcePhotoService.queuedSlotToken('avatar_job_resume_1'),
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text(avatarNeedsReviewMessage), findsOneWidget);
      expect(find.text('다시 시도'), findsNothing);
      expect(find.text(avatarGenerationFailedMessage), findsNothing);
      _drainExpectedImageLoadException(tester);
    });

    testWidgets('restart while terminal_failed offers no retry', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _StatusOnlyAvatarClient('terminal_failed'),
          initialPhotos: [
            AvatarSourcePhotoService.queuedSlotToken('avatar_job_resume_1'),
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text(avatarTerminalFailureMessage), findsOneWidget);
      expect(find.text('다시 시도'), findsNothing);
      _drainExpectedImageLoadException(tester);
    });

    testWidgets(
      'restart while retryable_failed offers retry when server allows',
      (tester) async {
        await _useMobileSurface(tester);

        await tester.pumpWidget(
          _harness(
            client: _StatusOnlyAvatarClient(
              'retryable_failed',
              retryAllowed: true,
            ),
            initialPhotos: [
              AvatarSourcePhotoService.queuedSlotToken('avatar_job_resume_1'),
            ],
            onNext: (_) {},
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        expect(find.text('다시 시도'), findsOneWidget);
        _drainExpectedImageLoadException(tester);
      },
    );
  });
}
