/// Avatar generation onboarding flow models.
///
/// 이 파일은 사진 업로드 → 아바타 생성 → 후보 선택 → 승인 흐름에서 사용하는
/// 순수 데이터 모델만 정의합니다. UI 위젯과 서비스 클라이언트가 공통으로 참조합니다.
///
/// 프라이버시 원칙
/// - 원본 사진/소스 GCS URI/서명 URL을 포함하지 않습니다.
/// - 임시 프리뷰 URL(`previewUrl`)은 위젯 상태에만 머물고 Firestore/로그에 남기지 않습니다.
library;

import 'dart:convert';
import 'dart:typed_data';

/// 아바타 온보딩 흐름의 상태 머신.
///
/// 사진 업로드 화면에서 [PhotoUploadScreen]이 이 enum을 통해 단일 진행 상태를
/// 관리합니다. 한 번에 하나의 상태만 활성화됩니다.
enum AvatarOnboardingFlowState {
  /// 아바타 흐름이 활성화되지 않은 기본 상태.
  idle,

  /// "다음" 버튼을 누른 직후 원본 사진 업로드를 시작했지만 아직 응답을 받지 못한 상태.
  uploadingSourcePhoto,

  /// 백엔드에 작업이 큐잉됐고 워커가 아바타를 생성하기 시작하기 전.
  avatarQueued,

  /// 아바타 생성이 실제로 진행 중이며 후보를 폴링하고 있는 상태.
  generatingAvatar,

  /// 아바타 후보가 준비돼 모달을 띄울 수 있는 상태.
  previewReady,

  /// 사용자가 후보를 선택하고 승인 API를 호출하는 중.
  approvingAvatar,

  /// 승인이 성공적으로 끝나 다음 온보딩 화면으로 이동 가능한 상태.
  approved,

  /// 흐름 중 어느 단계에서든 회복할 수 없는 오류가 발생한 상태.
  failed,
}

/// 사용자에게 노출 가능한 아바타 후보 정보.
///
/// Flutter UI는 `candidateId`와 `previewUrl`만 사용합니다.
/// 백엔드 내부 저장 경로(원본 사진 참조, 임시 GCS 객체 URI 등)는 절대 보유하지 않습니다.
class AvatarCandidate {
  static const int maxPreviewBytes = 1024 * 1024;

  final String candidateId;
  final String previewUrl;
  final Uint8List? previewBytes;
  final String previewMimeType;

  const AvatarCandidate({
    required this.candidateId,
    this.previewUrl = '',
    this.previewBytes,
    this.previewMimeType = '',
  });

  factory AvatarCandidate.fromMap(Map<String, dynamic> map) {
    final candidateId = map['candidateId']?.toString().trim() ?? '';
    final previewUrl = _safePreviewUrl(map['previewUrl']?.toString().trim());
    return AvatarCandidate(
      candidateId: candidateId,
      previewUrl: previewUrl,
      previewBytes: _decodePreviewBytes(
        map['previewImageBase64'],
        map['previewMimeType'],
      ),
      previewMimeType: _safePreviewMimeType(map['previewMimeType']),
    );
  }

  bool get hasPreviewBytes => previewBytes != null && previewBytes!.isNotEmpty;

  bool get isValid =>
      candidateId.isNotEmpty && (hasPreviewBytes || previewUrl.isNotEmpty);
}

Uint8List? _decodePreviewBytes(Object? value, Object? mimeType) {
  if (_safePreviewMimeType(mimeType).isEmpty) return null;
  if (value is! String || value.trim().isEmpty) return null;
  try {
    final bytes = base64Decode(value.trim());
    if (bytes.length > AvatarCandidate.maxPreviewBytes) return null;
    return bytes.isEmpty ? null : Uint8List.fromList(bytes);
  } on FormatException {
    return null;
  }
}

String _safePreviewMimeType(Object? value) {
  final mimeType = value?.toString().trim().toLowerCase() ?? '';
  return switch (mimeType) {
    'image/jpeg' || 'image/png' || 'image/webp' => mimeType,
    _ => '',
  };
}

String _safePreviewUrl(String? value) {
  final url = (value ?? '').trim();
  if (url.isEmpty) return '';
  final lower = url.toLowerCase();
  if (lower.startsWith('gs://') || lower.startsWith('gcs://')) return '';
  if (lower.contains('x-goog-signature') ||
      lower.contains('x-goog-credential') ||
      lower.contains('x-goog-expires') ||
      lower.contains('googleaccessid') ||
      lower.contains('signature=') ||
      lower.contains('x-amz-signature')) {
    return '';
  }
  if (RegExp(
        r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp)',
      ).hasMatch(lower) ||
      lower.contains('/source/') ||
      lower.contains('/jobs/') ||
      lower.contains('/candidates/')) {
    return '';
  }
  return url;
}

/// 백엔드 작업 상태.
///
/// 폴링 응답을 [AvatarOnboardingFlowState]로 매핑하는 데 사용합니다.
enum AvatarJobStatus {
  queued,
  running,
  qaPending,
  previewReady,
  noPreviewableCandidates,
  needsReview,
  approved,
  failed,
  unknown,
}

AvatarJobStatus avatarJobStatusFromString(String? raw) {
  switch ((raw ?? '').trim()) {
    case 'queued':
      return AvatarJobStatus.queued;
    case 'running':
    case 'generating':
      return AvatarJobStatus.running;
    case 'qa_pending':
    case 'qa_running':
      return AvatarJobStatus.qaPending;
    case 'preview_ready':
      return AvatarJobStatus.previewReady;
    case 'no_previewable_candidates':
      return AvatarJobStatus.noPreviewableCandidates;
    case 'needs_review':
      return AvatarJobStatus.needsReview;
    case 'approved':
    case 'approval_copying':
    case 'completed':
      return AvatarJobStatus.approved;
    case 'failed':
    case 'cancelled':
      return AvatarJobStatus.failed;
    default:
      return AvatarJobStatus.unknown;
  }
}

/// 후보 폴링 결과.
class AvatarCandidatesResult {
  final String jobId;
  final AvatarJobStatus status;
  final List<AvatarCandidate> candidates;

  const AvatarCandidatesResult({
    required this.jobId,
    required this.status,
    required this.candidates,
  });

  factory AvatarCandidatesResult.fromMap(Map<String, dynamic> map) {
    final jobId = map['jobId']?.toString() ?? '';
    final status = avatarJobStatusFromString(map['status']?.toString());
    final rawCandidates = map['candidates'];
    final List<AvatarCandidate> candidates;
    if (rawCandidates is List) {
      candidates = rawCandidates
          .whereType<Map>()
          .map(
            (e) => AvatarCandidate.fromMap(
              e.map((k, v) => MapEntry(k.toString(), v)),
            ),
          )
          .where((c) => c.isValid)
          .toList(growable: false);
    } else {
      candidates = const [];
    }
    return AvatarCandidatesResult(
      jobId: jobId,
      status: status,
      candidates: candidates,
    );
  }
}

/// 아바타 승인 응답.
class AvatarApprovalResult {
  final String avatarStatus;
  final String approvedAvatarUrl;
  final String selectedCandidateId;
  final bool duplicate;

  const AvatarApprovalResult({
    required this.avatarStatus,
    required this.approvedAvatarUrl,
    required this.selectedCandidateId,
    required this.duplicate,
  });

  factory AvatarApprovalResult.fromMap(Map<String, dynamic> map) {
    return AvatarApprovalResult(
      avatarStatus: map['avatarStatus']?.toString() ?? '',
      approvedAvatarUrl: map['approvedAvatarUrl']?.toString() ?? '',
      selectedCandidateId: map['selectedCandidateId']?.toString() ?? '',
      duplicate: map['duplicate'] == true,
    );
  }

  bool get isApproved => avatarStatus == 'approved';
}
