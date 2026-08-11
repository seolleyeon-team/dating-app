import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/foundation.dart';

import '../../../services/auth_service.dart';
import '../../../services/firebase_session_failure.dart';
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
    // users/{id} get/update requires request.auth. Attach the Kakao-bridged
    // custom-token session first; reading the doc beforehand yields
    // permission-denied on the login screen.
    final firebaseAttached = await _authService.ensureFirebaseSessionForKakao(
      kakaoUserId,
    );
    if (!firebaseAttached) {
      throw _authService.lastFirebaseSessionFailure ??
          const FirebaseSessionFailure(
            reason: FirebaseSessionFailureReason.callableFailed,
          );
    }

    final existedBeforeLogin = await _authService.kakaoUserExists(kakaoUserId);

    try {
      await _userService.setLastActivePlatform(
        kakaoUserId: kakaoUserId,
        platform: platform,
      );
    } catch (e) {
      debugPrint(
        '[KAKAO] setLastActivePlatform skipped: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }

    return existedBeforeLogin;
  }
}
