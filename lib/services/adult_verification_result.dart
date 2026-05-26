enum AdultVerificationStatus {
  notStarted,
  inProgress,
  pendingKakaoLogin,
  pendingServerVerification,
  verified,
  failed,
  cancelled,
  underAge,
}

class AdultVerificationResult {
  const AdultVerificationResult({
    required this.status,
    this.sessionId,
    this.identityVerificationTxId,
    this.provider,
    this.verifiedAt,
    this.expiresAt,
    this.message,
    this.providerPayload = const <String, dynamic>{},
  });

  final AdultVerificationStatus status;
  final String? sessionId;
  final String? identityVerificationTxId;
  final String? provider;
  final DateTime? verifiedAt;
  final DateTime? expiresAt;
  final String? message;
  final Map<String, dynamic> providerPayload;

  bool get isVerified => status == AdultVerificationStatus.verified;
  bool get isPendingKakaoLogin =>
      status == AdultVerificationStatus.pendingKakaoLogin;
  bool get isPendingServerVerification =>
      status == AdultVerificationStatus.pendingServerVerification;
  bool get isExpired =>
      expiresAt != null && DateTime.now().toUtc().isAfter(expiresAt!);
  bool get canProceedToKakao => isPendingKakaoLogin && !isExpired;

  static const notStarted = AdultVerificationResult(
    status: AdultVerificationStatus.notStarted,
  );

  AdultVerificationResult copyWith({
    AdultVerificationStatus? status,
    String? sessionId,
    String? identityVerificationTxId,
    String? provider,
    DateTime? verifiedAt,
    DateTime? expiresAt,
    String? message,
    Map<String, dynamic>? providerPayload,
  }) {
    return AdultVerificationResult(
      status: status ?? this.status,
      sessionId: sessionId ?? this.sessionId,
      identityVerificationTxId:
          identityVerificationTxId ?? this.identityVerificationTxId,
      provider: provider ?? this.provider,
      verifiedAt: verifiedAt ?? this.verifiedAt,
      expiresAt: expiresAt ?? this.expiresAt,
      message: message ?? this.message,
      providerPayload: providerPayload ?? this.providerPayload,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'status': status.name,
      if (sessionId != null) 'sessionId': sessionId,
      if (identityVerificationTxId != null)
        'identityVerificationTxId': identityVerificationTxId,
      if (provider != null) 'provider': provider,
      if (verifiedAt != null) 'verifiedAtIso': verifiedAt!.toIso8601String(),
      if (expiresAt != null) 'expiresAtIso': expiresAt!.toIso8601String(),
      if (message != null) 'message': message,
      'providerPayload': providerPayload,
    };
  }

  static AdultVerificationResult fromJson(Map<String, dynamic> json) {
    final rawStatus = json['status']?.toString();
    final status = AdultVerificationStatus.values.firstWhere(
      (value) => value.name == rawStatus,
      orElse: () => AdultVerificationStatus.notStarted,
    );
    final rawVerifiedAt = json['verifiedAtIso']?.toString();
    final rawExpiresAt = json['expiresAtIso']?.toString();

    return AdultVerificationResult(
      status: status,
      sessionId: json['sessionId']?.toString(),
      identityVerificationTxId: json['identityVerificationTxId']?.toString(),
      provider: json['provider']?.toString(),
      verifiedAt: rawVerifiedAt == null
          ? null
          : DateTime.tryParse(rawVerifiedAt),
      expiresAt: rawExpiresAt == null ? null : DateTime.tryParse(rawExpiresAt),
      message: json['message']?.toString(),
      providerPayload: json['providerPayload'] is Map
          ? Map<String, dynamic>.from(json['providerPayload'] as Map)
          : const <String, dynamic>{},
    );
  }
}
