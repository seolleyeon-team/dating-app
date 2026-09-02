import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';

/// 음주·흡연 정보가 없어 블라인드 미팅을 진행할 수 없을 때 쓰는 공통 안내.
Future<void> showBlindMeetingLifestyleRequiredDialog(
  BuildContext context, {
  bool heartAlreadyCharged = false,
}) async {
  final heartMessage = heartAlreadyCharged
      ? '이미 DNA 작성 시작 시 차감된 하트 외에 추가 차감은 없어요.'
      : '지금은 하트가 차감되지 않았어요.';
  final shouldOpenProfile = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('음주·흡연 정보가 필요해요'),
      content: Text(
        '3:3 블라인드 미팅을 신청하려면 음주와 흡연 정보를 모두 입력해야 해요.\n\n'
        '내 페이지 → 프로필 편집 맨 아래의 라이프스타일에서 입력해주세요. '
        '$heartMessage',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('채우러 가기'),
        ),
      ],
    ),
  );
  if (shouldOpenProfile == true && context.mounted) {
    await Navigator.of(context).pushNamed(RouteNames.profileEdit);
  }
}
