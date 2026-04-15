import 'package:flutter/material.dart';

/// 확인 다이얼로그 위젯
class ConfirmDialog extends StatelessWidget {
  final String title;
  final String message;
  final String confirmText;
  final String cancelText;
  final VoidCallback? onConfirm;
  final VoidCallback? onCancel;

  const ConfirmDialog({
    super.key,
    required this.title,
    required this.message,
    this.confirmText = '확인',
    this.cancelText = '취소',
    this.onConfirm,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final primary = theme.colorScheme.primary;
    final textSecondary = theme.brightness == Brightness.dark
        ? const Color(0xFFB0A0AC)
        : const Color(0xFF666666);

    return AlertDialog(
      backgroundColor: theme.colorScheme.surface,
      title: Text(
        title,
        style: TextStyle(
          fontFamily: 'Pretendard',
          color: theme.colorScheme.onSurface,
        ),
      ),
      content: Text(
        message,
        style: TextStyle(
          fontFamily: 'Pretendard',
          color: textSecondary,
        ),
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).pop();
            onCancel?.call();
          },
          child: Text(
            cancelText,
            style: TextStyle(
              fontFamily: 'Pretendard',
              color: textSecondary,
            ),
          ),
        ),
        TextButton(
          onPressed: () {
            Navigator.of(context).pop();
            onConfirm?.call();
          },
          child: Text(
            confirmText,
            style: TextStyle(
              fontFamily: 'Pretendard',
              color: primary,
            ),
          ),
        ),
      ],
    );
  }

  static Future<bool?> show(
    BuildContext context, {
    required String title,
    required String message,
    String confirmText = '확인',
    String cancelText = '취소',
  }) {
    return showDialog<bool>(
      context: context,
      builder: (context) => ConfirmDialog(
        title: title,
        message: message,
        confirmText: confirmText,
        cancelText: cancelText,
        onConfirm: () => Navigator.of(context).pop(true),
        onCancel: () => Navigator.of(context).pop(false),
      ),
    );
  }
}
