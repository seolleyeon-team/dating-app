import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart' show debugPrint;

import '../models/account_setup_state.dart';
import '../router/route_names.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'adult_verification_service.dart';
import 'auth_service.dart';
import 'storage_service.dart';

/// Post-auth setup orchestration for the Yonsei-email-primary flow.
///
/// Reads server truth (`users/{uid}` where uid == appUserId) and resolves the
/// next gate through the pure [resolveAccountSetupState] ladder. All screens
/// (splash, email login, kakao friend connect) route through this so no deep
/// link can reach `/main` before the ladder returns [AccountSetupState.complete].
class AccountSetupFlow {
  AccountSetupFlow({
    AuthService? authService,
    AdultVerificationService? adultVerificationService,
    StorageService? storageService,
    FirebaseAuth? firebaseAuth,
  }) : _authService = authService ?? AuthService(),
       _adultVerificationService =
           adultVerificationService ?? AdultVerificationService(),
       _storageService = storageService ?? StorageService(),
       _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final AuthService _authService;
  final AdultVerificationService _adultVerificationService;
  final StorageService _storageService;
  final FirebaseAuth _firebaseAuth;

  String? get currentAppUserId => _firebaseAuth.currentUser?.uid;

  /// Resolves the current setup gate from the canonical session + server doc.
  Future<AccountSetupState> resolveCurrentState({
    bool emailLinkPending = false,
  }) async {
    final uid = _firebaseAuth.currentUser?.uid;
    if (uid == null || uid.isEmpty) {
      return resolveAccountSetupState(
        hasFirebaseSession: false,
        userDoc: null,
        emailLinkPending: emailLinkPending,
        adultVerificationDisabled:
            AdultVerificationService.isTemporarilyDisabled,
      );
    }

    Map<String, dynamic>? userDoc;
    try {
      userDoc = await _authService.getUserProfile(uid);
    } catch (e) {
      debugPrint(
        '[SetupFlow] users read failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
      userDoc = null;
    }
    return resolveAccountSetupState(
      hasFirebaseSession: true,
      userDoc: userDoc,
      emailLinkPending: emailLinkPending,
      adultVerificationDisabled: AdultVerificationService.isTemporarilyDisabled,
    );
  }

  /// Maps a resolved state to the route the app should show next.
  ///
  /// `onboardingRequired` resolves the concrete next onboarding step from the
  /// server profile (via the untouched onboarding resolver).
  Future<String> routeForState(AccountSetupState state) async {
    switch (state) {
      case AccountSetupState.unauthenticated:
        return RouteNames.terms;
      case AccountSetupState.emailVerificationPending:
        return RouteNames.studentVerification;
      case AccountSetupState.adultVerificationRequired:
        return RouteNames.adultVerification;
      case AccountSetupState.kakaoConnectionRequired:
      case AccountSetupState.kakaoFriendsConsentRequired:
      case AccountSetupState.kakaoFriendSnapshotRequired:
        return RouteNames.kakaoFriendConnect;
      case AccountSetupState.onboardingRequired:
        final uid = currentAppUserId;
        final nextRoute = uid == null
            ? null
            : await _authService.getOnboardingNextRoute(uid);
        return nextRoute ?? RouteNames.onboardingBasicInfo;
      case AccountSetupState.tutorialRequired:
        return RouteNames.welcomeTutorial;
      case AccountSetupState.complete:
        return RouteNames.main;
    }
  }

  /// Convenience: resolve + map in one step.
  Future<String> resolveNextRoute({bool emailLinkPending = false}) async {
    final state = await resolveCurrentState(emailLinkPending: emailLinkPending);
    return routeForState(state);
  }

  /// Confirms the locally pending PortOne identity-verification session after
  /// the canonical email session is established (moved here from the deleted
  /// Kakao login screen's `_verifyAdultIdentityAfterKakaoLogin`).
  ///
  /// Unlike the legacy Kakao flow this does NOT sign the user out on failure:
  /// the canonical session is required to retry the server confirmation, and
  /// the setup ladder keeps the account gated at `/adult-verification` until
  /// the server confirms `adultVerified`.
  Future<bool> confirmPendingAdultVerificationIfNeeded() async {
    if (AdultVerificationService.isTemporarilyDisabled) return true;

    final uid = currentAppUserId;
    if (uid == null || uid.isEmpty) return false;

    try {
      if (await _authService.isAdultVerified(uid)) {
        return true;
      }
    } catch (e) {
      debugPrint(
        '[SetupFlow] adult verified read failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }

    final pending = await _adultVerificationService.getPendingSession();
    if (!pending.canProceedToKakao) {
      // No usable local PortOne result. The ladder routes the user to the
      // adult verification gate with the session kept.
      return false;
    }

    final result = await _adultVerificationService
        .verifyPendingSessionAfterLogin();
    return result.isVerified;
  }

  /// Flushes the terms-screen consents recorded before login onto the
  /// server-confirmed account (was post-Kakao-login; now post-email-auth).
  Future<void> flushPendingLegalConsents() async {
    final uid = currentAppUserId;
    if (uid == null || uid.isEmpty) return;
    try {
      await _authService.syncPendingLegalConsents(uid);
    } catch (e) {
      debugPrint(
        '[SetupFlow] legal consent flush failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  /// Rejoin-restriction guard for an attached session. When restricted the
  /// session and local identity are cleared and a notice is queued.
  /// Returns true when the account is restricted (caller must stop).
  Future<bool> handleRejoinRestriction() async {
    final uid = currentAppUserId;
    if (uid == null || uid.isEmpty) return false;

    final restricted = await _authService.isRejoinRestricted(uid);
    if (!restricted) return false;

    await _storageService.savePendingRejoinRestrictionNotice();
    await _authService.signOutAll();
    await _storageService.clearUserId();
    await _storageService.clearAppUserId();
    await _storageService.clearStudentVerification(uid);
    return true;
  }
}
