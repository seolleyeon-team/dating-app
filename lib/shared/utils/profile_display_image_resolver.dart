class ProfileDisplayImageResolver {
  static String resolve(Map<String, dynamic>? profile) {
    if (profile == null) return '';

    final avatar = profile['avatar'];
    if (avatar is Map) {
      final status = avatar['status']?.toString();
      final approved = avatar['approvedAvatarUrl']?.toString().trim() ?? '';
      if (status == 'approved' && _isDisplaySafe(approved)) {
        return approved;
      }
    }

    final onboarding = profile['onboarding'];
    if (onboarding is Map) {
      final avatarUrls = onboarding['avatarUrls'];
      if (avatarUrls is List && avatarUrls.isNotEmpty) {
        final first = avatarUrls.first?.toString().trim() ?? '';
        if (_isDisplaySafe(first)) return first;
      }
    }

    return '';
  }

  static String? resolveNullable(Map<String, dynamic>? profile) {
    final resolved = resolve(profile);
    return resolved.isEmpty ? null : resolved;
  }

  static bool _isDisplaySafe(String value) {
    if (value.isEmpty) return false;
    final decodedLowerValue = _safeDecode(value).toLowerCase();
    if (decodedLowerValue.startsWith('gs://') ||
        decodedLowerValue.startsWith('gcs://')) {
      return false;
    }
    if (RegExp(
      r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)',
    ).hasMatch(decodedLowerValue)) {
      return false;
    }
    if (decodedLowerValue.contains('x-goog-') ||
        decodedLowerValue.contains('x-amz-') ||
        decodedLowerValue.contains('googleaccessid') ||
        decodedLowerValue.contains('signature=') ||
        decodedLowerValue.contains('expires=') ||
        decodedLowerValue.contains('awsaccesskeyid') ||
        decodedLowerValue.contains('signedurl')) {
      return false;
    }
    if (decodedLowerValue.contains('/source/') ||
        decodedLowerValue.contains('/jobs/') ||
        decodedLowerValue.contains('/candidates/')) {
      return false;
    }
    final uri = Uri.tryParse(value);
    if (uri == null) return false;
    final host = uri.host.toLowerCase();
    final path = Uri.decodeFull(uri.path).toLowerCase();
    final bucketFromVirtualHost = host.endsWith('.storage.googleapis.com')
        ? host.replaceFirst('.storage.googleapis.com', '')
        : '';
    if (bucketFromVirtualHost.isNotEmpty &&
        RegExp(
          r'seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)',
        ).hasMatch(bucketFromVirtualHost)) {
      return false;
    }
    if ((host == 'storage.googleapis.com' ||
            host == 'firebasestorage.googleapis.com') &&
        (path.contains('/source/') ||
            path.contains('/jobs/') ||
            path.contains('/candidates/'))) {
      return false;
    }
    return true;
  }

  static String _safeDecode(String value) {
    try {
      return Uri.decodeFull(value);
    } on FormatException {
      return value;
    }
  }
}
