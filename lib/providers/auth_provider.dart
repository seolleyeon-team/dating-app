import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kIsWeb, visibleForTesting;
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
import '../features/event/models/event_team_route_args.dart';
import '../features/profile/widgets/friend_invite_confirmation_sheet.dart';
import '../router/route_names.dart';
import '../shared/layouts/main_scaffold_args.dart';
import '../shared/utils/session_image_cache.dart';
import 'auth_bootstrap_policy.dart';

export 'auth_bootstrap_policy.dart' show AuthBootstrapPhase;

/// App-wide auth state for the Yonsei-email-primary architecture.
///
/// AUTH INVARIANT: `_isAuthenticated` is derived ONLY from an attached
/// Firebase session (canonical email custom token, or a grandfathered legacy
/// session). A cached local id or a Kakao SDK session NEVER authenticates.
class AuthProvider with ChangeNotifier {
  final AuthService _authService;
  final StorageService _storageService;
  final FriendInviteService _friendInviteService;

  // One KakaoTalk hand-off reaches us through app_links (cold start + stream)
  // AND the Kakao SDK scheme stream. Accept each token once per hand-off.
  final FriendInviteDeepLinkDeduper _friendInviteDeduper =
      FriendInviteDeepLinkDeduper();

  // ✅ 앱 초기화 완료 여부 (router에서 splash 고정에 사용)
  bool _isInitialized = false;
  bool get isInitialized => _isInitialized;

  // ✅ 딥링크 수신(app_links)
  final AppLinks _appLinks;
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<String?>? _kakaoSchemeSub;
  bool _emailLinkHandling = false; // 중복 처리 방지
  bool _emailLinkPendingAtBootstrap = false;

  // The email action link this process was cold-started with. Splash /
  // StudentVerification own that single-use code, so the general app-link
  // listener skips exactly this link (and nothing else).
  String? _bootstrapEmailLink;
  bool _emailLinkBootstrapChecked = false;

  // ---------------------------------------------------------------------------
  // Launch-time session resolution (AUD-16 / B-17)
  // ---------------------------------------------------------------------------
  // Test seams. Production leaves them null and uses FirebaseAuth / the Kakao
  // SDK directly.
  final User? Function()? _firebaseUserOverride;
  final Stream<User?> Function()? _authStateChangesOverride;
  final Stream<String?> Function()? _kakaoSchemeLinksOverride;
  final Duration _launchDelay;
  final List<Duration> _bootstrapRetryDelays;

  static const Duration _tokenRefreshTimeout = Duration(seconds: 8);
  static const Duration _profileReadTimeout = Duration(seconds: 10);

  AuthBootstrapPhase _bootstrapPhase = AuthBootstrapPhase.initializing;

  /// Every resolution run, logout and login bumps this. A run that finds a
  /// newer generation after an `await` is stale and must not touch state: it
  /// could otherwise resurrect a logged-out session or sign out a new one.
  int _bootstrapGeneration = 0;
  Timer? _bootstrapRetryTimer;
  int _bootstrapRetryAttempt = 0;
  bool _launchDelayElapsed = false;
  bool _logoutInFlight = false;
  bool _disposed = false;

  /// True while the session is authenticated from locally cached evidence
  /// (the forced token refresh failed transiently). It is re-verified by the
  /// bounded retry and on app resume.
  bool _sessionVerificationDeferred = false;
  final Completer<void> _firstBootstrap = Completer<void>();
  final Completer<void> _authStateResolved = Completer<void>();
  StreamSubscription<User?>? _authStateSub;
  WidgetsBindingObserver? _resumeObserver;

  /// See [AuthBootstrapPhase]. `retryableError` means "session attached but
  /// not resolved yet": show a retry, never the login funnel.
  AuthBootstrapPhase get bootstrapPhase => _bootstrapPhase;

  /// Completes when the first launch-time resolution has finished, whatever
  /// its outcome. Splash waits for this so both never race on the session.
  Future<void> get bootstrapSettled => _firstBootstrap.future;

  @visibleForTesting
  bool get sessionVerificationDeferred => _sessionVerificationDeferred;

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

  AuthProvider({
    AuthService? authService,
    StorageService? storageService,
    FriendInviteService? friendInviteService,
    AppLinks? appLinks,
    @visibleForTesting User? Function()? currentFirebaseUser,
    @visibleForTesting Stream<User?> Function()? authStateChanges,
    @visibleForTesting Stream<String?> Function()? kakaoSchemeLinks,
    @visibleForTesting
    Duration launchDelay = const Duration(milliseconds: 1200),
    @visibleForTesting
    List<Duration> bootstrapRetryDelays = defaultAuthBootstrapRetryDelays,
  }) : _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService(),
       _friendInviteService = friendInviteService ?? FriendInviteService(),
       _appLinks = appLinks ?? AppLinks(),
       _firebaseUserOverride = currentFirebaseUser,
       _authStateChangesOverride = authStateChanges,
       _kakaoSchemeLinksOverride = kakaoSchemeLinks,
       _launchDelay = launchDelay,
       _bootstrapRetryDelays = bootstrapRetryDelays {
    debugPrint('[Auth] ctor');
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    debugPrint('[Auth] bootstrap start');

    // Attached BEFORE the awaited resolution so a sign-out or revocation is
    // never missed, and exactly once per provider (both starters are
    // idempotent).
    _startAuthStateListener();
    _startResumeObserver();

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
    // B-15: the previous account's decoded pictures go with its session.
    clearSessionImageCache();
    _appUserId = null;
    _firebaseUid = null;
    _isAuthenticated = false;
    _isInitialSetupComplete = false;
    _hasSeenTutorial = false;
    _isStudentVerified = false;
    _studentEmail = null;
    _setupState = AccountSetupState.unauthenticated;
  }

  User? _attachedFirebaseUser() {
    final override = _firebaseUserOverride;
    return override != null ? override() : FirebaseAuth.instance.currentUser;
  }

  /// A resolution run is stale when a newer run, a logout or a login started
  /// after it, or when another account is attached by now.
  bool _isStaleBootstrap(int generation, String uid) {
    return generation != _bootstrapGeneration ||
        _attachedFirebaseUser()?.uid != uid;
  }

  /// Ends every in-flight resolution and its retry, and releases anyone
  /// waiting on the first one. Called by logout, login and external
  /// session changes.
  void _supersedeBootstrap() {
    _bootstrapGeneration += 1;
    _bootstrapRetryTimer?.cancel();
    _bootstrapRetryTimer = null;
    _bootstrapRetryAttempt = 0;
    _sessionVerificationDeferred = false;
    _bootstrapPhase = AuthBootstrapPhase.ready;
    _isLoading = false;
    _isInitialized = true;
    if (!_firstBootstrap.isCompleted) _firstBootstrap.complete();
  }

  /// Ends any in-flight resolution / retry before a logout: it must not
  /// resurrect this session, nor sign out the next one.
  void _beginLogout() {
    _supersedeBootstrap();
    _logoutInFlight = true;
  }

  void _scheduleBootstrapRetry() {
    if (_disposed) return;
    if (_bootstrapRetryAttempt >= _bootstrapRetryDelays.length) {
      debugPrint('[Auth] bootstrap retry budget exhausted');
      return;
    }
    final delay = _bootstrapRetryDelays[_bootstrapRetryAttempt];
    _bootstrapRetryAttempt += 1;
    _bootstrapRetryTimer?.cancel();
    _bootstrapRetryTimer = Timer(delay, () {
      _bootstrapRetryTimer = null;
      unawaited(_checkAuthStatus());
    });
  }

  /// Re-runs the session resolution now, with a fresh retry budget. Used by
  /// the Splash retry button and on app resume.
  Future<void> retryBootstrap() {
    _bootstrapRetryAttempt = 0;
    return _checkAuthStatus();
  }

  /// App resume: finish what a transient failure left open.
  @visibleForTesting
  void handleAppResumed() {
    if (_disposed) return;
    if (_bootstrapPhase == AuthBootstrapPhase.retryableError ||
        _sessionVerificationDeferred) {
      unawaited(retryBootstrap());
    }
  }

  void _startResumeObserver() {
    if (_resumeObserver != null) return;
    final observer = _LifecycleResumeObserver(handleAppResumed);
    _resumeObserver = observer;
    WidgetsBinding.instance.addObserver(observer);
  }

  void _startAuthStateListener() {
    if (_authStateSub != null) return;
    final override = _authStateChangesOverride;
    final Stream<User?> changes;
    try {
      changes = override != null
          ? override()
          : FirebaseAuth.instance.authStateChanges();
    } catch (e) {
      debugPrint(
        '[Auth] auth state listener unavailable: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!_authStateResolved.isCompleted) _authStateResolved.complete();
      return;
    }
    _authStateSub = changes.listen(
      _onFirebaseAuthState,
      onError: (Object e) {
        debugPrint(
          '[Auth] auth state stream error: ${PrivacyLogUtils.errorSummary(e)}',
        );
        if (!_authStateResolved.isCompleted) _authStateResolved.complete();
      },
    );
  }

  /// Follows session changes this provider did not start itself.
  ///
  /// Only the two "the account I am showing is gone" transitions are acted
  /// on. A sign-IN is deliberately ignored: the email-link flow first
  /// attaches a temporary non-canonical session, and reacting to it here
  /// would race the single-use completion. Sign-ins are applied explicitly
  /// ([applyPrimaryEmailAuthCompletion], [refreshAfterExternalSignIn]).
  void _onFirebaseAuthState(User? user) {
    if (!_authStateResolved.isCompleted) _authStateResolved.complete();
    if (_disposed || _logoutInFlight) return;

    final holdsSession =
        _isAuthenticated ||
        _bootstrapPhase == AuthBootstrapPhase.retryableError;
    if (!holdsSession) return;

    final uid = user?.uid;
    if (uid == null) {
      // Signed out elsewhere (rejoin restriction, account deletion) or the
      // server revoked / disabled the account and the SDK dropped the user.
      debugPrint('[Auth] session ended outside the provider');
      final previousAppUserId = _appUserId;
      _supersedeBootstrap();
      _currentUser = null;
      _resetSessionState();
      notifyListeners();
      unawaited(_clearLocalIdentity(previousAppUserId));
      return;
    }
    if (_isAuthenticated && uid != _appUserId) {
      // Another account is attached without a logout() in between. Drop the
      // previous account's identity at once so nothing stays bound to it;
      // the explicit completion path hydrates the new account.
      debugPrint('[Auth] attached account changed outside the provider');
      _supersedeBootstrap();
      _currentUser = null;
      _resetSessionState();
      notifyListeners();
    }
  }

  Future<void> _clearLocalIdentity(String? appUserId) async {
    try {
      if (appUserId != null && appUserId.isNotEmpty) {
        await _storageService.clearUserScopedSession(appUserId);
      } else {
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
      }
    } catch (e) {
      debugPrint(
        '[Auth] local identity cleanup failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  /// On the web the persisted session is restored asynchronously: reading
  /// `currentUser` before the first auth-state event can see `null` for a
  /// signed-in user. Native platforms resolve within a frame.
  Future<void> _waitForInitialAuthState() async {
    if (_authStateSub == null || _authStateResolved.isCompleted) return;
    await _authStateResolved.future.timeout(
      const Duration(seconds: 3),
      onTimeout: () {},
    );
  }

  Future<void> _checkAuthStatus() async {
    final generation = ++_bootstrapGeneration;
    _bootstrapRetryTimer?.cancel();
    _bootstrapRetryTimer = null;
    _isLoading = true;
    if (!_launchDelayElapsed) {
      await Future.delayed(_launchDelay);
      _launchDelayElapsed = true;
    }
    if (generation != _bootstrapGeneration || _disposed) return;
    _isInitialized = false;
    notifyListeners();

    // `transientFailure`: the attached session could not be resolved this
    // time. It is KEPT (never signed out) and resolved again by the retry.
    var transientFailure = false;
    // `verificationDeferred`: resolved from cached evidence only.
    var verificationDeferred = false;
    try {
      // Do not consume any session state while a Firebase email action link
      // is pending: Splash/StudentVerification own that single-use code.
      // Only the FIRST run asks: the initial link never changes for the
      // lifetime of the process, so asking again would reset a session that
      // was established from that very link.
      if (!_emailLinkBootstrapChecked) {
        _emailLinkBootstrapChecked = true;
        if (await _hasPendingEmailLink()) {
          _emailLinkPendingAtBootstrap = true;
          _resetSessionState();
          _setupState = AccountSetupState.emailVerificationPending;
          _studentEmail = (await _storageService.getPendingStudentEmail())
              ?.trim()
              .toLowerCase();
          return;
        }
      }

      await _waitForInitialAuthState();
      if (generation != _bootstrapGeneration) return;

      // Canonical rule: only an attached Firebase session authenticates.
      // There is NO Kakao-based session restore in this client.
      final firebaseUser = _firebaseUserOverride != null
          ? _firebaseUserOverride()
          : FirebaseAuth.instance.currentUser;
      if (firebaseUser == null) {
        _currentUser = null;
        _resetSessionState();
        return;
      }
      final uid = firebaseUser.uid;

      // Firestore의 대나무숲 등 사용자 상호작용 기능은 canonical 앱 세션만
      // 허용한다. 이메일 링크를 막 열어 생긴 임시 Firebase 세션은 사용자를
      // 읽을 수 있는 경우가 있어도 appSession/kakaoUserId 클레임이 없으므로
      // 글쓰기는 permission-denied가 된다. 부팅 단계에서 이를 로그인 상태로
      // 오인하지 않고, 정상적인 연세 메일 로그인 플로우로 돌려보낸다.
      Map<String, dynamic>? claims;
      var tokenRead = false;
      try {
        // Bounded: on a stalled network the cached evidence below is used
        // instead of holding the launch for the SDK's own long timeout.
        claims =
            (await firebaseUser
                    .getIdTokenResult(true)
                    .timeout(_tokenRefreshTimeout))
                .claims;
        tokenRead = true;
      } catch (e) {
        if (_isStaleBootstrap(generation, uid)) return;
        if (classifyAuthBootstrapFailure(e) ==
            AuthBootstrapFailure.sessionInvalid) {
          // Revoked, disabled or deleted account: the one failure that is a
          // real sign-out.
          debugPrint(
            '[Auth] session rejected by the server: '
            '${PrivacyLogUtils.errorSummary(e)}',
          );
          await _authService.signOutAll();
          await _storageService.clearUserId();
          await _storageService.clearAppUserId();
          _currentUser = null;
          _resetSessionState();
          return;
        }
        // Transient (offline, timeout, backend hiccup). NEVER sign out on
        // this: fall back to the cached token, whose claims are still the
        // server-minted ones.
        debugPrint(
          '[Auth] token refresh failed, using cached evidence: '
          '${PrivacyLogUtils.errorSummary(e)}',
        );
        verificationDeferred = true;
        try {
          claims = (await firebaseUser.getIdTokenResult(false)).claims;
          tokenRead = true;
        } catch (_) {
          tokenRead = false;
        }
      }
      if (_isStaleBootstrap(generation, uid)) return;

      final bool hasCanonicalSession;
      if (tokenRead) {
        hasCanonicalSession =
            claims?['appSession'] == true || claims?['kakaoUserId'] != null;
      } else {
        // No token at all (offline with an expired one). The session is
        // accepted only when its uid is the appUserId this device already
        // verified as canonical; a temporary email-link session has a
        // different uid and can never match. Otherwise stay unresolved.
        if (await _storageService.getAppUserId() != uid) {
          transientFailure = true;
          return;
        }
        hasCanonicalSession = true;
      }
      if (_isStaleBootstrap(generation, uid)) return;
      if (!hasCanonicalSession) {
        await _authService.signOutAll();
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
        _resetSessionState();
        _setupState = AccountSetupState.emailVerificationPending;
        return;
      }

      final Map<String, dynamic>? profile;
      final bool rejoinRestricted;
      try {
        profile = await _authService
            .getUserProfile(uid)
            .timeout(_profileReadTimeout);
        rejoinRestricted =
            profile != null &&
            await _authService
                .isRejoinRestricted(uid)
                .timeout(_profileReadTimeout);
      } catch (e) {
        // The profile could not be read. Without it neither the rejoin
        // restriction nor the setup gate is known, so this run does not
        // authenticate (fail closed) - but the session is kept and retried.
        debugPrint(
          '[Auth] profile read failed: ${PrivacyLogUtils.errorSummary(e)}',
        );
        transientFailure = true;
        return;
      }
      if (_isStaleBootstrap(generation, uid)) return;

      if (rejoinRestricted) {
        await _storageService.savePendingRejoinRestrictionNotice();
        await _authService.signOutAll();
        await _storageService.clearUserId();
        await _storageService.clearAppUserId();
        await _storageService.clearStudentVerification(uid);
        _resetSessionState();
        return;
      }

      _firebaseUid = uid;
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

      final isPlayReviewer =
          profile['accountType'] == 'google_play_review' &&
          profile['dataPartition'] == 'play_review' &&
          profile['reviewAccess'] == true &&
          profile['reviewProfileReady'] == true;
      // This is an in-memory navigation capability, not a claim that the
      // reviewer owns a Yonsei mailbox. Firestore keeps isStudentVerified
      // false and the setup resolver checks the review markers independently.
      _isStudentVerified = profile['isStudentVerified'] == true;
      if (isPlayReviewer) _isStudentVerified = true;
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
      transientFailure = true;
    } finally {
      // A stale run leaves everything to whoever superseded it.
      if (generation == _bootstrapGeneration && !_disposed) {
        _isLoading = false;
        _isInitialized = true;
        final unresolved = transientFailure && !_isAuthenticated;
        _bootstrapPhase = unresolved
            ? AuthBootstrapPhase.retryableError
            : AuthBootstrapPhase.ready;
        _sessionVerificationDeferred =
            _isAuthenticated && (transientFailure || verificationDeferred);
        if (unresolved || _sessionVerificationDeferred) {
          _scheduleBootstrapRetry();
        } else {
          _bootstrapRetryAttempt = 0;
        }
        if (!_firstBootstrap.isCompleted) _firstBootstrap.complete();
        notifyListeners();
      }
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
      if (uri != null && _authService.isSignInWithEmailLink(uri.toString())) {
        _bootstrapEmailLink = uri.toString();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint(
        '[Auth] pending email link check failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      return false;
    }
  }

  void _startEmailLinkListener() {
    // Web links are owned by Splash/StudentVerification (the browser URL).
    if (kIsWeb) return;
    // Exactly one subscription per provider, however often this is called.
    if (_linkSub != null) return;

    // cold start: 앱이 꺼진 상태에서 링크로 실행된 경우.
    // A launch from the email action link is the one exception: Splash /
    // StudentVerification own that single-use code, and a second consumer
    // here would race signInWithEmailLink.
    if (!_emailLinkPendingAtBootstrap) {
      _appLinks.getInitialLink().then((uri) async {
        if (uri == null) return;
        await _handleAppLink(uri);
      });
    }

    // warm start: 앱 켜진 상태에서 링크가 들어온 경우.
    // AUD-24: this used to be skipped together with the cold-start read
    // after an email-link launch, so no App Link (friend / team invite, a
    // later email link) was delivered for the rest of that session.
    _linkSub = _appLinks.uriLinkStream.listen(
      (uri) async {
        await _handleAppLink(uri);
      },
      onError: (e) {
        debugPrint(
          'Deep link stream error: ${PrivacyLogUtils.errorSummary(e)}',
        );
      },
    );
  }

  /// The email-link single-consumer guard: the exact link this process was
  /// launched with stays with Splash/StudentVerification, even when the
  /// platform replays it on the stream. Every other link is handled.
  bool _isBootstrapEmailLink(Uri uri) {
    final bootstrapLink = _bootstrapEmailLink;
    return bootstrapLink != null && uri.toString() == bootstrapLink;
  }

  Future<void> _handleAppLink(Uri uri) async {
    if (_isBootstrapEmailLink(uri)) {
      debugPrint('[DeepLink] launch email link left to its owner');
      return;
    }
    await _handleIncomingUri(uri);
  }

  /// The Kakao scheme listener stays: the friend-connection OAuth callback
  /// arrives through it. It never authenticates the account.
  void _startKakaoSchemeListener() {
    if (_kakaoSchemeSub != null) return;
    final override = _kakaoSchemeLinksOverride;
    final links = override != null ? override() : kakaoSchemeStream;
    _kakaoSchemeSub = links.listen(
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
    // A share link (Kakao button, App Link, custom scheme) is a ROUTING
    // event only. It is persisted and turned into a confirmation step; no
    // friendship or team mutation happens on link open.
    final pendingInvite = FriendInviteService.parseInviteUri(uri);
    if (pendingInvite != null) {
      debugPrint(
        '[DeepLink] ${pendingInvite.purpose.name} invite detected '
        '${PrivacyLogUtils.idFingerprint(pendingInvite.token)}',
      );
      if (!_friendInviteDeduper.shouldProcess(pendingInvite.token)) {
        debugPrint('[DeepLink] duplicate invite hand-off ignored');
        return;
      }
      // Persist FIRST so login or an app restart cannot lose the context.
      await _friendInviteService.savePendingInvite(pendingInvite);
      debugPrint('[DeepLink] saved pending invite');
      await resumePendingInvite();
      if (await _friendInviteService.getPendingInvite() != null) {
        // Still pending (login/verification needed): a later hand-off of the
        // same link (the user taps the Kakao button again) must run again.
        _friendInviteDeduper.release(pendingInvite.token);
      }
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

      // A friend invite tapped before this login must not wait for the next
      // cold start: the canonical appUserId now exists, so accept it here.
      await _processPendingFriendInvite();

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
    _disposed = true;
    _bootstrapGeneration += 1;
    _bootstrapRetryTimer?.cancel();
    _bootstrapRetryTimer = null;
    _authStateSub?.cancel();
    final resumeObserver = _resumeObserver;
    if (resumeObserver != null) {
      WidgetsBinding.instance.removeObserver(resumeObserver);
    }
    if (!_firstBootstrap.isCompleted) _firstBootstrap.complete();
    _linkSub?.cancel();
    _kakaoSchemeSub?.cancel();
    super.dispose();
  }

  /// Bootstrap / warm-start entry point. See [resumePendingInvite].
  Future<void> _processPendingFriendInvite() => resumePendingInvite();

  bool _inviteResumeInFlight = false;

  // A confirmation that closed WITHOUT a decision (route reset on a cold
  // start) is re-presented a bounded number of times per pending invite.
  int _inviteConfirmationRetries = 0;
  static const int _maxInviteConfirmationRetries = 2;
  static const Duration _inviteConfirmationRetryDelay = Duration(
    milliseconds: 700,
  );

  void _scheduleInviteConfirmationRetry() {
    if (_inviteConfirmationRetries >= _maxInviteConfirmationRetries) {
      debugPrint('[FriendInvite] confirmation retry budget exhausted');
      return;
    }
    _inviteConfirmationRetries += 1;
    Future<void>.delayed(_inviteConfirmationRetryDelay, () {
      // The in-flight flag was released in resumePendingInvite's finally.
      unawaited(resumePendingInvite());
    });
  }

  /// Restores a pending share invite into its confirmation step.
  ///
  /// This NEVER accepts anything by itself:
  /// - friend invites open [FriendInviteConfirmationSheet]; only an explicit
  ///   [친구 추가] tap calls acceptFriendInvite.
  /// - team invites are redeemed into the canonical pending team invitation
  ///   and shown in the existing team response screen (accept / decline).
  /// The server preview's purpose is authoritative; the link's own hint is
  /// only used for logging.
  Future<void> resumePendingInvite() async {
    if (_inviteResumeInFlight) return;
    final pending = await _friendInviteService.getPendingInvite();
    if (pending == null) return;
    _inviteResumeInFlight = true;
    try {
      debugPrint('[FriendInvite] resume purpose=${pending.purpose.name}');

      // Gate 1: a canonical Firebase session. A cached id never counts.
      if (!_friendInviteService.hasCanonicalFirebaseSession) {
        await _authService.ensureCanonicalAppSession();
      }
      if (!_friendInviteService.hasCanonicalFirebaseSession ||
          !_isAuthenticated) {
        await _showFriendInviteResult(
          const FriendInviteAcceptResult(
            status: FriendInviteAcceptStatus.pendingLogin,
          ),
        );
        return; // the invite stays pending until the user logs in
      }
      if (!_isStudentVerified) {
        await _showFriendInviteResult(
          const FriendInviteAcceptResult(
            status: FriendInviteAcceptStatus.pendingVerification,
          ),
        );
        return;
      }

      // Gate 2: the server decides what the token is (purpose) and whether
      // it is still usable. Read-only — nothing is consumed here.
      InvitePreview preview;
      final inviteTitle = pending.purpose == InvitePurpose.team
          ? '3:3 팀 초대'
          : '친구 초대';
      try {
        preview = await _friendInviteService.previewInvite(pending.token);
      } on FirebaseFunctionsException catch (e) {
        if (e.code == 'unauthenticated' || e.code == 'failed-precondition') {
          await _showFriendInviteResult(
            FriendInviteAcceptResult(
              status: FriendInviteAcceptStatus.pendingVerification,
              message: e.message,
            ),
          );
          return; // stays pending until the account is eligible
        }
        // Network / server / deployment failure: the token was not judged
        // by the server, so it stays pending and is retried at the next
        // hand-off or bootstrap instead of being silently dropped.
        debugPrint(
          '[FriendInvite] preview unavailable (${e.code}); invite kept pending',
        );
        await _showInviteNotice(
          inviteTitle,
          _friendInviteService.describeFunctionsError(e),
        );
        return;
      }

      final purpose = preview.purpose;
      if (!preview.isValid || purpose == null) {
        _inviteConfirmationRetries = 0;
        await _friendInviteService.clearPendingInvite();
        await _showInviteNotice(inviteTitle, preview.displayMessage);
        return;
      }
      if (purpose != pending.purpose) {
        debugPrint(
          '[FriendInvite] link hint ${pending.purpose.name} disagrees with '
          'server purpose ${purpose.name}; routing on the server value',
        );
      }

      switch (purpose) {
        case InvitePurpose.friend:
          await _confirmAndAcceptFriendInvite(pending.token, preview);
        case InvitePurpose.team:
          await _confirmAndRedeemTeamInvite(pending.token, preview);
      }
    } finally {
      _inviteResumeInFlight = false;
    }
  }

  Future<void> _confirmAndAcceptFriendInvite(
    String token,
    InvitePreview preview,
  ) async {
    await _waitForResumedLifecycle();
    final context = NavigationService.navigatorKey.currentContext;
    if (context == null || !context.mounted) {
      debugPrint('[FriendInvite] skip confirmation: navigator not ready');
      return; // stays pending; retried at the next bootstrap
    }

    final confirmed = await showFriendInviteConfirmationSheet(
      context,
      inviterName: preview.inviterName ?? '',
      inviterImageUrl: preview.inviterImageUrl,
    );
    if (confirmed == null) {
      // The sheet is not barrier-dismissible, so `null` means the route was
      // removed underneath it (splash → main reset on a cold start). No
      // decision was made: keep the invite pending and re-present it.
      debugPrint('[FriendInvite] confirmation interrupted; re-presenting');
      _scheduleInviteConfirmationRetry();
      return;
    }
    _inviteConfirmationRetries = 0;
    if (confirmed != true) {
      // Explicit "나중에": no mutation, and no re-prompt.
      debugPrint('[FriendInvite] confirmation declined');
      await _friendInviteService.clearPendingInvite();
      return;
    }

    final result = await _friendInviteService.acceptFriendInvite(token);
    if (result.isTerminal) {
      await _friendInviteService.clearPendingInvite();
    }
    await _showFriendInviteResult(result);
  }

  Future<void> _confirmAndRedeemTeamInvite(
    String token,
    InvitePreview preview,
  ) async {
    await _waitForResumedLifecycle();
    final context = NavigationService.navigatorKey.currentContext;
    if (context == null || !context.mounted) {
      debugPrint('[FriendInvite] skip team confirmation: navigator not ready');
      return; // stays pending; retried at the next bootstrap
    }

    // Even though redemption grants no membership, it occupies a pending
    // team slot and consumes the one-time token — so it, too, only happens
    // after an explicit in-app tap.
    final proceed = await _confirmTeamInviteOpen(context, preview.inviterName);
    if (proceed == null) {
      // Dialog removed by a route reset, not answered: keep pending.
      debugPrint('[FriendInvite] team confirmation interrupted; re-presenting');
      _scheduleInviteConfirmationRetry();
      return;
    }
    _inviteConfirmationRetries = 0;
    if (proceed != true) {
      debugPrint('[FriendInvite] team invite confirmation declined');
      await _friendInviteService.clearPendingInvite();
      return;
    }

    final result = await _friendInviteService.redeemTeamShareInvite(token);
    if (result.isTerminal) {
      await _friendInviteService.clearPendingInvite();
    }
    await _waitForResumedLifecycle();
    final navigator = NavigationService.navigatorKey.currentState;
    final teamInviteId = result.teamInviteId;
    if (result.opensResponseScreen &&
        navigator != null &&
        teamInviteId != null) {
      // The existing team response screen is the explicit accept/decline.
      navigator.pushNamed(
        RouteNames.eventTeamInviteResponse,
        arguments: EventTeamInviteResponseArgs(inviteId: teamInviteId),
      );
      return;
    }
    await _showInviteNotice('3:3 팀 초대', result.displayMessage);
  }

  Future<bool?> _confirmTeamInviteOpen(
    BuildContext context,
    String? inviterName,
  ) {
    final name = (inviterName ?? '').trim();
    final who = name.isEmpty ? '설레연 친구' : name;
    return showCupertinoDialog<bool>(
      context: context,
      useRootNavigator: true,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('3:3 팀 초대'),
        content: Text('$who님이 3:3 미팅 팀 참여를 요청했어요.\n초대를 확인할까요?'),
        actions: [
          CupertinoDialogAction(
            onPressed: () =>
                Navigator.of(dialogContext, rootNavigator: true).pop(false),
            child: const Text('나중에'),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () =>
                Navigator.of(dialogContext, rootNavigator: true).pop(true),
            child: const Text('초대 확인'),
          ),
        ],
      ),
    );
  }

  Future<void> _showInviteNotice(String title, String message) async {
    await _waitForResumedLifecycle();
    final context = NavigationService.navigatorKey.currentContext;
    if (context == null || !context.mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      useRootNavigator: true,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            onPressed: () =>
                Navigator.of(dialogContext, rootNavigator: true).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
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
      FriendInviteAcceptStatus.blockedRelationship => '친구 추가 불가',
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
    final uid = _attachedFirebaseUser()?.uid;
    if (uid == null || uid != completion.appUserId) {
      throw StateError('primary_email_auth_uid_mismatch');
    }

    // A login supersedes any launch-time resolution still in flight.
    _supersedeBootstrap();
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

  /// Re-hydrates provider state after the dedicated Play review custom-token
  /// sign-in. The setup resolver verifies the immutable review profile again.
  Future<void> refreshAfterExternalSignIn() => _checkAuthStatus();

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
    _beginLogout();
    _isLoading = true;
    notifyListeners();

    try {
      final appUserId = _appUserId;
      // Firebase sign-out + Kakao SDK logout: the next user on this device
      // must not inherit a stale Kakao friend-connection session.
      await _authService.signOutAll();
      await _friendInviteService.clearPendingInvite();
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
      _logoutInFlight = false;
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
