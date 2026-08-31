import '../services/onboarding_route_resolver.dart';

/// Ladder of account-setup gates for the Yonsei-email-primary architecture.
///
/// The canonical Seolleyeon session is established ONLY by the verified
/// Yonsei email link (`completePrimaryStudentEmailAuth`). Kakao OAuth is a
/// friend-exclusion authorization step and never authenticates the account.
enum AccountSetupState {
  /// No Firebase session. The user must start from terms → adult
  /// verification → Yonsei email login.
  unauthenticated,

  /// Either an email action link is being consumed, or the session/user doc
  /// does not carry a server-confirmed `isStudentVerified == true` yet.
  emailVerificationPending,

  /// Canonical session exists but the server has not confirmed the PortOne
  /// identity verification (`adultVerified` / `realNameVerified`).
  adultVerificationRequired,

  /// Kakao friend connection has not been linked for this account.
  kakaoConnectionRequired,

  /// Kakao OAuth session exists but the friends scope consent is missing.
  /// (Screen-internal sub-state of the connection flow; the coarse resolver
  /// returns [kakaoConnectionRequired] and the connection screen drives this.)
  kakaoFriendsConsentRequired,

  /// Friends consent given but the Friends API access has not been verified.
  /// (Screen-internal sub-state, see [kakaoFriendsConsentRequired].)
  kakaoFriendsVerificationRequired,

  /// Kakao identity is linked but the initial friend-exclusion sync has not
  /// completed, or the fail-closed `recommendationPrivacyReady` flag is not
  /// true yet.
  initialFriendSyncRequired,

  /// Profile onboarding has remaining required steps.
  onboardingRequired,

  /// Everything except the welcome tutorial is complete.
  tutorialRequired,

  /// Fully set up; the user may enter `/main`.
  complete,
}

bool _isTruthy(Object? value) {
  return value == true || value == 'true' || (value is num && value != 0);
}

/// Pure resolver over server-truth fields of `users/{appUserId}`.
///
/// Gate order (contract §7): session → student email → adult verification →
/// Kakao friend connection → initial friend sync → onboarding → tutorial.
///
/// Grandfather rule: legacy documents WITHOUT a `kakaoFriendConnection` field
/// whose `recommendationPrivacyReady == true` are treated as connected (no
/// forced re-link). Legacy documents that are not privacy-ready must go
/// through `/kakao-friend-connect`.
AccountSetupState resolveAccountSetupState({
  required bool hasFirebaseSession,
  required Map<String, dynamic>? userDoc,
  bool emailLinkPending = false,
  bool adultVerificationDisabled = false,
}) {
  if (!hasFirebaseSession) {
    // While an email action link is being consumed the app must stay on the
    // verification screen instead of restarting the login funnel.
    return emailLinkPending
        ? AccountSetupState.emailVerificationPending
        : AccountSetupState.unauthenticated;
  }

  // A canonical session without a readable user document is treated as an
  // incomplete primary auth: the email completion callable is the only place
  // that creates the shell, so fail closed toward re-verification.
  if (userDoc == null || userDoc['isStudentVerified'] != true) {
    return AccountSetupState.emailVerificationPending;
  }

  final adultVerified =
      userDoc['adultVerified'] == true && userDoc['realNameVerified'] == true;
  if (!adultVerificationDisabled && !adultVerified) {
    return AccountSetupState.adultVerificationRequired;
  }

  final recommendationPrivacyReady =
      userDoc['recommendationPrivacyReady'] == true;
  final rawConnection = userDoc['kakaoFriendConnection'];
  if (rawConnection is Map) {
    if (rawConnection['connected'] != true) {
      return AccountSetupState.kakaoConnectionRequired;
    }
    if (rawConnection['initialSyncComplete'] != true ||
        !recommendationPrivacyReady) {
      return AccountSetupState.initialFriendSyncRequired;
    }
  } else {
    // GRANDFATHER: legacy accounts have no kakaoFriendConnection field. Only
    // the fail-closed recommendationPrivacyReady flag proves an effective
    // friend connection; otherwise they must link via /kakao-friend-connect.
    if (!recommendationPrivacyReady) {
      return AccountSetupState.kakaoConnectionRequired;
    }
  }

  final initialSetupComplete = _isTruthy(userDoc['initialSetupComplete']);
  if (!initialSetupComplete && resolveOnboardingNextRoute(userDoc) != null) {
    return AccountSetupState.onboardingRequired;
  }

  if (userDoc['hasSeenTutorial'] != true) {
    return AccountSetupState.tutorialRequired;
  }

  return AccountSetupState.complete;
}
