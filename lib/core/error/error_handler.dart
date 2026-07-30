import 'package:flutter/cupertino.dart';
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

  /// 에러 로깅
  static void logError(Object error, [StackTrace? stackTrace]) {
    // TODO: 에러 로깅 서비스 연동 (Firebase Crashlytics 등)
    // ignore: avoid_print
    print('[Error] $error');
    if (stackTrace != null) {
      // ignore: avoid_print
      print('[StackTrace] $stackTrace');
    }
  }
}
