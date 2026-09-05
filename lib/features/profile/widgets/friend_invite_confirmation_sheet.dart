import 'package:flutter/cupertino.dart';

/// 친구 초대 확인 Bottom Sheet — 설레연 톤 (Quiet Romance / Clear Trust)
///
/// 외부 링크(카카오 버튼, App Link, custom scheme)는 이 화면까지만 연다.
/// 친구 관계는 사용자가 여기서 [친구 추가]를 눌러야만 서버에 요청된다.
class _C {
  static const Color bg = Color(0xFFFFFBF7);
  static const Color textMain = Color(0xFF3D2C33);
  static const Color textSub = Color(0xFF89616B);
  static const Color plumLight = Color(0xFFF5EBF0);
  static const Color plumAccent = Color(0xFF9B5A6A);
  static const Color primary = Color(0xFFE8466E);
  static const Color gray200 = Color(0xFFEEEEEE);
}

/// Returns true when the user explicitly tapped [친구 추가], false/null
/// otherwise (나중에, dismiss). Callers must not mutate anything unless the
/// result is exactly `true`.
Future<bool?> showFriendInviteConfirmationSheet(
  BuildContext context, {
  required String inviterName,
  String? inviterImageUrl,
}) {
  return showCupertinoModalPopup<bool>(
    context: context,
    useRootNavigator: true,
    // Only the two buttons close the sheet, so `null` can only mean the
    // route was removed underneath it (e.g. the splash → main reset on a
    // cold start) — never a user decision. Callers keep the invite pending
    // in that case and re-present it.
    barrierDismissible: false,
    builder: (_) => FriendInviteConfirmationSheet(
      inviterName: inviterName,
      inviterImageUrl: inviterImageUrl,
    ),
  );
}

class FriendInviteConfirmationSheet extends StatelessWidget {
  final String inviterName;
  final String? inviterImageUrl;

  const FriendInviteConfirmationSheet({
    super.key,
    required this.inviterName,
    this.inviterImageUrl,
  });

  static const String confirmLabel = '친구 추가';
  static const String laterLabel = '나중에';

  String get _displayName {
    final trimmed = inviterName.trim();
    return trimmed.isEmpty ? '설레연 친구' : trimmed;
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).padding.bottom;
    final imageUrl = inviterImageUrl?.trim();
    final hasImage = imageUrl != null && imageUrl.isNotEmpty;

    return Container(
      decoration: const BoxDecoration(
        color: _C.bg,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: EdgeInsets.fromLTRB(24, 20, 24, 20 + bottomInset),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: _C.gray200,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 24),
            Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                color: _C.plumLight,
                shape: BoxShape.circle,
                image: hasImage
                    ? DecorationImage(
                        image: NetworkImage(imageUrl),
                        fit: BoxFit.cover,
                      )
                    : null,
              ),
              child: hasImage
                  ? null
                  : const Icon(
                      CupertinoIcons.person_fill,
                      size: 36,
                      color: _C.plumAccent,
                    ),
            ),
            const SizedBox(height: 18),
            Text(
              '$_displayName님을 친구로 추가할까요?',
              key: const Key('friend_invite_confirmation_title'),
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 19,
                fontWeight: FontWeight.w800,
                color: _C.textMain,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '친구로 추가하면 서로의 친구 목록에 표시되고\n3:3 미팅 팀에 함께 참여할 수 있어요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 14,
                height: 1.5,
                color: _C.textSub,
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: CupertinoButton(
                key: const Key('friend_invite_confirm_button'),
                color: _C.primary,
                borderRadius: BorderRadius.circular(16),
                padding: const EdgeInsets.symmetric(vertical: 16),
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text(
                  confirmLabel,
                  style: TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                    color: CupertinoColors.white,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: CupertinoButton(
                key: const Key('friend_invite_later_button'),
                padding: const EdgeInsets.symmetric(vertical: 14),
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text(
                  laterLabel,
                  style: TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                    color: _C.textSub,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
