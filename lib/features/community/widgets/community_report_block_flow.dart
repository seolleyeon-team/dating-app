import 'package:flutter/cupertino.dart';

import '../../../services/interaction_service.dart';

Future<void> showCommunityReportAndBlockFlow({
  required BuildContext context,
  required String reporterId,
  required String reportedUserId,
  required String source,
  required String contentType,
  required String contentId,
  String? parentContentId,
}) async {
  final reason = await showCupertinoModalPopup<String>(
    context: context,
    builder: (sheetContext) => CupertinoActionSheet(
      title: const Text('신고 및 차단'),
      message: const Text('신고하면 해당 사용자는 차단되고, 대나무숲과 1:1 채팅에서 더 이상 노출되지 않아요.'),
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
  if (reason == null || !context.mounted) return;

  try {
    await InteractionService().blockAndReportUser(
      fromUserId: reporterId,
      toUserId: reportedUserId,
      reason: reason,
      source: source,
      contentType: contentType,
      contentId: contentId,
      parentContentId: parentContentId,
    );
    if (!context.mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('신고가 접수되었어요'),
        content: const Text('해당 사용자를 차단했어요. 운영팀이 신고 내용을 검토합니다.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  } catch (_) {
    if (!context.mounted) return;
    showCupertinoDialog<void>(
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
  }
}
