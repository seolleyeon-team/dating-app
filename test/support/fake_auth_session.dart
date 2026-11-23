import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart' hide AuthProvider;
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/providers/auth_provider.dart';
import 'package:seolleyeon/services/auth_service.dart';
import 'package:seolleyeon/services/friend_invite_service.dart';
import 'package:seolleyeon/services/storage_service.dart';

// Fakes for driving the real AuthProvider without Firebase: the attached
// session and its token behaviour, the profile reads and the link channels.

class FakeIdTokenResult implements IdTokenResult {
  FakeIdTokenResult(this.claims);

  @override
  final Map<String, dynamic>? claims;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeUser implements User {
  FakeUser(this.uid, this._session);

  @override
  final String uid;
  final FakeSession _session;

  @override
  Future<IdTokenResult> getIdTokenResult([bool forceRefresh = false]) {
    return _session.readToken(forceRefresh);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// The fake Firebase Auth: the attached user, its token behaviour and the
/// auth-state stream.
class FakeSession {
  FakeUser? user;
  final StreamController<User?> _changes = StreamController<User?>.broadcast(
    sync: true,
  );
  int authStateListens = 0;
  int activeAuthStateListeners = 0;

  Map<String, dynamic>? claims = {'appSession': true};

  /// Thrown by a forced refresh (the network / the server).
  Object? refreshError;

  /// Thrown when even the cached token cannot be produced.
  Object? cachedTokenError;

  /// When set, a forced refresh waits for it (slow network).
  Completer<void>? refreshGate;
  int forcedRefreshCalls = 0;

  Future<IdTokenResult> readToken(bool forceRefresh) async {
    if (forceRefresh) {
      forcedRefreshCalls += 1;
      final gate = refreshGate;
      if (gate != null) await gate.future;
      final error = refreshError;
      if (error != null) throw error;
    } else {
      final error = cachedTokenError;
      if (error != null) throw error;
    }
    return FakeIdTokenResult(claims);
  }

  Stream<User?> authStateChanges() {
    authStateListens += 1;
    return Stream<User?>.multi((controller) {
      activeAuthStateListeners += 1;
      controller.add(user);
      final sub = _changes.stream.listen(controller.add);
      controller.onCancel = () {
        activeAuthStateListeners -= 1;
        return sub.cancel();
      };
    });
  }

  void signIn(String uid) {
    user = FakeUser(uid, this);
    _changes.add(user);
  }

  void signOut() {
    user = null;
    _changes.add(null);
  }
}

class FakeAuthService implements AuthService {
  FakeAuthService(this._session);

  final FakeSession _session;
  final Map<String, Map<String, dynamic>?> profiles = {};
  final Set<String> rejoinRestricted = {};
  Object? profileError;
  Completer<void>? profileGate;
  int signOutCalls = 0;
  int profileReads = 0;
  int emailLinkCompletions = 0;
  int emailLinkTokenLookups = 0;

  @override
  Future<Map<String, dynamic>?> getUserProfile(String appUserId) async {
    profileReads += 1;
    final gate = profileGate;
    if (gate != null) await gate.future;
    final error = profileError;
    if (error != null) throw error;
    return profiles[appUserId];
  }

  @override
  Future<bool> isRejoinRestricted(String appUserId) async {
    return rejoinRestricted.contains(appUserId);
  }

  @override
  Future<void> signOutAll() async {
    signOutCalls += 1;
    _session.signOut();
  }

  @override
  bool isSignInWithEmailLink(String link) => link.contains('oobCode=');

  @override
  Future<bool> ensureCanonicalAppSession() async => _session.user != null;

  @override
  Future<String?> getEmailForStudentEmailLinkToken(String token) async {
    emailLinkTokenLookups += 1;
    return null;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) {
    if (invocation.memberName == #completePrimaryStudentEmailLink) {
      emailLinkCompletions += 1;
    }
    return super.noSuchMethod(invocation);
  }
}

class FakeFriendInviteService implements FriendInviteService {
  final List<String> savedTokens = [];

  @override
  Future<PendingInvite?> getPendingInvite() async => null;

  @override
  Future<void> savePendingInvite(PendingInvite invite) async {
    savedTokens.add(invite.token);
  }

  @override
  Future<void> clearPendingInvite() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeAppLinks implements AppLinks {
  Uri? initialLink;
  final StreamController<Uri> links = StreamController<Uri>.broadcast(
    sync: true,
  );
  int streamListens = 0;
  int initialLinkReads = 0;

  @override
  Future<Uri?> getInitialLink() async {
    initialLinkReads += 1;
    return initialLink;
  }

  @override
  Stream<Uri> get uriLinkStream {
    streamListens += 1;
    return links.stream;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const verifiedProfile = <String, dynamic>{
  'isStudentVerified': true,
  'studentEmail': 'someone@yonsei.ac.kr',
  'hasSeenTutorial': true,
};

FirebaseAuthException authError(String code) =>
    FirebaseAuthException(code: code);

class AuthHarness {
  AuthHarness() {
    auth = FakeAuthService(session);
  }

  final FakeSession session = FakeSession();
  late final FakeAuthService auth;
  final FakeFriendInviteService invites = FakeFriendInviteService();
  final FakeAppLinks appLinks = FakeAppLinks();
  final StorageService storage = StorageService();
  final StreamController<String?> kakaoLinks =
      StreamController<String?>.broadcast();
  int kakaoListens = 0;
  int notifications = 0;
  late AuthProvider provider;

  AuthProvider start({
    List<Duration> retryDelays = const [
      Duration(seconds: 1),
      Duration(seconds: 2),
    ],
  }) {
    provider = AuthProvider(
      authService: auth,
      storageService: storage,
      friendInviteService: invites,
      appLinks: appLinks,
      currentFirebaseUser: () => session.user,
      authStateChanges: session.authStateChanges,
      kakaoSchemeLinks: () {
        kakaoListens += 1;
        return kakaoLinks.stream;
      },
      launchDelay: Duration.zero,
      bootstrapRetryDelays: retryDelays,
    )..addListener(() => notifications += 1);
    return provider;
  }

  void signedInAs(String uid, {Map<String, dynamic>? profile}) {
    session.user = FakeUser(uid, session);
    auth.profiles[uid] = profile ?? verifiedProfile;
  }
}

/// Lets queued microtasks, zero timers and SharedPreferences calls run.
Future<void> settleAsync(WidgetTester tester, [Duration? advance]) async {
  if (advance != null) await tester.pump(advance);
  // `pump()` without a duration does not fire zero-delay timers.
  for (var i = 0; i < 6; i++) {
    await tester.pump(Duration.zero);
  }
}
