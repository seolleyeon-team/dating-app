import 'package:flutter/cupertino.dart';

/// Secondary 버튼 위젯
class SecondaryButton extends StatelessWidget {
  final String text;
  final VoidCallback? onPressed;
  final bool isLoading;
  final bool isFullWidth;

  const SecondaryButton({
    super.key,
    required this.text,
    this.onPressed,
    this.isLoading = false,
    this.isFullWidth = true,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: isFullWidth ? double.infinity : null,
      height: 56,
      child: CupertinoButton(
        onPressed: isLoading ? null : onPressed,
        padding: EdgeInsets.zero,
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: const Color(0xFFEF3976), width: 1.5),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Center(
            child: isLoading
                ? const CupertinoActivityIndicator()
                : Text(
                    text,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFFEF3976),
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}
