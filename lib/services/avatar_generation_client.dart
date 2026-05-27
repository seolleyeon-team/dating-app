import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

import '../features/onboarding/widgets/avatar_generation_models.dart';
import 'avatar_source_photo_service.dart';

/// 아바타 생성 파이프라인 클라이언트 추상화.
///
/// 사진 업로드 → 후보 조회 → 승인의 3단계를 단일 인터페이스로 제공해 UI/테스트
/// 코드가 백엔드 호출과 분리되도록 합니다.
///
/// 이 인터페이스를 구현한 클래스는 다음을 지켜야 합니다.
/// - 원본 사진 URL을 노출하지 않는다.
/// - 사설/임시 버킷 경로(gs://, gcs://, signed URL)를 UI에 전달하지 않는다.
/// - Firestore 직접 쓰기를 하지 않는다.
abstract class AvatarGenerationClient {
  /// 사용자가 선택한 사진 파일을 백엔드 콜러블로 업로드한다.
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
  });

  /// 단일 폴 호출. 진행 중이면 후보 리스트가 비어 있을 수 있다.
  Future<AvatarCandidatesResult> getCandidates(String jobId);

  /// 사용자가 선택한 후보를 승인하고 Firestore 업데이트는 백엔드에 위임한다.
  Future<AvatarApprovalResult> approveCandidate(String candidateId);

  /// 흐름 단위로 사용 가능한 폴링 도우미.
  ///
  /// [pollInterval] 간격으로 [getCandidates]를 호출하면서 다음 중 하나가
  /// 발생할 때까지 반복한다:
  /// - 상태가 `preview_ready`이고 후보가 1개 이상 도착 → 결과 반환
  /// - 상태가 `failed`/`cancelled`/`superseded`/`no_previewable_candidates`/`needs_review` → 결과 반환
  /// - [timeout] 초과 → [TimeoutException]
  /// - [shouldContinue]가 false를 반환 → [_AvatarPollingCancelled]
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
  }) async {
    final deadline = DateTime.now().add(timeout);
    AvatarCandidatesResult last = const AvatarCandidatesResult(
      jobId: '',
      status: AvatarJobStatus.unknown,
      candidates: [],
    );

    while (DateTime.now().isBefore(deadline)) {
      if (shouldContinue != null && !shouldContinue()) {
        throw const AvatarPollingCancelled();
      }
      try {
        last = await getCandidates(jobId);
        _logAvatarClient(
          'avatar_poll_tick',
          jobId: jobId,
          status: last.status,
          candidateCount: last.candidates.length,
        );
      } catch (error) {
        _logAvatarClient('avatar_poll_error', jobId: jobId, error: error);
        rethrow;
      }
      switch (last.status) {
        case AvatarJobStatus.previewReady:
          if (last.candidates.isNotEmpty) return last;
          break;
        case AvatarJobStatus.noPreviewableCandidates:
          return last;
        case AvatarJobStatus.failed:
          return last;
        case AvatarJobStatus.superseded:
          return last;
        case AvatarJobStatus.cancelled:
          return last;
        case AvatarJobStatus.needsReview:
          return last;
        case AvatarJobStatus.approved:
          return last;
        default:
          break;
      }
      await Future<void>.delayed(pollInterval);
    }

    _logAvatarClient(
      'avatar_poll_timeout',
      jobId: jobId,
      status: last.status,
      candidateCount: last.candidates.length,
    );
    throw TimeoutException(
      'Avatar generation timed out',
      DateTime.now().difference(deadline.subtract(timeout)),
    );
  }
}

void _logAvatarClient(
  String phase, {
  String? jobId,
  AvatarJobStatus? status,
  int? candidateCount,
  Object? error,
}) {
  final parts = <String>['[AvatarFlow]', phase];
  if (jobId != null) parts.add('jobId=${_redactIdentifier(jobId)}');
  if (status != null) parts.add('status=${status.name}');
  if (candidateCount != null) parts.add('candidateCount=$candidateCount');
  if (error != null) parts.add('error=${_redactError(error)}');
  debugPrint(parts.join(' '));
}

String _redactIdentifier(String value) {
  final normalized = value.trim();
  if (normalized.length <= 10) return '<redacted>';
  return '${normalized.substring(0, 10)}...';
}

String _redactError(Object error) {
  if (error is FirebaseFunctionsException) {
    return 'FirebaseFunctionsException('
        'code=${error.code}, '
        'message=${_sanitizeLogText(error.message)})';
  }
  return error.runtimeType.toString();
}

String _sanitizeLogText(String? value) {
  var text = (value ?? '').trim();
  if (text.isEmpty) return '';
  text = text.replaceAll(
    RegExp(r'g(?:s|cs)://[^\s]+', caseSensitive: false),
    '<private-ref-redacted>',
  );
  text = text.replaceAll(
    RegExp(
      r'(X-Goog-[^=&\s]+|Google'
      r'AccessId|Signature|Expires|X-Amz-[^=&\s]+)=([^&\s]+)',
      caseSensitive: false,
    ),
    r'$1=<redacted>',
  );
  text = text.replaceAll(
    RegExp(
      r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)',
      caseSensitive: false,
    ),
    '<private-bucket-redacted>',
  );
  return text.length <= 180 ? text : '${text.substring(0, 180)}...';
}

/// 폴링이 외부 신호에 의해 취소됐을 때 던지는 예외.
class AvatarPollingCancelled implements Exception {
  const AvatarPollingCancelled();

  @override
  String toString() => 'AvatarPollingCancelled';
}

/// Firebase Functions(`asia-northeast3`) 콜러블을 호출하는 기본 구현.
///
/// `uploadAvatarSourcePhoto`, `getAvatarJobCandidates`, `approveAvatarCandidate`
/// 콜러블 이름은 백엔드 구현과 일치합니다.
class BackendAvatarGenerationClient extends AvatarGenerationClient {
  BackendAvatarGenerationClient({
    AvatarSourcePhotoService? sourcePhotoService,
    FirebaseFunctions? functions,
  }) : _sourcePhotoService = sourcePhotoService ?? AvatarSourcePhotoService(),
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  final AvatarSourcePhotoService _sourcePhotoService;
  final FirebaseFunctions _functions;

  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
  }) {
    return _sourcePhotoService.uploadPickedImage(
      file: file,
      slotIndex: slotIndex,
      uid: uid,
    );
  }

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    final currentUser = FirebaseAuth.instance.currentUser;
    if (currentUser == null) {
      throw Exception('Firebase login session is required.');
    }
    final callable = _functions.httpsCallable('getAvatarJobCandidates');
    final result = await callable.call(<String, dynamic>{'jobId': jobId});
    final raw = result.data;
    final map = raw is Map
        ? raw.map((key, value) => MapEntry(key.toString(), value))
        : <String, dynamic>{};
    return AvatarCandidatesResult.fromMap(map);
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    final currentUser = FirebaseAuth.instance.currentUser;
    if (currentUser == null) {
      throw Exception('Firebase login session is required.');
    }
    final callable = _functions.httpsCallable('approveAvatarCandidate');
    final result = await callable.call(<String, dynamic>{
      'candidateId': candidateId,
    });
    final raw = result.data;
    final map = raw is Map
        ? raw.map((key, value) => MapEntry(key.toString(), value))
        : <String, dynamic>{};
    final parsed = AvatarApprovalResult.fromMap(map);
    if (parsed.avatarStatus.isEmpty) {
      throw Exception('Avatar approval response was incomplete.');
    }
    return parsed;
  }
}

/// 위젯 테스트 및 디자인 QA에서만 사용하는 가짜 클라이언트.
///
/// 운영 빌드의 기본 클라이언트로 사용해선 안 됩니다.
class MockAvatarGenerationClient extends AvatarGenerationClient {
  MockAvatarGenerationClient({
    this.uploadDelay = const Duration(milliseconds: 300),
    this.firstPollDelay = const Duration(milliseconds: 800),
    this.approveDelay = const Duration(milliseconds: 400),
    List<AvatarCandidate>? candidates,
    this.simulatedJobStatus = AvatarJobStatus.previewReady,
    this.simulatedApprovalStatus = 'approved',
    this.failApproval = false,
  }) : _candidates =
           candidates ??
           const [
             AvatarCandidate(
               candidateId: 'mock_cand_1',
               previewUrl:
                   'https://placehold.co/512x512/F4ECEE/4A2C40?text=Mock+1',
             ),
             AvatarCandidate(
               candidateId: 'mock_cand_2',
               previewUrl:
                   'https://placehold.co/512x512/F4ECEE/4A2C40?text=Mock+2',
             ),
             AvatarCandidate(
               candidateId: 'mock_cand_3',
               previewUrl:
                   'https://placehold.co/512x512/F4ECEE/4A2C40?text=Mock+3',
             ),
             AvatarCandidate(
               candidateId: 'mock_cand_4',
               previewUrl:
                   'https://placehold.co/512x512/F4ECEE/4A2C40?text=Mock+4',
             ),
           ];

  final Duration uploadDelay;
  final Duration firstPollDelay;
  final Duration approveDelay;
  final List<AvatarCandidate> _candidates;
  final AvatarJobStatus simulatedJobStatus;
  final String simulatedApprovalStatus;
  final bool failApproval;

  int _pollCount = 0;

  @override
  Future<AvatarSourcePhotoUploadResult> uploadSourcePhoto({
    required XFile file,
    required String uid,
    int? slotIndex,
  }) async {
    await Future<void>.delayed(uploadDelay);
    return const AvatarSourcePhotoUploadResult(
      jobId: 'mock_job_id',
      photoId: 'mock_photo_id',
      avatarStatus: 'queued',
      message: 'avatar_generation_queued',
      duplicate: false,
    );
  }

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    _pollCount += 1;
    if (_pollCount == 1) {
      await Future<void>.delayed(firstPollDelay);
    }
    return AvatarCandidatesResult(
      jobId: jobId,
      status: simulatedJobStatus,
      candidates: simulatedJobStatus == AvatarJobStatus.previewReady
          ? List<AvatarCandidate>.unmodifiable(_candidates)
          : const [],
    );
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    await Future<void>.delayed(approveDelay);
    if (failApproval) {
      throw Exception('mock_approval_failure');
    }
    return AvatarApprovalResult(
      avatarStatus: simulatedApprovalStatus,
      approvedAvatarUrl:
          'https://placehold.co/512x512/4A2C40/F9F9F7?text=Approved',
      selectedCandidateId: candidateId,
      duplicate: false,
    );
  }
}
