import 'dart:convert';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:image_picker/image_picker.dart';

class OnboardingPhotoUploadResult {
  const OnboardingPhotoUploadResult({
    required this.photoUrl,
    required this.slotIndex,
  });

  final String photoUrl;
  final int? slotIndex;

  factory OnboardingPhotoUploadResult.fromMap(Map<String, dynamic> data) {
    return OnboardingPhotoUploadResult(
      photoUrl: data['photoUrl']?.toString().trim() ?? '',
      slotIndex: int.tryParse(data['slotIndex']?.toString() ?? ''),
    );
  }
}

/// Uploads regular onboarding profile photos without starting avatar
/// generation. The callable owns the Storage write and returns a display URL.
class OnboardingPhotoUploadService {
  OnboardingPhotoUploadService({
    FirebaseFunctions? functions,
    FirebaseAuth? auth,
  }) : _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
       _auth = auth ?? FirebaseAuth.instance;

  final FirebaseFunctions _functions;
  final FirebaseAuth _auth;

  Future<OnboardingPhotoUploadResult> uploadPickedImage({
    required XFile file,
    required int slotIndex,
    required String uid,
  }) async {
    final currentUser = _auth.currentUser;
    if (currentUser == null) {
      throw Exception('Firebase login session is required for photo upload.');
    }

    await currentUser.getIdToken(true);
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      throw Exception('Image file is empty.');
    }

    final result = await _functions.httpsCallable('uploadOnboardingPhoto').call(
      <String, dynamic>{
        'imageBase64': base64Encode(bytes),
        'slotIndex': slotIndex,
        'uid': uid,
      },
    );

    final raw = result.data;
    final map = raw is Map
        ? raw.map((key, value) => MapEntry(key.toString(), value))
        : <String, dynamic>{};
    final parsed = OnboardingPhotoUploadResult.fromMap(map);
    if (parsed.photoUrl.isEmpty) {
      throw Exception('Onboarding photo upload response was incomplete.');
    }
    return parsed;
  }
}
