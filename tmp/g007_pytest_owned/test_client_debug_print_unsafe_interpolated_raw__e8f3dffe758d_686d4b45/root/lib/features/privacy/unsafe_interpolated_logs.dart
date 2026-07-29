
void logUnsafe({
  required String uid,
  required String email,
  required String token,
  required String url,
  required String path,
  required dynamic error,
  required Map<String, dynamic> userInfo,
}) {
  debugPrint('uid=$uid email=$email token=$token url=$url path=$path error=$error');
  debugPrint('nickname=${userInfo['nickname'] != null ? userInfo['nickname'] : 'none'}');
}
