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

String _mobileHostingOrigin(String firebaseProjectId) {
  if (firebaseProjectId == 'seolleyeon-final') {
    return 'https://seolleyeon-final.web.app';
  }
  return 'https://seolleyeon.web.app';
}
