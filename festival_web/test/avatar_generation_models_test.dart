import 'dart:convert';

import 'package:festival_web/avatar/avatar_generation_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('candidate accepts runtime preview bytes and rejects private refs', () {
    final candidate = AvatarCandidate.fromMap({
      'candidateId': 'cand_1',
      'previewImageBase64': base64Encode([1, 2, 3]),
      'previewMimeType': 'image/png',
      'previewUrl':
          'https://storage.googleapis.com/seolleyeon-avatar-temp/jobs/j/c.png',
    });

    expect(candidate.candidateId, 'cand_1');
    expect(candidate.previewBytes, isNotNull);
    expect(candidate.previewUrl, isEmpty);
    expect(candidate.isValid, isTrue);
  });

  test('candidates result filters invalid and maps terminal statuses', () {
    final result = AvatarCandidatesResult.fromMap({
      'jobId': 'avatar_job_123',
      'status': 'no_previewable_candidates',
      'errorCode': 'avatar_source_multi_face',
      'candidates': [
        {'candidateId': 'cand_empty'},
        {
          'candidateId': 'cand_ok',
          'previewImageBase64': base64Encode([4, 5, 6]),
          'previewMimeType': 'image/jpeg',
        },
      ],
    });

    expect(result.jobId, 'avatar_job_123');
    expect(result.status, AvatarJobStatus.noPreviewableCandidates);
    expect(result.errorCode, 'avatar_source_multi_face');
    expect(result.candidates.map((c) => c.candidateId), ['cand_ok']);
  });
}
