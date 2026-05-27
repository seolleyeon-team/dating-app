library;

import 'dart:convert';
import 'dart:typed_data';

enum AvatarJobStatus {
  queued,
  running,
  qaPending,
  previewReady,
  noPreviewableCandidates,
  needsReview,
  approved,
  failed,
  superseded,
  cancelled,
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
      return AvatarJobStatus.failed;
    case 'superseded':
      return AvatarJobStatus.superseded;
    case 'cancelled':
    case 'canceled':
      return AvatarJobStatus.cancelled;
    default:
      return AvatarJobStatus.unknown;
  }
}

class AvatarCandidate {
  static const int maxPreviewBytes = 1024 * 1024;

  const AvatarCandidate({
    required this.candidateId,
    this.previewUrl = '',
    this.previewBytes,
    this.previewMimeType = '',
  });

  final String candidateId;
  final String previewUrl;
  final Uint8List? previewBytes;
  final String previewMimeType;

  factory AvatarCandidate.fromMap(Map<String, dynamic> map) {
    return AvatarCandidate(
      candidateId: map['candidateId']?.toString().trim() ?? '',
      previewUrl: _safePreviewUrl(map['previewUrl']?.toString().trim()),
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

class AvatarCandidatesResult {
  const AvatarCandidatesResult({
    required this.jobId,
    required this.status,
    required this.candidates,
    this.errorCode = '',
  });

  final String jobId;
  final AvatarJobStatus status;
  final List<AvatarCandidate> candidates;
  final String errorCode;

  factory AvatarCandidatesResult.fromMap(Map<String, dynamic> map) {
    final rawCandidates = map['candidates'];
    final candidates = rawCandidates is List
        ? rawCandidates
              .whereType<Map>()
              .map(
                (item) => AvatarCandidate.fromMap(
                  item.map((key, value) => MapEntry(key.toString(), value)),
                ),
              )
              .where((candidate) => candidate.isValid)
              .toList(growable: false)
        : <AvatarCandidate>[];
    return AvatarCandidatesResult(
      jobId: map['jobId']?.toString().trim() ?? '',
      status: avatarJobStatusFromString(map['status']?.toString()),
      candidates: candidates,
      errorCode: map['errorCode']?.toString().trim() ?? '',
    );
  }
}

class AvatarSourcePhotoUploadResult {
  const AvatarSourcePhotoUploadResult({
    required this.jobId,
    required this.photoId,
    required this.avatarStatus,
    required this.message,
    required this.duplicate,
    this.sourceSelectionVersion,
    this.approvedAvatarUrl = '',
  });

  final String jobId;
  final String photoId;
  final String avatarStatus;
  final String message;
  final bool duplicate;
  final int? sourceSelectionVersion;
  final String approvedAvatarUrl;

  factory AvatarSourcePhotoUploadResult.fromMap(Map<String, dynamic> map) {
    return AvatarSourcePhotoUploadResult(
      jobId: map['jobId']?.toString().trim() ?? '',
      photoId: map['photoId']?.toString().trim() ?? '',
      avatarStatus: map['avatarStatus']?.toString().trim() ?? '',
      message: map['message']?.toString().trim() ?? '',
      duplicate: map['duplicate'] == true,
      sourceSelectionVersion: int.tryParse(
        map['sourceSelectionVersion']?.toString() ?? '',
      ),
      approvedAvatarUrl: map['approvedAvatarUrl']?.toString().trim() ?? '',
    );
  }
}

class AvatarApprovalResult {
  const AvatarApprovalResult({
    required this.avatarStatus,
    required this.approvedAvatarUrl,
    required this.selectedCandidateId,
    required this.duplicate,
    this.avatarId = '',
  });

  final String avatarStatus;
  final String approvedAvatarUrl;
  final String selectedCandidateId;
  final bool duplicate;
  final String avatarId;

  factory AvatarApprovalResult.fromMap(Map<String, dynamic> map) {
    return AvatarApprovalResult(
      avatarStatus: map['avatarStatus']?.toString().trim() ?? '',
      approvedAvatarUrl: map['approvedAvatarUrl']?.toString().trim() ?? '',
      selectedCandidateId:
          map['selectedCandidateId']?.toString().trim() ??
          map['candidateId']?.toString().trim() ??
          '',
      duplicate: map['duplicate'] == true,
      avatarId: map['avatarId']?.toString().trim() ?? '',
    );
  }

  bool get isApproved => avatarStatus == 'approved';
}

Uint8List? _decodePreviewBytes(Object? value, Object? mimeType) {
  if (_safePreviewMimeType(mimeType).isEmpty) return null;
  if (value is! String || value.trim().isEmpty) return null;
  try {
    final bytes = base64Decode(value.trim());
    if (bytes.isEmpty || bytes.length > AvatarCandidate.maxPreviewBytes) {
      return null;
    }
    return Uint8List.fromList(bytes);
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
  final lower = _safeDecode(url).toLowerCase();
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
        r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)',
      ).hasMatch(lower) ||
      lower.contains('/source/') ||
      lower.contains('/jobs/') ||
      lower.contains('/candidates/')) {
    return '';
  }
  return url;
}

String _safeDecode(String value) {
  try {
    return Uri.decodeFull(value);
  } on FormatException {
    return value;
  }
}
