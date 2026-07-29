
void logFestival({
  required dynamic error,
  required dynamic user,
  required String token,
}) {
  debugPrint('user=${PrivacyLogUtils.idFingerprint(user.uid)} token=${PrivacyLogUtils.idFingerprint(token)}');
}
