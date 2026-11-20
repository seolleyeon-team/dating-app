import 'package:flutter/cupertino.dart';

/// 온보딩 단계 저장이 실패했을 때의 공통 안내.
///
/// 저장 실패를 그대로 흘려보내면 진행 플래그가 켜진 채 남아 버튼이 다시
/// 눌리지 않거나, 사용자에게는 아무 일도 일어나지 않은 것처럼 보인다.
Future<void> showOnboardingSaveFailure(BuildContext context) {
  return showCupertinoDialog<void>(
    context: context,
    builder: (dialogContext) => CupertinoAlertDialog(
      title: const Text('저장하지 못했어요'),
      content: const Text('네트워크 상태를 확인한 뒤 다시 시도해주세요.'),
      actions: [
        CupertinoDialogAction(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: const Text('확인'),
        ),
      ],
    ),
  );
}
