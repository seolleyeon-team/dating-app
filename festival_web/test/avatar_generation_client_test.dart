import 'dart:convert';
import 'dart:typed_data';

import 'package:festival_web/avatar/avatar_generation_client.dart';
import 'package:festival_web/avatar/avatar_generation_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'upload sends base64 image through callable transport with auth required',
    () async {
      final transport = RecordingAvatarCallableTransport(
        currentUid: 'uid_1',
        responses: {
          'uploadAvatarSourcePhoto': {
            'jobId': 'avatar_job_1',
            'photoId': 'src_1',
            'avatarStatus': 'queued',
            'message': 'avatar_generation_queued',
            'duplicate': false,
            'sourceSelectionVersion': 1,
          },
        },
      );
      final client = FestivalAvatarGenerationClient(transport: transport);

      final result = await client.uploadAvatarSourcePhoto(
        bytes: Uint8List.fromList([1, 2, 3]),
        fileName: 'face.png',
        contentType: 'image/png',
      );

      expect(result.jobId, 'avatar_job_1');
      expect(transport.calls.single.name, 'uploadAvatarSourcePhoto');
      expect(
        transport.calls.single.payload['imageBase64'],
        base64Encode([1, 2, 3]),
      );
      expect(transport.calls.single.payload['contentType'], 'image/png');
      expect(
        transport.calls.single.payload.containsKey('storagePath'),
        isFalse,
      );
    },
  );

  test(
    'client maps locked and approved errors to safe Korean messages',
    () async {
      final lockedClient = FestivalAvatarGenerationClient(
        transport: RecordingAvatarCallableTransport(
          currentUid: 'uid_1',
          errors: {
            'uploadAvatarSourcePhoto': const AvatarCallableException(
              code: 'failed-precondition',
              message: 'avatar_source_locked',
            ),
          },
        ),
      );

      expect(
        () => lockedClient.uploadAvatarSourcePhoto(
          bytes: Uint8List.fromList([1]),
          fileName: 'face.jpg',
          contentType: 'image/jpeg',
        ),
        throwsA(
          isA<AvatarGenerationClientException>().having(
            (e) => e.userMessage,
            'message',
            '아바타 생성이 시작되어 사진을 변경할 수 없어요.',
          ),
        ),
      );
    },
  );

  test(
    'polling stops on preview ready and timeout is reported safely',
    () async {
      final transport = RecordingAvatarCallableTransport(
        currentUid: 'uid_1',
        sequenceResponses: {
          'getAvatarJobCandidates': [
            {'jobId': 'avatar_job_1', 'status': 'running', 'candidates': []},
            {
              'jobId': 'avatar_job_1',
              'status': 'preview_ready',
              'candidates': [
                {
                  'candidateId': 'cand_1',
                  'previewImageBase64': base64Encode([1, 2, 3]),
                  'previewMimeType': 'image/png',
                },
              ],
            },
          ],
        },
      );
      final client = FestivalAvatarGenerationClient(transport: transport);

      final result = await client.pollUntilPreviewReady(
        'avatar_job_1',
        pollInterval: Duration.zero,
        timeout: const Duration(seconds: 1),
      );

      expect(result.status, AvatarJobStatus.previewReady);
      expect(result.candidates.single.candidateId, 'cand_1');
      expect(
        transport.calls.where((call) => call.name == 'getAvatarJobCandidates'),
        hasLength(2),
      );
    },
  );

  test('approval requires selected candidate id in backend response', () async {
    final client = FestivalAvatarGenerationClient(
      transport: RecordingAvatarCallableTransport(
        currentUid: 'uid_1',
        responses: {
          'approveAvatarCandidate': {
            'avatarStatus': 'approved',
            'approvedAvatarUrl': 'https://cdn.example/avatar.png',
          },
        },
      ),
    );

    expect(
      () => client.approveAvatarCandidate('cand_1'),
      throwsA(isA<AvatarGenerationClientException>()),
    );
  });

  test(
    'polling returns terminal statuses without leaking candidates',
    () async {
      final terminalStatuses = {
        'no_previewable_candidates': AvatarJobStatus.noPreviewableCandidates,
        'failed': AvatarJobStatus.failed,
        'superseded': AvatarJobStatus.superseded,
        'cancelled': AvatarJobStatus.cancelled,
        'needs_review': AvatarJobStatus.needsReview,
      };

      for (final entry in terminalStatuses.entries) {
        final transport = RecordingAvatarCallableTransport(
          currentUid: 'uid_1',
          responses: {
            'getAvatarJobCandidates': {
              'jobId': 'avatar_job_1',
              'status': entry.key,
              'candidates': [
                {
                  'candidateId': 'unsafe',
                  'previewUrl': 'https://cdn.example/jobs/j/candidates/c.png',
                },
              ],
            },
          },
        );
        final client = FestivalAvatarGenerationClient(transport: transport);

        final result = await client.pollUntilPreviewReady(
          'avatar_job_1',
          pollInterval: Duration.zero,
        );

        expect(result.status, entry.value);
        expect(result.candidates, isEmpty);
        expect(
          transport.calls.where(
            (call) => call.name == 'getAvatarJobCandidates',
          ),
          hasLength(1),
        );
      }
    },
  );

  test('polling supports timeout and stale job cancellation', () async {
    final timeoutClient = FestivalAvatarGenerationClient(
      transport: RecordingAvatarCallableTransport(
        currentUid: 'uid_1',
        responses: {
          'getAvatarJobCandidates': {
            'jobId': 'avatar_job_1',
            'status': 'running',
            'candidates': [],
          },
        },
      ),
    );

    expect(
      () => timeoutClient.pollUntilPreviewReady(
        'avatar_job_1',
        pollInterval: Duration.zero,
        timeout: Duration.zero,
      ),
      throwsA(
        isA<AvatarGenerationClientException>().having(
          (error) => error.code,
          'code',
          'timeout',
        ),
      ),
    );

    final staleClient = FestivalAvatarGenerationClient(
      transport: RecordingAvatarCallableTransport(
        currentUid: 'uid_1',
        responses: {
          'getAvatarJobCandidates': {
            'jobId': 'avatar_job_1',
            'status': 'running',
            'candidates': [],
          },
        },
      ),
    );

    expect(
      () => staleClient.pollUntilPreviewReady(
        'avatar_job_1',
        pollInterval: Duration.zero,
        shouldContinue: () => false,
      ),
      throwsA(isA<AvatarGenerationClientException>()),
    );
  });
}

class RecordingAvatarCallableTransport implements AvatarCallableTransport {
  RecordingAvatarCallableTransport({
    required this.currentUid,
    this.responses = const {},
    this.sequenceResponses = const {},
    this.errors = const {},
  });

  @override
  final String? currentUid;

  final Map<String, Map<String, dynamic>> responses;
  final Map<String, List<Map<String, dynamic>>> sequenceResponses;
  final Map<String, AvatarCallableException> errors;
  final List<RecordedAvatarCallableCall> calls = [];
  final Map<String, int> _sequenceIndexes = {};

  @override
  Future<Map<String, dynamic>> call(
    String name,
    Map<String, dynamic> payload,
  ) async {
    calls.add(RecordedAvatarCallableCall(name, payload));
    final error = errors[name];
    if (error != null) throw error;
    final sequence = sequenceResponses[name];
    if (sequence != null && sequence.isNotEmpty) {
      final index = _sequenceIndexes[name] ?? 0;
      _sequenceIndexes[name] = index + 1;
      return sequence[index.clamp(0, sequence.length - 1)];
    }
    return responses[name] ?? <String, dynamic>{};
  }
}

class RecordedAvatarCallableCall {
  const RecordedAvatarCallableCall(this.name, this.payload);

  final String name;
  final Map<String, dynamic> payload;
}
