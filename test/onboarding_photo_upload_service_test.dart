import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/onboarding_photo_upload_service.dart';

/// P1-9 — bounded, responsive onboarding photo upload.
void main() {
  test(
    'the picker is bounded and the service re-encodes off the UI isolate',
    () {
      final screen = File(
        'lib/features/onboarding/screens/photo_upload_screen.dart',
      ).readAsStringSync();
      expect(
        screen,
        contains('maxWidth: OnboardingPhotoUploadService.maxPickDimension'),
      );
      expect(
        screen,
        contains('maxHeight: OnboardingPhotoUploadService.maxPickDimension'),
      );
      expect(
        screen,
        contains('imageQuality: OnboardingPhotoUploadService.pickImageQuality'),
      );
      expect(screen, isNot(contains('imageQuality: 88,')));

      final service = File(
        'lib/services/onboarding_photo_upload_service.dart',
      ).readAsStringSync();
      expect(service, contains('compute(encodeImageBase64ForUpload, bytes)'));
      expect(
        service,
        isNot(contains('getIdToken(true)')),
        reason: 'no forced token refresh per upload',
      );
      expect(service, contains('maxUploadBytes'));
      expect(OnboardingPhotoUploadService.maxPickDimension, 2048);
      expect(OnboardingPhotoUploadService.pickImageQuality, 88);
      expect(OnboardingPhotoUploadService.maxUploadBytes, 12 * 1024 * 1024);
    },
  );

  test('the isolate entry point encodes exactly the bytes it is given', () {
    final bytes = Uint8List.fromList(List<int>.generate(1024, (i) => i % 251));
    expect(encodeImageBase64ForUpload(bytes), base64Encode(bytes));
  });
}
