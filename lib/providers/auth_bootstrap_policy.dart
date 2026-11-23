import 'package:firebase_core/firebase_core.dart' show FirebaseException;

/// Where the launch-time session resolution of `AuthProvider` stands.
///
/// "Signed out" is not a phase: it is [ready] with `isAuthenticated == false`.
enum AuthBootstrapPhase {
  /// The first resolution has not finished yet.
  initializing,

  /// Resolved. `isAuthenticated` is final until the next login / logout.
  ready,

  /// A Firebase session IS attached, but it could not be verified or
  /// hydrated because of a transient failure (offline, timeout, backend
  /// error). The session is kept, a bounded retry is running, and
  /// `AuthProvider.retryBootstrap()` retries immediately. The UI must offer
  /// a retry here instead of sending the user to the login funnel.
  retryableError,
}

enum AuthBootstrapFailure {
  /// Worth retrying. Never a reason to sign the user out.
  transient,

  /// The server says this session is over (revoked, disabled or deleted
  /// account). The only failure that ends the session.
  sessionInvalid,
}

/// Firebase Auth error codes that mean the refresh token itself is dead.
const Set<String> _sessionInvalidCodes = {
  'user-token-expired',
  'user-token-revoked',
  'invalid-user-token',
  'invalid-refresh-token',
  'user-disabled',
  'user-not-found',
  'no-current-user',
};

/// Classifies a failure seen while resolving the launch session.
///
/// Everything that is not an explicit "this session is over" answer from
/// Firebase Auth is transient: a network error, a timeout, a Firestore
/// `unavailable`, an App Check hiccup or an unexpected exception must never
/// sign the user out.
AuthBootstrapFailure classifyAuthBootstrapFailure(Object error) {
  if (error is FirebaseException) {
    var code = error.code.trim().toLowerCase();
    if (code.startsWith('auth/')) code = code.substring('auth/'.length);
    if (_sessionInvalidCodes.contains(code)) {
      return AuthBootstrapFailure.sessionInvalid;
    }
  }
  return AuthBootstrapFailure.transient;
}

/// Delays between automatic re-resolutions after a transient failure. The
/// list length is the retry budget; after it is spent only an app resume or
/// an explicit `retryBootstrap()` tries again.
const List<Duration> defaultAuthBootstrapRetryDelays = [
  Duration(seconds: 2),
  Duration(seconds: 5),
  Duration(seconds: 15),
  Duration(seconds: 30),
  Duration(seconds: 60),
];
