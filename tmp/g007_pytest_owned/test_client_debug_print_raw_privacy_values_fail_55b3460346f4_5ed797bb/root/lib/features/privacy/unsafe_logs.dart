
void logRaw({
  required String uid,
  required String email,
  required String token,
  required String sourcePhotoUrl,
  required String authorIdStr,
  required String currentUserId,
  required Object e,
  required StackTrace st,
}) {
  debugPrint('uid=$uid email=$email token=$token source=$sourcePhotoUrl error=$e stack=$st');
  debugPrint('author=$authorIdStr current=$currentUserId');
  // print('comment example $token $error');
  print('[API Request] ${request['url']}');
  print('[API Error] $error');
}
