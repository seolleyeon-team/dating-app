import 'package:firebase_app_check/firebase_app_check.dart';

import '../shared/utils/privacy_log_utils.dart';

enum AppCheckPreflightStatus { ready, empty, unavailable, rejected }

class AppCheckPreflightResult {
  const AppCheckPreflightResult({
    required this.status,
    this.errorCode,
    this.errorSummary,
    this.diagnosticSummary,
    this.firebasePlugin,
    this.httpStatus,
    this.responseBodySummary,
    this.stackTraceSummary,
    this.supportCode,
  });

  final AppCheckPreflightStatus status;
  final String? errorCode;
  final String? errorSummary;

  /// A redacted provider error summary. It is only rendered by the explicit
  /// internal-test diagnostic build and must never include an App Check token.
  final String? diagnosticSummary;
  final String? firebasePlugin;
  final String? httpStatus;
  final String? responseBodySummary;
  final String? stackTraceSummary;
  final String? supportCode;

  bool get isReady => status == AppCheckPreflightStatus.ready;
}

typedef AppCheckTokenProvider = Future<String?> Function(bool forceRefresh);

/// Verifies that the client can obtain an App Check token before invoking a
/// callable that has `enforceAppCheck` enabled.
class AppCheckReadiness {
  AppCheckReadiness({required this.tokenProvider});

  factory AppCheckReadiness.firebase() {
    return AppCheckReadiness(
      tokenProvider: (forceRefresh) =>
          FirebaseAppCheck.instance.getToken(forceRefresh),
    );
  }

  final AppCheckTokenProvider tokenProvider;
  Future<AppCheckPreflightResult>? _inFlight;

  /// Reuses Firebase's cached token by default and shares an active request.
  ///
  /// Forced refreshes consume Play Integrity/App Check quota and should only
  /// be used for an explicit diagnostic action, not for every login attempt.
  Future<AppCheckPreflightResult> preflight({bool forceRefresh = false}) {
    final active = _inFlight;
    if (active != null) return active;

    final request = _requestToken(forceRefresh: forceRefresh);
    _inFlight = request;
    request.whenComplete(() {
      if (identical(_inFlight, request)) {
        _inFlight = null;
      }
    });
    return request;
  }

  Future<AppCheckPreflightResult> _requestToken({
    required bool forceRefresh,
  }) async {
    try {
      final token = await tokenProvider(forceRefresh);
      if (token == null || token.trim().isEmpty) {
        return const AppCheckPreflightResult(
          status: AppCheckPreflightStatus.empty,
          errorCode: 'app_check_token_empty',
          errorSummary: 'app_check_token_empty',
          supportCode: 'AC-E-TOKEN-EMPTY',
        );
      }

      return const AppCheckPreflightResult(
        status: AppCheckPreflightStatus.ready,
      );
    } catch (error, stackTrace) {
      final normalized = _errorText(error);
      final rejected = _isRejected(normalized);
      final errorCode = _errorCode(error, rejected: rejected);
      return AppCheckPreflightResult(
        status: rejected
            ? AppCheckPreflightStatus.rejected
            : AppCheckPreflightStatus.unavailable,
        errorCode: errorCode,
        errorSummary: PrivacyLogUtils.errorSummary(error),
        diagnosticSummary: _diagnosticSummary(error),
        firebasePlugin: error is FirebaseException ? error.plugin : null,
        httpStatus: _httpStatus(normalized),
        responseBodySummary: _responseBodySummary(error),
        stackTraceSummary: _stackTraceSummary(stackTrace),
        supportCode: _supportCode(
          normalized,
          errorCode: errorCode,
          rejected: rejected,
        ),
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

  static String _diagnosticSummary(Object error) {
    final type = error.runtimeType.toString();
    final raw = error is FirebaseException
        ? 'firebaseCode=${error.code}; plugin=${error.plugin}; '
              'message=${error.message ?? ''}'
        : error.toString();
    final redacted = raw
        .replaceAllMapped(
          RegExp(
            r'(token|authorization|bearer)\s*[:=]\s*[^\s,;]+',
            caseSensitive: false,
          ),
          (match) => '${match.group(1)}=[redacted]',
        )
        .replaceAll(
          RegExp(r'[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}'),
          '[redacted-jwt]',
        )
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    final truncated = redacted.length <= 280
        ? redacted
        : '${redacted.substring(0, 280)}…';
    return 'errorType=$type; $truncated';
  }

  static String? _httpStatus(String normalizedError) {
    final match = RegExp(r'\bcode:\s*(\d{3})\b').firstMatch(normalizedError);
    return match?.group(1);
  }

  static String? _responseBodySummary(Object error) {
    final message = error is FirebaseException
        ? error.message
        : error.toString();
    final match = RegExp(
      r'body:\s*(.+)',
      caseSensitive: false,
    ).firstMatch(message ?? '');
    if (match == null) return null;
    return _redactAndTruncate(match.group(1) ?? '', maxLength: 180);
  }

  static String _stackTraceSummary(StackTrace stackTrace) {
    return _redactAndTruncate(
      stackTrace.toString().split('\n').take(4).join(' | '),
      maxLength: 360,
    );
  }

  static String _redactAndTruncate(String value, {required int maxLength}) {
    final redacted = value
        .replaceAllMapped(
          RegExp(
            r'(token|authorization|bearer)\s*[:=]\s*[^\s,;]+',
            caseSensitive: false,
          ),
          (match) => '${match.group(1)}=[redacted]',
        )
        .replaceAll(
          RegExp(r'[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}'),
          '[redacted-jwt]',
        )
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    return redacted.length <= maxLength
        ? redacted
        : '${redacted.substring(0, maxLength)}…';
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

  /// Returns a stable, non-sensitive code that a remote tester can report.
  /// Provider messages are deliberately classified instead of displayed.
  static String _supportCode(
    String normalizedError, {
    required String errorCode,
    required bool rejected,
  }) {
    // A provider can describe a rejected attestation and rate limiting in the
    // same error. Prefer the actionable temporary limit in that case.
    if (normalizedError.contains('too many requests') ||
        normalizedError.contains('too many attempts') ||
        normalizedError.contains('rate limit')) {
      return 'AC-U-RATE-LIMITED';
    }
    if (rejected) return 'AC-R-ATTESTATION';

    const classifications = <(List<String>, String)>[
      (['network'], 'AC-U-NETWORK'),
      (
        ['play_store_account_not_found', 'play store account not found'],
        'AC-U-PLAY-ACCOUNT',
      ),
      (
        ['play_store_not_found', 'play store not found'],
        'AC-U-PLAY-STORE-MISSING',
      ),
      (
        ['app_not_installed', 'app not installed by google play'],
        'AC-U-NOT-PLAY-INSTALL',
      ),
      (['app_uid_mismatch', 'app uid mismatch'], 'AC-U-APP-UID'),
      (
        ['play_services_version_outdated', 'play services version outdated'],
        'AC-U-PLAY-SERVICES-OLD',
      ),
      (
        ['play_store_version_outdated', 'play store version outdated'],
        'AC-U-PLAY-STORE-OLD',
      ),
      (
        ['cloud_project_number_is_invalid', 'cloud project number is invalid'],
        'AC-U-CLOUD-PROJECT',
      ),
      (['api_not_available', 'api not available'], 'AC-U-API-UNAVAILABLE'),
      (['cannot_bind_to_service', 'cannot bind to service'], 'AC-U-BIND'),
      (
        ['google_server_unavailable', 'google server unavailable'],
        'AC-U-GOOGLE-SERVER',
      ),
      (
        ['client_transient_error', 'client transient error'],
        'AC-U-CLIENT-TRANSIENT',
      ),
    ];

    for (final (needles, supportCode) in classifications) {
      if (needles.any(normalizedError.contains)) return supportCode;
    }

    final safeErrorCode = errorCode
        .trim()
        .toUpperCase()
        .replaceAll(RegExp(r'[^A-Z0-9]+'), '-')
        .replaceAll(RegExp(r'^-+|-+$'), '');
    if (safeErrorCode.isEmpty) return 'AC-U-UNKNOWN';
    final truncated = safeErrorCode.length <= 32
        ? safeErrorCode
        : safeErrorCode.substring(0, 32);
    return 'AC-U-$truncated';
  }
}
