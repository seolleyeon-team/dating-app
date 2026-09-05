import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import '../features/onboarding/services/avatar_resume_policy.dart';
import '../features/onboarding/widgets/avatar_generation_models.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'avatar_source_photo_service.dart';
import 'onboarding_photo_source_ref.dart';

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
  /// 폴링 호출이 연속으로 이만큼 실패하기 전까지는 생성 흐름을 중단하지 않는다.
  static const int defaultMaxConsecutivePollErrors = 3;

  Future<AvatarSourcePhotoUploadResult> beginFromOnboardingPhotos({
    required List<OnboardingPhotoSourceRef> sourcePhotos,
    required String uid,
    String? clientRequestId,
    bool chatPartnerRealPhotoDisclosure = false,
  }) {
    throw UnsupportedError('Server source-set selection is not implemented.');
  }

  /// 단일 폴 호출. 진행 중이면 후보 리스트가 비어 있을 수 있다.
  Future<AvatarCandidatesResult> getCandidates(String jobId);

  /// 사용자가 선택한 후보를 승인하고 Firestore 업데이트는 백엔드에 위임한다.
  Future<AvatarApprovalResult> approveCandidate(String candidateId);

  /// 현재 사용자의 아바타 생성 상태를 서버에서 읽는다.
  ///
  /// 앱 재시작/화면 재진입 시 복구의 권위다. 기본 구현은 null을 돌려주므로
  /// 이 값을 읽지 못하는 구현에서는 로컬 상태가 그대로 유지된다.
  Future<AvatarGenerationStatusSnapshot?> getCurrentGenerationStatus() async =>
      null;

  /// 서버가 재시도를 허용한 실패를 재시도한다. 같은 logical generation 을
  /// 서버가 재디스패치하며, 돌아온 상태의 jobId 로 폴링을 잇는다.
  /// 기본 구현은 null(재시도 콜러블 없음) 이라 호출자는 폴링으로 되돌아간다.
  Future<AvatarGenerationStatusSnapshot?> retryCurrentGeneration({
    required String clientRequestId,
  }) async => null;

  /// "사진을 바꾸고 다시 만들기": 현재 generation 을 서버에서 종료하고 source
  /// lock 을 풀어 새 사진 세트로 새 generation 을 열 수 있게 한다.
  /// 같은 generation 재시도가 아니다. 기본 구현은 false(불가).
  Future<bool> replaceCurrentGeneration({
    required String clientRequestId,
  }) async => false;

  /// 흐름 단위로 사용 가능한 폴링 도우미.
  ///
  /// [pollInterval] 간격으로 [getCandidates]를 호출하면서 다음 중 하나가
  /// 발생할 때까지 반복한다:
  /// - 상태가 `preview_ready`이고 후보가 1개 이상 도착 → 결과 반환
  /// - 상태가 `failed`/`cancelled`/`superseded`/`no_previewable_candidates`/`needs_review` → 결과 반환
  /// - [timeout] 초과 → [TimeoutException]
  /// - [shouldContinue]가 false를 반환 → [_AvatarPollingCancelled]
  /// - 폴링 호출이 [maxConsecutiveErrors]회 연속 실패 → 마지막 예외를 그대로 전파
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors = defaultMaxConsecutivePollErrors,
  }) async {
    final deadline = DateTime.now().add(timeout);
    var consecutiveErrors = 0;
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
        consecutiveErrors = 0;
        _logAvatarClient(
          'avatar_poll_tick',
          jobId: jobId,
          status: last.status,
          candidateCount: last.candidates.length,
        );
      } catch (error) {
        // 폴링 호출 실패는 서버 작업의 실패가 아니다. 일시적인 네트워크 오류
        // 하나로 진행 중인 생성 작업을 최종 실패로 확정하면 안 되므로
        // 연속 실패가 예산을 넘길 때까지는 같은 간격으로 재시도한다.
        consecutiveErrors += 1;
        _logAvatarClient(
          'avatar_poll_error',
          jobId: jobId,
          error: error,
          consecutiveErrors: consecutiveErrors,
        );
        if (consecutiveErrors >= maxConsecutiveErrors) {
          rethrow;
        }
        await Future<void>.delayed(pollInterval);
        continue;
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
  int? consecutiveErrors,
  Object? error,
}) {
  final parts = <String>['[AvatarFlow]', phase];
  if (jobId != null) parts.add('jobId=${_redactIdentifier(jobId)}');
  if (status != null) parts.add('status=${status.name}');
  if (candidateCount != null) parts.add('candidateCount=$candidateCount');
  if (consecutiveErrors != null) {
    parts.add('consecutiveErrors=$consecutiveErrors');
  }
  if (error != null) parts.add('error=${PrivacyLogUtils.errorSummary(error)}');
  debugPrint(parts.join(' '));
}

String _redactIdentifier(String value) {
  final normalized = value.trim();
  if (normalized.length <= 10) return '<redacted>';
  return '${normalized.substring(0, 10)}...';
}

/// 폴링이 외부 신호에 의해 취소됐을 때 던지는 예외.
class AvatarPollingCancelled implements Exception {
  const AvatarPollingCancelled();

  @override
  String toString() => 'AvatarPollingCancelled';
}

/// Firebase Functions(`asia-northeast3`) 콜러블을 호출하는 기본 구현.
///
/// `beginAvatarGenerationFromOnboardingPhotos`, `getAvatarJobCandidates`,
/// `approveAvatarCandidate`
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
  Future<AvatarSourcePhotoUploadResult> beginFromOnboardingPhotos({
    required List<OnboardingPhotoSourceRef> sourcePhotos,
    required String uid,
    String? clientRequestId,
    bool chatPartnerRealPhotoDisclosure = false,
  }) {
    return _sourcePhotoService.beginFromOnboardingPhotos(
      sourcePhotos: sourcePhotos,
      uid: uid,
      clientRequestId: clientRequestId,
      chatPartnerRealPhotoDisclosure: chatPartnerRealPhotoDisclosure,
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
  Future<AvatarGenerationStatusSnapshot?> getCurrentGenerationStatus() async {
    final currentUser = FirebaseAuth.instance.currentUser;
    if (currentUser == null) return null;
    try {
      final callable = _functions.httpsCallable(
        'getCurrentAvatarGenerationStatus',
      );
      final result = await callable.call(<String, dynamic>{});
      final raw = result.data;
      if (raw is! Map) return null;
      return AvatarGenerationStatusSnapshot.fromMap(
        raw.map((key, value) => MapEntry(key.toString(), value)),
      );
    } catch (error) {
      // 상태 조회 실패는 생성 실패가 아니다. 로컬 상태를 유지한다.
      _logAvatarClient('avatar_status_fetch_failed', error: error);
      return null;
    }
  }

  @override
  Future<AvatarGenerationStatusSnapshot?> retryCurrentGeneration({
    required String clientRequestId,
  }) async {
    final currentUser = FirebaseAuth.instance.currentUser;
    if (currentUser == null) return null;
    final callable = _functions.httpsCallable('retryCurrentAvatarGeneration');
    final result = await callable.call(<String, dynamic>{
      'clientRequestId': clientRequestId,
    });
    final raw = result.data;
    if (raw is! Map) return null;
    return AvatarGenerationStatusSnapshot.fromMap(
      raw.map((key, value) => MapEntry(key.toString(), value)),
    );
  }

  @override
  Future<bool> replaceCurrentGeneration({
    required String clientRequestId,
  }) async {
    final currentUser = FirebaseAuth.instance.currentUser;
    if (currentUser == null) return false;
    final callable = _functions.httpsCallable('replaceAvatarGeneration');
    final result = await callable.call(<String, dynamic>{
      'clientRequestId': clientRequestId,
    });
    final raw = result.data;
    return raw is Map && raw['replaced'] == true;
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
