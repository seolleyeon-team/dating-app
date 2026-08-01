import 'dart:async';
import 'dart:typed_data';

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
import 'package:seolleyeon/services/storage_service.dart';
import 'package:seolleyeon/services/user_profile_reader.dart';
import 'package:seolleyeon/shared/utils/avatar_lock_policy.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _ReadyAvatarClient extends AvatarGenerationClient {
  _ReadyAvatarClient({this.candidateCount = 4});

  final int candidateCount;
  String? approvedCandidateId;
  int uploadCount = 0;
  int retryCount = 0;
  int currentStatusCount = 0;
  final List<String> polledJobIds = <String>[];
  final List<int?> uploadedSlotIndexes = <int?>[];

  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    uploadCount += 1;
    uploadedSlotIndexes.add(slotIndex);
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
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: 'job_ready',
      sourceSelectionVersion: 1,
      status: AvatarJobStatus.queued,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
  }

  @override
  Future<AvatarGenerationStatusResult> retryCurrentAvatarGeneration() async {
    retryCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: 'job_ready',
      sourceSelectionVersion: 1,
      status: AvatarJobStatus.queued,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
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

class _StatusAvatarClient extends _ReadyAvatarClient {
  _StatusAvatarClient(this.status);

  final AvatarJobStatus status;

  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
  }) async {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: status,
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
    polledJobIds.add(jobId);
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

  @override
  Future<AvatarGenerationStatusResult> retryCurrentAvatarGeneration() async {
    retryCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: 'job_retry',
      sourceSelectionVersion: 2,
      status: AvatarJobStatus.queued,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
  }
}

class _PreCallFailThenReadyAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    uploadCount += 1;
    uploadedSlotIndexes.add(slotIndex);
    if (uploadCount == 1) {
      throw Exception('auth failed before callable');
    }
    return const AvatarSourcePhotoUploadResult(
      jobId: 'job_ready',
      photoId: 'photo_ready',
      avatarStatus: 'queued',
      message: 'avatar_generation_queued',
      duplicate: false,
    );
  }

  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: false,
      jobId: null,
      sourceSelectionVersion: 0,
      status: AvatarJobStatus.queued,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
  }
}

class _FreshUnlockedAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: false,
      jobId: null,
      sourceSelectionVersion: 0,
      status: AvatarJobStatus.unknown,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
  }
}

class _DelayedFreshUnlockedAvatarClient extends _ReadyAvatarClient {
  final Completer<AvatarGenerationStatusResult> statusCompleter =
      Completer<AvatarGenerationStatusResult>();

  @override
  Future<AvatarGenerationStatusResult> getCurrentAvatarGenerationStatus() {
    currentStatusCount += 1;
    return statusCompleter.future;
  }

  void completeUnlocked() {
    statusCompleter.complete(
      const AvatarGenerationStatusResult(
        sourceLocked: false,
        jobId: null,
        sourceSelectionVersion: 0,
        status: AvatarJobStatus.unknown,
        candidateAvailability: 'none',
        retryAllowed: false,
        approved: false,
      ),
    );
  }
}

class _CurrentStatusFailureAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    throw TimeoutException('current status unavailable');
  }
}

class _ApprovedWithoutUrlAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: null,
      sourceSelectionVersion: 10,
      status: AvatarJobStatus.approved,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: true,
      approvedAvatarUrl: '',
    );
  }
}

class _TestStorageService extends StorageService {
  @override
  Future<String?> getKakaoUserId() async => 'kakao_test';
}

class _RefetchApprovedUserService implements UserProfileReader {
  int getUserProfileCount = 0;

  @override
  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    getUserProfileCount += 1;
    return {
      'avatar': {
        'status': 'approved',
        'approvedAvatarUrl': 'https://cdn.example/refetched-avatar.png',
      },
    };
  }
}

class _CurrentStatusAvatarClient extends _ReadyAvatarClient {
  _CurrentStatusAvatarClient(this.currentStatus, {this.retryAllowed = false});

  final AvatarJobStatus currentStatus;
  final bool retryAllowed;

  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: 'job_current',
      sourceSelectionVersion: 9,
      status: currentStatus,
      candidateAvailability: 'none',
      retryAllowed: retryAllowed,
      approved: false,
      safeReasonCode: currentStatus == AvatarJobStatus.terminalFailed
          ? 'avatar_state_inconsistent'
          : 'retryable_failed',
    );
  }
}

class _RecoveringUploadAvatarClient extends _ReadyAvatarClient {
  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    uploadCount += 1;
    throw TimeoutException('network disconnected after upload');
  }

  @override
  Future<AvatarGenerationStatusResult>
  getCurrentAvatarGenerationStatus() async {
    currentStatusCount += 1;
    return const AvatarGenerationStatusResult(
      sourceLocked: true,
      jobId: 'job_recovered',
      sourceSelectionVersion: 3,
      status: AvatarJobStatus.queued,
      candidateAvailability: 'none',
      retryAllowed: false,
      approved: false,
    );
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
  List<XFile?>? initialLocalPhotos,
  StorageService? storageService,
  UserProfileReader? userProfileReader,
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
      initialLocalPhotosForTesting: initialLocalPhotos,
      onNext: onNext,
      storageServiceForTesting: storageService,
      userProfileReaderForTesting: userProfileReader,
    ),
  );
}

XFile _localPhoto([int seed = 1]) => XFile.fromData(
  Uint8List.fromList(<int>[seed, seed + 1, seed + 2, seed + 3]),
  name: 'local_$seed.jpg',
);

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
      SharedPreferences.setMockInitialValues({'kakao_user_id': 'kakao_test'});
    });

    testWidgets(
      'local photo stays local until final action and uploads exactly once',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _ReadyAvatarClient();

        await tester.pumpWidget(
          _harness(
            client: client,
            initialPhotos: const [null, null],
            initialLocalPhotos: [_localPhoto()],
            onNext: (_) {},
          ),
        );
        await tester.pump();

        expect(client.uploadCount, 0);
        expect(find.byIcon(Icons.close_rounded), findsOneWidget);

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.uploadCount, 1);
        expect(client.polledJobIds, ['job_ready']);
        expect(_candidateDialog(), findsOneWidget);
      },
    );

    testWidgets(
      'uncertain final upload stays locked and recovers through current status',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _RecoveringUploadAvatarClient();

        await tester.pumpWidget(
          _harness(
            client: client,
            initialPhotos: const [null, null],
            initialLocalPhotos: [_localPhoto()],
            onNext: (_) {},
          ),
        );
        await tester.pump();

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.uploadCount, 1);
        expect(client.currentStatusCount, 1);
        expect(client.polledJobIds, ['job_recovered']);
        expect(find.byIcon(Icons.close_rounded), findsNothing);
        expect(_candidateDialog(), findsOneWidget);
      },
    );
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
      _drainExpectedImageLoadException(tester);

      expect(client.approvedCandidateId, 'cand_0');
      expect(advancedPhotos, ['https://cdn.example/avatar.png']);
    });

    testWidgets('queued resume uses authoritative current status job', (
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

      expect(client.currentStatusCount, 1);
      expect(client.polledJobIds, ['job_ready']);
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

    testWidgets('fresh authoritative unlocked status makes source selectable', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _FreshUnlockedAvatarClient();

      await tester.pumpWidget(
        _harness(client: client, initialPhotos: const [null], onNext: (_) {}),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.currentStatusCount, 1);
      expect(find.text(sourceLockedAvatarMessage), findsNothing);
      expect(find.byIcon(Icons.add_rounded), findsWidgets);
    });

    testWidgets(
      'delayed authoritative lookup blocks source mutation until unlocked',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _DelayedFreshUnlockedAvatarClient();

        await tester.pumpWidget(
          _harness(client: client, initialPhotos: const [null], onNext: (_) {}),
        );
        await tester.pump();

        expect(client.currentStatusCount, 1);
        await tester.tap(find.byIcon(Icons.add_rounded).first);
        await tester.pump();
        expect(find.text(sourceLockedAvatarMessage), findsOneWidget);

        client.completeUnlocked();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(find.text(sourceLockedAvatarMessage), findsNothing);
        expect(find.byIcon(Icons.add_rounded), findsWidgets);
      },
    );
    testWidgets('current status lookup failure keeps provisional source lock', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _CurrentStatusFailureAvatarClient();

      await tester.pumpWidget(
        _harness(client: client, initialPhotos: const [null], onNext: (_) {}),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.currentStatusCount, 1);
      expect(find.text(sourceLockedAvatarMessage), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsNothing);
    });

    testWidgets(
      'approved current status without URL refetches and stays locked',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _ApprovedWithoutUrlAvatarClient();
        final users = _RefetchApprovedUserService();

        await tester.pumpWidget(
          _harness(
            client: client,
            initialPhotos: const [null],
            storageService: _TestStorageService(),
            userProfileReader: users,
            onNext: (_) {},
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        _drainExpectedImageLoadException(tester);

        expect(client.currentStatusCount, 1);
        expect(users.getUserProfileCount, 1);
        expect(find.text(lockedAvatarNotice), findsOneWidget);
        expect(find.byIcon(Icons.close_rounded), findsNothing);
      },
    );
    testWidgets(
      'stale public user doc still locks from authoritative private status',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _CurrentStatusAvatarClient(AvatarJobStatus.running);

        await tester.pumpWidget(
          _harness(client: client, initialPhotos: const [null], onNext: (_) {}),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.currentStatusCount, 1);
        expect(find.text(sourceLockedAvatarMessage), findsOneWidget);
        expect(find.byIcon(Icons.close_rounded), findsNothing);

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.polledJobIds, ['job_current']);
        expect(_candidateDialog(), findsOneWidget);
      },
    );
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

    testWidgets('retryable and terminal failed statuses show retryable error', (
      tester,
    ) async {
      await _useMobileSurface(tester);

      for (final status in const [
        AvatarJobStatus.retryableFailed,
        AvatarJobStatus.terminalFailed,
      ]) {
        await tester.pumpWidget(
          _harness(client: _StatusAvatarClient(status), onNext: (_) {}),
        );
        await tester.pump();

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(find.byType(AvatarCandidateSelectionDialog), findsNothing);
        expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);
        expect(find.textContaining('아바타 생성에 실패'), findsWidgets);
      }
    });
    testWidgets(
      'authoritative running current status resumes polling from current job',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _CurrentStatusAvatarClient(AvatarJobStatus.running);

        await tester.pumpWidget(_harness(client: client, onNext: (_) {}));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.currentStatusCount, 1);

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.polledJobIds, ['job_current']);
        expect(_candidateDialog(), findsOneWidget);
      },
    );
    testWidgets('authoritative retryable current status shows retry action', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _CurrentStatusAvatarClient(
        AvatarJobStatus.retryableFailed,
        retryAllowed: true,
      );

      await tester.pumpWidget(_harness(client: client, onNext: (_) {}));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.currentStatusCount, 1);
      expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('authoritative terminal current status hides retry action', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _CurrentStatusAvatarClient(AvatarJobStatus.terminalFailed);

      await tester.pumpWidget(_harness(client: client, onNext: (_) {}));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(client.currentStatusCount, 1);
      expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);
      expect(find.text('다시 시도'), findsNothing);
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

    testWidgets(
      'retry after pre-call failure reuploads retained local source',
      (tester) async {
        await _useMobileSurface(tester);
        final client = _PreCallFailThenReadyAvatarClient();

        await tester.pumpWidget(
          _harness(
            client: client,
            initialPhotos: const [null],
            initialLocalPhotos: [_localPhoto()],
            onNext: (_) {},
          ),
        );
        await tester.pump();

        await tester.tap(_nextButton());
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.uploadCount, 1);
        expect(client.currentStatusCount, 1);
        expect(client.retryCount, 0);
        expect(find.byType(AvatarGenerationErrorBanner), findsOneWidget);

        await tester.ensureVisible(find.text('다시 시도'));
        await tester.pump();
        await tester.tap(find.text('다시 시도'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(client.uploadCount, 2);
        expect(client.retryCount, 0);
        expect(client.polledJobIds, ['job_ready']);
        expect(_candidateDialog(), findsOneWidget);
      },
    );
    testWidgets(
      'retry button retries current avatar generation without bytes',
      (tester) async {
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

        expect(client.retryCount, 1);
        expect(client.pollCount, 2);
        expect(client.polledJobIds.last, 'job_retry');
        expect(_candidateDialog(), findsOneWidget);
        expect(_dialogCandidateTiles(), findsNWidgets(4));
      },
    );

    test('queued tokens do not carry source bytes or refs', () {
      final token = AvatarSourcePhotoService.queuedSlotToken('job_ready');
      expect(token, isNotEmpty);
      expect(token, isNot(contains('gs://')));
      expect(token, isNot(contains('gcs://')));
      expect(token, isNot(contains('sourcePhotoRefs')));
    });
  });
}
