// =============================================================================
// 팀 요청 카드 위젯
// 경로: lib/features/event/widgets/team_request_card.dart
//
// sent_hearts_screen.dart 의 _ProfileListItem 감도를 참고하되
// 팀 단위(3명 아바타 preview) 카드로 재구성
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../data/models/event/event_team_match_model.dart';
import '../../../data/models/event/team_meeting_request_model.dart';

class _AppColors {
  static const Color primary = Color(0xFFB44AC0);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF2E243F);
  static const Color textSub = Color(0xFF776886);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color statusPending = Color(0xFFF59E0B);
  static const Color statusAccepted = Color(0xFF10B981);
  static const Color statusDeclined = Color(0xFF9CA3AF);
}

class TeamRequestCard extends StatelessWidget {
  final TeamMeetingRequestDoc request;
  final String currentTeamId;
  final VoidCallback? onTap;

  const TeamRequestCard({
    super.key,
    required this.request,
    required this.currentTeamId,
    this.onTap,
  });

  bool get _isSent => request.fromTeamId == currentTeamId;

  EventTeamMatchTeamSnapshot? get _displayTeamSnapshot {
    return _isSent ? request.toTeamSnapshot : request.fromTeamSnapshot;
  }

  @override
  Widget build(BuildContext context) {
    final team = _displayTeamSnapshot;
    final members = team?.members ?? const <EventTeamMatchMemberSnapshot>[];

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.selectionClick();
        onTap?.call();
      },
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: _AppColors.primary.withValues(alpha: 0.08),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF8E74B3).withValues(alpha: 0.06),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Row(
          children: [
            // 3명 아바타 preview
            _TeamAvatarPreview(members: members),
            const SizedBox(width: 14),

            // 팀 정보
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _teamDisplayName(members),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      _StatusChip(
                        status: request.status,
                        isReceived: !_isSent,
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _teamSubtitle(members),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textSub,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      if (!_isSent &&
                          request.status == TeamMeetingRequestStatus.pending)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 3,
                          ),
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(
                            color: _AppColors.primary.withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            '답변 필요',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.primary,
                            ),
                          ),
                        ),
                      Expanded(
                        child: Text(
                          _formatRelativeTime(request.createdAt),
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.gray400,
                          ),
                        ),
                      ),
                      const Icon(
                        CupertinoIcons.chevron_right,
                        size: 16,
                        color: _AppColors.gray400,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _teamDisplayName(List<EventTeamMatchMemberSnapshot> members) {
    if (members.isEmpty) return '팀 정보 없음';
    final names = members.take(3).map((m) => m.displayName).toList();
    return names.join(', ');
  }

  String _teamSubtitle(List<EventTeamMatchMemberSnapshot> members) {
    final parts = <String>[];
    final universities = members
        .where((m) => m.universityName?.trim().isNotEmpty == true)
        .map((m) => m.universityName!)
        .toSet();
    if (universities.isNotEmpty) parts.add(universities.first);
    parts.add('${members.length}명');
    return parts.join(' · ');
  }

  String _formatRelativeTime(DateTime? dt) {
    if (dt == null) return '';
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return '방금';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';
    return '${dt.month}월 ${dt.day}일';
  }
}

// =============================================================================
// 3명 아바타 겹침 미리보기
// =============================================================================

class _TeamAvatarPreview extends StatelessWidget {
  final List<EventTeamMatchMemberSnapshot> members;

  const _TeamAvatarPreview({required this.members});

  @override
  Widget build(BuildContext context) {
    final displayMembers = members.take(3).toList();
    if (displayMembers.isEmpty) {
      return _singleAvatar(null);
    }

    const double size = 40;
    const double overlap = 14;
    final width = size + (displayMembers.length - 1) * (size - overlap);

    return SizedBox(
      width: width,
      height: size + 4,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          for (var i = displayMembers.length - 1; i >= 0; i--)
            Positioned(
              left: i * (size - overlap),
              top: 0,
              child: _AvatarCircle(
                photoUrl: displayMembers[i].photoUrl,
                size: size,
                borderColor: i == 0
                    ? _AppColors.primary.withValues(alpha: 0.2)
                    : CupertinoColors.white,
              ),
            ),
        ],
      ),
    );
  }

  Widget _singleAvatar(String? url) {
    return _AvatarCircle(photoUrl: url, size: 40);
  }
}

class _AvatarCircle extends StatelessWidget {
  final String? photoUrl;
  final double size;
  final Color borderColor;

  const _AvatarCircle({
    required this.photoUrl,
    required this.size,
    this.borderColor = CupertinoColors.white,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: borderColor, width: 2),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF000000).withValues(alpha: 0.06),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: photoUrl != null && photoUrl!.isNotEmpty
          ? Image.network(
              photoUrl!,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _placeholder(),
            )
          : _placeholder(),
    );
  }

  Widget _placeholder() {
    return Container(
      color: _AppColors.gray100,
      child: Icon(
        CupertinoIcons.person_fill,
        size: size * 0.5,
        color: _AppColors.gray400,
      ),
    );
  }
}

// =============================================================================
// 상태 칩
// =============================================================================

class _StatusChip extends StatelessWidget {
  final TeamMeetingRequestStatus status;
  final bool isReceived;

  const _StatusChip({required this.status, required this.isReceived});

  @override
  Widget build(BuildContext context) {
    final (label, bgColor, textColor) = _chipStyle();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: textColor,
        ),
      ),
    );
  }

  (String, Color, Color) _chipStyle() {
    switch (status) {
      case TeamMeetingRequestStatus.pending:
        return (
          '응답 대기',
          _AppColors.statusPending.withValues(alpha: 0.12),
          _AppColors.statusPending,
        );
      case TeamMeetingRequestStatus.accepted:
        return (
          '수락됨',
          _AppColors.statusAccepted.withValues(alpha: 0.12),
          _AppColors.statusAccepted,
        );
      case TeamMeetingRequestStatus.declined:
        return (
          '거절됨',
          _AppColors.statusDeclined.withValues(alpha: 0.12),
          _AppColors.statusDeclined,
        );
    }
  }
}
