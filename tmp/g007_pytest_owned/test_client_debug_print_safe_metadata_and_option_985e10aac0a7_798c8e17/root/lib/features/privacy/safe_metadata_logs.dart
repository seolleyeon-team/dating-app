
void logMetadata({
  required Uri uri,
  required dynamic request,
  required dynamic response,
  required dynamic e,
  required Map<String, dynamic> userInfo,
}) {
  debugPrint('uri scheme=${uri.scheme} host=${uri.host} queryKeys=${uri.queryParameters.keys.join(',')}');
  debugPrint('http method=${request.method} status=${response.statusCode} url=${PrivacyLogUtils.pathFingerprint(uri.toString())}');
  debugPrint('hasErrorMessage=${e.message?.isNotEmpty ?? false}');
  debugPrint('hasNickname=${userInfo['nickname']?.toString().isNotEmpty ?? false}');
  // debugPrint('commented raw token=$token uid=$uid error=$error');
  /* print('example url=$url path=$path stack=$stackTrace'); */
}
