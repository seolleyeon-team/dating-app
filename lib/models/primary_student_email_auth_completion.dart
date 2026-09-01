/// Server-confirmed result of `completePrimaryStudentEmailAuth`.
///
/// `appUserId` equals the Firebase runtime UID of the canonical session
/// (contract §1). The Kakao identity NEVER appears in this payload.
class PrimaryStudentEmailAuthCompletion {
  const PrimaryStudentEmailAuthCompletion({
    required this.appUserId,
    required this.normalizedEmail,
    required this.isNewUser,
    required this.initialSetupComplete,
    required this.adultVerified,
    required this.recommendationPrivacyReady,
  });

  final String appUserId;
  final String normalizedEmail;
  final bool isNewUser;
  final bool initialSetupComplete;
  final bool adultVerified;
  final bool recommendationPrivacyReady;

  /// Strictly validates the callable response map. Throws [StateError] with a
  /// stable code when the payload does not match the contract; never logs or
  /// includes the raw email/token values in the error.
  factory PrimaryStudentEmailAuthCompletion.fromMap(Map<String, dynamic> map) {
    final appUserId = map['appUserId']?.toString().trim() ?? '';
    final email = map['email']?.toString().trim().toLowerCase() ?? '';
    if (appUserId.isEmpty) {
      throw StateError('primary_email_auth_response_missing_app_user_id');
    }
    if (!email.endsWith('@yonsei.ac.kr')) {
      throw StateError('primary_email_auth_response_invalid_email_domain');
    }
    return PrimaryStudentEmailAuthCompletion(
      appUserId: appUserId,
      normalizedEmail: email,
      isNewUser: map['isNewUser'] == true,
      initialSetupComplete: map['initialSetupComplete'] == true,
      adultVerified: map['adultVerified'] == true,
      recommendationPrivacyReady: map['recommendationPrivacyReady'] == true,
    );
  }
}
