import 'package:flutter/foundation.dart';

import '../../../services/auth_service.dart';
import '../../../services/user_service.dart';

class KakaoLoginFirestoreBootstrap {
  KakaoLoginFirestoreBootstrap({
    required AuthService authService,
    required UserService userService,
  }) : _authService = authService,
       _userService = userService;

  final AuthService _authService;
  final UserService _userService;

  Future<bool> bootstrap({
    required String kakaoUserId,
    required String platform,
  }) async {
    final existedBeforeLogin = await _authService.kakaoUserExists(kakaoUserId);

    final firebaseAttached = await _authService.ensureFirebaseSessionForKakao(
      kakaoUserId,
    );
    if (!firebaseAttached) {
      throw Exception('Firebase 로그인 세션을 준비하지 못했습니다. 다시 시도해주세요.');
    }

    try {
      await _userService.setLastActivePlatform(
        kakaoUserId: kakaoUserId,
        platform: platform,
      );
    } catch (e, st) {
      debugPrint('[KAKAO] setLastActivePlatform skipped: $e');
      debugPrint(st.toString());
    }

    return existedBeforeLogin;
  }
}
