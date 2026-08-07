String buildStudentEmailLinkContinueUrl({
  required String token,
  required bool isWeb,
  required String webOrigin,
  required String firebaseProjectId,
}) {
  final origin = isWeb ? webOrigin : _mobileHostingOrigin(firebaseProjectId);
  return Uri.parse(
    origin,
  ).replace(path: '/auth/email-link', queryParameters: {'t': token}).toString();
}

/// Extracts the opaque binding token from either the final app URL or the
/// Firebase action URL's nested continueUrl.
String? extractStudentEmailLinkToken(String link) {
  final uri = Uri.tryParse(link);
  if (uri == null) return null;

  final direct = uri.queryParameters['t']?.trim();
  if (direct != null && direct.isNotEmpty) return direct;

  final continueUrl = uri.queryParameters['continueUrl'];
  if (continueUrl == null || continueUrl.isEmpty) return null;
  final nestedUri = Uri.tryParse(continueUrl);
  final nested = nestedUri?.queryParameters['t']?.trim();
  return nested == null || nested.isEmpty ? null : nested;
}

/// Recognizes the app continuation URL even when Firebase has not appended its
/// action parameters yet. It is used only for routing; actual completion still
/// requires FirebaseAuth.isSignInWithEmailLink.
bool isStudentEmailLinkContinuation(Uri uri) {
  final path = uri.path;
  final isContinuationPath =
      path == '/auth/email-link' || path.endsWith('/auth/email-link');
  return isContinuationPath &&
      extractStudentEmailLinkToken(uri.toString()) != null;
}

String _mobileHostingOrigin(String firebaseProjectId) {
  if (firebaseProjectId == 'seolleyeon-final') {
    return 'https://seolleyeon-final.web.app';
  }
  return 'https://seolleyeon.web.app';
}
