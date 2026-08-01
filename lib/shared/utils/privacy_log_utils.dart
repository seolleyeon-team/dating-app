import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:crypto/crypto.dart';

class PrivacyLogUtils {
  static const int _fingerprintLength = 12;

  const PrivacyLogUtils._();

  static String idFingerprint(String? value) =>
      _fingerprint('id', value, emptyLabel: 'id=empty');

  static String pathFingerprint(String? value) =>
      _fingerprint('path', value, emptyLabel: 'path=empty');

  static String errorSummary(Object error) {
    final type = error.runtimeType.toString();
    if (error is FirebaseException) {
      return 'errorType=$type code=${error.code}';
    }
    return 'errorType=$type';
  }

  static String _fingerprint(
    String label,
    String? value, {
    required String emptyLabel,
  }) {
    final normalized = value?.trim();
    if (normalized == null || normalized.isEmpty) return emptyLabel;

    final digest = sha256.convert(utf8.encode(normalized)).toString();
    return '${label}Hash=${digest.substring(0, _fingerprintLength)}';
  }
}
