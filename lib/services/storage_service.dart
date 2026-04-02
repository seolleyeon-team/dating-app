import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class StorageService {
  static const String _userIdKey = 'user_id';
  static const String _kakaoUserIdKey = 'kakao_user_id';
  static const String _isFirstLaunchKey = 'is_first_launch';
  static const String _hasSeenTutorialKey = 'has_seen_tutorial';
  static const String _studentEmailKeyPrefix = 'student_email_';
  static const String _studentVerifiedKeyPrefix = 'student_verified_';
  static const String _onboardingDraftKeyPrefix = 'onboarding_draft_';
  static const String _pendingFriendInviteTokenKey = 'pending_friend_invite';

  Future<void> saveUserId(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userIdKey, userId);
  }

  Future<String?> getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_userIdKey);
  }

  Future<void> clearUserId() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_userIdKey);
  }

  Future<void> saveKakaoUserId(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kakaoUserIdKey, kakaoUserId);
  }

  Future<String?> getKakaoUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kakaoUserIdKey);
  }

  Future<void> clearKakaoUserId() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kakaoUserIdKey);
  }

  Future<bool> isFirstLaunch() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_isFirstLaunchKey) ?? true;
  }

  Future<void> setFirstLaunchComplete() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_isFirstLaunchKey, false);
  }

  Future<bool> hasSeenTutorial() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_hasSeenTutorialKey) ?? false;
  }

  Future<void> setTutorialSeen() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_hasSeenTutorialKey, true);
  }

  Future<void> saveStudentEmail(String kakaoUserId, String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_studentEmailKeyPrefix$kakaoUserId', email);
  }

  Future<String?> getStudentEmail(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('$_studentEmailKeyPrefix$kakaoUserId');
  }

  Future<void> setStudentVerified(String kakaoUserId, bool isVerified) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('$_studentVerifiedKeyPrefix$kakaoUserId', isVerified);
  }

  Future<bool> isStudentVerified(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('$_studentVerifiedKeyPrefix$kakaoUserId') ?? false;
  }

  Future<void> clearStudentVerification(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('$_studentEmailKeyPrefix$kakaoUserId');
    await prefs.remove('$_studentVerifiedKeyPrefix$kakaoUserId');
  }

  // ---------------------------------------------------------------------------
  // Onboarding draft (step-by-step 입력값 임시 저장)
  // ---------------------------------------------------------------------------

  /// jsonEncode가 처리 가능한 형태로 변환
  /// - Set -> List
  /// - Map/List 내부도 재귀 변환
  dynamic _jsonFriendly(dynamic value) {
    if (value == null) return null;
    if (value is num || value is bool || value is String) return value;
    if (value is Set) return value.map(_jsonFriendly).toList();
    if (value is List) return value.map(_jsonFriendly).toList();
    if (value is Map) {
      final out = <String, dynamic>{};
      value.forEach((k, v) {
        out[k.toString()] = _jsonFriendly(v);
      });
      return out;
    }
    // Enums 등은 문자열로 저장
    return value.toString();
  }

  Future<Map<String, dynamic>> getOnboardingDraft(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('$_onboardingDraftKeyPrefix$kakaoUserId');
    if (raw == null || raw.trim().isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : {};
    } catch (_) {
      return {};
    }
  }

  Future<void> mergeOnboardingDraft(
    String kakaoUserId,
    Map<String, dynamic> partial,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final current = await getOnboardingDraft(kakaoUserId);
    current.addAll(
      _jsonFriendly(partial) as Map<String, dynamic>,
    ); // shallow merge
    await prefs.setString(
      '$_onboardingDraftKeyPrefix$kakaoUserId',
      jsonEncode(current),
    );
  }

  Future<void> clearOnboardingDraft(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('$_onboardingDraftKeyPrefix$kakaoUserId');
  }

  Future<void> savePendingFriendInviteToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingFriendInviteTokenKey, token);
  }

  Future<String?> getPendingFriendInviteToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_pendingFriendInviteTokenKey);
  }

  Future<void> clearPendingFriendInviteToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingFriendInviteTokenKey);
  }

  Future<void> clearAll() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  }
}
