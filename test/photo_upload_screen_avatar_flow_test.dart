import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:seolleyeon/features/onboarding/screens/photo_upload_screen.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_selection_dialog.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_tile.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_error_banner.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';
import 'package:seolleyeon/shared/utils/avatar_lock_policy.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _ReadyAvatarClient extends AvatarGenerationClient {
  _ReadyAvatarClient({this.candidateCount = 4});

  final int candidateCount;
  String? approvedCandidateId;
  final List<String> polledJobIds = <String>[];

  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
  }) async {
    return const AvatarSourcePhotoUploadResult(
      jobId: 'job_ready',
      photoId: 'photo_ready',
      avatarStatus: 'queued',
      message: 'avatar_generation_queued',
      duplicate: false,
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
      expect(_dialogCandidateTiles(), findsNWidgets(4));

      await tester.tap(_dialogCandidateTiles().first);
      await tester.pump();
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);

      await tester.tap(_dialogConfirmButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.approvedCandidateId, 'cand_0');
      expect(advancedPhotos, hasLength(2));
    });

    testWidgets('사진 없이도 임시 설정에서 다음 단계로 넘어간다', (tester) async {
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
      expect(nextButton.onPressed, isNotNull);
      expect(find.text('사진은 나중에 추가할 수 있어요'), findsOneWidget);

      await tester.tap(_nextButton());
      await tester.pump();

      expect(advancedPhotos, isEmpty);
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
      expect(_dialogCandidateTiles(), findsNWidgets(4));
    });

    test('queued tokens do not carry source bytes or refs', () {
      final token = AvatarSourcePhotoService.queuedSlotToken('job_ready');
      expect(token, isNotEmpty);
      expect(token, isNot(contains('gs://')));
      expect(token, isNot(contains('gcs://')));
      expect(token, isNot(contains('sourcePhotoRefs')));
    });
  });
}
