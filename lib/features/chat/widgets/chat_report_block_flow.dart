import 'package:flutter/cupertino.dart';

import '../../../services/interaction_service.dart';

/// Opens the 1:1 chat safety flow. The backend records the report and writes
/// the bilateral block atomically, so both participants can no longer send
/// messages in the existing conversation.
Future<bool> showChatReportAndBlockFlow({
  required BuildContext context,
  required String reporterId,
  required String reportedUserId,
}) async {
  final reason = await showCupertinoModalPopup<String>(
    context: context,
    builder: (sheetContext) => CupertinoActionSheet(
      title: const Text('신고 및 차단'),
      message: const Text('신고하면 해당 사용자가 차단되며, 이 채팅방에서 더 이상 새 메시지를 주고받을 수 없어요.'),
      actions: [
        for (final item in const ['괴롭힘·혐오', '성적 콘텐츠', '스팸·광고', '개인정보 노출', '기타'])
          CupertinoActionSheetAction(
            onPressed: () => Navigator.of(sheetContext).pop(item),
            child: Text(item),
          ),
      ],
      cancelButton: CupertinoActionSheetAction(
        isDefaultAction: true,
        onPressed: () => Navigator.of(sheetContext).pop(),
        child: const Text('취소'),
      ),
    ),
  );
  if (reason == null || !context.mounted) return false;

  try {
    await InteractionService().blockAndReportUser(
      fromUserId: reporterId,
      toUserId: reportedUserId,
      reason: reason,
      source: 'chat',
    );
    if (!context.mounted) return true;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('신고가 접수되었어요'),
        content: const Text('해당 사용자를 차단했어요. 이 채팅방에서 새 메시지를 주고받을 수 없어요.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
    return true;
  } catch (_) {
    if (!context.mounted) return false;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('신고하지 못했어요'),
        content: const Text('잠시 후 다시 시도해주세요.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
    return false;
  }
}
