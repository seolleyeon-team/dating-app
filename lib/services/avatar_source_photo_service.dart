import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:uuid/uuid.dart';

import 'onboarding_photo_source_ref.dart';

class AvatarSourcePhotoUploadResult {
  final String jobId;
  final String photoId;
  final String avatarStatus;
  final String message;
  final bool duplicate;
  final int? sourceSelectionVersion;

  const AvatarSourcePhotoUploadResult({
    required this.jobId,
    required this.photoId,
    required this.avatarStatus,
    required this.message,
    required this.duplicate,
    this.sourceSelectionVersion,
  });

  factory AvatarSourcePhotoUploadResult.fromMap(Map<String, dynamic> data) {
    return AvatarSourcePhotoUploadResult(
      jobId: data['jobId']?.toString() ?? '',
      photoId: data['photoId']?.toString() ?? '',
      avatarStatus: data['avatarStatus']?.toString() ?? '',
      message: data['message']?.toString() ?? '',
      duplicate: data['duplicate'] == true,
      sourceSelectionVersion: int.tryParse(
        data['sourceSelectionVersion']?.toString() ?? '',
      ),
    );
  }
}

class AvatarAlreadyApprovedException implements Exception {
  const AvatarAlreadyApprovedException();

  static const message = '아바타가 등록되어 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요.';

  @override
  String toString() => message;
}

class AvatarSourceLockedException implements Exception {
  const AvatarSourceLockedException();

  static const message = '아바타 생성이 시작되어 사진을 변경할 수 없어요.';

  @override
  String toString() => message;
}

class AvatarSourcePhotoService {
  AvatarSourcePhotoService({FirebaseFunctions? functions, FirebaseAuth? auth})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
      _auth = auth ?? FirebaseAuth.instance;

  static const String _queuedTokenPrefix = 'avatar_generation_queued:';
  static const String sourceConsentVersion = 'photo_consent_v4';
  static const Map<String, bool> defaultConsentPurposes = <String, bool>{
    'avatarGeneration': true,
    'clipRecommendation': false,
    'sourcePhotoRetention': false,
  };

  static String createClientRequestId() => const Uuid().v4();

  static Map<String, dynamic> buildUploadMetadata({
    required String clientRequestId,
  }) {
    return <String, dynamic>{
      'clientRequestId': clientRequestId,
      'consentVersion': sourceConsentVersion,
      'consentPurposes': Map<String, bool>.from(defaultConsentPurposes),
    };
  }

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

  Future<AvatarSourcePhotoUploadResult> beginFromOnboardingPhotos({
    required List<OnboardingPhotoSourceRef> sourcePhotos,
    String? uid,
    String? clientRequestId,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    final currentUser = _auth.currentUser;
    if (currentUser == null) {
      throw Exception('Firebase login session is required for private upload.');
    }
    if (sourcePhotos.length < 2 ||
        sourcePhotos.length > 6 ||
        sourcePhotos.any((source) => !source.isValid)) {
      throw ArgumentError.value(sourcePhotos, 'sourcePhotos');
    }
    await currentUser.getIdToken(true);
    final stableClientRequestId = clientRequestId?.trim().isNotEmpty == true
        ? clientRequestId!.trim()
        : createClientRequestId();
    final HttpsCallableResult<dynamic> result;
    try {
      result = await _functions
          .httpsCallable('beginAvatarGenerationFromOnboardingPhotos')
          .call(<String, dynamic>{
            ...buildUploadMetadata(clientRequestId: stableClientRequestId),
            'sourcePhotos': sourcePhotos
                .map((source) => source.toMap())
                .toList(),
            if (uid != null && uid.trim().isNotEmpty) 'uid': uid,
            'chatPartnerRealPhotoDisclosure': chatPartnerRealPhotoDisclosure,
          });
    } on FirebaseFunctionsException catch (error) {
      if (error.code == 'failed-precondition' &&
          (error.message ?? '').contains('avatar_already_approved')) {
        throw const AvatarAlreadyApprovedException();
      }
      if (error.code == 'failed-precondition' &&
          (error.message ?? '').contains('avatar_source_locked')) {
        throw const AvatarSourceLockedException();
      }
      rethrow;
    }
    final raw = result.data;
    final map = raw is Map
        ? raw.map((key, value) => MapEntry(key.toString(), value))
        : <String, dynamic>{};
    final parsed = AvatarSourcePhotoUploadResult.fromMap(map);
    if (parsed.jobId.isEmpty) {
      throw Exception('Private source-set response was incomplete.');
    }
    return parsed;
  }

}
