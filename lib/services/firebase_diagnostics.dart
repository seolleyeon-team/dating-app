import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

class FirebaseDiagnostics {
  const FirebaseDiagnostics._();

  static void logCurrentFirebaseApp(String phase) {
    if (kReleaseMode) return;

    try {
      final app = Firebase.app();
      final options = app.options;
      debugPrint(
        '[FirebaseDiag] phase=$phase '
        'projectId=${options.projectId} '
        'appId=${options.appId} '
        'apiKeyPrefix=${_prefix(options.apiKey)} '
        'authProjectId=${FirebaseAuth.instance.app.options.projectId}',
      );
    } catch (e) {
      debugPrint('[FirebaseDiag] phase=$phase error=${_safeError(e)}');
    }
  }

  static void logAuthBridgePhase(
    String phase, {
    String functionName = 'createFirebaseCustomToken',
    String region = 'asia-northeast3',
    String? kakaoUserId,
    Object? error,
    StackTrace? stackTrace,
  }) {
    if (kReleaseMode) return;

    String projectId = 'unknown';
    String appId = 'unknown';
    String? firebaseUid;
    try {
      final app = Firebase.app();
      projectId = app.options.projectId;
      appId = app.options.appId;
      firebaseUid = FirebaseAuth.instance.currentUser?.uid;
    } catch (_) {
      // Firebase may not be initialized when an early diagnostic is emitted.
    }

    final parts = <String>[
      '[AuthDiag]',
      'phase=$phase',
      'projectId=$projectId',
      'appId=$appId',
      'firebaseUid=${firebaseUid ?? 'null'}',
      'kakaoUserId=${kakaoUserId ?? 'null'}',
      'function=$functionName',
      'region=$region',
    ];

    if (error != null) {
      parts.addAll(_errorParts(error));
    }

    debugPrint(parts.join(' '));
    if (stackTrace != null) {
      debugPrint(stackTrace.toString());
    }
  }

  static List<String> _errorParts(Object error) {
    if (error is FirebaseFunctionsException) {
      return [
        'callableCode=${error.code}',
        'callableMessage=${_safeError(error.message)}',
      ];
    }
    if (error is FirebaseAuthException) {
      return [
        'authCode=${error.code}',
        'authMessage=${_safeError(error.message)}',
        'plugin=${error.plugin}',
      ];
    }
    return ['error=${_safeError(error)}'];
  }

  static String safeErrorForLog(Object? value) => _safeError(value);

  static String _prefix(String value) {
    if (value.length <= 6) return '<redacted>';
    return '${value.substring(0, 6)}...';
  }

  static String _safeError(Object? value) {
    final raw = value?.toString() ?? '';
    return raw
        .replaceAll(
          RegExp(r'Bearer\s+[A-Za-z0-9._~+/=-]+'),
          'Bearer <redacted>',
        )
        .replaceAll(
          RegExp(r'access[_-]?token[=:]\s*[^,\s}]+', caseSensitive: false),
          'accessToken=<redacted>',
        )
        .replaceAll(
          RegExp(r'custom[_-]?token[=:]\s*[^,\s}]+', caseSensitive: false),
          'customToken=<redacted>',
        )
        .replaceAll(
          RegExp(
            r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',
            caseSensitive: false,
          ),
          '<redacted-email>',
        )
        .replaceAll(
          RegExp(
            r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
            caseSensitive: false,
          ),
          '<redacted-id>',
        )
        .replaceAllMapped(
          RegExp(
            r'([?&](?:apiKey|oobCode|code|state|t)=)[^&\s]+',
            caseSensitive: false,
          ),
          (match) => '${match.group(1)}<redacted>',
        );
  }
}
