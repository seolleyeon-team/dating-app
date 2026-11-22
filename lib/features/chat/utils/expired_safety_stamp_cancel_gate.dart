import 'package:flutter/foundation.dart' show debugPrint;

import '../../../shared/utils/privacy_log_utils.dart';

/// Decides when the client may ask the server to cancel a promise whose
/// meetup safety-stamp window has passed.
///
/// The request is validated against SERVER time. A phone whose clock runs
/// fast believes the window is over before the server does, and the request
/// is refused (permission-denied). The callers re-evaluate on every timer
/// tick and on every room snapshot, so without this gate a refused request
/// was re-sent each time, and its error was not caught at all.
///
/// After a refusal or any other failure the same promise is left alone for
/// [retryAfter]; by then the server clock has usually caught up, or another
/// participant has already cancelled it.
class ExpiredSafetyStampCancelGate {
  ExpiredSafetyStampCancelGate({
    this.retryAfter = const Duration(minutes: 5),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Duration retryAfter;
  final DateTime Function() _now;

  bool _inFlight = false;
  String? _failedPromiseId;
  DateTime? _failedAt;

  bool shouldAttempt(String promiseId) {
    if (promiseId.isEmpty || _inFlight) return false;
    final failedAt = _failedAt;
    if (_failedPromiseId == promiseId && failedAt != null) {
      return _now().difference(failedAt) >= retryAfter;
    }
    return true;
  }

  /// Runs [cancel] when allowed. Never throws: a failure is logged and the
  /// promise is backed off. Returns whether the request succeeded.
  Future<bool> run(String promiseId, Future<void> Function() cancel) async {
    if (!shouldAttempt(promiseId)) return false;
    _inFlight = true;
    try {
      await cancel();
      _failedPromiseId = null;
      _failedAt = null;
      return true;
    } catch (e) {
      _failedPromiseId = promiseId;
      _failedAt = _now();
      debugPrint(
        '[SafetyStamp] expired-promise cancel not accepted: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      return false;
    } finally {
      _inFlight = false;
    }
  }
}
