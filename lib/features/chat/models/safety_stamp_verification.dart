enum SafetyStampVerificationFailure {
  bluetoothUnsupported,
  bluetoothPermissionDenied,
  bluetoothOff,
  locationServiceDisabled,
  locationPermissionDenied,
  locationUnavailable,
  partnerNotNearby,
  unknown,
}

class SafetyStampLocationSnapshot {
  const SafetyStampLocationSnapshot({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
    required this.capturedAt,
  });

  final double latitude;
  final double longitude;
  final double accuracyMeters;
  final DateTime capturedAt;

  Map<String, dynamic> toMap() {
    return {
      'latitude': latitude,
      'longitude': longitude,
      'accuracyMeters': accuracyMeters,
      'capturedAt': capturedAt.toIso8601String(),
    };
  }
}

class SafetyStampVerificationResult {
  const SafetyStampVerificationResult._({
    required this.isSuccess,
    required this.message,
    this.failure,
    this.rssi,
    this.location,
  });

  final bool isSuccess;
  final String message;
  final SafetyStampVerificationFailure? failure;
  final int? rssi;
  final SafetyStampLocationSnapshot? location;

  factory SafetyStampVerificationResult.success({
    required String message,
    required int rssi,
    required SafetyStampLocationSnapshot location,
  }) {
    return SafetyStampVerificationResult._(
      isSuccess: true,
      message: message,
      rssi: rssi,
      location: location,
    );
  }

  factory SafetyStampVerificationResult.failure({
    required SafetyStampVerificationFailure failure,
    required String message,
  }) {
    return SafetyStampVerificationResult._(
      isSuccess: false,
      message: message,
      failure: failure,
    );
  }

  Map<String, dynamic> toFirestoreMap({
    required String phase,
    required String verifierUserId,
  }) {
    return {
      'phase': phase,
      'verifierUserId': verifierUserId,
      'verifiedAt': DateTime.now().toIso8601String(),
      'rssi': rssi,
      'location': location?.toMap(),
    };
  }
}
