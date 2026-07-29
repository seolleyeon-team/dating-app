
void logUnsafe(dynamic error, String uid, String path) {
  debugPrint('error=${_safeErrorType(error)}');
  debugPrint('uid=${_safeHashPrefix(uid)}');
  debugPrint('uid=${_logHashPrefix(uid)}');
  debugPrint('path=${_redactStoragePath(path)}');
}
