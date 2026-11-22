import 'package:cloud_functions/cloud_functions.dart';

/// What the user is told when `submitSafetyStamp` does not accept a stamp.
class SafetyStampSubmitFailureNotice {
  const SafetyStampSubmitFailureNotice({
    required this.title,
    required this.message,
    required this.reason,
  });

  final String title;
  final String message;

  /// The server's refusal reason, or null when the failure was not a
  /// decision of the server (network, unexpected error).
  final String? reason;
}

/// Maps a `submitSafetyStamp` failure to a message the user can act on.
///
/// The server refuses with `failed-precondition` and
/// `details.reason` in `too_early | too_late | promise_time_missing |
/// meetup_not_completed`. Those are decisions, not errors: telling the user
/// to "try again later" for a window that has closed is wrong.
SafetyStampSubmitFailureNotice describeSafetyStampSubmitFailure(Object error) {
  if (error is FirebaseFunctionsException) {
    final details = error.details;
    final reason = details is Map ? details['reason']?.toString() : null;
    if (error.code == 'failed-precondition') {
      switch (reason) {
        case 'too_early':
          return const SafetyStampSubmitFailureNotice(
            title: '아직 도장을 찍을 수 없어요',
            message: '약속 시간이 가까워지면 안전도장을 찍을 수 있어요.',
            reason: 'too_early',
          );
        case 'too_late':
          return const SafetyStampSubmitFailureNotice(
            title: '도장을 찍을 수 있는 시간이 지났어요',
            message: '이 약속은 안전도장을 찍을 수 있는 시간이 지나 더 이상 기록할 수 없어요.',
            reason: 'too_late',
          );
        case 'promise_time_missing':
          return const SafetyStampSubmitFailureNotice(
            title: '약속 시간을 확인할 수 없어요',
            message: '약속 정보를 다시 확인한 뒤 시도해주세요.',
            reason: 'promise_time_missing',
          );
        case 'meetup_not_completed':
          return const SafetyStampSubmitFailureNotice(
            title: '만남 확인이 먼저 필요해요',
            message: '두 사람 모두 만남 도장을 찍은 뒤에 헤어짐 도장을 찍을 수 있어요.',
            reason: 'meetup_not_completed',
          );
      }
    }
    if (error.code == 'unavailable' || error.code == 'deadline-exceeded') {
      return const SafetyStampSubmitFailureNotice(
        title: '도장을 찍지 못했어요',
        message: '네트워크 연결을 확인한 뒤 다시 시도해주세요.',
        reason: null,
      );
    }
  }
  return const SafetyStampSubmitFailureNotice(
    title: '도장을 찍지 못했어요',
    message: '잠시 후 다시 시도해주세요.',
    reason: null,
  );
}
