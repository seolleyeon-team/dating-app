import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;
import 'package:cloud_functions/cloud_functions.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:uuid/uuid.dart';

import '../models/user_model.dart';
import '../router/route_names.dart';
import '../utils/phone_hash_utils.dart';
import 'storage_service.dart';
import 'user_service.dart';

class AuthService {
  final _uuid = const Uuid();
  final _userService = UserService();
  final _storageService = StorageService();
  final FirebaseAuth _firebaseAuth = FirebaseAuth.instance;
  final FirebaseFunctions _functions =
      FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  Future<bool> _hasMatchingFirebaseSession(String kakaoUserId) async {
    final currentUser = _firebaseAuth.currentUser;
    if (currentUser == null) {
      return false;
    }

    try {
      final tokenResult = await currentUser.getIdTokenResult(true);
      final claimedKakaoUserId =
          tokenResult.claims?['kakaoUserId']?.toString().trim() ?? '';
      final matches =
          currentUser.uid == kakaoUserId || claimedKakaoUserId == kakaoUserId;
      if (!matches) {
        debugPrint(
          '[Auth] Firebase session mismatch: '
          'uid=${currentUser.uid} '
          'claimKakaoUserId=$claimedKakaoUserId '
          'expected=$kakaoUserId',
        );
      }
      return matches;
    } catch (e, st) {
      debugPrint('[Auth] Firebase session inspection failed: $e');
      debugPrint(st.toString());
      return false;
    }
  }

  Future<void> _signOutFirebaseIfMismatched(String kakaoUserId) async {
    final currentUser = _firebaseAuth.currentUser;
    if (currentUser == null) {
      return;
    }

    final matches = await _hasMatchingFirebaseSession(kakaoUserId);
    if (matches) {
      return;
    }

    await _firebaseAuth.signOut();
    debugPrint('[Auth] Signed out mismatched Firebase session');
  }

  /// ✅ 카카오 로그인
  /// - Web: 카카오 계정 로그인
  /// - Mobile(iOS/Android): 카카오톡 앱 우선 -> 실패/미설치 시 계정 로그인 fallback
  /// 반환: userInfo(Map) = {id, nickname, profileImageUrl, email}
  Future<Map<String, dynamic>> loginWithKakao() async {
    _ensureKakaoInit();

    try {
      if (kIsWeb) {
        // Web: JS SDK 기반 카카오 계정 로그인
        await UserApi.instance.loginWithKakaoAccount();
      } else {
        // Mobile: 카카오톡 설치되어 있으면 카톡 앱 로그인 우선, 실패/미설치/크래시 시 웹 로그인
        bool tryKakaoTalk = false;
        try {
          final installed = await isKakaoTalkInstalled();
          debugPrint('[Kakao] isKakaoTalkInstalled=$installed');
          tryKakaoTalk = installed;
        } catch (e) {
          debugPrint('[Kakao] isKakaoTalkInstalled error (fallback to web): $e');
        }

        if (tryKakaoTalk) {
          try {
            await UserApi.instance.loginWithKakaoTalk();
          } on KakaoException catch (e) {
            final detail = e.message ?? e.toString();
            debugPrint('[Kakao] loginWithKakaoTalk failed: $detail');
            if (detail.contains('bundleId') || detail.contains('IOS bundleId')) {
              rethrow;
            }
            debugPrint('[Kakao] fallback to loginWithKakaoAccount');
            await UserApi.instance.loginWithKakaoAccount();
          } catch (e, st) {
            debugPrint('[Kakao] loginWithKakaoTalk error (fallback to web): $e');
            debugPrint(st.toString());
            final detail = e.toString();
            if (detail.contains('bundleId') || detail.contains('IOS bundleId')) {
              rethrow;
            }
            await UserApi.instance.loginWithKakaoAccount();
          }
        } else {
          await UserApi.instance.loginWithKakaoAccount();
        }
      }

      // 사용자 정보
      final user = await UserApi.instance.me();
      final kakaoUserId = user.id.toString();

      if (kakaoUserId.isEmpty) {
        throw Exception('카카오 사용자 ID를 가져오지 못했습니다.');
      }

      final phoneNumber = user.kakaoAccount?.phoneNumber;

      // 전화번호가 있으면 비동기로 phoneHash 저장 (실패해도 로그인 막지 않음)
      if (phoneNumber != null && phoneNumber.trim().isNotEmpty) {
        _savePhoneHashInBackground(kakaoUserId, phoneNumber);
      }

      return {
        'id': kakaoUserId,
        'nickname': user.kakaoAccount?.profile?.nickname,
        'profileImageUrl': user.kakaoAccount?.profile?.profileImageUrl,
        'email': user.kakaoAccount?.email,
        'phoneNumber': phoneNumber,
      };
    } on KakaoException catch (e) {
      final detail = e.message ?? e.toString();
      throw Exception('카카오 로그인 실패: $detail');
    } catch (e) {
      throw Exception('로그인 실패: $e');
    }
  }

  static bool _kakaoInited = false;

  void _ensureKakaoInit() {
    if (_kakaoInited) return;

    const kakaoNativeAppKey = 'cb08e2aea50a58b7d0c5e610e0c5a644';
    const kakaoJavaScriptKey = 'bff1db6356fcd7aaf5dc466080359ce0';

    KakaoSdk.init(
      nativeAppKey: kIsWeb ? null : kakaoNativeAppKey,
      javaScriptAppKey: kIsWeb ? kakaoJavaScriptKey : null,
    );

    _kakaoInited = true;
    debugPrint('[Kakao] KakaoSdk.init ensured (kIsWeb=$kIsWeb)');
  }

  /// 카카오 계정(웹) 로그인만 수행. iOS 번들 ID 오류 시 사용자가 "웹으로 로그인" 선택할 때 사용.
  Future<Map<String, dynamic>> loginWithKakaoAccountOnly() async {
    _ensureKakaoInit();
    await UserApi.instance.loginWithKakaoAccount();
    final user = await UserApi.instance.me();
    final kakaoUserId = user.id.toString();
    if (kakaoUserId.isEmpty) {
      throw Exception('카카오 사용자 ID를 가져오지 못했습니다.');
    }
    final phoneNumber = user.kakaoAccount?.phoneNumber;
    if (phoneNumber != null && phoneNumber.trim().isNotEmpty) {
      _savePhoneHashInBackground(kakaoUserId, phoneNumber);
    }
    return {
      'id': kakaoUserId,
      'nickname': user.kakaoAccount?.profile?.nickname,
      'profileImageUrl': user.kakaoAccount?.profile?.profileImageUrl,
      'email': user.kakaoAccount?.email,
      'phoneNumber': phoneNumber,
    };
  }

  /// 전화번호 해시를 서버에 저장 (fire-and-forget)
  void _savePhoneHashInBackground(String kakaoUserId, String rawPhone) {
    Future(() async {
      try {
        final phoneHash = PhoneHashUtils.normalizeAndHash(rawPhone);
        if (phoneHash == null) {
          debugPrint('[Auth] 전화번호 정규화 실패: $rawPhone');
          return;
        }
        final callable = _functions.httpsCallable('saveUserPhoneHash');
        await callable.call(<String, dynamic>{
          'phoneHash': phoneHash,
          'phoneSource': 'kakao',
        });
        debugPrint('[Auth] phoneHash 저장 완료');
      } catch (e) {
        debugPrint('[Auth] phoneHash 저장 실패 (무시): $e');
      }
    });
  }

  // -------------------------
  // 이하 기존 기능 (너 코드 유지)
  // -------------------------

  Future<bool> kakaoUserExists(String kakaoUserId) async {
    return await _userService.existsKakaoUser(kakaoUserId);
  }

  Future<bool> isInitialSetupComplete(String kakaoUserId) async {
    return await _userService.isInitialSetupComplete(kakaoUserId);
  }

  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    return await _userService.getUserProfile(kakaoUserId);
  }

  /// 연세 인증은 됐지만 초기설정이 미완료일 때, 이어서 채울 다음 단계 라우트 (예: 3단계까지 했으면 4단계)
  Future<String?> getOnboardingNextRoute(String kakaoUserId) async {
    final profile = await _userService.getUserProfile(kakaoUserId);
    final onboarding = profile?['onboarding'];
    if (onboarding is! Map || onboarding.isEmpty) {
      return RouteNames.onboardingBasicInfo;
    }
    if (_isEmpty(onboarding['nickname']) && _isEmpty(onboarding['gender'])) {
      return RouteNames.onboardingBasicInfo;
    }
    final interests = onboarding['interests'];
    if (interests == null || (interests is List && interests.isEmpty)) {
      return RouteNames.onboardingInterestsSelection;
    }
    final lifestyle = onboarding['lifestyle'];
    if (lifestyle == null || (lifestyle is Map && lifestyle.isEmpty)) {
      return RouteNames.onboardingLifestyle;
    }
    if (_isEmpty(onboarding['major'])) {
      return RouteNames.onboardingMajor;
    }
    final photoUrls = onboarding['photoUrls'];
    if (photoUrls == null || (photoUrls is List && photoUrls.isEmpty)) {
      return RouteNames.onboardingPhoto;
    }
    if (_isEmpty(onboarding['selfIntroduction'])) {
      return RouteNames.onboardingSelfIntro;
    }
    final profileQa = onboarding['profileQa'];
    if (profileQa == null || (profileQa is List && profileQa.isEmpty)) {
      return RouteNames.onboardingProfileQa;
    }
    final keywords = onboarding['keywords'];
    if (keywords == null || (keywords is List && keywords.isEmpty)) {
      return RouteNames.onboardingKeywords;
    }
    final idealType = profile?['idealType'];
    if (idealType is! Map || idealType.isEmpty) {
      return RouteNames.onboardingIdealType;
    }
    if (idealType['preferredLifestyles'] == null) {
      return RouteNames.onboardingIdealLifestyle;
    }
    return null;
  }

  static bool _isEmpty(dynamic v) {
    if (v == null) return true;
    if (v is String) return v.trim().isEmpty;
    return false;
  }

  Future<bool> hasSeenTutorial(String kakaoUserId) async {
    return await _userService.hasSeenTutorial(kakaoUserId);
  }

  Future<void> setTutorialSeen(String kakaoUserId) async {
    await _userService.setTutorialSeen(kakaoUserId);
  }

  Future<bool> isStudentVerified(String kakaoUserId) async {
    return await _userService.isStudentVerified(kakaoUserId);
  }

  Future<String?> getStudentEmail(String kakaoUserId) async {
    return await _userService.getStudentEmail(kakaoUserId);
  }

  Future<void> setStudentVerified({
    required String kakaoUserId,
    required String studentEmail,
  }) async {
    await _userService.setStudentVerification(
      kakaoUserId: kakaoUserId,
      studentEmail: studentEmail,
    );
  }

  Future<void> sendStudentEmailLink({
    required String email,
    required String continueUrl,
  }) async {
    final acs = ActionCodeSettings(
      url: continueUrl,
      handleCodeInApp: true,
      iOSBundleId: 'com.yonsei.dating',
      androidPackageName: 'com.yonsei.dating', // TODO: 안드로이드 패키지명으로 바꿔
      androidInstallApp: true,
      androidMinimumVersion: '21',
    );

    await _firebaseAuth.sendSignInLinkToEmail(
      email: email,
      actionCodeSettings: acs,
    );
  }

  bool isSignInWithEmailLink(String link) {
    return _firebaseAuth.isSignInWithEmailLink(link);
  }

  Future<void> signInWithEmailLink({
    required String email,
    required String emailLink,
  }) async {
    await _firebaseAuth.signInWithEmailLink(email: email, emailLink: emailLink);
  }

  Future<bool> ensureFirebaseSessionForKakao(String kakaoUserId) async {
    try {
      if (await _hasMatchingFirebaseSession(kakaoUserId)) {
        debugPrint('[Auth] Firebase session already attached to $kakaoUserId');
        return true;
      }

      await _signOutFirebaseIfMismatched(kakaoUserId);

      final kakaoToken = await TokenManagerProvider.instance.manager.getToken();
      final accessToken = kakaoToken?.accessToken.trim() ?? '';

      if (accessToken.isEmpty) {
        debugPrint('[Auth] No Kakao access token available for Firebase auth bridge');
        return false;
      }

      await UserApi.instance.accessTokenInfo();

      final callable = _functions.httpsCallable('createFirebaseCustomToken');
      final result = await callable.call(<String, dynamic>{
        'accessToken': accessToken,
      });
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final customToken = data['customToken']?.toString() ?? '';
      if (customToken.isEmpty) {
        debugPrint('[Auth] Firebase custom token response was empty');
        return false;
      }

      final credential = await _firebaseAuth.signInWithCustomToken(customToken);
      await credential.user?.getIdToken(true);
      debugPrint('[Auth] Firebase custom auth attached to $kakaoUserId');
      return true;
    } on FirebaseFunctionsException catch (e, st) {
      debugPrint(
        '[Auth] ensureFirebaseSessionForKakao functions error: '
        'code=${e.code} message=${e.message} details=${e.details}',
      );
      debugPrint(st.toString());
      return false;
    } catch (e, st) {
      debugPrint('[Auth] ensureFirebaseSessionForKakao error: $e');
      debugPrint(st.toString());
      return false;
    }
  }

  Future<bool> ensureFirebaseSessionForVerifiedUser(String kakaoUserId) async {
    try {
      if (await _hasMatchingFirebaseSession(kakaoUserId)) {
        debugPrint(
          '[Auth] Existing Firebase session is available for verified user '
          '(kakaoUserId=$kakaoUserId)',
        );
        return true;
      }
    } catch (e) {
      debugPrint('[Auth] Existing Firebase session refresh failed: $e');
    }

    await _signOutFirebaseIfMismatched(kakaoUserId);

    final verificationToken = await _storageService.getStudentVerificationToken(
      kakaoUserId,
    );
    final savedEmail = await _storageService.getStudentEmail(kakaoUserId);
    final normalizedEmail = savedEmail?.trim().toLowerCase() ?? '';

    if (verificationToken != null &&
        verificationToken.trim().isNotEmpty &&
        normalizedEmail.isNotEmpty &&
        normalizedEmail.endsWith('@yonsei.ac.kr')) {
      try {
        final callable = _functions.httpsCallable(
          'createFirebaseCustomTokenFromEmailLinkToken',
        );
        final result = await callable.call(<String, dynamic>{
          'verificationToken': verificationToken.trim(),
          'studentEmail': normalizedEmail,
          'kakaoUserId': kakaoUserId,
        });
        final data = Map<String, dynamic>.from(
          (result.data as Map?)?.cast<String, dynamic>() ?? const {},
        );
        final customToken = data['customToken']?.toString() ?? '';
        if (customToken.isNotEmpty) {
          final credential = await _firebaseAuth.signInWithCustomToken(
            customToken,
          );
          await credential.user?.getIdToken(true);
          debugPrint(
            '[Auth] Firebase session restored from student verification token '
            'for $kakaoUserId',
          );
          return true;
        }
        debugPrint('[Auth] Email-link token bridge returned empty custom token');
      } on FirebaseFunctionsException catch (e, st) {
        debugPrint(
          '[Auth] ensureFirebaseSessionForVerifiedUser functions error: '
          'code=${e.code} message=${e.message} details=${e.details}',
        );
        debugPrint(st.toString());
      } catch (e, st) {
        debugPrint('[Auth] ensureFirebaseSessionForVerifiedUser error: $e');
        debugPrint(st.toString());
      }
    } else {
      debugPrint('[Auth] No stored verified email-link token bridge is available');
    }

    return await ensureFirebaseSessionForKakao(kakaoUserId);
  }

  Future<void> signOutAll() async {
    try {
      await _firebaseAuth.signOut();
    } catch (e, st) {
      debugPrint('[Auth] Firebase signOut failed: $e');
      debugPrint(st.toString());
    }

    try {
      await UserApi.instance.logout();
    } catch (e, st) {
      debugPrint('[Auth] Kakao logout failed: $e');
      debugPrint(st.toString());
    }
  }

  /// Firebase Auth 세션이 없을 때 Cloud Functions에서 카카오로 본인 확인할 때 사용
  Future<String?> getKakaoAccessTokenForFunctions() async {
    try {
      final kakaoToken = await TokenManagerProvider.instance.manager.getToken();
      final accessToken = kakaoToken?.accessToken.trim() ?? '';
      if (accessToken.isEmpty) {
        return null;
      }

      try {
        await UserApi.instance.accessTokenInfo();
        return accessToken;
      } catch (e) {
        debugPrint('[Auth] Kakao access token is not usable anymore: $e');
        // 만료·폐기 토큰이 로컬에 남아 있으면 이후 호출이 계속 실패하므로 세션 정리
        final msg = e.toString();
        if (msg.contains('-401') || msg.contains('does not exist')) {
          try {
            await UserApi.instance.logout();
            debugPrint('[Auth] Kakao logout after invalid access token');
          } catch (logoutErr) {
            debugPrint('[Auth] Kakao logout after invalid token failed: $logoutErr');
          }
        }
        return null;
      }
    } catch (e, st) {
      debugPrint('[Auth] getKakaoAccessTokenForFunctions: $e');
      debugPrint('$st');
      return null;
    }
  }

  Future<UserModel?> signUp({
    required String phoneNumber,
    required String verificationCode,
    String? kakaoToken,
  }) async {
    try {
      final user = UserModel(
        id: _uuid.v4(),
        phoneNumber: phoneNumber,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
      );

      await Future.delayed(const Duration(seconds: 1));
      return user;
    } catch (e) {
      throw Exception('Sign up failed: $e');
    }
  }

  Future<bool> verifyStudent({
    required String userId,
    required String portalId,
    required String portalPassword,
  }) async {
    try {
      await Future.delayed(const Duration(seconds: 1));
      return true;
    } catch (e) {
      throw Exception('Student verification failed: $e');
    }
  }

  Future<UserModel?> getUser(String userId) async {
    try {
      await Future.delayed(const Duration(milliseconds: 500));
      return null;
    } catch (e) {
      throw Exception('Get user failed: $e');
    }
  }

  Future<void> updateUser(UserModel user) async {
    try {
      await Future.delayed(const Duration(milliseconds: 500));
    } catch (e) {
      throw Exception('Update user failed: $e');
    }
  }
}
