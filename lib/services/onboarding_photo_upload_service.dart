import 'dart:convert';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

import 'onboarding_photo_source_ref.dart';

/// P1-9: base64 of a multi-megabyte frame on the UI isolate stalls the
/// screen for hundreds of milliseconds. Runs through [compute] (a background
/// isolate on mobile/desktop; synchronous on web where isolates are absent).
String encodeImageBase64ForUpload(Uint8List bytes) => base64Encode(bytes);

class OnboardingPhotoUploadResult {
  const OnboardingPhotoUploadResult({
    required this.photoUrl,
    required this.slotIndex,
    this.sourceRef,
  });

  final String photoUrl;
  final int? slotIndex;
  final OnboardingPhotoSourceRef? sourceRef;

  factory OnboardingPhotoUploadResult.fromMap(Map<String, dynamic> data) {
    final sourceRef = OnboardingPhotoSourceRef.tryParse(data);
    return OnboardingPhotoUploadResult(
      photoUrl: data['photoUrl']?.toString().trim() ?? '',
      slotIndex: int.tryParse(data['slotIndex']?.toString() ?? ''),
      sourceRef: sourceRef,
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

  /// P1-9: bounds applied when the gallery frame is picked. The server
  /// re-validates and re-encodes (longest side 2048, JPEG 88, metadata
  /// stripped); picking at the same bound keeps the base64 callable payload
  /// small and the UI responsive without a second quality loss.
  static const int maxPickDimension = 2048;
  static const int pickImageQuality = 88;

  /// Hard client-side ceiling, mirrors the callable's MAX_IMAGE_BYTES.
  static const int maxUploadBytes = 12 * 1024 * 1024;

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

    // P1-9: no forced ID-token refresh here. The Functions SDK attaches a
    // valid token itself and refreshes only when it has expired; forcing a
    // refresh on every upload added a network round trip per photo.
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      throw Exception('Image file is empty.');
    }
    if (bytes.length > maxUploadBytes) {
      throw Exception('Image file is too large.');
    }

    final imageBase64 = await compute(encodeImageBase64ForUpload, bytes);
    final result = await _functions.httpsCallable('uploadOnboardingPhoto').call(
      <String, dynamic>{
        'imageBase64': imageBase64,
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
