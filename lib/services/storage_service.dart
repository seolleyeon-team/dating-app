import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../constants/legal_texts.dart';
import 'adult_verification_result.dart';

class StorageService {
  static const String _userIdKey = 'user_id';

  /// Canonical appUserId cache (= `users/{docId}` document id).
  ///
  /// Historically this held the Kakao numeric ID; existing accounts keep that
  /// value as their appUserId forever, so the SAME pref key is reused for
  /// install compatibility. The value is a UX cache only — never proof of
  /// authentication (the Firebase session is the authority).
  static const String _appUserIdKey = 'kakao_user_id';
  static const String _pendingStudentEmailKey = 'pending_student_email';
  static const String _pendingStudentEmailRequestIdKey =
      'pending_student_email_request_id';
  static const String _isFirstLaunchKey = 'is_first_launch';
  static const String _hasSeenTutorialKey = 'has_seen_tutorial';
  static const String _studentEmailKeyPrefix = 'student_email_';
  static const String _studentVerifiedKeyPrefix = 'student_verified_';
  static const String _studentVerificationTokenKeyPrefix =
      'student_verification_token_';
  static const String _studentVerificationWelcomeKeyPrefix =
      'student_verification_welcome_';
  static const String _onboardingDraftKeyPrefix = 'onboarding_draft_';
  static const String _pendingFriendInviteTokenKey = 'pending_friend_invite';
  static const String _eventTeamSetupIdKeyPrefix = 'event_team_setup_id_';
  static const String _pendingLegalConsentsKey = 'pending_legal_consents';
  static const String _pendingAdultVerificationResultKey =
      'pending_adult_verification_result';
  static const String _pendingRejoinRestrictionNoticeKey =
      'pending_rejoin_restriction_notice';

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

  Future<void> saveAppUserId(String appUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_appUserIdKey, appUserId);
  }

  Future<String?> getAppUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_appUserIdKey);
  }

  Future<void> clearAppUserId() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_appUserIdKey);
  }

  /// Legacy name. Delegates to [saveAppUserId] (same pref key).
  Future<void> saveKakaoUserId(String kakaoUserId) =>
      saveAppUserId(kakaoUserId);

  /// Legacy name. Delegates to [getAppUserId] (same pref key).
  Future<String?> getKakaoUserId() => getAppUserId();

  /// Legacy name. Delegates to [clearAppUserId] (same pref key).
  Future<void> clearKakaoUserId() => clearAppUserId();

  // ---------------------------------------------------------------------------
  // Pre-auth pending Yonsei email (global keys — NO user namespace; primary
  // email login runs before any identity exists on the device).
  // ---------------------------------------------------------------------------

  Future<void> savePendingStudentEmail(String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingStudentEmailKey, email);
  }

  Future<String?> getPendingStudentEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_pendingStudentEmailKey);
  }

  Future<void> clearPendingStudentEmail() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingStudentEmailKey);
  }

  Future<void> savePendingStudentEmailRequestId(String requestId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingStudentEmailRequestIdKey, requestId);
  }

  Future<String?> getPendingStudentEmailRequestId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_pendingStudentEmailRequestIdKey);
  }

  Future<void> clearPendingStudentEmailRequestId() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingStudentEmailRequestIdKey);
  }

  Future<void> saveEventTeamSetupDraftId(
    String kakaoUserId,
    String teamSetupId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      '$_eventTeamSetupIdKeyPrefix$kakaoUserId',
      teamSetupId,
    );
  }

  Future<String?> getEventTeamSetupDraftId(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('$_eventTeamSetupIdKeyPrefix$kakaoUserId');
  }

  Future<void> clearEventTeamSetupDraftId(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('$_eventTeamSetupIdKeyPrefix$kakaoUserId');
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
    await prefs.remove('$_studentVerificationTokenKeyPrefix$kakaoUserId');
  }

  Future<void> saveStudentVerificationToken(
    String kakaoUserId,
    String token,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      '$_studentVerificationTokenKeyPrefix$kakaoUserId',
      token,
    );
  }

  Future<String?> getStudentVerificationToken(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('$_studentVerificationTokenKeyPrefix$kakaoUserId');
  }

  Future<void> clearStudentVerificationToken(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('$_studentVerificationTokenKeyPrefix$kakaoUserId');
  }

  Future<void> saveStudentVerificationWelcome(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(
      '$_studentVerificationWelcomeKeyPrefix$kakaoUserId',
      true,
    );
  }

  Future<bool> consumeStudentVerificationWelcome(String kakaoUserId) async {
    final prefs = await SharedPreferences.getInstance();
    final key = '$_studentVerificationWelcomeKeyPrefix$kakaoUserId';
    final shouldShow = prefs.getBool(key) == true;
    if (shouldShow) await prefs.remove(key);
    return shouldShow;
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

  Future<void> savePendingLegalConsents() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _pendingLegalConsentsKey,
      jsonEncode({
        'termsOfService': true,
        'privacyPolicy': true,
        'kakaoNamePhone': true,
        'ageOver20': true,
        'ageOver18': true,
        'agreedAtClientIso': DateTime.now().toUtc().toIso8601String(),
        'version': LegalTexts.version,
      }),
    );
  }

  Future<Map<String, dynamic>?> getPendingLegalConsents() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_pendingLegalConsentsKey);
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> clearPendingLegalConsents() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingLegalConsentsKey);
  }

  Future<void> savePendingAdultVerificationResult(
    AdultVerificationResult result,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _pendingAdultVerificationResultKey,
      jsonEncode(result.toJson()),
    );
  }

  Future<AdultVerificationResult?> getPendingAdultVerificationResult() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_pendingAdultVerificationResultKey);
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic>
          ? AdultVerificationResult.fromJson(decoded)
          : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> clearPendingAdultVerificationResult() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingAdultVerificationResultKey);
  }

  Future<void> savePendingRejoinRestrictionNotice() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_pendingRejoinRestrictionNoticeKey, true);
  }

  Future<bool> consumePendingRejoinRestrictionNotice() async {
    final prefs = await SharedPreferences.getInstance();
    final hasNotice =
        prefs.getBool(_pendingRejoinRestrictionNoticeKey) ?? false;
    if (hasNotice) {
      await prefs.remove(_pendingRejoinRestrictionNoticeKey);
    }
    return hasNotice;
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

  /// Clears local preferences scoped to an app user on logout.
  /// Keeps device-level flags such as first-launch / tutorial if desired by caller.
  Future<void> clearUserScopedSession(String appUserId) async {
    await clearStudentVerification(appUserId);
    await clearEventTeamSetupDraftId(appUserId);
    await clearOnboardingDraft(appUserId);
    await clearAppUserId();
    await clearUserId();
    await clearPendingFriendInviteToken();
    await clearPendingStudentEmail();
    await clearPendingStudentEmailRequestId();
  }
}
