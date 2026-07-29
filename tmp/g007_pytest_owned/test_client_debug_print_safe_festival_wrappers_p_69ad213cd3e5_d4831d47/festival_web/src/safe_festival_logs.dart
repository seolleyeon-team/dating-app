
void logFestival({
  required dynamic error,
  required dynamic user,
  required String token,
}) {
  debugPrint('errorType=${_safeErrorType(error)} uid=${_safeHashPrefix(user.uid)} token=${_safeHashPrefix(token)}');
  debugPrint('user=${PrivacyLogUtils.idFingerprint(user.uid)} token=${PrivacyLogUtils.idFingerprint(token)}');
}
