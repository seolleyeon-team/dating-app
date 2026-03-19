import 'package:flutter/cupertino.dart';

/// 로딩 다이얼로그
class LoadingDialog extends StatelessWidget {
  final String? message;

  const LoadingDialog({super.key, this.message});

  /// 로딩 다이얼로그 표시
  static Future<void> show(BuildContext context, {String? message}) {
    return showCupertinoDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => LoadingDialog(message: message),
    );
  }

  /// 로딩 다이얼로그 닫기
  static void hide(BuildContext context) {
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: CupertinoColors.systemBackground,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CupertinoActivityIndicator(radius: 16),
            if (message != null) ...[
              const SizedBox(height: 16),
              Text(
                message!,
                style: const TextStyle(
                  fontFamily: 'Noto Sans KR',
                  fontSize: 14,
                  color: Color(0xFF181113),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
