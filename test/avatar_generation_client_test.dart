import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';

void main() {
  group('AvatarCandidate', () {
    test('parses candidateId and runtime preview bytes from map', () {
      final bytes = Uint8List.fromList([1, 2, 3, 4]);
      final c = AvatarCandidate.fromMap({
        'candidateId': 'cand_abc',
        'previewImageBase64': base64Encode(bytes),
        'previewMimeType': 'image/jpeg',
      });
      expect(c.candidateId, 'cand_abc');
      expect(c.previewUrl, isEmpty);
      expect(c.previewBytes, bytes);
      expect(c.previewMimeType, 'image/jpeg');
      expect(c.isValid, isTrue);
    });

    test('rejects signed preview URL and internal gcs/source fields', () {
      final c = AvatarCandidate.fromMap({
        'candidateId': 'cand_abc',
        'previewUrl':
            'https://storage.googleapis.com/x.png?X-Goog-Signature=secret',
        'sourcePhotoRefs': ['gs://private/source.jpg'],
        'gcsUri': 'gs://seolleyeon-avatar-temp/x.png',
      });
      expect(c.candidateId, 'cand_abc');
      expect(c.previewUrl, isEmpty);
      expect(c.isValid, isFalse);
    });

    test('rejects encoded internal preview URL markers and private buckets', () {
      final encodedCandidate = AvatarCandidate.fromMap({
        'candidateId': 'cand_abc',
        'previewUrl': 'https://cdn.example/%2Fjobs%2Fjob%2Fcandidates%2Fc.png',
      });
      final privateBucket = AvatarCandidate.fromMap({
        'candidateId': 'cand_def',
        'previewUrl':
            'https://seolleyeon-final-chat-profile-photos.storage.googleapis.com/users/u/profile.jpg',
      });

      expect(encodedCandidate.previewUrl, isEmpty);
      expect(encodedCandidate.isValid, isFalse);
      expect(privateBucket.previewUrl, isEmpty);
      expect(privateBucket.isValid, isFalse);
    });

    test(
      'rejects preview bytes with unsupported mime or oversized payload',
      () {
        final validBytes = Uint8List.fromList([1, 2, 3]);
        final unsupportedMime = AvatarCandidate.fromMap({
          'candidateId': 'cand_abc',
          'previewImageBase64': base64Encode(validBytes),
          'previewMimeType': 'text/plain',
        });
        expect(unsupportedMime.previewBytes, isNull);
        expect(unsupportedMime.isValid, isFalse);

        final oversized = AvatarCandidate.fromMap({
          'candidateId': 'cand_abc',
          'previewImageBase64': base64Encode(
            Uint8List(AvatarCandidate.maxPreviewBytes + 1),
          ),
          'previewMimeType': 'image/jpeg',
        });
        expect(oversized.previewBytes, isNull);
        expect(oversized.isValid, isFalse);
      },
    );
  });

  group('AvatarCandidatesResult', () {
    test('parses preview_ready status and skips invalid candidates', () {
      final r = AvatarCandidatesResult.fromMap({
        'jobId': 'job_x',
        'status': 'preview_ready',
        'candidates': [
          {
            'candidateId': 'cand_1',
            'previewImageBase64': base64Encode(Uint8List.fromList([1, 2, 3])),
            'previewMimeType': 'image/jpeg',
          },
          {
            'candidateId': '',
            'previewImageBase64': base64Encode(Uint8List.fromList([1])),
          },
          {'candidateId': 'cand_3', 'previewImageBase64': ''},
        ],
      });
      expect(r.status, AvatarJobStatus.previewReady);
      expect(r.candidates.length, 1);
      expect(r.candidates.first.candidateId, 'cand_1');
    });

    test('maps generation-failing job statuses explicitly', () {
      final failed = AvatarCandidatesResult.fromMap({
        'jobId': 'job',
        'status': 'failed',
        'candidates': const [],
      });
      expect(failed.status, AvatarJobStatus.failed);

      for (final raw in const ['cancelled', 'canceled']) {
        final r = AvatarCandidatesResult.fromMap({
          'jobId': 'job',
          'status': raw,
          'candidates': const [],
        });
        expect(r.status, AvatarJobStatus.cancelled, reason: 'for status=$raw');
      }

      final superseded = AvatarCandidatesResult.fromMap({
        'jobId': 'job',
        'status': 'superseded',
        'errorCode': 'avatar_job_superseded',
        'candidates': const [],
      });
      expect(superseded.status, AvatarJobStatus.superseded);
      expect(superseded.errorCode, 'avatar_job_superseded');

      final noPreviewable = AvatarCandidatesResult.fromMap({
        'jobId': 'job',
        'status': 'no_previewable_candidates',
        'errorCode': 'avatar_source_multi_face',
        'candidates': const [],
      });
      expect(noPreviewable.status, AvatarJobStatus.noPreviewableCandidates);
      expect(noPreviewable.errorCode, 'avatar_source_multi_face');
    });

    test('maps server terminal failure statuses instead of unknown', () {
      // 회귀: 서버가 실제로 기록하는 retryable_failed / terminal_failed /
      // no_previewable 이 unknown 으로 떨어지면 클라이언트가 이미 끝난 작업을
      // 폴링 데드라인까지 계속 기다린다.
      expect(
        avatarJobStatusFromString('retryable_failed'),
        AvatarJobStatus.failed,
      );
      expect(
        avatarJobStatusFromString('terminal_failed'),
        AvatarJobStatus.failed,
      );
      expect(
        avatarJobStatusFromString('no_previewable'),
        AvatarJobStatus.noPreviewableCandidates,
      );
    });

    test('maps source reject error codes to Korean guidance', () {
      expect(
        avatarGenerationFailureMessage(
          status: AvatarJobStatus.failed,
          errorCode: 'avatar_source_multi_face',
        ),
        '얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요.',
      );
      expect(
        avatarGenerationFailureMessage(
          status: AvatarJobStatus.failed,
          errorCode: 'avatar_source_face_too_small',
        ),
        '얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요.',
      );
      expect(
        avatarGenerationFailureMessage(
          status: AvatarJobStatus.noPreviewableCandidates,
          errorCode: 'avatar_background_text_logo_risky',
        ),
        '배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요.',
      );
      expect(
        avatarGenerationFailureMessage(
          status: AvatarJobStatus.failed,
          errorCode: 'avatar_no_eligible_source_photo',
        ),
        '얼굴이 잘 보이는 사진을 추가하거나 변경해 주세요.',
      );
    });

    test('maps needs_review and completed statuses explicitly', () {
      final review = AvatarCandidatesResult.fromMap({
        'jobId': 'job',
        'status': 'needs_review',
        'candidates': const [],
      });
      expect(review.status, AvatarJobStatus.needsReview);

      final completed = AvatarCandidatesResult.fromMap({
        'jobId': 'job',
        'status': 'completed',
        'candidates': const [],
      });
      expect(completed.status, AvatarJobStatus.approved);
    });
  });

  group('AvatarApprovalResult', () {
    test('isApproved is true only for status=approved', () {
      final approved = AvatarApprovalResult.fromMap({
        'avatarStatus': 'approved',
        'approvedAvatarUrl': 'https://cdn.example/avatar.png',
        'selectedCandidateId': 'cand_1',
      });
      expect(approved.isApproved, isTrue);

      final pending = AvatarApprovalResult.fromMap({
        'avatarStatus': 'approval_copying',
      });
      expect(pending.isApproved, isFalse);
    });
  });

  group('MockAvatarGenerationClient', () {
    test(
      'pollUntilPreviewReady returns 2 mock candidates by default',
      () async {
        final client = MockAvatarGenerationClient(
          firstPollDelay: Duration.zero,
          uploadDelay: Duration.zero,
          approveDelay: Duration.zero,
        );
        final result = await client.pollUntilPreviewReady(
          jobId: 'job_mock',
          pollInterval: const Duration(milliseconds: 1),
          timeout: const Duration(seconds: 2),
        );
        expect(result.status, AvatarJobStatus.previewReady);
        expect(result.candidates.length, 2);
        expect(result.candidates.first.previewUrl.startsWith('http'), isTrue);
      },
    );

    test(
      'approveCandidate returns approved result with selectedCandidateId',
      () async {
        final client = MockAvatarGenerationClient(
          firstPollDelay: Duration.zero,
          uploadDelay: Duration.zero,
          approveDelay: Duration.zero,
        );
        final r = await client.approveCandidate('cand_xyz');
        expect(r.avatarStatus, 'approved');
        expect(r.selectedCandidateId, 'cand_xyz');
        expect(r.isApproved, isTrue);
      },
    );

    test('pollUntilPreviewReady honors shouldContinue cancellation', () async {
      final client = MockAvatarGenerationClient(
        firstPollDelay: const Duration(milliseconds: 50),
        uploadDelay: Duration.zero,
        approveDelay: Duration.zero,
        simulatedJobStatus: AvatarJobStatus.running,
      );
      var allow = true;
      Future<void>.delayed(
        const Duration(milliseconds: 80),
        () => allow = false,
      );
      expect(
        () => client.pollUntilPreviewReady(
          jobId: 'job',
          pollInterval: const Duration(milliseconds: 30),
          timeout: const Duration(seconds: 2),
          shouldContinue: () => allow,
        ),
        throwsA(isA<AvatarPollingCancelled>()),
      );
    });

    test(
      'transient poll errors do not abort an in-progress generation',
      () async {
        // 회귀: 폴링 중 일시적인 네트워크 오류 1회가 진행 중인 서버 작업을
        // 클라이언트에서 최종 실패로 확정시키면 안 된다.
        final client = _FlakyPollClient(
          failuresBeforeSuccess: 2,
          eventualStatus: AvatarJobStatus.previewReady,
        );

        final result = await client.pollUntilPreviewReady(
          jobId: 'job_flaky',
          pollInterval: const Duration(milliseconds: 1),
          timeout: const Duration(seconds: 5),
        );

        expect(result.status, AvatarJobStatus.previewReady);
        expect(client.callCount, 3);
      },
    );

    test(
      'persistent poll errors still surface after the retry budget',
      () async {
        final client = _FlakyPollClient(
          failuresBeforeSuccess: 999,
          eventualStatus: AvatarJobStatus.previewReady,
        );

        await expectLater(
          client.pollUntilPreviewReady(
            jobId: 'job_dead',
            pollInterval: const Duration(milliseconds: 1),
            timeout: const Duration(seconds: 5),
          ),
          throwsA(isA<StateError>()),
        );
      },
    );

  });
}

/// 폴링 중 처음 [failuresBeforeSuccess]회는 예외를 던지고 이후 성공하는 테스트 클라이언트.
class _FlakyPollClient extends AvatarGenerationClient {
  _FlakyPollClient({
    required this.failuresBeforeSuccess,
    required this.eventualStatus,
  });

  final int failuresBeforeSuccess;
  final AvatarJobStatus eventualStatus;
  int callCount = 0;

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    callCount += 1;
    if (callCount <= failuresBeforeSuccess) {
      throw StateError('transient_network_error');
    }
    return AvatarCandidatesResult(
      jobId: jobId,
      status: eventualStatus,
      candidates: const [
        AvatarCandidate(candidateId: 'cand_1', previewUrl: 'https://x/a.png'),
      ],
    );
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    throw UnimplementedError();
  }
}
