abstract interface class UserProfileReader {
  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId);
}
