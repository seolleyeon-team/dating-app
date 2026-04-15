import 'package:flutter/cupertino.dart';

/// 기본 바텀시트
class BaseBottomSheet extends StatelessWidget {
  final String? title;
  final Widget child;
  final double initialChildSize;
  final double maxChildSize;
  final bool showDragHandle;

  const BaseBottomSheet({
    super.key,
    this.title,
    required this.child,
    this.initialChildSize = 0.5,
    this.maxChildSize = 0.9,
    this.showDragHandle = true,
  });

  /// 바텀시트 표시
  static Future<T?> show<T>({
    required BuildContext context,
    String? title,
    required Widget child,
    double initialChildSize = 0.5,
    double maxChildSize = 0.9,
    bool showDragHandle = true,
  }) {
    return showCupertinoModalPopup<T>(
      context: context,
      builder: (context) => BaseBottomSheet(
        title: title,
        initialChildSize: initialChildSize,
        maxChildSize: maxChildSize,
        showDragHandle: showDragHandle,
        child: child,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final bgColor = isDark ? const Color(0xFF261E2C) : CupertinoColors.systemBackground;
    final handleColor = isDark ? const Color(0xFF4A4054) : CupertinoColors.systemGrey4;
    final textColor = isDark ? const Color(0xFFF0E8ED) : CupertinoColors.label;

    return Container(
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showDragHandle)
            Container(
              margin: const EdgeInsets.only(top: 12),
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: handleColor,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          if (title != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                title!,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: textColor,
                ),
              ),
            ),
          Flexible(child: child),
        ],
      ),
    );
  }
}
