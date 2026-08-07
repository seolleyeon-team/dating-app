/// Converts technical Firestore errors into short messages that are safe to
/// show inside the blind meeting UI.
String blindMeetingUserErrorMessage(String rawMessage) {
  final message = rawMessage.trim();
  final lower = message.toLowerCase();

  if (message.isEmpty ||
      (lower.contains('firestore') && lower.contains('unexpected state')) ||
      lower.contains('nativeerror') ||
      lower.contains('lateerror')) {
    return '데이터를 불러오는 중 일시적인 문제가 발생했어요. 다시 시도해 주세요.';
  }

  if (lower.contains('permission-denied') ||
      lower.contains('permission denied')) {
    return '참여 정보를 확인할 권한이 없어요. 로그인 상태를 확인한 뒤 다시 시도해 주세요.';
  }

  // Avoid rendering a full browser/SDK stack trace if another technical
  // exception reaches the screen in the future.
  if (message.length > 240 || message.contains('\n')) {
    return '잠시 문제가 생겼어요. 다시 시도해 주세요.';
  }

  return message;
}
