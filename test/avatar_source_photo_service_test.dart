import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';

void main() {
  test('queued slot token stores job id without a URL', () {
    final token = AvatarSourcePhotoService.queuedSlotToken('avatar_job_abc123');

    expect(token, 'avatar_generation_queued:avatar_job_abc123');
    expect(AvatarSourcePhotoService.isQueuedSlotToken(token), isTrue);
    expect(AvatarSourcePhotoService.queuedJobId(token), 'avatar_job_abc123');
    expect(token.startsWith('http'), isFalse);
    expect(token.startsWith('gs://'), isFalse);
  });

  test('regular URLs are not queued source-photo tokens', () {
    const approvedAvatarUrl = 'https://cdn.example/avatar.png';

    expect(
      AvatarSourcePhotoService.isQueuedSlotToken(approvedAvatarUrl),
      isFalse,
    );
    expect(AvatarSourcePhotoService.queuedJobId(approvedAvatarUrl), isNull);
  });

  test('upload result parses safe photo id without source refs', () {
    final result = AvatarSourcePhotoUploadResult.fromMap({
      'jobId': 'avatar_job_abc123',
      'photoId': 'src_abc123',
      'avatarStatus': 'queued',
      'message': 'avatar_generation_queued',
      'duplicate': true,
    });

    expect(result.jobId, 'avatar_job_abc123');
    expect(result.photoId, 'src_abc123');
    expect(result.avatarStatus, 'queued');
    expect(result.duplicate, isTrue);
  });

  test('approved avatar exception exposes safe Korean message', () {
    expect(
      const AvatarAlreadyApprovedException().toString(),
      '이미 등록된 아바타가 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.',
    );
  });
}
