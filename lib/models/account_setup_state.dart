import '../constants/legal_texts.dart';
import '../services/onboarding_route_resolver.dart';

/// Ladder of account-setup gates for the Yonsei-email-primary architecture.
///
/// The canonical Seolleyeon session is established ONLY by the verified
/// Yonsei email link (`completePrimaryStudentEmailAuth`). Kakao OAuth is a
/// friend-exclusion authorization step and never authenticates the account.
enum AccountSetupState {
  /// No Firebase session. The user must start from terms → Yonsei email
  /// login → canonical session → adult verification.
  unauthenticated,

  /// Either an email action link is being consumed, or the session/user doc
  /// does not carry a server-confirmed `isStudentVerified == true` yet.
  emailVerificationPending,

  /// The account carries no acceptance of the CURRENT `LegalTexts.version`
  /// (terms-gate contract §7). Routes back to `RouteNames.terms`, where an
  /// authenticated user re-consents through `recordTermsAcceptance`.
  termsAcceptanceRequired,

  /// Canonical session exists but the server has not confirmed the PortOne
  /// identity verification (`adultVerified` / `realNameVerified`).
  adultVerificationRequired,

  /// Kakao friend connection has not been linked for this account.
  kakaoConnectionRequired,

  /// Kakao OAuth session exists but the friends scope consent is missing.
  /// (Screen-internal sub-state of the connection flow; the coarse resolver
  /// returns [kakaoConnectionRequired] and the connection screen drives this.)
  kakaoFriendsConsentRequired,

  /// Kakao identity is linked but the ONE-TIME server friend snapshot
  /// (`users/{uid}.kakaoFriendSnapshot.status == "completed"`) has not
  /// completed yet (kakao-friend-pairs contract §3/§8).
  kakaoFriendSnapshotRequired,

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

/// Reads a `version` string out of a consent map, tolerating a missing or
/// wrongly-typed field (both mean "no usable acceptance").
String? _consentVersion(Object? raw) {
  if (raw is! Map) return null;
  final version = raw['version']?.toString().trim() ?? '';
  return version.isEmpty ? null : version;
}

/// Pure resolver over server-truth fields of `users/{appUserId}`.
///
/// Gate order (kakao-friend-pairs contract §8 + terms-gate contract §7):
/// session → student email → TERMS ACCEPTANCE → adult verification →
/// Kakao friend connection → one-time friend snapshot → onboarding →
/// tutorial.
///
/// GRANDFATHER / MIGRATION GATE (spec §30): legacy documents without a
/// `kakaoFriendConnection` map and/or without a `kakaoFriendSnapshot` field
/// resolve to the connection/snapshot gate ONCE, regardless of the legacy
/// `recommendationPrivacyReady` flag — that flag is no longer consulted
/// anywhere in this resolver. The connection screen runs consent-check →
/// link (idempotent) → snapshot-once, and after `status == "completed"` the
/// gate never re-triggers (a completed snapshot is immutable; no re-fetch).
/// Migration never re-requests profile onboarding.
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

  // TERMS GATE (terms-gate contract §7). The server-owned `termsAcceptance`
  // record is the ONLY authority. `legalConsents` is a client-writable UX
  // receipt — three firestore.rules allowlists let the owner rewrite it at
  // will — so it can never satisfy a security gate, not even for legacy
  // accounts. An account without the server record re-consents once; that
  // writes `termsAcceptance` and touches nothing else, so the profile, Kakao
  // identity, friend snapshot, and onboarding all survive untouched.
  final acceptedVersion = _consentVersion(userDoc['termsAcceptance']);
  if (acceptedVersion != LegalTexts.version) {
    return AccountSetupState.termsAcceptanceRequired;
  }

  final adultVerified =
      userDoc['adultVerified'] == true && userDoc['realNameVerified'] == true;
  if (!adultVerificationDisabled && !adultVerified) {
    return AccountSetupState.adultVerificationRequired;
  }

  final rawConnection = userDoc['kakaoFriendConnection'];
  final connected = rawConnection is Map && rawConnection['connected'] == true;
  if (!connected) {
    // Covers both new accounts and legacy docs without the field (migration
    // gate) — fail closed toward /kakao-friend-connect.
    return AccountSetupState.kakaoConnectionRequired;
  }

  final rawSnapshot = userDoc['kakaoFriendSnapshot'];
  final snapshotCompleted =
      rawSnapshot is Map && rawSnapshot['status'] == 'completed';
  if (!snapshotCompleted) {
    // Missing field == not_started (legacy migration) and in_progress/failed
    // both stay gated until the server records the one-time completion.
    return AccountSetupState.kakaoFriendSnapshotRequired;
  }

  // `hasSeenTutorial` is also a durable proof that onboarding was crossed:
  // the tutorial is only reachable after onboarding. This repairs accounts
  // created by older clients that entered the main screen but failed to save
  // `initialSetupComplete` (commonly while avatar generation was unfinished).
  // Without this compatibility rule those users are sent back to the photo
  // step on every cold start even though they already finished the journey.
  final hasSeenTutorial = userDoc['hasSeenTutorial'] == true;
  final initialSetupComplete =
      _isTruthy(userDoc['initialSetupComplete']) || hasSeenTutorial;
  if (!initialSetupComplete && resolveOnboardingNextRoute(userDoc) != null) {
    return AccountSetupState.onboardingRequired;
  }

  if (!hasSeenTutorial) {
    return AccountSetupState.tutorialRequired;
  }

  return AccountSetupState.complete;
}
