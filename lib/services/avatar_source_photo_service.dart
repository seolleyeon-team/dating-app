import 'dart:convert';
import 'dart:typed_data';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:image_picker/image_picker.dart';

class AvatarSourcePhotoUploadResult {
  final String jobId;
  final String photoId;
  final String avatarStatus;
  final String message;
  final bool duplicate;

  const AvatarSourcePhotoUploadResult({
    required this.jobId,
    required this.photoId,
    required this.avatarStatus,
    required this.message,
    required this.duplicate,
  });

  factory AvatarSourcePhotoUploadResult.fromMap(Map<String, dynamic> data) {
    return AvatarSourcePhotoUploadResult(
      jobId: data['jobId']?.toString() ?? '',
      photoId: data['photoId']?.toString() ?? '',
      avatarStatus: data['avatarStatus']?.toString() ?? '',
      message: data['message']?.toString() ?? '',
      duplicate: data['duplicate'] == true,
    );
  }
}

class AvatarAlreadyApprovedException implements Exception {
  const AvatarAlreadyApprovedException();

  static const message = '이미 등록된 아바타가 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.';

  @override
  String toString() => message;
}

class AvatarSourcePhotoService {
  AvatarSourcePhotoService({FirebaseFunctions? functions, FirebaseAuth? auth})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
      _auth = auth ?? FirebaseAuth.instance;

  static const String _queuedTokenPrefix = 'avatar_generation_queued:';

  final FirebaseFunctions _functions;
  final FirebaseAuth _auth;

  static String queuedSlotToken(String jobId) {
    return '$_queuedTokenPrefix$jobId';
  }

  static bool isQueuedSlotToken(String? value) {
    return value != null && value.startsWith(_queuedTokenPrefix);
  }

  static String? queuedJobId(String? value) {
    if (!isQueuedSlotToken(value)) return null;
    return value!.substring(_queuedTokenPrefix.length);
  }

  Future<AvatarSourcePhotoUploadResult> uploadPickedImage({
    required XFile file,
    int? slotIndex,
    String? uid,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    final currentUser = _auth.currentUser;
    if (currentUser == null) {
      throw Exception('Firebase login session is required for private upload.');
    }

    await currentUser.getIdToken(true);
    final bytes = await file.readAsBytes();
    return uploadBytes(
      bytes: bytes,
      fileName: file.name,
      slotIndex: slotIndex,
      uid: uid,
      chatPartnerRealPhotoDisclosure: chatPartnerRealPhotoDisclosure,
    );
  }

  Future<AvatarSourcePhotoUploadResult> uploadBytes({
    required Uint8List bytes,
    String? fileName,
    int? slotIndex,
    String? uid,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    if (bytes.isEmpty) {
      throw Exception('Image file is empty.');
    }

    final callable = _functions.httpsCallable('uploadAvatarSourcePhoto');
    final HttpsCallableResult<dynamic> result;
    try {
      result = await callable.call(<String, dynamic>{
        'imageBase64': base64Encode(bytes),
        'contentType': _contentTypeForFileName(fileName ?? ''),
        if (fileName != null && fileName.trim().isNotEmpty)
          'fileName': fileName,
        if (slotIndex != null) 'slotIndex': slotIndex,
        if (uid != null && uid.trim().isNotEmpty) 'uid': uid,
        'chatPartnerRealPhotoDisclosure': chatPartnerRealPhotoDisclosure,
      });
    } on FirebaseFunctionsException catch (error) {
      if (error.code == 'failed-precondition' &&
          (error.message ?? '').contains('avatar_already_approved')) {
        throw const AvatarAlreadyApprovedException();
      }
      rethrow;
    }

    final raw = result.data;
    final map = raw is Map
        ? raw.map((key, value) => MapEntry(key.toString(), value))
        : <String, dynamic>{};
    final parsed = AvatarSourcePhotoUploadResult.fromMap(map);
    if (parsed.jobId.isEmpty) {
      throw Exception('Private upload response was incomplete.');
    }
    return parsed;
  }

  String _contentTypeForFileName(String fileName) {
    final lower = fileName.toLowerCase().trim();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {
      return 'image/jpeg';
    }
    if (lower.endsWith('.heic') || lower.endsWith('.heif')) {
      return 'image/heic';
    }
    return 'image/jpeg';
  }
}
