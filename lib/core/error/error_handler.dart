import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/cupertino.dart';
import 'crash_reporting.dart';
import 'exceptions.dart';

/// 전역 에러 핸들러
class ErrorHandler {
  ErrorHandler._();

  /// 에러를 사용자 친화적 메시지로 변환
  static String getErrorMessage(Object error) {
    if (error is AppException) {
      return error.message;
    } else if (error is TypeError) {
      return '데이터 처리 중 오류가 발생했습니다.';
    } else {
      return '알 수 없는 오류가 발생했습니다.';
    }
  }

  /// 에러 알림 표시
  static void showError(BuildContext context, Object error) {
    final message = getErrorMessage(error);
    showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('오류'),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  /// 에러 로깅 — 콘솔 요약 + Crashlytics 비치명 보고 (P1-6).
  /// 원문 메시지는 전송하지 않는다 (SanitizedCrashError).
  static void logError(Object error, [StackTrace? stackTrace]) {
    // ignore: avoid_print
    print('[Error] ${PrivacyLogUtils.errorSummary(error)}');
    if (stackTrace != null) {
      // ignore: avoid_print
      print('[Error] hasStackTrace=true');
    }
    CrashReporting.instance.recordNonFatal(
      error,
      stackTrace,
      reason: 'error_handler',
    );
  }
}
