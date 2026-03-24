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
    showCupertinoModalPopup(
      context: context,
      builder: (context) => Container(
        height: 250,
        color: CupertinoColors.systemBackground,
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                CupertinoButton(
                  child: const Text(
                    '취소',
                    style: TextStyle(fontFamily: 'Noto Sans KR'),
                  ),
                  onPressed: () => Navigator.of(context).pop(),
                ),
                CupertinoButton(
                  child: const Text(
                    '완료',
                    style: TextStyle(fontFamily: 'Noto Sans KR'),
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
    return GestureDetector(
      onTap: () => _showPicker(context),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: CupertinoColors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE6DBDF)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              value != null ? labelBuilder(value as T) : (placeholder ?? '선택'),
              style: TextStyle(
                fontFamily: 'Noto Sans KR',
                fontSize: 16,
                color: value != null
                    ? const Color(0xFF181113)
                    : const Color(0xFF89616F).withValues(alpha: 0.6),
              ),
            ),
            const Icon(
              CupertinoIcons.chevron_down,
              size: 18,
              color: Color(0xFF89616F),
            ),
          ],
        ),
      ),
    );
  }
}
