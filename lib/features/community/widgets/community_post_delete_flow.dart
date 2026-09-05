import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

bool isCommunityPostOwner({
  required String? currentUserId,
  required String authorId,
}) {
  final normalizedCurrentUserId = currentUserId?.trim() ?? '';
  final normalizedAuthorId = authorId.trim();
  return normalizedCurrentUserId.isNotEmpty &&
      normalizedCurrentUserId == normalizedAuthorId;
}

/// Shows the post action sheet and a second destructive-action confirmation.
///
/// Returns true only when the user explicitly confirms deletion.
Future<bool> confirmCommunityPostDeletion(BuildContext context) async {
  HapticFeedback.lightImpact();

  final selectedDelete = await showCupertinoModalPopup<bool>(
    context: context,
    useRootNavigator: true,
    builder: (popupContext) => CupertinoActionSheet(
      title: const Text('게시글 관리'),
      actions: [
        CupertinoActionSheetAction(
          key: const ValueKey('community-post-delete-action'),
          isDestructiveAction: true,
          onPressed: () => Navigator.of(popupContext).pop(true),
          child: const Text('게시글 삭제'),
        ),
      ],
      cancelButton: CupertinoActionSheetAction(
        key: const ValueKey('community-post-delete-cancel'),
        onPressed: () => Navigator.of(popupContext).pop(false),
        child: const Text('취소'),
      ),
    ),
  );

  if (selectedDelete != true || !context.mounted) return false;

  return await showCupertinoDialog<bool>(
        context: context,
        useRootNavigator: true,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text('게시글을 삭제할까요?'),
          content: const Text('삭제한 게시글은 다시 복구할 수 없어요.'),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('취소'),
            ),
            CupertinoDialogAction(
              key: const ValueKey('community-post-delete-confirm'),
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('삭제'),
            ),
          ],
        ),
      ) ??
      false;
}
