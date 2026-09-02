import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:kakao_flutter_sdk_common/kakao_flutter_sdk_common.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../models/account_setup_state.dart';
import '../models/primary_student_email_auth_completion.dart';
import '../models/user_model.dart';
import '../services/adult_verification_service.dart';
import '../services/auth_service.dart';
import '../services/friend_invite_service.dart';
import '../services/navigation_service.dart';
import '../services/storage_service.dart';
import '../services/push_notification_service.dart';
import '../features/auth/utils/email_link_continue_url.dart';
import '../router/route_names.dart';
import '../shared/layouts/main_scaffold_args.dart';

/// App-wide auth state for the Yonsei-email-primary architecture.
///
/// AUTH INVARIANT: `_isAuthenticated` is derived ONLY from an attached
/// Firebase session (canonical email custom token, or a grandfathered legacy
/// session). A cached local id or a Kakao SDK session NEVER authenticates.
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
  StreamSubscription<String?>? _kakaoSchemeSub;
  bool _emailLinkHandling = false; // 중복 처리 방지
  bool _emailLinkPendingAtBootstrap = false;

  UserModel? _currentUser;
  bool _isLoading = false;
  bool _isAuthenticated = false;
  String? _appUserId;
  String? _firebaseUid;
  bool _isInitialSetupComplete = false;
  bool _hasSeenTutorial = false;
  bool _isStudentVerified = false;
  String? _studentEmail;
  AccountSetupState _setupState = AccountSetupState.unauthenticated;

  UserModel? get currentUser => _currentUser;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _isAuthenticated;
  String? get appUserId => _appUserId;
  String? get firebaseUid => _firebaseUid;

  /// Legacy name: existing accounts' appUserId IS the old Kakao numeric id.
  String? get kakaoUserId => _appUserId;

  /// Legacy surface for dead stub screens; the new flow never collects Kakao
  /// profile data.
  Map<String, dynamic>? get kakaoUserInfo => null;
  bool get isInitialSetupComplete => _isInitialSetupComplete;
  bool get hasSeenTutorial => _hasSeenTutorial;
  bool get isStudentVerified => _isStudentVerified;
  String? get studentEmail => _studentEmail;
  AccountSetupState get setupState => _setupState;

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

  void _resetSessionState() {
    _appUserId = null;
    _firebaseUid = null;
    _isAuthenticated = false;
    _isInitialSetupComplete = false;
    _hasSeenTutorial = false;
    _isStudentVerified = false;
    _studentEmail = null;
    _setupState = AccountSetupState.unauthenticated;
  }

  Future<void> _checkAuthStatus() async {
    _isLoading = true;
    await Future.delayed(const Duration(milliseconds: 1200));
    _isInitialized = false;
    notifyListeners();

    try {
      // Do not consume any session state while a Firebase email action link
      // is pending: Splash/StudentVerification own that single-use code.
      if (await _hasPendingEmailLink()) {
        _emailLinkPendingAtBootstrap = true;
        _resetSessionState();
        _setupState = AccountSetupState.emailVerificationPending;
        _studentEmail = (await _storageService.getPendingStudentEmail())
            ?.trim()
            .toLowerCase();
        return;
      }

      // Canonical rule: only an attached Firebase session authenticates.
      // There is NO Kakao-based session restore in this client.
      final firebaseUser = FirebaseAuth.instance.currentUser;
      if (firebaseUser == null) {
        _resetSessionState();
        return;
      }

      // Firestore의 대나무숲 등 사용자 상호작용 기능은 canonical 앱 세션만
      // 허용한다. 이메일 링크를 막 열어 생긴 임시 Firebase 세션은 사용자를
      // 읽을 수 있는 경우가 있어도 appSession/kakaoUserId 클레임이 없으므로
      // 글쓰기는 permission-denied가 된다. 부팅 단계에서 이를 로그인 상태로
      // 오인하지 않고, 정상적인 연세 메일 로그인 플로우로 돌려보낸다.
      final tokenResult = await firebaseUser.getIdTokenResult(true);
      final claims = tokenResult.claims;
      final hasCanonicalSession =
          claims?['appSession'] == true || claims?['kakaoUserId'] != null;
      if (!hasCanonicalSession) {
        await _authService.signOutAll();
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
        _resetSessionState();
        _setupState = AccountSetupState.emailVerificationPending;
        return;
      }

      final uid = firebaseUser.uid;
      _firebaseUid = uid;

      final profile = await _authService.getUserProfile(uid);

      if (profile != null && await _authService.isRejoinRestricted(uid)) {
        await _storageService.savePendingRejoinRestrictionNotice();
        await _authService.signOutAll();
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
        await _storageService.clearStudentVerification(uid);
        _resetSessionState();
        return;
      }

      _appUserId = uid;
      _isAuthenticated = true;
      await _storageService.saveAppUserId(uid);

      if (profile == null) {
        // Session without a users doc: primary email auth did not finish.
        // Never trust local SharedPreferences alone for student verification.
        _isInitialSetupComplete = false;
        _hasSeenTutorial = false;
        _isStudentVerified = false;
        _studentEmail = null;
        await _storageService.setStudentVerified(uid, false);
        _setupState = AccountSetupState.emailVerificationPending;
        return;
      }

      _isStudentVerified = profile['isStudentVerified'] == true;
      final rawEmail = profile['studentEmail'];
      _studentEmail = rawEmail is String && rawEmail.trim().isNotEmpty
          ? rawEmail.trim().toLowerCase()
          : null;
      _hasSeenTutorial = profile['hasSeenTutorial'] == true;
      _isInitialSetupComplete =
          _isTruthyMarker(profile['initialSetupComplete']) || _hasSeenTutorial;
      _setupState = resolveAccountSetupState(
        hasFirebaseSession: true,
        userDoc: profile,
        adultVerificationDisabled:
            AdultVerificationService.isTemporarilyDisabled,
      );
      // One-time-snapshot architecture: bootstrap never touches Kakao
      // friends. Pair-based recommendationExclusions are server-maintained
      // and applied at serving time only.
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

  static bool _isTruthyMarker(Object? v) {
    return v == true || v == 'true' || (v is num && v != 0);
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

  /// The Kakao scheme listener stays: the friend-connection OAuth callback
  /// arrives through it. It never authenticates the account.
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
      final verificationToken = extractStudentEmailLinkToken(link);
      if (verificationToken == null || verificationToken.isEmpty) {
        debugPrint('No email-link binding token. Cannot complete sign-in.');
        return;
      }

      final tokenEmail = await _authService.getEmailForStudentEmailLinkToken(
        verificationToken,
      );
      final pendingEmail =
          (await _storageService.getPendingStudentEmail() ?? '')
              .trim()
              .toLowerCase();
      final email = (tokenEmail ?? pendingEmail).isNotEmpty
          ? (tokenEmail ?? pendingEmail)
          : (_studentEmail ?? '').trim().toLowerCase();

      if (email.isEmpty) {
        debugPrint('No email information. Cannot complete email link sign-in.');
        return;
      }

      _isLoading = true;
      notifyListeners();

      // All observers of this native link share one process-wide completion
      // future, so the one-time Firebase action code is consumed once.
      final completion = await _authService.completePrimaryStudentEmailLink(
        email: email,
        emailLink: link,
        token: verificationToken,
      );
      final appUserId = completion.appUserId;
      await _storageService.saveAppUserId(appUserId);
      await _storageService.saveStudentEmail(
        appUserId,
        completion.normalizedEmail,
      );
      await _storageService.setStudentVerified(appUserId, true);
      await _storageService.clearPendingStudentEmail();
      await _storageService.clearPendingStudentEmailRequestId();
      await applyPrimaryEmailAuthCompletion(completion);

      debugPrint(
        'Email link verification complete '
        '${PrivacyLogUtils.idFingerprint(completion.normalizedEmail)}',
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
      const actionLabel = '연세 메일 로그인';
      // Both states resolve on the same primary email login screen.
      const route = RouteNames.studentVerification;

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
              child: const Text(actionLabel),
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
        result.isSuccessLike &&
        _isStudentVerified &&
        _isInitialSetupComplete &&
        _setupState == AccountSetupState.complete;

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
  // ✅ Primary email auth completion / State setters
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // ✅ Student Verification / Initial Setup / Tutorial
  // ---------------------------------------------------------------------------

  Future<void> setStudentVerified(String email) async {
    final appUserId = _appUserId;
    if (appUserId == null) return;

    // 안전장치: 연세 메일만 허용
    final normalized = email.trim().toLowerCase();
    if (!normalized.endsWith('@yonsei.ac.kr')) {
      debugPrint(
        'Rejected non-yonsei email ${PrivacyLogUtils.idFingerprint(normalized)}',
      );
      return;
    }

    await _authService.setStudentVerified(
      kakaoUserId: appUserId,
      studentEmail: normalized,
    );

    _isStudentVerified = true;
    _studentEmail = normalized;

    await _storageService.saveAppUserId(appUserId);
    await _storageService.saveStudentEmail(appUserId, normalized);
    await _storageService.setStudentVerified(appUserId, true);

    notifyListeners();
  }

  /// Applies the server-confirmed primary email auth completion to the
  /// in-memory provider. Called after `completePrimaryStudentEmailAuth`
  /// signed in with the canonical custom token (uid == appUserId).
  Future<void> applyPrimaryEmailAuthCompletion(
    PrimaryStudentEmailAuthCompletion completion,
  ) async {
    final uid = FirebaseAuth.instance.currentUser?.uid;
    if (uid == null || uid != completion.appUserId) {
      throw StateError('primary_email_auth_uid_mismatch');
    }

    _appUserId = completion.appUserId;
    _firebaseUid = uid;
    _isAuthenticated = true;
    _isStudentVerified = true;
    _studentEmail = completion.normalizedEmail;
    _emailLinkPendingAtBootstrap = false;
    _isInitialSetupComplete = completion.initialSetupComplete;

    await _storageService.saveAppUserId(uid);
    try {
      await PushNotificationService.instance.syncFcmToken();
    } catch (e) {
      debugPrint('[Auth] FCM sync skipped: ${PrivacyLogUtils.errorSummary(e)}');
    }

    try {
      final profile = await _authService.getUserProfile(uid);
      _hasSeenTutorial = profile?['hasSeenTutorial'] == true;
      _isInitialSetupComplete =
          completion.initialSetupComplete || _hasSeenTutorial;
      _setupState = resolveAccountSetupState(
        hasFirebaseSession: true,
        userDoc: profile,
        adultVerificationDisabled:
            AdultVerificationService.isTemporarilyDisabled,
      );
    } catch (e) {
      debugPrint(
        '[Auth] post-completion hydrate failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
    notifyListeners();
  }

  Future<void> markTutorialSeen() async {
    final appUserId = _appUserId;
    if (appUserId == null || appUserId.isEmpty) {
      throw StateError('tutorial_completion_requires_authenticated_user');
    }

    await _authService.setTutorialSeen(appUserId);
    _hasSeenTutorial = true;
    _isInitialSetupComplete = true;
    _setupState = AccountSetupState.complete;
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
      final appUserId = _appUserId;
      // Firebase sign-out + Kakao SDK logout: the next user on this device
      // must not inherit a stale Kakao friend-connection session.
      await _authService.signOutAll();
      await _friendInviteService.clearPendingInviteToken();
      if (appUserId != null && appUserId.isNotEmpty) {
        await _storageService.clearUserScopedSession(appUserId);
      } else {
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
        await _storageService.clearPendingStudentEmail();
        await _storageService.clearPendingStudentEmailRequestId();
      }

      _currentUser = null;
      _resetSessionState();
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

  @Deprecated('Phone signup is deprecated. Use Yonsei email link.')
  Future<bool> signUp({
    required String phoneNumber,
    required String verificationCode,
    String? kakaoToken,
  }) async {
    // Authentication state may only come from a verified Firebase session
    // (contract §1). This legacy path must never fabricate one.
    return false;
  }

  @Deprecated('Portal ID/PW collection is not allowed. Do not use.')
  Future<bool> verifyStudent(String portalId, String portalPassword) async {
    // Student verification may only come from the server-verified email flow.
    return false;
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
