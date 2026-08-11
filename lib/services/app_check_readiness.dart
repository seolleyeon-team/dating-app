import 'package:firebase_app_check/firebase_app_check.dart';

import '../shared/utils/privacy_log_utils.dart';

enum AppCheckPreflightStatus { ready, empty, unavailable, rejected }

class AppCheckPreflightResult {
  const AppCheckPreflightResult({
    required this.status,
    this.errorCode,
    this.errorSummary,
  });

  final AppCheckPreflightStatus status;
  final String? errorCode;
  final String? errorSummary;

  bool get isReady => status == AppCheckPreflightStatus.ready;
}

typedef AppCheckTokenProvider = Future<String?> Function(bool forceRefresh);

/// Verifies that the client can obtain an App Check token before invoking a
/// callable that has `enforceAppCheck` enabled.
class AppCheckReadiness {
  const AppCheckReadiness({required this.tokenProvider});

  factory AppCheckReadiness.firebase() {
    return AppCheckReadiness(
      tokenProvider: (forceRefresh) =>
          FirebaseAppCheck.instance.getToken(forceRefresh),
    );
  }

  final AppCheckTokenProvider tokenProvider;

  Future<AppCheckPreflightResult> preflight({bool forceRefresh = true}) async {
    try {
      final token = await tokenProvider(forceRefresh);
      if (token == null || token.trim().isEmpty) {
        return const AppCheckPreflightResult(
          status: AppCheckPreflightStatus.empty,
          errorCode: 'app_check_token_empty',
          errorSummary: 'app_check_token_empty',
        );
      }

      return const AppCheckPreflightResult(
        status: AppCheckPreflightStatus.ready,
      );
    } catch (error) {
      final normalized = _errorText(error);
      final rejected = _isRejected(normalized);
      final errorCode = _errorCode(error, rejected: rejected);
      return AppCheckPreflightResult(
        status: rejected
            ? AppCheckPreflightStatus.rejected
            : AppCheckPreflightStatus.unavailable,
        errorCode: errorCode,
        errorSummary: PrivacyLogUtils.errorSummary(error),
      );
    }
  }

  static String _errorText(Object error) {
    if (error is FirebaseException) {
      return '${error.code} ${error.message ?? ''} ${error.toString()}'
          .toLowerCase();
    }
    return error.toString().toLowerCase();
  }

  static bool _isRejected(String normalizedError) {
    return normalizedError.contains('403') ||
        normalizedError.contains('attestation') ||
        normalizedError.contains('app check rejected') ||
        normalizedError.contains('invalid app check');
  }

  static String _errorCode(Object error, {required bool rejected}) {
    if (error is FirebaseException && error.code.trim().isNotEmpty) {
      return error.code.trim();
    }
    return rejected ? 'app_check_rejected' : 'app_check_unavailable';
  }
}
