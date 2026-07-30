import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:seolleyeon/shared/utils/app_check_provider_policy.dart';

/// Last App Check bootstrap outcome for diagnostics / recoverable UX.
AppCheckInitResult? lastAppCheckInitResult;

void recordAppCheckInitResult(AppCheckInitResult result) {
  lastAppCheckInitResult = result;
  // Structured, PII-free telemetry line for log-based monitoring.
  // ignore: avoid_print
  print(
    '[AppCheckTelemetry] status=${result.status.name} '
    'platform=${result.platform} debug=${result.usedDebugProvider} '
    'blocked=${result.callablesLikelyBlocked} '
    'error=${result.errorSummary ?? ''}',
  );
}

String summarizeAppCheckError(Object error) =>
    PrivacyLogUtils.errorSummary(error);
