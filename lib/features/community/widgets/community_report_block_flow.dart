import 'package:flutter/cupertino.dart';

/// 대나무숲 신고 사유. 서버 `reportBambooContent` 의 허용 목록과 같다.
const List<String> bambooReportReasons = [
  '괴롭힘·혐오',
  '성적 콘텐츠',
  '스팸·광고',
  '개인정보 노출',
  '기타',
];

/// 대나무숲 글/댓글 신고.
///
/// P0-3: 익명 작성자의 UID 는 앱이 알지 못한다. 신고는 콘텐츠 id 만 서버에 보내고,
/// 서버가 비공개 소유권 매핑으로 작성자를 찾아 운영 신고에 남긴다. 신고한 사람에게는
/// 그 글/댓글을 숨긴다. 실명 기반 차단은 만들지 않는다 — 차단 목록은 본인이 읽을 수
/// 있어 익명 작성자의 정체를 알려 주게 된다.
///
/// [submit] 은 선택한 사유로 신고를 보낸다. 성공하면 true 를 돌려준다.
Future<bool> showCommunityReportFlow({
  required BuildContext context,
  required String targetLabel,
  required Future<void> Function(String reason) submit,
}) async {
  final reason = await showCupertinoModalPopup<String>(
    context: context,
    builder: (sheetContext) => CupertinoActionSheet(
      title: const Text('신고하기'),
      message: Text('신고하면 이 $targetLabel은(는) 더 이상 보이지 않고, 운영팀이 검토해요.'),
      actions: [
        for (final item in bambooReportReasons)
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
    await submit(reason);
    if (!context.mounted) return true;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('신고가 접수되었어요'),
        content: Text('이 $targetLabel은(는) 더 이상 보이지 않아요. 운영팀이 신고 내용을 검토합니다.'),
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
