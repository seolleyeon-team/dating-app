class FestivalAvatarDisplayResolver {
  const FestivalAvatarDisplayResolver._();

  static String resolve(Map<String, dynamic>? profile) {
    if (profile == null) return '';

    final avatar = profile['avatar'];
    if (avatar is Map) {
      final status = avatar['status']?.toString().trim().toLowerCase() ?? '';
      final approved = avatar['approvedAvatarUrl']?.toString().trim() ?? '';
      if (status == 'approved' && isSafeDisplayUrl(approved)) {
        return approved;
      }
    }

    return '';
  }

  static String? resolveNullable(Map<String, dynamic>? profile) {
    final resolved = resolve(profile);
    return resolved.isEmpty ? null : resolved;
  }

  static bool isSafeDisplayUrl(String value) {
    final url = value.trim();
    if (url.isEmpty) return false;
    final decoded = _safeDecode(url).toLowerCase();
    if (decoded.startsWith('gs://') || decoded.startsWith('gcs://')) {
      return false;
    }
    if (RegExp(
      r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)',
    ).hasMatch(decoded)) {
      return false;
    }
    if (decoded.contains('x-goog-') ||
        decoded.contains('x-amz-') ||
        decoded.contains('googleaccessid') ||
        decoded.contains('signature=') ||
        decoded.contains('expires=') ||
        decoded.contains('awsaccesskeyid') ||
        decoded.contains('signedurl')) {
      return false;
    }
    if (decoded.contains('/source/') ||
        decoded.contains('/jobs/') ||
        decoded.contains('/candidates/')) {
      return false;
    }
    final uri = Uri.tryParse(url);
    return uri != null && (uri.scheme == 'https' || uri.scheme == 'http');
  }

  static String _safeDecode(String value) {
    try {
      return Uri.decodeFull(value);
    } on FormatException {
      return value;
    }
  }
}
