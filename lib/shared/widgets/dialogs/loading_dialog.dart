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
    final brightness = MediaQuery.platformBrightnessOf(context);
    final isDark = brightness == Brightness.dark;
    final bgColor = isDark ? const Color(0xFF261E2C) : CupertinoColors.systemBackground;
    final textColor = isDark ? const Color(0xFFF0E8ED) : const Color(0xFF181113);

    return Center(
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: bgColor,
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
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: textColor,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
