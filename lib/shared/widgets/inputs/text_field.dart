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
            color: CupertinoColors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: errorText != null
                  ? CupertinoColors.destructiveRed
                  : const Color(0xFFE6DBDF),
            ),
          ),
          style: const TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 16,
            color: Color(0xFF181113),
          ),
          placeholderStyle: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 16,
            color: const Color(0xFF89616F).withValues(alpha: 0.6),
          ),
        ),
        if (errorText != null) ...[
          const SizedBox(height: 6),
          Text(
            errorText!,
            style: const TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 12,
              color: CupertinoColors.destructiveRed,
            ),
          ),
        ],
      ],
    );
  }
}
