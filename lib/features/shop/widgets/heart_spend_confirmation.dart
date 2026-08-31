import 'package:flutter/cupertino.dart';

/// Shows a final confirmation immediately before a paid feature is requested.
///
/// The server remains the source of truth for both the balance and the amount
/// charged. This dialog only makes the user's intent and the expected charge
/// explicit before the request starts.
Future<bool> confirmHeartSpend(
  BuildContext context, {
  required String action,
  required int amount,
  String? detail,
  String? chargeMessage,
}) async {
  final detailText = detail == null || detail.trim().isEmpty
      ? ''
      : '\n${detail.trim()}';
  final chargeText = chargeMessage ?? '❤️$amount 하트가 차감됩니다.';
  final result = await showCupertinoDialog<bool>(
    context: context,
    builder: (dialogContext) => CupertinoAlertDialog(
      title: const Text('하트 사용 확인'),
      content: Text('$action\n$chargeText$detailText'),
      actions: [
        CupertinoDialogAction(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('취소'),
        ),
        CupertinoDialogAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('확인'),
        ),
      ],
    ),
  );
  return result == true;
}
