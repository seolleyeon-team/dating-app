import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';

import 'avatar_generation_models.dart';

const avatarAlreadyApprovedMessage =
    '이미 등록된 아바타가 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.';
const avatarSourceLockedMessage = '아바타 생성이 시작되어 사진을 변경할 수 없어요.';
const avatarInvalidImageMessage = '이미지 파일을 확인해주세요.';
const avatarNoPreviewableMessage = '안전한 아바타 후보를 만들지 못했어요. 같은 사진으로 다시 시도해주세요.';
const avatarGenericFailureMessage = '아바타 생성에 실패했어요. 다시 시도해주세요.';
const avatarTimeoutMessage = '아바타 생성이 지연되고 있어요. 잠시 후 다시 확인해주세요.';

abstract class AvatarCallableTransport {
  String? get currentUid;

  Future<Map<String, dynamic>> call(String name, Map<String, dynamic> payload);
}

class FirebaseAvatarCallableTransport implements AvatarCallableTransport {
  FirebaseAvatarCallableTransport({
    FirebaseAuth? auth,
    FirebaseFunctions? functions,
  }) : _auth = auth ?? FirebaseAuth.instance,
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  final FirebaseAuth _auth;
  final FirebaseFunctions _functions;

  @override
  String? get currentUid => _auth.currentUser?.uid;

  @override
  Future<Map<String, dynamic>> call(
    String name,
    Map<String, dynamic> payload,
  ) async {
    final user = _auth.currentUser;
    if (user == null) {
      throw const AvatarCallableException(
        code: 'unauthenticated',
        message: '로그인이 필요해요.',
      );
    }
    await user.getIdToken(true);
    try {
      final result = await _functions.httpsCallable(name).call(payload);
      final raw = result.data;
      return raw is Map
          ? raw.map((key, value) => MapEntry(key.toString(), value))
          : <String, dynamic>{};
    } on FirebaseFunctionsException catch (error) {
      throw AvatarCallableException(
        code: error.code,
        message: error.message ?? '',
      );
    }
  }
}

class AvatarCallableException implements Exception {
  const AvatarCallableException({required this.code, required this.message});

  final String code;
  final String message;

  @override
  String toString() => 'AvatarCallableException($code)';
}

class AvatarGenerationClientException implements Exception {
  const AvatarGenerationClientException(this.userMessage, {this.code = ''});

  final String userMessage;
  final String code;

  @override
  String toString() => userMessage;
}

class FestivalAvatarGenerationClient {
  FestivalAvatarGenerationClient({AvatarCallableTransport? transport})
    : _transport = transport ?? FirebaseAvatarCallableTransport();

  final AvatarCallableTransport _transport;

  Future<AvatarSourcePhotoUploadResult> uploadAvatarSourcePhoto({
    required Uint8List bytes,
    required String fileName,
    required String contentType,
  }) async {
    if (_transport.currentUid == null || _transport.currentUid!.isEmpty) {
      throw const AvatarGenerationClientException('로그인이 필요해요.');
    }
    if (bytes.isEmpty) {
      throw const AvatarGenerationClientException(avatarInvalidImageMessage);
    }
    if (!_isSupportedImageContentType(contentType)) {
      throw const AvatarGenerationClientException(avatarInvalidImageMessage);
    }
    if (bytes.length > 10 * 1024 * 1024) {
      throw const AvatarGenerationClientException('이미지는 10MB 이하로 올려주세요.');
    }

    final data = await _callSafely('uploadAvatarSourcePhoto', {
      'imageBase64': base64Encode(bytes),
      'contentType': contentType,
      if (fileName.trim().isNotEmpty) 'fileName': fileName.trim(),
      'uid': _transport.currentUid,
      'chatPartnerRealPhotoDisclosure': false,
    });
    final parsed = AvatarSourcePhotoUploadResult.fromMap(data);
    if (parsed.jobId.isEmpty) {
      throw const AvatarGenerationClientException(avatarGenericFailureMessage);
    }
    return parsed;
  }

  Future<AvatarCandidatesResult> getAvatarJobCandidates(String jobId) async {
    final data = await _callSafely('getAvatarJobCandidates', {'jobId': jobId});
    return AvatarCandidatesResult.fromMap(data);
  }

  Future<AvatarApprovalResult> approveAvatarCandidate(
    String candidateId,
  ) async {
    final data = await _callSafely('approveAvatarCandidate', {
      'candidateId': candidateId,
    });
    final parsed = AvatarApprovalResult.fromMap(data);
    if (!parsed.isApproved ||
        parsed.approvedAvatarUrl.isEmpty ||
        parsed.selectedCandidateId.isEmpty) {
      throw const AvatarGenerationClientException(avatarGenericFailureMessage);
    }
    return parsed;
  }

  Future<AvatarCandidatesResult> pollUntilPreviewReady(
    String jobId, {
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 180),
    bool Function()? shouldContinue,
  }) async {
    final deadline = DateTime.now().add(timeout);
    AvatarCandidatesResult last = AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.unknown,
      candidates: const [],
    );

    while (DateTime.now().isBefore(deadline)) {
      if (shouldContinue != null && !shouldContinue()) {
        throw const AvatarGenerationClientException(
          avatarGenericFailureMessage,
        );
      }
      last = await getAvatarJobCandidates(jobId);
      switch (last.status) {
        case AvatarJobStatus.previewReady:
          if (last.candidates.isNotEmpty) return last;
          break;
        case AvatarJobStatus.noPreviewableCandidates:
        case AvatarJobStatus.needsReview:
        case AvatarJobStatus.failed:
        case AvatarJobStatus.superseded:
        case AvatarJobStatus.cancelled:
        case AvatarJobStatus.approved:
          return last;
        case AvatarJobStatus.queued:
        case AvatarJobStatus.running:
        case AvatarJobStatus.qaPending:
        case AvatarJobStatus.unknown:
          break;
      }
      if (pollInterval > Duration.zero) {
        await Future<void>.delayed(pollInterval);
      }
    }

    throw const AvatarGenerationClientException(
      avatarTimeoutMessage,
      code: 'timeout',
    );
  }

  Future<Map<String, dynamic>> _callSafely(
    String name,
    Map<String, dynamic> payload,
  ) async {
    try {
      return await _transport.call(name, payload);
    } on AvatarCallableException catch (error) {
      throw AvatarGenerationClientException(
        _messageForCallableError(error),
        code: error.code,
      );
    }
  }

  String _messageForCallableError(AvatarCallableException error) {
    final message = error.message.toLowerCase();
    if (message.contains('avatar_already_approved')) {
      return avatarAlreadyApprovedMessage;
    }
    if (message.contains('avatar_source_locked')) {
      return avatarSourceLockedMessage;
    }
    if (error.code == 'invalid-argument' ||
        error.code == 'resource-exhausted') {
      return avatarInvalidImageMessage;
    }
    if (message.contains('no_previewable_candidates')) {
      return avatarNoPreviewableMessage;
    }
    if (error.code == 'unauthenticated') {
      return '로그인이 필요해요.';
    }
    if (error.code == 'permission-denied') {
      return '아바타 생성 권한을 확인해주세요.';
    }
    return avatarGenericFailureMessage;
  }
}

bool _isSupportedImageContentType(String contentType) {
  switch (contentType.trim().toLowerCase()) {
    case 'image/jpeg':
    case 'image/png':
    case 'image/webp':
      return true;
    default:
      return false;
  }
}
