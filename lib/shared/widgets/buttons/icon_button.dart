import 'package:flutter/cupertino.dart';

/// 아이콘 버튼 위젯
class SeolIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final double size;
  final Color? color;
  final Color? backgroundColor;

  const SeolIconButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.size = 24,
    this.color,
    this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final defaultBg = isDark
        ? CupertinoColors.white.withValues(alpha: 0.1)
        : CupertinoColors.white.withValues(alpha: 0.8);
    final defaultColor = isDark ? const Color(0xFFF0E8ED) : const Color(0xFF181113);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size(size + 16, size + 16),
      onPressed: onPressed,
      child: Container(
        width: size + 16,
        height: size + 16,
        decoration: BoxDecoration(
          color: backgroundColor ?? defaultBg,
          borderRadius: BorderRadius.circular((size + 16) / 2),
        ),
        child: Icon(icon, size: size, color: color ?? defaultColor),
      ),
    );
  }
}
