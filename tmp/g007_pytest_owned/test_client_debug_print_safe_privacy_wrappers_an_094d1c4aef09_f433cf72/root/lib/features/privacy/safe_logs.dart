
void logSafe({
  required String uid,
  required String token,
  required Object e,
  required dynamic storagePath,
}) {
  debugPrint('token/email labels only');
  debugPrint('uid=${PrivacyLogUtils.idFingerprint(uid)}');
  debugPrint('path=${PrivacyLogUtils.pathFingerprint(storagePath)}');
  debugPrint('error=${PrivacyLogUtils.errorSummary(e)} code=${e.code} type=${e.runtimeType}');
  debugPrint('hasToken=${token != null && token.isNotEmpty}');
  debugPrint('legacy=${_logHashPrefix(uid)} ${_redactStoragePath(storagePath)}');
  print('constant token/email labels only');
  print('hasToken=${token != null && token.isNotEmpty} error=${PrivacyLogUtils.errorSummary(e)}');
}
