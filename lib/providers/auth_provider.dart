import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:app_links/app_links.dart';

import '../models/user_model.dart';
import '../services/auth_service.dart';
import '../services/friend_invite_service.dart';
import '../services/navigation_service.dart';
import '../services/storage_service.dart';
import '../services/push_notification_service.dart';
import '../router/route_names.dart';
import '../shared/layouts/main_scaffold_args.dart';

class AuthProvider with ChangeNotifier {
  final AuthService _authService = AuthService();
  final StorageService _storageService = StorageService();
  final FriendInviteService _friendInviteService = FriendInviteService();

  // ✅ 앱 초기화 완료 여부 (router에서 splash 고정에 사용)
  bool _isInitialized = false;
  bool get isInitialized => _isInitialized;

  // ✅ 딥링크 수신(app_links)
  final AppLinks _appLinks = AppLinks();
  StreamSubscription<Uri>? _linkSub;
  bool _emailLinkHandling = false; // 중복 처리 방지

  UserModel? _currentUser;
  bool _isLoading = false;
  bool _isAuthenticated = false;
  String? _kakaoUserId;
  Map<String, dynamic>? _kakaoUserInfo;
  bool _isInitialSetupComplete = false;
  bool _hasSeenTutorial = false;
  bool _isStudentVerified = false;
  String? _studentEmail;

  UserModel? get currentUser => _currentUser;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _isAuthenticated;
  String? get kakaoUserId => _kakaoUserId;
  Map<String, dynamic>? get kakaoUserInfo => _kakaoUserInfo;
  bool get isInitialSetupComplete => _isInitialSetupComplete;
  bool get hasSeenTutorial => _hasSeenTutorial;
  bool get isStudentVerified => _isStudentVerified;
  String? get studentEmail => _studentEmail;

  AuthProvider() {
    debugPrint('[Auth] ctor');
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    debugPrint('[Auth] bootstrap start');

    await _checkAuthStatus();

    debugPrint(
      '[Auth] status checked: init=$_isInitialized loading=$_isLoading authed=$_isAuthenticated',
    );

    await _processPendingFriendInvite();

    _startEmailLinkListener();

    debugPrint('[Auth] deep link listener started');
  }

  Future<void> _checkAuthStatus() async {
    _isLoading = true;
    await Future.delayed(const Duration(milliseconds: 1200));
    _isInitialized = false;
    notifyListeners();

    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        _kakaoUserId = null;
        _isAuthenticated = false;
        _isInitialSetupComplete = false;
        _hasSeenTutorial = false;
        _isStudentVerified = false;
        _studentEmail = null;
      } else {
        // Firestore에 users 문서가 아직 없어도(가입 직후·지연) 로컬 카카오 ID는 유지한다.
        // 예전 로직은 exists == false 일 때 clearKakaoUserId() 해서 연세 인증 직후에도 uid가 사라졌다.
        _kakaoUserId = kakaoUserId;
        _isAuthenticated = true;

        try {
          await _authService.ensureFirebaseSessionForKakao(kakaoUserId);
        } catch (e) {
          debugPrint('[Auth] ensureFirebaseSessionForKakao (bootstrap): $e');
        }

        final exists = await _authService.kakaoUserExists(kakaoUserId);
        if (exists) {
          _isInitialSetupComplete = await _authService.isInitialSetupComplete(
            kakaoUserId,
          );
          _hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
          _isStudentVerified = await _authService.isStudentVerified(kakaoUserId);
          _studentEmail = await _authService.getStudentEmail(kakaoUserId);
        } else {
          _isInitialSetupComplete = false;
          _hasSeenTutorial = false;
          _isStudentVerified =
              await _storageService.isStudentVerified(kakaoUserId);
          _studentEmail = await _storageService.getStudentEmail(kakaoUserId);
        }
      }
    } catch (e) {
      debugPrint('Error checking auth status: $e');
    } finally {
      _isLoading = false;
      _isInitialized = true;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------
  // ✅ Email Link Deep Link Handling (Mobile)
  // ---------------------------------------------------------------------------

  void _startEmailLinkListener() {
    // cold start: 앱이 꺼진 상태에서 링크로 실행된 경우
    _appLinks.getInitialLink().then((uri) async {
      if (uri == null) return;
      await _handleIncomingUri(uri);
    });

    // warm start: 앱 켜진 상태에서 링크가 들어온 경우
    _linkSub = _appLinks.uriLinkStream.listen(
      (uri) async {
        await _handleIncomingUri(uri);
      },
      onError: (e) {
        debugPrint('Deep link stream error: $e');
      },
    );
  }

  Future<void> _handleIncomingUri(Uri uri) async {
    if (_friendInviteService.isFriendInviteUri(uri)) {
      final token = _friendInviteService.extractInviteToken(uri);
      if (token == null || token.isEmpty) {
        await _showFriendInviteResult(
          const FriendInviteAcceptResult(
            status: FriendInviteAcceptStatus.invalid,
          ),
        );
        return;
      }

      await _friendInviteService.savePendingInviteToken(token);
      await _processPendingFriendInvite();
      return;
    }

    final link = uri.toString();

    // Firebase 이메일 링크인지 확인
    if (!_authService.isSignInWithEmailLink(link)) return;

    // 중복 처리 방지
    if (_emailLinkHandling) return;
    _emailLinkHandling = true;

    try {
      var kakaoUserId = _kakaoUserId;
      kakaoUserId ??= await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        debugPrint('No kakaoUserId. Cannot complete email link sign-in.');
        return;
      }
      _kakaoUserId = kakaoUserId;
      await _storageService.saveKakaoUserId(kakaoUserId);

      // 저장된 이메일 우선 사용 (가장 안정적)
      final savedEmail = await _storageService.getStudentEmail(kakaoUserId);
      final email = (savedEmail ?? _studentEmail ?? '').trim();

      if (email.isEmpty) {
        debugPrint('No saved email. Cannot complete email link sign-in.');
        return;
      }

      _isLoading = true;
      notifyListeners();

      await _authService.signInWithEmailLink(email: email, emailLink: link);

      // 학생 인증 완료 기록 + 상태 반영
      await setStudentVerified(email);

      // 이메일 링크 UID ≠ 카카오 문서 ID. 가능하면 카카오 커스텀 토큰으로 통일(실패해도 이메일 세션 유지)
      await _authService.ensureFirebaseSessionForKakao(kakaoUserId);

      debugPrint('Email link verification complete for $email');
    } catch (e) {
      debugPrint('Email link sign-in failed: $e');
    } finally {
      _isLoading = false;
      _emailLinkHandling = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _linkSub?.cancel();
    super.dispose();
  }

  Future<void> _processPendingFriendInvite() async {
    final result = await _friendInviteService.processPendingInviteIfPossible();
    if (result == null) return;
    await _showFriendInviteResult(result);
  }

  Future<void> _showFriendInviteResult(
    FriendInviteAcceptResult result,
  ) async {
    if (result.status == FriendInviteAcceptStatus.pendingLogin ||
        result.status == FriendInviteAcceptStatus.pendingVerification) {
      return;
    }

    final context = NavigationService.navigatorKey.currentContext;
    final navigator = NavigationService.navigatorKey.currentState;
    if (context == null || navigator == null) return;

    final shouldNavigateToFriends =
        result.isSuccessLike && _isStudentVerified && _isInitialSetupComplete;

    final title = switch (result.status) {
      FriendInviteAcceptStatus.accepted => '친구 추가 완료',
      FriendInviteAcceptStatus.alreadyFriends => '이미 친구예요',
      FriendInviteAcceptStatus.expired => '링크 만료',
      FriendInviteAcceptStatus.invalid => '잘못된 링크',
      FriendInviteAcceptStatus.selfInvite => '초대 링크 확인',
      FriendInviteAcceptStatus.error => '처리 실패',
      _ => '친구 초대',
    };

    await showCupertinoDialog<void>(
      context: context,
      useRootNavigator: true,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(result.displayMessage),
        actions: [
          if (shouldNavigateToFriends)
            CupertinoDialogAction(
              onPressed: () {
                Navigator.of(dialogContext, rootNavigator: true).pop();
                navigator.pushNamedAndRemoveUntil(
                  RouteNames.main,
                  (route) => false,
                  arguments: const MainScaffoldArgs(
                    initialTabIndex: 4,
                    pendingRouteName: RouteNames.friendsList,
                  ),
                );
              },
              child: const Text('친구 목록 보기'),
            )
          else
            CupertinoDialogAction(
              onPressed: () =>
                  Navigator.of(dialogContext, rootNavigator: true).pop(),
              child: const Text('확인'),
            ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // ✅ Kakao Login / State setters
  // ---------------------------------------------------------------------------

  Future<void> setKakaoLogin(
    String kakaoUserId, {
    Map<String, dynamic>? userInfo,
  }) async {
    _isLoading = true;
    notifyListeners();

    try {
      await _storageService.saveKakaoUserId(kakaoUserId);
      await PushNotificationService.instance.syncFcmToken();

      _kakaoUserId = kakaoUserId;
      _isAuthenticated = true;
      _kakaoUserInfo = userInfo;

      _isInitialSetupComplete = await _authService.isInitialSetupComplete(
        kakaoUserId,
      );
      _hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
      _isStudentVerified = await _authService.isStudentVerified(kakaoUserId);
      _studentEmail = await _authService.getStudentEmail(kakaoUserId);
    } catch (e) {
      debugPrint('Error saving kakao user id: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------
  // ✅ Student Verification / Initial Setup / Tutorial
  // ---------------------------------------------------------------------------

  Future<void> setStudentVerified(String email) async {
    final kakaoUserId = _kakaoUserId;
    if (kakaoUserId == null) return;

    // 안전장치: 연세 메일만 허용
    final normalized = email.trim().toLowerCase();
    if (!normalized.endsWith('@yonsei.ac.kr')) {
      debugPrint('Rejected non-yonsei email: $normalized');
      return;
    }

    await _authService.setStudentVerified(
      kakaoUserId: kakaoUserId,
      studentEmail: normalized,
    );

    _isStudentVerified = true;
    _studentEmail = normalized;

    await _storageService.saveKakaoUserId(kakaoUserId);
    await _storageService.saveStudentEmail(kakaoUserId, normalized);
    await _storageService.setStudentVerified(kakaoUserId, true);

    notifyListeners();
  }

  Future<void> markTutorialSeen() async {
    final kakaoUserId = _kakaoUserId;
    if (kakaoUserId == null) return;

    await _authService.setTutorialSeen(kakaoUserId);
    _hasSeenTutorial = true;
    notifyListeners();
  }

  void markInitialSetupComplete() {
    _isInitialSetupComplete = true;
    notifyListeners();
  }

  Future<bool> completeInitialSetup(UserModel updatedUser) async {
    if (_currentUser == null) return false;

    _isLoading = true;
    notifyListeners();

    try {
      final user = updatedUser.copyWith(
        isInitialSetupComplete: true,
        updatedAt: DateTime.now(),
      );

      await _authService.updateUser(user);
      _currentUser = user;
      _isInitialSetupComplete = true;
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('Error completing initial setup: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------
  // ✅ Logout
  // ---------------------------------------------------------------------------

  Future<void> logout() async {
    _isLoading = true;
    notifyListeners();

    try {
      await _storageService.clearUserId();
      await _storageService.clearKakaoUserId();
      if (_kakaoUserId != null) {
        await _storageService.clearStudentVerification(_kakaoUserId!);
      }

      _currentUser = null;
      _isAuthenticated = false;
      _kakaoUserId = null;
      _kakaoUserInfo = null;
      _hasSeenTutorial = false;
      _isInitialSetupComplete = false;
      _isStudentVerified = false;
      _studentEmail = null;
    } catch (e) {
      debugPrint('Error during logout: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------
  // ⚠️ Legacy (Phone / Portal) - 지금 정책상 미사용이지만 당장 삭제는 보류
  // ---------------------------------------------------------------------------

  @Deprecated('Phone signup is deprecated. Use Kakao + Yonsei email link.')
  Future<bool> signUp({
    required String phoneNumber,
    required String verificationCode,
    String? kakaoToken,
  }) async {
    _isLoading = true;
    notifyListeners();

    try {
      final user = await _authService.signUp(
        phoneNumber: phoneNumber,
        verificationCode: verificationCode,
        kakaoToken: kakaoToken,
      );

      if (user != null) {
        _currentUser = user;
        _isAuthenticated = true;
        await _storageService.saveUserId(user.id);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error during signup: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  @Deprecated('Portal ID/PW collection is not allowed. Do not use.')
  Future<bool> verifyStudent(String portalId, String portalPassword) async {
    if (_currentUser == null) return false;

    _isLoading = true;
    notifyListeners();

    try {
      final verified = await _authService.verifyStudent(
        userId: _currentUser!.id,
        portalId: portalId,
        portalPassword: portalPassword,
      );

      if (verified) {
        _currentUser = _currentUser!.copyWith(isStudentVerified: true);
        await _authService.updateUser(_currentUser!);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error during student verification: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
