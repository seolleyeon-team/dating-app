import 'package:flutter/cupertino.dart';

/// 공용 드롭다운
class SeolDropdown<T> extends StatelessWidget {
  final T? value;
  final List<T> items;
  final String Function(T) labelBuilder;
  final ValueChanged<T>? onChanged;
  final String? placeholder;

  const SeolDropdown({
    super.key,
    this.value,
    required this.items,
    required this.labelBuilder,
    this.onChanged,
    this.placeholder,
  });

  void _showPicker(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final pickerBg = isDark ? const Color(0xFF261E2C) : CupertinoColors.systemBackground;

    showCupertinoModalPopup(
      context: context,
      builder: (context) => Container(
        height: 250,
        color: pickerBg,
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                CupertinoButton(
                  child: const Text(
                    '취소',
                    style: TextStyle(fontFamily: 'Pretendard'),
                  ),
                  onPressed: () => Navigator.of(context).pop(),
                ),
                CupertinoButton(
                  child: const Text(
                    '완료',
                    style: TextStyle(fontFamily: 'Pretendard'),
                  ),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
            Expanded(
              child: CupertinoPicker(
                itemExtent: 36,
                onSelectedItemChanged: (index) {
                  onChanged?.call(items[index]);
                },
                children: items
                    .map((item) => Center(child: Text(labelBuilder(item))))
                    .toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final fieldBg = isDark ? const Color(0xFF302838) : CupertinoColors.white;
    final borderColor = isDark ? const Color(0xFF3E3548) : const Color(0xFFE6DBDF);
    final textColor = isDark ? const Color(0xFFF0E8ED) : const Color(0xFF181113);
    final hintColor = isDark
        ? const Color(0xFF7A6B76)
        : const Color(0xFF89616F).withValues(alpha: 0.6);
    final iconColor = isDark ? const Color(0xFF7A6B76) : const Color(0xFF89616F);

    return GestureDetector(
      onTap: () => _showPicker(context),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: fieldBg,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              value != null ? labelBuilder(value as T) : (placeholder ?? '선택'),
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 16,
                color: value != null ? textColor : hintColor,
              ),
            ),
            Icon(
              CupertinoIcons.chevron_down,
              size: 18,
              color: iconColor,
            ),
          ],
        ),
      ),
    );
  }
}
