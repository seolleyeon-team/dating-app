import 'package:flutter/cupertino.dart';

/// 공용 텍스트 필드
class SeolTextField extends StatelessWidget {
  final TextEditingController? controller;
  final String? placeholder;
  final TextInputType keyboardType;
  final bool obscureText;
  final int? maxLines;
  final int? maxLength;
  final ValueChanged<String>? onChanged;
  final bool enabled;
  final String? errorText;

  const SeolTextField({
    super.key,
    this.controller,
    this.placeholder,
    this.keyboardType = TextInputType.text,
    this.obscureText = false,
    this.maxLines = 1,
    this.maxLength,
    this.onChanged,
    this.enabled = true,
    this.errorText,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final fieldBg = isDark ? const Color(0xFF302838) : CupertinoColors.white;
    final borderColor = errorText != null
        ? CupertinoColors.destructiveRed
        : (isDark ? const Color(0xFF3E3548) : const Color(0xFFE6DBDF));
    final textColor = isDark ? const Color(0xFFF0E8ED) : const Color(0xFF181113);
    final placeholderColor = isDark
        ? const Color(0xFF7A6B76)
        : const Color(0xFF89616F).withValues(alpha: 0.6);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CupertinoTextField(
          controller: controller,
          placeholder: placeholder,
          keyboardType: keyboardType,
          obscureText: obscureText,
          maxLines: maxLines,
          maxLength: maxLength,
          onChanged: onChanged,
          enabled: enabled,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: fieldBg,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: borderColor),
          ),
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            color: textColor,
          ),
          placeholderStyle: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            color: placeholderColor,
          ),
        ),
        if (errorText != null) ...[
          const SizedBox(height: 6),
          Text(
            errorText!,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              color: CupertinoColors.destructiveRed,
            ),
          ),
        ],
      ],
    );
  }
}
