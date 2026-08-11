/// The outcome of checking whether the current Firebase user belongs to the
/// Kakao identity that the caller is about to use.
enum FirebaseSessionIdentityState {
  noSession,
  matching,
  mismatched,
  inspectionFailed,
}

class FirebaseSessionInspection {
  const FirebaseSessionInspection({
    required this.state,
    this.firebaseUid,
    this.claimedKakaoUserId,
    this.error,
  });

  final FirebaseSessionIdentityState state;
  final String? firebaseUid;
  final String? claimedKakaoUserId;

  /// Kept for in-process diagnostics only. Callers must not print it raw.
  final Object? error;
}

typedef FirebaseTokenClaimsLoader =
    Future<Map<String, dynamic>?> Function(bool forceRefresh);

/// Classifies a Firebase session without coupling the decision to FirebaseAuth.
///
/// A UID match is the strong identity contract used by the custom-token
/// bridge. Claims are loaded only for legacy sessions whose UID differs. A
/// token refresh failure is deliberately distinct from an actual mismatch so
/// callers can fail closed without signing out a possibly valid session.
class FirebaseSessionInspector {
  const FirebaseSessionInspector();

  Future<FirebaseSessionInspection> inspect({
    required String expectedKakaoUserId,
    required String? currentUid,
    required FirebaseTokenClaimsLoader loadClaims,
  }) async {
    final expected = expectedKakaoUserId.trim();
    final firebaseUid = currentUid?.trim() ?? '';

    if (firebaseUid.isEmpty) {
      return const FirebaseSessionInspection(
        state: FirebaseSessionIdentityState.noSession,
      );
    }

    if (firebaseUid == expected) {
      return FirebaseSessionInspection(
        state: FirebaseSessionIdentityState.matching,
        firebaseUid: firebaseUid,
      );
    }

    try {
      final claims = await loadClaims(true);
      final claimedKakaoUserId =
          claims?['kakaoUserId']?.toString().trim() ?? '';
      final state = claimedKakaoUserId == expected
          ? FirebaseSessionIdentityState.matching
          : FirebaseSessionIdentityState.mismatched;

      return FirebaseSessionInspection(
        state: state,
        firebaseUid: firebaseUid,
        claimedKakaoUserId: claimedKakaoUserId,
      );
    } catch (error) {
      return FirebaseSessionInspection(
        state: FirebaseSessionIdentityState.inspectionFailed,
        firebaseUid: firebaseUid,
        error: error,
      );
    }
  }
}
