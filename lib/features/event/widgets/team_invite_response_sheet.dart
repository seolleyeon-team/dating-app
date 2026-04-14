import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/event_team_service.dart';
import '../../../services/storage_service.dart';

/// 팀 초대 상세 응답 Bottom Sheet
/// 설레연 톤 — Quiet Romance / Clear Trust
class _C {
  static const Color bg = Color(0xFFFFFBF7);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF3D2C33);
  static const Color textSub = Color(0xFF89616B);
  static const Color plumAccent = Color(0xFF9B5A6A);
  static const Color plumLight = Color(0xFFF5EBF0);
  static const Color primary = Color(0xFFE8466E);
  static const Color gray200 = Color(0xFFEEEEEE);
  static const Color verifiedBadge = Color(0xFF6BA385);
}

/// 이벤트 탭이나 초대 응답 화면에서 호출
Future<void> showTeamInviteResponseSheet(
  BuildContext context, {
  required EventTeamInviteDoc invite,
}) {
  return showCupertinoModalPopup<void>(
    context: context,
    builder: (_) => _TeamInviteResponseSheet(invite: invite),
  );
}

class _TeamInviteResponseSheet extends StatefulWidget {
  final EventTeamInviteDoc invite;

  const _TeamInviteResponseSheet({required this.invite});

  @override
  State<_TeamInviteResponseSheet> createState() =>
      _TeamInviteResponseSheetState();
}

class _TeamInviteResponseSheetState extends State<_TeamInviteResponseSheet> {
  final EventTeamService _eventTeam = EventTeamService();
  final StorageService _storage = StorageService();

  InviterProfile? _inviterProfile;
  EventTeamSetupState? _teamState;
  List<EventTeamMemberProfile>? _memberProfiles;
  bool _busy = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      final inviterFuture =
          _eventTeam.getInviterProfile(widget.invite.inviterUserId);
      final teamFuture =
          _eventTeam.getTeamSetupOnce(widget.invite.teamSetupId);

      final results = await Future.wait([inviterFuture, teamFuture]);
      final inviter = results[0] as InviterProfile;
      final team = results[1] as EventTeamSetupState?;

      List<EventTeamMemberProfile>? members;
      if (team != null) {
        members = await _eventTeam.buildMemberProfiles(
          state: team,
          currentUserId: '', // 수신자 본인은 아직 합류 전
        );
      }

      if (!mounted) return;
      setState(() {
        _inviterProfile = inviter;
        _teamState = team;
        _memberProfiles = members;
        _loading = false;
      });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _codeMessage(String code) {
    switch (code) {
      case 'not_found':
        return '초대를 찾을 수 없어요.';
      case 'already_responded':
        return '이미 처리된 초대예요.';
      case 'team_full':
        return '팀 정원이 이미 찼어요.';
      case 'not_friends':
        return '더는 친구 관계가 아니어서 참여할 수 없어요.';
      case 'stale_invite':
        return '유효하지 않은 초대예요.';
      case 'team_missing':
        return '팀 정보가 없어요.';
      default:
        return '초대를 처리하지 못했어요.';
    }
  }

  Future<void> _respond(bool accept) async {
    if (_busy) return;
    setState(() => _busy = true);
    HapticFeedback.mediumImpact();
    try {
      final res = await _eventTeam.respondInvite(
        inviteId: widget.invite.inviteId,
        accept: accept,
      );
      final ok = res['ok'] == true;
      if (!mounted) return;
      if (ok) {
        if (accept) {
          final kakaoUserId = await _storage.getKakaoUserId();
          if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
            await _storage.saveEventTeamSetupDraftId(
              kakaoUserId,
              widget.invite.teamSetupId,
            );
          }
        }
        if (!mounted) return;
        Navigator.of(context).pop();
        return;
      }
      final code = res['code']?.toString() ?? '';
      await _showAlert(_codeMessage(code));
    } on FirebaseFunctionsException catch (e) {
      if (mounted) {
        await _showAlert(e.message ?? '요청을 처리하지 못했어요.');
      }
    } catch (e) {
      if (mounted) {
        await _showAlert('요청을 처리하지 못했어요.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _showAlert(String msg) {
    return showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(msg),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomPad = MediaQuery.of(context).padding.bottom;

    return Container(
      decoration: const BoxDecoration(
        color: _C.bg,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: SafeArea(
        top: false,
        child: _loading
            ? const SizedBox(
                height: 300,
                child: Center(child: CupertinoActivityIndicator()),
              )
            : SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(24, 8, 24, bottomPad + 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 드래그 핸들
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        margin: const EdgeInsets.only(top: 12, bottom: 20),
                        decoration: BoxDecoration(
                          color: _C.gray200,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),

                    // 헤더
                    const Text(
                      '팀 초대가 도착했어요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: _C.textMain,
                        height: 1.3,
                      ),
                    ),
                    const SizedBox(height: 24),

                    // 초대자 프로필 카드
                    _buildInviterCard(),
                    const SizedBox(height: 16),

                    // 팀 정보
                    _buildTeamInfo(),
                    const SizedBox(height: 20),

                    // 설명 문구
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 14,
                      ),
                      decoration: BoxDecoration(
                        color: _C.plumLight.withValues(alpha: 0.5),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '수락하면 이 팀에 합류하게 돼요.',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: _C.textMain,
                              height: 1.4,
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            '팀이 모두 모이면 다음 단계로 진행할 수 있어요.',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 13,
                              fontWeight: FontWeight.w400,
                              color: _C.textSub,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 28),

                    // 하단 CTA
                    _buildCTA(),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildInviterCard() {
    final p = _inviterProfile;
    if (p == null) {
      return const SizedBox.shrink();
    }
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _C.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: _C.plumAccent.withValues(alpha: 0.06),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        children: [
          // 프로필 이미지
          ClipOval(
            child:
                p.imageUrl != null && p.imageUrl!.isNotEmpty
                    ? Image.network(
                        p.imageUrl!,
                        width: 56,
                        height: 56,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _fallbackAvatar(),
                      )
                    : _fallbackAvatar(),
          ),
          const SizedBox(width: 14),
          // 정보
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        p.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: _C.textMain,
                        ),
                      ),
                    ),
                    if (p.isStudentVerified) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: _C.verifiedBadge.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              CupertinoIcons.checkmark_seal_fill,
                              size: 11,
                              color: _C.verifiedBadge,
                            ),
                            SizedBox(width: 3),
                            Text(
                              '인증됨',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: _C.verifiedBadge,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    if (p.university != null && p.university!.isNotEmpty)
                      p.university!,
                    if (p.mbti != null && p.mbti!.isNotEmpty) p.mbti!,
                  ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                    color: _C.textSub,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTeamInfo() {
    final team = _teamState;
    if (team == null) return const SizedBox.shrink();

    final currentCount = team.acceptedCount + team.pendingInviteeIds.length;
    final members = _memberProfiles ?? [];
    final memberNames =
        members.where((m) => !m.isPending).map((m) => m.name).toList();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _C.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: _C.plumAccent.withValues(alpha: 0.04),
            blurRadius: 12,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.person_3_fill,
                size: 18,
                color: _C.plumAccent,
              ),
              const SizedBox(width: 8),
              const Text(
                '현재 팀 구성',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: _C.textMain,
                ),
              ),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _C.plumLight,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '$currentCount/3명',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _C.plumAccent,
                  ),
                ),
              ),
            ],
          ),
          if (memberNames.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              '참여 중: ${memberNames.join(', ')}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                fontWeight: FontWeight.w400,
                color: _C.textSub,
                height: 1.4,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCTA() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Primary: 팀 참여하기
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _busy ? null : () => _respond(true),
          child: Container(
            width: double.infinity,
            height: 54,
            decoration: BoxDecoration(
              color: _busy ? _C.gray200 : _C.primary,
              borderRadius: BorderRadius.circular(16),
              boxShadow: _busy
                  ? null
                  : [
                      BoxShadow(
                        color: _C.primary.withValues(alpha: 0.25),
                        blurRadius: 16,
                        offset: const Offset(0, 6),
                      ),
                    ],
            ),
            alignment: Alignment.center,
            child: _busy
                ? const CupertinoActivityIndicator(
                    color: CupertinoColors.white,
                  )
                : const Text(
                    '팀 참여하기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 10),
        // Secondary: 거절하기
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _busy ? null : () => _respond(false),
          child: Container(
            width: double.infinity,
            height: 46,
            alignment: Alignment.center,
            child: const Text(
              '거절하기',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _C.textSub,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _fallbackAvatar() {
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: _C.gray200,
        shape: BoxShape.circle,
        border: Border.all(
          color: _C.plumAccent.withValues(alpha: 0.15),
          width: 2,
        ),
      ),
      child: const Icon(
        CupertinoIcons.person_fill,
        color: CupertinoColors.white,
        size: 28,
      ),
    );
  }
}
