import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_application.dart';
import '../../domain/blind_meeting_party.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingPartyScreen extends StatefulWidget {
  final BlindMeetingRepository? repository;

  const BlindMeetingPartyScreen({super.key, this.repository});

  @override
  State<BlindMeetingPartyScreen> createState() =>
      _BlindMeetingPartyScreenState();
}

class _BlindMeetingPartyScreenState extends State<BlindMeetingPartyScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  String? _partyId;
  String? _userId;
  bool _loading = true;
  bool _busy = false;
  String? _error;
  BlindMeetingApplication? _application;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    try {
      final userId = await _repository.currentUserId();
      if (userId == null || userId.isEmpty) {
        throw StateError('로그인이 필요해요.');
      }
      final application = await _repository.loadMyApplication();
      if (application?.isActive == true) {
        if (!mounted) return;
        Navigator.of(
          context,
        ).pushReplacementNamed(RouteNames.blindTasteMeeting);
        return;
      }

      final pendingInvites = await _repository.watchPendingPartyInvites().first;
      if (!mounted) return;
      if (pendingInvites.isNotEmpty) {
        final accepted = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            title: const Text('친구 팀 초대가 도착했어요'),
            content: const Text('친구와 같은 편으로 블라인드 취향 미팅에 참가할까요?'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('거절'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('함께하기'),
              ),
            ],
          ),
        );
        await _repository.respondPartyInvite(
          inviteId: pendingInvites.first.inviteId,
          accept: accepted == true,
        );
      }

      final current = await _repository.loadCurrentParty();
      final partyId = current?.partyId ?? await _repository.ensureParty();
      if (!mounted) return;
      setState(() {
        _userId = userId;
        _partyId = partyId;
        _application = application;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error
            .toString()
            .replaceFirst('StateError: ', '')
            .replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _lockAndContinue(BlindMeetingParty party) async {
    if (_busy) return;
    if (party.pendingInviteeIds.isNotEmpty) {
      final proceed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('현재 멤버로 시작할까요?'),
          content: const Text('아직 수락하지 않은 초대는 취소되고, 지금 참여한 친구끼리 팀이 확정돼요.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('더 기다리기'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('시작하기'),
            ),
          ],
        ),
      );
      if (proceed != true || !mounted) return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _repository.lockParty(party.partyId);
      if (!mounted) return;
      HapticFeedback.mediumImpact();
      Navigator.of(context).pushReplacementNamed(RouteNames.blindTasteMeeting);
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error.toString().replaceFirst('Exception: ', ''),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _openFriendPicker(String partyId) {
    Navigator.of(context).pushNamed(
      RouteNames.blindTasteMeetingPartyFriendPicker,
      arguments: partyId,
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return Scaffold(
      backgroundColor: palette.background,
      body: Column(
        children: [
          BlindMeetingAppBar(
            title: '친구와 함께 참여해요',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _partyId == null
                ? _errorBody(palette)
                : StreamBuilder<BlindMeetingParty?>(
                    stream: _repository.watchParty(_partyId!),
                    builder: (context, snapshot) {
                      if (!snapshot.hasData) {
                        return snapshot.hasError
                            ? _errorBody(palette, message: '${snapshot.error}')
                            : const Center(child: CircularProgressIndicator());
                      }
                      return _body(palette, snapshot.data!);
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _body(BlindMeetingPalette palette, BlindMeetingParty party) {
    final isLeader = party.leaderUserId == _userId;
    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, bottom: 40),
      child: BlindMeetingResponsiveBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '혼자도, 친구와도\n같은 편으로 만나요',
              style: BlindMeetingText.title(palette.ink),
            ),
            const SizedBox(height: 8),
            Text(
              '1~3명으로 시작할 수 있어요. 함께 시작한 친구는 절대 다른 미팅으로 나뉘지 않아요.',
              style: BlindMeetingText.caption(palette.inkSoft),
            ),
            const SizedBox(height: 20),
            Row(
              children: List.generate(3, (index) {
                if (index < party.acceptedUserIds.length) {
                  final userId = party.acceptedUserIds[index];
                  return Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(right: index < 2 ? 8 : 0),
                      child: _MemberCard(
                        profile: party.memberProfiles[userId],
                        isMe: userId == _userId,
                        applicationComplete: party.completedApplicationUserIds
                            .contains(userId),
                      ),
                    ),
                  );
                }
                return Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(right: index < 2 ? 8 : 0),
                    child: _EmptySlot(
                      pending:
                          index <
                          party.acceptedUserIds.length +
                              party.pendingInviteeIds.length,
                      onTap:
                          isLeader &&
                              party.isForming &&
                              party.remainingInviteSlots > 0
                          ? () => _openFriendPicker(party.partyId)
                          : null,
                    ),
                  ),
                );
              }),
            ),
            const SizedBox(height: 16),
            BlindMeetingCard(
              background: palette.surfaceMuted,
              child: Text(
                party.isForming
                    ? '친구를 기다리거나 지금 인원으로 바로 시작할 수 있어요.'
                    : '${party.completedApplicationUserIds.length}/${party.memberCount}명이 날짜 신청을 완료했어요. 전원이 완료해야 함께 매칭을 시작해요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              BlindMeetingErrorState(message: _error!),
            ],
            const SizedBox(height: 20),
            if (party.isForming && isLeader)
              BlindMeetingPrimaryButton(
                label: switch (party.memberCount) {
                  1 => '혼자 DNA 작성하기',
                  2 => '2명으로 DNA 작성하기',
                  _ => '3명으로 DNA 작성하기',
                },
                loading: _busy,
                onPressed: () => _lockAndContinue(party),
              )
            else if (party.isLocked &&
                _application?.dnaApplicationCompleted != true)
              BlindMeetingPrimaryButton(
                label: '미팅 DNA 작성하기',
                onPressed: () => Navigator.of(
                  context,
                ).pushReplacementNamed(RouteNames.blindTasteMeeting),
              ),
          ],
        ),
      ),
    );
  }

  Widget _errorBody(BlindMeetingPalette palette, {String? message}) =>
      SingleChildScrollView(
        padding: const EdgeInsets.only(top: 24),
        child: BlindMeetingResponsiveBody(
          child: BlindMeetingErrorState(
            message: message ?? _error ?? '팀 정보를 불러오지 못했어요.',
            onRetry: _bootstrap,
          ),
        ),
      );
}

class _MemberCard extends StatelessWidget {
  final BlindMeetingPartyMemberProfile? profile;
  final bool isMe;
  final bool applicationComplete;

  const _MemberCard({
    required this.profile,
    required this.isMe,
    required this.applicationComplete,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final url = profile?.profileImageUrl ?? '';
    return BlindMeetingCard(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 14),
      child: Column(
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              CircleAvatar(
                radius: 28,
                backgroundColor: palette.surfaceMuted,
                backgroundImage: url.isNotEmpty ? NetworkImage(url) : null,
                child: url.isEmpty
                    ? Icon(Icons.person, color: palette.inkFaint)
                    : null,
              ),
              if (isMe)
                Positioned(
                  right: -8,
                  top: -6,
                  child: BlindMeetingBadge(label: 'ME', color: palette.accent),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            profile?.nickname ?? '친구',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: BlindMeetingText.caption(palette.ink),
          ),
          const SizedBox(height: 4),
          Text(
            applicationComplete ? '날짜 신청 완료' : '참여 완료',
            textAlign: TextAlign.center,
            style: BlindMeetingText.caption(
              applicationComplete ? palette.positive : palette.inkFaint,
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptySlot extends StatelessWidget {
  final bool pending;
  final VoidCallback? onTap;

  const _EmptySlot({required this.pending, this.onTap});

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: onTap,
      child: Container(
        height: 144,
        decoration: BoxDecoration(
          color: palette.surfaceMuted,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: palette.accent.withValues(alpha: 0.22)),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              pending ? Icons.hourglass_top : Icons.person_add_alt_1,
              color: palette.accent,
            ),
            const SizedBox(height: 8),
            Text(
              pending
                  ? '수락 대기'
                  : onTap != null
                  ? '설레연\n친구 초대'
                  : '빈 자리',
              textAlign: TextAlign.center,
              style: BlindMeetingText.caption(palette.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
