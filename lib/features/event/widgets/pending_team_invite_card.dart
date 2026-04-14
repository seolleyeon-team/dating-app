import 'package:flutter/cupertino.dart';

import '../../../services/event_team_service.dart';
import '../../../services/user_service.dart';

/// 이벤트 탭 상단 pending invite 카드 / 배너
/// warm off-white · plum 포인트 · 라운드 카드 · 부드러운 shadow
class _Colors {
  static const Color cardBg = Color(0xFFFFFBF7);       // warm ivory
  static const Color cardBorder = Color(0xFFF2E6E9);    // subtle plum border
  static const Color plumAccent = Color(0xFF9B5A6A);    // plum 라벨
  static const Color plumLight = Color(0xFFF5EBF0);     // plum tint bg
  static const Color textMain = Color(0xFF3D2C33);
  static const Color textSub = Color(0xFF89616B);
  static const Color btnConfirm = Color(0xFFE8466E);    // 확인하기
  static const Color btnLater = Color(0xFFD4C4C8);      // 나중에 보기
}

class PendingTeamInviteCard extends StatefulWidget {
  final List<EventTeamInviteDoc> pendingInvites;
  final VoidCallback onConfirm;
  final VoidCallback onDismiss;

  const PendingTeamInviteCard({
    super.key,
    required this.pendingInvites,
    required this.onConfirm,
    required this.onDismiss,
  });

  @override
  State<PendingTeamInviteCard> createState() => _PendingTeamInviteCardState();
}

class _PendingTeamInviteCardState extends State<PendingTeamInviteCard> {
  final UserService _userService = UserService();
  String _inviterName = '';

  @override
  void initState() {
    super.initState();
    _loadInviterName();
  }

  @override
  void didUpdateWidget(covariant PendingTeamInviteCard old) {
    super.didUpdateWidget(old);
    if (widget.pendingInvites.isNotEmpty &&
        (old.pendingInvites.isEmpty ||
            old.pendingInvites.first.inviteId !=
                widget.pendingInvites.first.inviteId)) {
      _loadInviterName();
    }
  }

  Future<void> _loadInviterName() async {
    if (widget.pendingInvites.isEmpty) return;
    final uid = widget.pendingInvites.first.inviterUserId;
    if (uid.isEmpty) {
      if (mounted) setState(() => _inviterName = '친구');
      return;
    }
    final user = await _userService.getUserProfile(uid);
    if (!mounted) return;
    if (user == null) {
      setState(() => _inviterName = '친구');
      return;
    }
    final raw = user['onboarding'];
    final ob =
        raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    if (ob['nickname']?.toString().trim().isNotEmpty == true) {
      setState(() => _inviterName = ob['nickname'].toString());
    } else if (user['nickname']?.toString().trim().isNotEmpty == true) {
      setState(() => _inviterName = user['nickname'].toString());
    } else {
      setState(() => _inviterName = '친구');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.pendingInvites.isEmpty) return const SizedBox.shrink();
    final count = widget.pendingInvites.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _Colors.cardBg,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: _Colors.cardBorder, width: 1),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF9B5A6A).withValues(alpha: 0.08),
              blurRadius: 20,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 상단 라벨
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: _Colors.plumLight,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    CupertinoIcons.mail_solid,
                    size: 13,
                    color: _Colors.plumAccent,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '답변이 필요한 초대${count > 1 ? ' · $count건' : ''}',
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: _Colors.plumAccent,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            // 본문
            Text(
              _inviterName.isNotEmpty
                  ? '$_inviterName님이 팀 초대했어요'
                  : '팀 초대가 도착했어요',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: _Colors.textMain,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              '이벤트 팀에 함께할지 확인해보세요',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                fontWeight: FontWeight.w400,
                color: _Colors.textSub,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 18),
            // 버튼
            Row(
              children: [
                // 나중에 보기
                Expanded(
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: widget.onDismiss,
                    child: Container(
                      height: 42,
                      decoration: BoxDecoration(
                        color: _Colors.btnLater.withValues(alpha: 0.35),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      alignment: Alignment.center,
                      child: const Text(
                        '나중에 보기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: _Colors.textSub,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // 확인하기
                Expanded(
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: widget.onConfirm,
                    child: Container(
                      height: 42,
                      decoration: BoxDecoration(
                        color: _Colors.btnConfirm,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      alignment: Alignment.center,
                      child: const Text(
                        '확인하기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: CupertinoColors.white,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
