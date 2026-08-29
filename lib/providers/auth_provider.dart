import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:kakao_flutter_sdk_common/kakao_flutter_sdk_common.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../models/user_model.dart';
import '../services/auth_service.dart';
import '../services/contact_block_service.dart';
import '../services/firebase_session_failure.dart';
import '../services/friend_invite_service.dart';
import '../services/navigation_service.dart';
import '../services/storage_service.dart';
import '../services/push_notification_service.dart';
import '../features/auth/utils/email_link_continue_url.dart';
import '../router/route_names.dart';
import '../shared/layouts/main_scaffold_args.dart';

class AuthProvider with ChangeNotifier {
  final AuthService _authService = AuthService();
  final ContactBlockService _contactBlockService = ContactBlockService();
  final StorageService _storageService = StorageService();
  final FriendInviteService _friendInviteService = FriendInviteService();

  // ✅ 앱 초기화 완료 여부 (router에서 splash 고정에 사용)
  bool _isInitialized = false;
  bool get isInitialized => _isInitialized;

  // ✅ 딥링크 수신(app_links)
  final AppLinks _appLinks = AppLinks();
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<String?>? _kakaoSchemeSub;
  bool _emailLinkHandling = false; // 중복 처리 방지
  bool _emailLinkPendingAtBootstrap = false;

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
    _startKakaoSchemeListener();
    debugPrint('[Auth] deep link listeners started');
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
        // Do not delete the local Kakao identity while the Firebase email
        // action link is being handled by StudentVerificationScreen.
        if (await _hasPendingEmailLink()) {
          _emailLinkPendingAtBootstrap = true;
          _kakaoUserId = kakaoUserId;
          _isAuthenticated = false;
          _isInitialSetupComplete = false;
          _hasSeenTutorial = false;
          _isStudentVerified = false;
          _studentEmail = await _storageService.getStudentEmail(kakaoUserId);
          return;
        }

        // 로컬 kakaoUserId만으로 인증 상태를 만들지 않는다. 먼저 서버가
        // 검증한 Kakao 토큰으로 Firebase 세션을 복구해야 Firestore 조회와
        // 이후 라우팅을 수행할 수 있다.
        final restoredBeforeBootstrap = await _authService
            .ensureFirebaseSessionForKakao(kakaoUserId);
        debugPrint(
          '[Auth] bootstrap Firebase session restored=$restoredBeforeBootstrap',
        );
        if (!restoredBeforeBootstrap) {
          final preserveLocalIdentity =
              _authService.lastFirebaseSessionFailure?.isTransient ?? false;
          if (preserveLocalIdentity) {
            _kakaoUserId = kakaoUserId;
          } else {
            await _storageService.clearKakaoUserId();
            await _storageService.clearUserId();
            _kakaoUserId = null;
          }
          _isAuthenticated = false;
          _isInitialSetupComplete = false;
          _hasSeenTutorial = false;
          _isStudentVerified = false;
          _studentEmail = null;
          return;
        }

        _kakaoUserId = kakaoUserId;
        _isAuthenticated = true;

        final exists = await _authService.kakaoUserExists(kakaoUserId);
        if (exists) {
          final isRejoinRestricted = await _authService.isRejoinRestricted(
            kakaoUserId,
          );
          if (isRejoinRestricted) {
            await _storageService.savePendingRejoinRestrictionNotice();
            await _authService.signOutAll();
            await _storageService.clearUserId();
            await _storageService.clearKakaoUserId();
            await _storageService.clearStudentVerification(kakaoUserId);
            _kakaoUserId = null;
            _isAuthenticated = false;
            _isInitialSetupComplete = false;
            _hasSeenTutorial = false;
            _isStudentVerified = false;
            _studentEmail = null;
            return;
          }
          _isInitialSetupComplete = await _authService.isInitialSetupComplete(
            kakaoUserId,
          );
          _hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
          _isStudentVerified = await _authService.isStudentVerified(
            kakaoUserId,
          );
          _isStudentVerified = await _authService.isStudentVerified(
            kakaoUserId,
          );
          _studentEmail = await _authService.getStudentEmail(kakaoUserId);
          if (_isInitialSetupComplete) {
            await _reconcileRecommendationPrivacyIfNeeded();
          }
        } else {
          // Never trust local SharedPreferences alone for student verification -
          // a modified device could skip the Yonsei email gate.
          _isInitialSetupComplete = false;
          _hasSeenTutorial = false;
          _isStudentVerified = false;
          _studentEmail = null;
          await _storageService.setStudentVerified(kakaoUserId, false);
        }
      }
    } catch (e) {
      debugPrint(
        'Error checking auth status: ${PrivacyLogUtils.errorSummary(e)}',
      );
    } finally {
      _isLoading = false;
      _isInitialized = true;
      notifyListeners();
    }
  }

  // ---------------------------------------------------------------------------
  // ✅ Email Link Deep Link Handling (Mobile)
  // ---------------------------------------------------------------------------
  Future<bool> _hasPendingEmailLink() async {
    try {
      if (_authService.isSignInWithEmailLink(Uri.base.toString())) {
        return true;
      }
      if (kIsWeb && isStudentEmailLinkContinuation(Uri.base)) {
        return true;
      }
    } catch (_) {}

    if (kIsWeb) return false;

    try {
      final uri = await _appLinks.getInitialLink();
      return uri != null && _authService.isSignInWithEmailLink(uri.toString());
    } catch (e) {
      debugPrint(
        '[Auth] pending email link check failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      return false;
    }
  }

  void _startEmailLinkListener() {
    // Web and cold-start email links are owned by Splash/StudentVerification.
    // Keeping a second consumer here causes signInWithEmailLink to race and
    // one consumer receives an already-used action code.
    if (kIsWeb || _emailLinkPendingAtBootstrap) return;

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
        debugPrint(
          'Deep link stream error: ${PrivacyLogUtils.errorSummary(e)}',
        );
      },
    );
  }

  void _startKakaoSchemeListener() {
    _kakaoSchemeSub = kakaoSchemeStream.listen(
      (link) async {
        if (link == null || link.isEmpty) return;
        await _handleIncomingKakaoScheme(link);
      },
      onError: (e) {
        debugPrint(
          'Kakao scheme stream error: ${PrivacyLogUtils.errorSummary(e)}',
        );
      },
    );
  }

  Future<void> _handleIncomingKakaoScheme(String link) async {
    debugPrint(
      '[Auth] incoming Kakao scheme ${PrivacyLogUtils.pathFingerprint(link)}',
    );
    final uri = Uri.tryParse(link);
    if (uri == null) return;
    await _handleIncomingUri(uri);
  }

  Future<void> _handleIncomingUri(Uri uri) async {
    debugPrint(
      '[DeepLink] incoming ${PrivacyLogUtils.pathFingerprint(uri.toString())}',
    );
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

      debugPrint(
        '[DeepLink] friend invite detected ${PrivacyLogUtils.idFingerprint(token)}',
      );
      await _friendInviteService.savePendingInviteToken(token);
      debugPrint('[DeepLink] saved pending friend invite token');
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
      final localKakaoUserId =
          (_kakaoUserId ?? await _storageService.getKakaoUserId())?.trim();
      final verificationToken = extractStudentEmailLinkToken(link);
      if (verificationToken == null || verificationToken.isEmpty) {
        debugPrint('No email-link binding token. Cannot complete sign-in.');
        return;
      }

      final tokenEmail = await _authService.getEmailForStudentEmailLinkToken(
        verificationToken,
      );
      final savedEmail = localKakaoUserId == null
          ? ''
          : (await _storageService.getStudentEmail(localKakaoUserId) ?? '')
                .trim()
                .toLowerCase();
      final email = (tokenEmail ?? savedEmail).isNotEmpty
          ? (tokenEmail ?? savedEmail)
          : (_studentEmail ?? '').trim().toLowerCase();

      if (email.isEmpty) {
        debugPrint('No email information. Cannot complete email link sign-in.');
        return;
      }

      _isLoading = true;
      notifyListeners();

      await _authService.signInWithEmailLink(email: email, emailLink: link);
      final completion = await _authService.completeStudentEmailLink(
        token: verificationToken,
        expectedKakaoUserId: localKakaoUserId,
      );
      final kakaoUserId = completion.kakaoUserId;
      await _storageService.saveKakaoUserId(kakaoUserId);
      await _storageService.saveStudentEmail(kakaoUserId, completion.email);
      await _storageService.saveStudentVerificationToken(
        kakaoUserId,
        verificationToken,
      );
      await _storageService.setStudentVerified(kakaoUserId, true);
      await applyEmailLinkCompletion(
        kakaoUserId: kakaoUserId,
        email: completion.email,
      );

      debugPrint(
        'Email link verification complete ${PrivacyLogUtils.idFingerprint(completion.email)}',
      );
    } catch (e) {
      debugPrint(
        'Email link sign-in failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
    } finally {
      _isLoading = false;
      _emailLinkHandling = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _linkSub?.cancel();
    _kakaoSchemeSub?.cancel();
    super.dispose();
  }

  Future<void> _processPendingFriendInvite() async {
    final result = await _friendInviteService.processPendingInviteIfPossible();
    if (result == null) return;
    await _showFriendInviteResult(result);
  }

  Future<void> _waitForResumedLifecycle({
    Duration timeout = const Duration(seconds: 3),
  }) async {
    final binding = WidgetsBinding.instance;
    if (binding.lifecycleState == AppLifecycleState.resumed) {
      await Future<void>.delayed(Duration.zero);
      return;
    }

    final completer = Completer<void>();
    late final WidgetsBindingObserver observer;
    observer = _LifecycleResumeObserver(() {
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    binding.addObserver(observer);

    try {
      await completer.future.timeout(
        timeout,
        onTimeout: () {
          debugPrint(
            '[FriendInvite] resume wait timed out; continuing with result UI',
          );
        },
      );
      // One frame after resume so native/Flutter privacy covers can clear.
      await Future<void>.delayed(const Duration(milliseconds: 50));
    } finally {
      binding.removeObserver(observer);
    }
  }

  Future<void> _showFriendInviteResult(FriendInviteAcceptResult result) async {
    // Wait until the app is fully resumed after KakaoTalk deep-link handoff.
    // Showing a dialog while still inactive races the privacy splash overlay.
    await _waitForResumedLifecycle();

    final context = NavigationService.navigatorKey.currentContext;
    final navigator = NavigationService.navigatorKey.currentState;
    if (context == null || navigator == null || !context.mounted) {
      debugPrint('[FriendInvite] skip result UI: navigator not ready');
      return;
    }

    // 딥링크로 앱이 열렸지만 로그인/학생인증이 아직이면 "아무 반응 없음"처럼 보여서,
    // 사용자에게 다음 액션을 안내하고 해당 화면으로 보낸다.
    if (result.status == FriendInviteAcceptStatus.pendingLogin ||
        result.status == FriendInviteAcceptStatus.pendingVerification) {
      final title = result.status == FriendInviteAcceptStatus.pendingLogin
          ? '로그인이 필요해요'
          : '학생 인증이 필요해요';
      final actionLabel = result.status == FriendInviteAcceptStatus.pendingLogin
          ? '카카오 로그인'
          : '학생 인증하기';
      final route = result.status == FriendInviteAcceptStatus.pendingLogin
          ? RouteNames.kakaoAuth
          : RouteNames.studentVerification;

      await showCupertinoDialog<void>(
        context: context,
        useRootNavigator: true,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: Text(title),
          content: Text(result.displayMessage),
          actions: [
            CupertinoDialogAction(
              onPressed: () {
                Navigator.of(dialogContext, rootNavigator: true).pop();
                navigator.pushNamed(route);
              },
              child: Text(actionLabel),
            ),
            CupertinoDialogAction(
              onPressed: () =>
                  Navigator.of(dialogContext, rootNavigator: true).pop(),
              child: const Text('나중에'),
            ),
          ],
        ),
      );
      return;
    }

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
      final firebaseAttached = await _authService.ensureFirebaseSessionForKakao(
        kakaoUserId,
      );
      if (!firebaseAttached) {
        throw _authService.lastFirebaseSessionFailure ??
            const FirebaseSessionFailure(
              reason: FirebaseSessionFailureReason.callableFailed,
            );
      }

      await _storageService.saveKakaoUserId(kakaoUserId);
      await PushNotificationService.instance.syncFcmToken();
      await _authService.syncPendingLegalConsents(kakaoUserId);

      _kakaoUserId = kakaoUserId;
      _isAuthenticated = true;
      _kakaoUserInfo = userInfo;

      _isInitialSetupComplete = await _authService.isInitialSetupComplete(
        kakaoUserId,
      );
      _hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
      _isStudentVerified = await _authService.isStudentVerified(kakaoUserId);
      _studentEmail = await _authService.getStudentEmail(kakaoUserId);
      if (_isInitialSetupComplete) {
        await _reconcileRecommendationPrivacyIfNeeded();
      }
    } catch (e) {
      debugPrint(
        'Error saving kakao user id: ${PrivacyLogUtils.errorSummary(e)}',
      );
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _reconcileRecommendationPrivacyIfNeeded() async {
    try {
      // Re-check on every authenticated app start. This catches Kakao consent
      // revoked outside the app and friends who joined after the last sync.
      // No consent dialog is opened from this background path.
      await _contactBlockService.syncKakaoTalkFriendBlocks(
        requestConsentIfNeeded: false,
      );
    } catch (error) {
      // Recommendation loading stays fail-closed. The user can retry from the
      // contact/privacy settings screen after cancelling or a network error.
      debugPrint(
        '[Auth] recommendation privacy reconciliation pending: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
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
      debugPrint(
        'Rejected non-yonsei email ${PrivacyLogUtils.idFingerprint(normalized)}',
      );
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

  /// Applies the server-confirmed email-link completion to the in-memory
  /// provider. This is needed when the link opens in a new browser tab where
  /// bootstrap had no local Kakao identity to restore.
  Future<void> applyEmailLinkCompletion({
    required String kakaoUserId,
    required String email,
  }) async {
    final normalizedEmail = email.trim().toLowerCase();
    if (kakaoUserId.trim().isEmpty ||
        !normalizedEmail.endsWith('@yonsei.ac.kr')) {
      throw ArgumentError('invalid_email_link_completion');
    }

    _kakaoUserId = kakaoUserId;
    _isAuthenticated = true;
    _isStudentVerified = true;
    _studentEmail = normalizedEmail;
    _emailLinkPendingAtBootstrap = false;
    _isInitialSetupComplete = await _authService.isInitialSetupComplete(
      kakaoUserId,
    );
    _hasSeenTutorial = await _authService.hasSeenTutorial(kakaoUserId);
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
      debugPrint(
        'Error completing initial setup: ${PrivacyLogUtils.errorSummary(e)}',
      );
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
      final kakaoUserId = _kakaoUserId;
      await _authService.signOutAll();
      await _friendInviteService.clearPendingInviteToken();
      if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
        await _storageService.clearUserScopedSession(kakaoUserId);
      } else {
        await _storageService.clearUserId();
        await _storageService.clearKakaoUserId();
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
      debugPrint('Error during logout: ${PrivacyLogUtils.errorSummary(e)}');
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
      debugPrint('Error during signup: ${PrivacyLogUtils.errorSummary(e)}');
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
      debugPrint(
        'Error during student verification: ${PrivacyLogUtils.errorSummary(e)}',
      );
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}

class _LifecycleResumeObserver with WidgetsBindingObserver {
  _LifecycleResumeObserver(this._onResumed);

  final VoidCallback _onResumed;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _onResumed();
    }
  }
}
