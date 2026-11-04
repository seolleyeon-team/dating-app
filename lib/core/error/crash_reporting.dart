import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/foundation.dart';

import '../../shared/utils/privacy_log_utils.dart';

/// P1-6 — production crash and error reporting.
///
/// One facade owns every error sink so an exception is recorded exactly once:
///   * `FlutterError.onError` — framework errors (build / layout / gesture),
///     recorded as non-fatal;
///   * `PlatformDispatcher.instance.onError` — uncaught asynchronous errors
///     outside the root zone, recorded as fatal;
///   * the `runZonedGuarded` handler in `main.dart` → [recordZoneError];
///   * explicit `ErrorHandler.logError` calls → [recordNonFatal].
///
/// Privacy: the raw exception is never sent. Crashlytics receives a
/// [SanitizedCrashError] that carries only the runtime type and the
/// `PrivacyLogUtils.errorSummary` (type + Firebase error code), plus the stack
/// trace. Student emails, tokens, chat text, phone numbers and profile data
/// that exception messages sometimes embed therefore stay on the device.
///
/// Collection is enabled only for release builds on Android / iOS. Debug and
/// profile builds, tests and web keep the handlers (so the behaviour is the
/// same) but print locally instead of uploading.
class CrashReporting {
  CrashReporting._();

  static final CrashReporting instance = CrashReporting._();

  static const int _maxRememberedErrors = 256;

  FirebaseCrashlytics? _crashlytics;
  bool _installed = false;
  bool _collectionEnabled = false;
  final List<int> _reportedErrorIds = <int>[];

  bool get isInstalled => _installed;
  bool get isCollectionEnabled => _collectionEnabled;

  /// Wires the global handlers. Safe to call before Firebase is initialised
  /// (Crashlytics is then unavailable and errors are only printed) and safe
  /// to call twice (the second call is a no-op).
  Future<void> install({bool? enableCollection}) async {
    if (_installed) return;
    _installed = true;

    final enable = enableCollection ?? (kReleaseMode && !kIsWeb);
    if (!kIsWeb) {
      try {
        Firebase.app();
        final crashlytics = FirebaseCrashlytics.instance;
        await crashlytics.setCrashlyticsCollectionEnabled(enable);
        _crashlytics = crashlytics;
        _collectionEnabled = enable;
      } catch (e) {
        _crashlytics = null;
        _collectionEnabled = false;
        debugPrint(
          '[Crash] crashlytics unavailable: ${PrivacyLogUtils.errorSummary(e)}',
        );
      }
    }

    FlutterError.onError = (FlutterErrorDetails details) {
      // Keep the framework's console output in every mode.
      FlutterError.presentError(details);
      recordFlutterError(details);
    };
    PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
      recordError(error, stack, fatal: true, source: 'platform_dispatcher');
      return true;
    };
  }

  /// Handler for the `runZonedGuarded` root zone in `main.dart`.
  void recordZoneError(Object error, StackTrace stack) {
    recordError(error, stack, fatal: true, source: 'root_zone');
  }

  /// Explicit, caught-but-noteworthy errors (ErrorHandler.logError).
  void recordNonFatal(Object error, StackTrace? stack, {String? reason}) {
    recordError(error, stack, fatal: false, source: reason ?? 'non_fatal');
  }

  /// Records once per error object. A framework error that also surfaces in
  /// the zone, or a retry that rethrows the same instance, is not uploaded
  /// twice.
  @visibleForTesting
  bool claimReport(Object error) {
    final id = identityHashCode(error);
    if (_reportedErrorIds.contains(id)) return false;
    _reportedErrorIds.add(id);
    if (_reportedErrorIds.length > _maxRememberedErrors) {
      _reportedErrorIds.removeAt(0);
    }
    return true;
  }

  void recordFlutterError(FlutterErrorDetails details) {
    final error = details.exception;
    if (!claimReport(error)) return;
    debugPrint(
      '[Crash] flutter error ${PrivacyLogUtils.errorSummary(error)} '
      'library=${details.library ?? 'unknown'}',
    );
    final crashlytics = _crashlytics;
    if (crashlytics == null || !_collectionEnabled) return;
    final sanitized = FlutterErrorDetails(
      exception: SanitizedCrashError.from(error),
      stack: details.stack,
      library: details.library,
      context: details.context,
      silent: details.silent,
    );
    crashlytics.recordFlutterError(sanitized, fatal: false).catchError((_) {});
  }

  void recordError(
    Object error,
    StackTrace? stack, {
    required bool fatal,
    required String source,
  }) {
    if (!claimReport(error)) return;
    final label = _safeReason(source);
    final severity = fatal ? 'fatal' : 'non-fatal';
    debugPrint(
      '[Crash] $severity ${PrivacyLogUtils.errorSummary(error)} reason=$label',
    );
    final crashlytics = _crashlytics;
    if (crashlytics == null || !_collectionEnabled) return;
    crashlytics
        .recordError(
          SanitizedCrashError.from(error),
          stack,
          reason: label,
          fatal: fatal,
        )
        .catchError((_) {});
  }

  /// Reasons are fixed source labels (root_zone, platform_dispatcher,
  /// error_handler, …), never user data; anything else is reduced to a
  /// fingerprint before it reaches a log line.
  static String _safeReason(String source) {
    const known = {
      'root_zone',
      'platform_dispatcher',
      'non_fatal',
      'error_handler',
    };
    return known.contains(source)
        ? source
        : PrivacyLogUtils.idFingerprint(source);
  }

  @visibleForTesting
  void resetForTest() {
    _installed = false;
    _collectionEnabled = false;
    _crashlytics = null;
    _reportedErrorIds.clear();
  }
}

/// What leaves the device: the exception's type and its privacy-safe summary.
/// Never the original message.
class SanitizedCrashError implements Exception {
  SanitizedCrashError._(this.errorType, this.summary);

  factory SanitizedCrashError.from(Object error) {
    if (error is SanitizedCrashError) return error;
    return SanitizedCrashError._(
      error.runtimeType.toString(),
      PrivacyLogUtils.errorSummary(error),
    );
  }

  final String errorType;
  final String summary;

  @override
  String toString() => 'SanitizedCrashError($summary)';
}
