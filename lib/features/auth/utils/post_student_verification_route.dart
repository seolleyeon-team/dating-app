import '../../../router/route_names.dart';

/// Resolves the next screen after a server-confirmed Yonsei email verification.
///
/// `initialSetupComplete` is read from the user's Firestore document. For
/// legacy documents without that marker, a null [nextOnboardingRoute] means
/// every required step is already present in Firestore.
String resolvePostStudentVerificationRoute({
  required bool initialSetupComplete,
  String? nextOnboardingRoute,
}) {
  if (initialSetupComplete || nextOnboardingRoute == null) {
    return RouteNames.main;
  }
  return nextOnboardingRoute;
}
