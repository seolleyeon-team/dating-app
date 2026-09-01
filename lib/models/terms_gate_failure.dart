import 'package:cloud_functions/cloud_functions.dart';

/// Machine-readable terms-gate failures (terms-gate contract §9).
///
/// The server returns these on `FirebaseFunctionsException.details.detail`
/// from `sendPrimaryStudentEmailLink`, `completePrimaryStudentEmailAuth` and
/// `recordTermsAcceptance`. Mapping them to a typed client failure is what
/// closes the deep-link bypass (finding F7) end to end: any entry point that
/// reaches account creation without a recorded acceptance is bounced back to
/// the terms screen instead of dead-ending on a raw error string.
enum TermsGateFailure {
  /// No acceptance was recorded for this request at all.
  acceptanceRequired,

  /// An acceptance exists but its version is not in the server allowlist.
  versionOutdated,
}

class TermsGateException implements Exception {
  const TermsGateException(this.failure);

  final TermsGateFailure failure;

  static const Map<TermsGateFailure, String> _detailByFailure =
      <TermsGateFailure, String>{
        TermsGateFailure.acceptanceRequired: 'terms_acceptance_required',
        TermsGateFailure.versionOutdated: 'terms_version_outdated',
      };

  /// The contract §9 `details.detail` value this failure corresponds to.
  String get detail => _detailByFailure[failure]!;

  /// User-facing copy. Contract §9: no internal detail, no user data.
  String get userMessage => switch (failure) {
    TermsGateFailure.acceptanceRequired => '약관 동의가 필요해요',
    TermsGateFailure.versionOutdated => '약관이 업데이트되어 다시 동의가 필요해요',
  };

  /// Returns the typed failure when [error] carries a terms-gate detail, and
  /// `null` otherwise so the caller can rethrow the original exception.
  static TermsGateException? fromFunctionsException(
    FirebaseFunctionsException error,
  ) {
    final details = error.details;
    final detail = details is Map ? details['detail']?.toString() : null;
    if (detail == null || detail.isEmpty) return null;

    for (final entry in _detailByFailure.entries) {
      if (entry.value == detail) return TermsGateException(entry.key);
    }
    return null;
  }

  @override
  String toString() => 'TermsGateException($detail)';
}
