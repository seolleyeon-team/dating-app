// =============================================================================
// 3:3 블라인드 취향 미팅 — 추천 결과 / 확정 / 진행 화면
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_result_screen.dart
//
// 여섯 명을 `우리 팀 3명`과 `상대 팀 3명`으로 명확히 구분해서 보여주고,
// 미팅 상태에 따라 수락 → 보증금 → 채팅 → 참석 확인 → 안전도장 → 후속 선택으로
// 이어지는 다음 행동을 제시한다. 상태 전환 자체는 모두 서버가 수행한다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../../chat/models/chat_room_data.dart';
import '../../data/blind_meeting_analytics.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_enums.dart';
import '../../domain/blind_meeting_policy.dart';
import '../../domain/blind_meeting_public_profile.dart';
import '../../domain/blind_meeting_session.dart';
import '../../domain/blind_meeting_availability.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_action_sheets.dart';
import '../widgets/blind_meeting_common.dart';
import '../widgets/blind_meeting_profile_card.dart';
import '../widgets/blind_meeting_recommendation_banner.dart';

class BlindMeetingResultScreen extends StatefulWidget {
  final BlindMeetingMeetingArgs args;
  final BlindMeetingRepository? repository;
  final BlindMeetingAnalytics? analytics;

  const BlindMeetingResultScreen({
    super.key,
    required this.args,
    this.repository,
    this.analytics,
  });

  @override
  State<BlindMeetingResultScreen> createState() =>
      _BlindMeetingResultScreenState();
}

class _BlindMeetingResultScreenState extends State<BlindMeetingResultScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();
  late final BlindMeetingAnalytics _analytics =
      widget.analytics ?? BlindMeetingAnalytics();

  BlindMeetingRecommendationView? _view;
  bool _loading = true;
  String? _error;
  bool _busy = false;
  String? _actionError;
  String? _actionNotice;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final view = await _repository.loadRecommendation(widget.args.meetingId);
      if (!mounted) return;
      setState(() {
        _view = view;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _loading = false;
      });
    }
  }

  Future<void> _run(
    Future<void> Function() action, {
    String? successNotice,
  }) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _actionError = null;
      _actionNotice = null;
    });
    try {
      await action();
      if (!mounted) return;
      setState(() => _actionNotice = successNotice);
      await _load();
    } catch (error) {
      if (!mounted) return;
      setState(() => _actionError = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Scaffold(
      backgroundColor: palette.background,
      body: Column(
        children: [
          BlindMeetingAppBar(
            title: '블라인드 취향 미팅',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(child: _buildBody(palette)),
        ],
      ),
    );
  }

  Widget _buildBody(BlindMeetingPalette palette) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final error = _error;
    if (error != null) {
      return _wrap(BlindMeetingErrorState(message: error, onRetry: _load));
    }
    final view = _view;
    if (view == null) {
      return _wrap(
        const BlindMeetingEmptyState(
          title: '미팅 정보를 찾을 수 없어요',
          description: '참가 중인 미팅이 아니거나 이미 종료되었어요.',
        ),
      );
    }

    return StreamBuilder<BlindMeetingSession?>(
      stream: _repository.watchMeeting(widget.args.meetingId),
      initialData: view.session,
      builder: (context, snapshot) {
        final session = snapshot.data ?? view.session;
        return _wrap(_buildContent(palette, view, session));
      },
    );
  }

  Widget _wrap(Widget child) => SingleChildScrollView(
    physics: const BouncingScrollPhysics(),
    padding: const EdgeInsets.only(top: 8, bottom: 48),
    child: BlindMeetingResponsiveBody(child: child),
  );

  Widget _buildContent(
    BlindMeetingPalette palette,
    BlindMeetingRecommendationView view,
    BlindMeetingSession session,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.args.showRecommendationBanner)
          _RecommendationBannerSlot(
            alcoholFree: session.isAlcoholFree,
            onShown: () => _analytics.log(
              BlindMeetingAnalyticsEvent.recommendationBannerShown,
              params: {
                'meetingId': session.meetingId,
                'isAlcoholFree': session.isAlcoholFree,
              },
            ),
          ),
        _summaryCard(palette, session),
        const SizedBox(height: 16),
        _actionCard(palette, view, session),
        if (_actionNotice != null) ...[
          const SizedBox(height: 12),
          Text(
            _actionNotice!,
            style: BlindMeetingText.caption(palette.positive),
          ),
        ],
        if (_actionError != null) ...[
          const SizedBox(height: 12),
          BlindMeetingErrorState(message: _actionError!),
        ],
        const SizedBox(height: 24),
        _teamSection(palette, '우리 팀 3명', view.myTeam, isMyTeam: true),
        const SizedBox(height: 8),
        _teamSection(palette, '상대 팀 3명', view.opponentTeam, isMyTeam: false),
        const SizedBox(height: 12),
        Text(
          '블라인드 미팅에서는 얼굴 사진과 비공개 답변을 공개하지 않아요.',
          style: BlindMeetingText.caption(palette.inkFaint),
        ),
      ],
    );
  }

  Widget _summaryCard(
    BlindMeetingPalette palette,
    BlindMeetingSession session,
  ) {
    final slot = session.slot;
    final venue = session.venue;

    return BlindMeetingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              BlindMeetingBadge(
                label: session.isAlcoholFree ? '무알코올 미팅' : '3:3 블라인드',
                icon: session.isAlcoholFree
                    ? Icons.local_cafe_outlined
                    : Icons.people_outline,
                color: session.isAlcoholFree
                    ? palette.positive
                    : palette.accent,
              ),
              const SizedBox(width: 6),
              BlindMeetingBadge(
                label: _statusLabel(session.status),
                icon: Icons.timelapse_outlined,
                color: palette.accentDeep,
              ),
            ],
          ),
          const SizedBox(height: 14),
          _infoRow(palette, '일정', slot?.label ?? '단체 채팅에서 함께 정해요'),
          if (slot == null && session.scheduleDateCandidates.isNotEmpty)
            _infoRow(
              palette,
              '가능한 날짜',
              BlindMeetingAvailability.selectionSummary(
                session.scheduleDateCandidates,
                visibleCount: 3,
              ),
            ),
          _infoRow(palette, '장소', venue?.name ?? '단체 채팅에서 함께 정해요'),
          _infoRow(palette, '인원', '3:3 (여섯 명)'),
        ],
      ),
    );
  }

  Widget _infoRow(BlindMeetingPalette palette, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 52,
            child: Text(
              label,
              style: BlindMeetingText.caption(palette.inkFaint),
            ),
          ),
          Expanded(
            child: Text(value, style: BlindMeetingText.body(palette.ink)),
          ),
        ],
      ),
    );
  }

  Widget _actionCard(
    BlindMeetingPalette palette,
    BlindMeetingRecommendationView view,
    BlindMeetingSession session,
  ) {
    final me = view.me;
    final meetingId = session.meetingId;

    switch (session.status) {
      case BlindMeetingStatus.awaitingAcceptance:
        final accepted =
            me != null &&
            me.status != BlindMeetingParticipantStatus.invited &&
            me.status != BlindMeetingParticipantStatus.applied;
        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                accepted ? '수락이 완료됐어요' : '참가를 수락해주세요',
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                accepted
                    ? '남은 참가자의 수락을 기다리고 있어요.'
                    : '여섯 명 모두 수락하면 개인별 보증금 결제로 넘어가요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              if (!accepted) ...[
                const SizedBox(height: 16),
                BlindMeetingPrimaryButton(
                  label: '참가할게요',
                  loading: _busy,
                  onPressed: _busy
                      ? null
                      : () => _run(() async {
                          await _repository.acceptInvitation(meetingId);
                          await _analytics.log(
                            BlindMeetingAnalyticsEvent.invitationAccepted,
                            params: {'meetingId': meetingId},
                          );
                        }, successNotice: '참가를 수락했어요.'),
                ),
                const SizedBox(height: 10),
                BlindMeetingSecondaryButton(
                  label: '이번에는 참가하지 않을게요',
                  onPressed: _busy
                      ? null
                      : () => _run(
                          () => _repository.declineInvitation(meetingId),
                          successNotice: '참가하지 않기로 처리했어요.',
                        ),
                ),
              ],
            ],
          ),
        );

      case BlindMeetingStatus.awaitingDeposits:
        final paid = me?.depositStatus == BlindMeetingDepositStatus.paid;
        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                paid ? '보증금 결제가 완료됐어요' : '개인별 보증금을 결제해주세요',
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                paid
                    ? '나머지 참가자의 결제를 기다리고 있어요.'
                    : '노쇼를 막기 위한 보증금이에요. 정상 참석 후 종료 안전도장까지 완료하면 전액 환급돼요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 10),
              Text(
                '보증금 ${BlindMeetingPolicy.current.depositAmount}원',
                style: BlindMeetingText.body(palette.ink),
              ),
              if (!paid) ...[
                const SizedBox(height: 16),
                BlindMeetingPrimaryButton(
                  label: '보증금 결제하기',
                  loading: _busy,
                  onPressed: _busy
                      ? null
                      : () => _run(() async {
                          final intent = await _repository.startDeposit(
                            meetingId,
                          );
                          await _analytics.log(
                            BlindMeetingAnalyticsEvent.depositCompleted,
                            params: {
                              'meetingId': meetingId,
                              'depositStatus': intent.status.name,
                            },
                          );
                          if (!mounted) return;
                          setState(
                            () => _actionNotice =
                                intent.message ??
                                '결제 상태: ${intent.status.name}',
                          );
                        }),
                ),
              ],
            ],
          ),
        );

      case BlindMeetingStatus.confirmed:
      case BlindMeetingStatus.chatOpen:
      case BlindMeetingStatus.scheduleConfirmed:
      case BlindMeetingStatus.checkinOpen:
      case BlindMeetingStatus.inProgress:
        final showCheckin =
            session.status == BlindMeetingStatus.scheduleConfirmed ||
            session.status == BlindMeetingStatus.checkinOpen ||
            session.status == BlindMeetingStatus.inProgress;
        final showCheckout =
            (session.status == BlindMeetingStatus.checkinOpen ||
                session.status == BlindMeetingStatus.inProgress) &&
            (me?.checkedIn ?? false);

        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '단체 채팅에서 약속을 정해주세요',
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                '여섯 명이 모두 확정되어 단체 채팅방이 열렸어요.\n시간과 장소를 정하고, 도착 후 안전도장을 찍어주세요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 16),
              BlindMeetingPrimaryButton(
                label: '단체 채팅방 열기',
                icon: Icons.forum_outlined,
                onPressed: session.groupChatId == null
                    ? null
                    : () => Navigator.of(context).pushNamed(
                        RouteNames.chatRoom,
                        arguments: ChatRoomData(
                          chatRoomId: session.groupChatId!,
                          partnerId: '',
                          partnerName: '블라인드 취향 미팅',
                          partnerUniversity: '3:3 단체 채팅',
                        ),
                      ),
              ),
              const SizedBox(height: 10),
              BlindMeetingSecondaryButton(
                label: '약속 시간·장소 투표하기',
                onPressed: _busy ? null : () => _openScheduleVote(session),
              ),
              if (session.status == BlindMeetingStatus.scheduleConfirmed) ...[
                const SizedBox(height: 10),
                _attendanceRow(palette, session, me),
              ],
              if (showCheckin) ...[
                const SizedBox(height: 10),
                BlindMeetingSecondaryButton(
                  label: (me?.checkedIn ?? false) ? '도착 안전도장 완료' : '도착 안전도장 찍기',
                  onPressed: (_busy || (me?.checkedIn ?? false))
                      ? null
                      : () => _markStamp(meetingId, isCheckout: false),
                ),
              ],
              if (showCheckout) ...[
                const SizedBox(height: 10),
                BlindMeetingSecondaryButton(
                  label: (me?.checkedOut ?? false)
                      ? '종료 안전도장 완료'
                      : '종료 안전도장 찍기',
                  onPressed: (_busy || (me?.checkedOut ?? false))
                      ? null
                      : () => _markStamp(meetingId, isCheckout: true),
                ),
              ],
              if (session.fivePersonVoteOpen) ...[
                const SizedBox(height: 16),
                Text(
                  '참가자 한 분이 참석하지 못했어요.',
                  style: BlindMeetingText.body(palette.ink),
                ),
                const SizedBox(height: 8),
                BlindMeetingSecondaryButton(
                  label: '다섯 명이서 미팅을 계속 진행할게요',
                  onPressed: _busy
                      ? null
                      : () => _run(
                          () => _repository.voteFivePersonException(
                            meetingId: meetingId,
                            agree: true,
                          ),
                          successNotice: '5인 진행에 동의했어요.',
                        ),
                ),
                const SizedBox(height: 8),
                BlindMeetingSecondaryButton(
                  label: '오늘은 진행하지 않고 재매칭을 받을게요',
                  onPressed: _busy
                      ? null
                      : () => _run(
                          () => _repository.voteFivePersonException(
                            meetingId: meetingId,
                            agree: false,
                          ),
                          successNotice: '재매칭으로 처리할게요.',
                        ),
                ),
              ],
              const SizedBox(height: 10),
              BlindMeetingSecondaryButton(
                label: '참가 취소 요청',
                onPressed: _busy
                    ? null
                    : () => _run(
                        () => _repository.requestCancellation(
                          meetingId: meetingId,
                        ),
                        successNotice: '취소 요청을 접수했어요. 대체 참가자를 찾아볼게요.',
                      ),
              ),
            ],
          ),
        );

      case BlindMeetingStatus.completed:
      case BlindMeetingStatus.followupOpen:
        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '미팅이 마무리됐어요',
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                '만족도를 남기고, 다시 대화해보고 싶은 사람을 조용히 선택해보세요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 16),
              BlindMeetingPrimaryButton(
                label: '후속 대화 선택하기',
                onPressed: () => Navigator.of(context).pushNamed(
                  RouteNames.blindTasteMeetingFollowUp,
                  arguments: BlindMeetingMeetingArgs(meetingId: meetingId),
                ),
              ),
              const SizedBox(height: 10),
              BlindMeetingSecondaryButton(
                label: '만족도 남기기',
                onPressed: () => Navigator.of(context).pushNamed(
                  RouteNames.blindTasteMeetingFeedback,
                  arguments: BlindMeetingMeetingArgs(meetingId: meetingId),
                ),
              ),
            ],
          ),
        );

      case BlindMeetingStatus.cancelled:
        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '이번 미팅은 진행되지 않았어요',
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                '정상 참석자에게는 보증금을 전액 환급하고 다음 미팅 우선권을 드려요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
            ],
          ),
        );

      default:
        return BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _statusLabel(session.status),
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                '진행 상황이 바뀌면 알림을 보내드려요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
            ],
          ),
        );
    }
  }

  /// 24시간 / 3시간 전 참석 재확인.
  Widget _attendanceRow(
    BlindMeetingPalette palette,
    BlindMeetingSession session,
    BlindMeetingParticipant? me,
  ) {
    final startAt = session.scheduledStartAt;
    final now = DateTime.now();
    final untilStart = startAt == null
        ? const Duration(days: 365)
        : startAt.difference(now);
    final isFinalPhase = untilStart <= const Duration(hours: 3);
    final phase = isFinalPhase ? '3h' : '24h';
    final answered = isFinalPhase
        ? me?.attendanceConfirmation3h != AttendanceConfirmation.pending
        : me?.attendanceConfirmation24h != AttendanceConfirmation.pending;

    if (answered) {
      return Text(
        isFinalPhase ? '오늘 참석 확인을 완료했어요.' : '참석 확인을 완료했어요.',
        style: BlindMeetingText.caption(palette.positive),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          isFinalPhase ? '오늘 미팅 참석 준비는 괜찮으신가요?' : '내일 블라인드 취향 미팅에 참석할 수 있나요?',
          style: BlindMeetingText.body(palette.ink),
        ),
        const SizedBox(height: 8),
        BlindMeetingSecondaryButton(
          label: isFinalPhase ? '예정대로 참석해요' : '참석할게요',
          onPressed: _busy
              ? null
              : () => _run(
                  () => _repository.confirmAttendance(
                    meetingId: session.meetingId,
                    phase: phase,
                    attending: true,
                  ),
                  successNotice: '참석 확인을 보냈어요.',
                ),
        ),
        const SizedBox(height: 8),
        BlindMeetingSecondaryButton(
          label: isFinalPhase ? '문제가 생겼어요' : '참석이 어려워요',
          onPressed: _busy
              ? null
              : () => _run(
                  () => _repository.confirmAttendance(
                    meetingId: session.meetingId,
                    phase: phase,
                    attending: false,
                  ),
                  successNotice: '대체 참가자를 찾아볼게요.',
                ),
        ),
      ],
    );
  }

  Future<void> _openScheduleVote(BlindMeetingSession session) async {
    final venues = await _repository.loadVenueOptions(
      alcoholFreeOnly: session.isAlcoholFree,
    );
    if (!mounted) return;

    // 날짜 후보는 여섯 명이 신청 단계에서 공통으로 고른 날짜만 쓴다.
    // 세부 시간은 이 시트에서 정한다.
    final candidateDateKeys = session.scheduleDateCandidates;
    // analytics는 UI를 막지 않도록 await 하지 않는다.
    _analytics.log(
      BlindMeetingAnalyticsEvent.scheduleVoteOpened,
      params: {
        'meetingId': session.meetingId,
        'candidateDateCount': candidateDateKeys.length,
      },
    );
    final vote = await showBlindMeetingScheduleVoteSheet(
      context,
      candidateDateKeys: candidateDateKeys,
      venueOptions: venues
          .map(
            (v) => BlindMeetingVenueOption(
              placeId: v.placeId,
              name: v.name,
              category: v.category,
              alcoholFreeFriendly: v.alcoholFreeFriendly,
            ),
          )
          .toList(),
      initialSlotIds: session.slot == null
          ? const <String>[]
          : <String>[session.slot!.slotId],
    );
    if (vote == null || !mounted) return;

    await _run(
      () => _repository.voteSchedule(
        meetingId: session.meetingId,
        preferredSlotIds: vote.preferredSlotIds,
        preferredPlaceId: vote.preferredPlaceId,
      ),
      successNotice: '투표를 보냈어요. 전원이 투표하면 확정돼요.',
    );
    _analytics.log(
      BlindMeetingAnalyticsEvent.scheduleVoteSubmitted,
      params: {
        'meetingId': session.meetingId,
        'votedDateCount': vote.preferredSlotIds
            .map((s) => s.split('#').first)
            .toSet()
            .length,
      },
    );
  }

  Future<void> _markStamp(String meetingId, {required bool isCheckout}) async {
    final confirmed = await confirmBlindMeetingSafetyStamp(
      context,
      isCheckout: isCheckout,
    );
    if (!confirmed || !mounted) return;
    await _run(
      () => _repository.markSafetyStamp(
        meetingId: meetingId,
        phase: isCheckout ? 'goodbye' : 'meetup',
      ),
      successNotice: isCheckout ? '종료 안전도장을 찍었어요.' : '도착 안전도장을 찍었어요.',
    );
    if (!mounted) return;
    await _analytics.log(
      isCheckout
          ? BlindMeetingAnalyticsEvent.checkoutCompleted
          : BlindMeetingAnalyticsEvent.checkinCompleted,
      params: {'meetingId': meetingId},
    );
  }

  Widget _teamSection(
    BlindMeetingPalette palette,
    String title,
    List<BlindMeetingPublicProfile> profiles, {
    required bool isMyTeam,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isMyTeam ? palette.accent : palette.accentDeep,
              ),
            ),
            const SizedBox(width: 8),
            Text(title, style: BlindMeetingText.sectionTitle(palette.ink)),
          ],
        ),
        const SizedBox(height: 12),
        if (profiles.isEmpty)
          BlindMeetingEmptyState(
            title: '프로필을 준비하고 있어요',
            description: '잠시 후 다시 확인해주세요.',
          )
        else
          for (final profile in profiles)
            BlindMeetingProfileCard(
              profile: profile,
              isMe: isMyTeam && profile.userId == _view?.me?.userId,
            ),
      ],
    );
  }

  String _statusLabel(BlindMeetingStatus status) => switch (status) {
    BlindMeetingStatus.applicationOpen => '신청 접수',
    BlindMeetingStatus.forming => '팀 구성 중',
    BlindMeetingStatus.awaitingAcceptance => '참가 수락 대기',
    BlindMeetingStatus.awaitingDeposits => '보증금 결제 대기',
    BlindMeetingStatus.confirmed => '미팅 확정',
    BlindMeetingStatus.chatOpen => '단체 채팅 진행',
    BlindMeetingStatus.scheduleConfirmed => '일정 확정',
    BlindMeetingStatus.checkinOpen => '도착 안전도장',
    BlindMeetingStatus.inProgress => '미팅 진행 중',
    BlindMeetingStatus.completed => '미팅 종료',
    BlindMeetingStatus.followupOpen => '후속 선택 진행',
    BlindMeetingStatus.readOnly => '읽기 전용',
    BlindMeetingStatus.archived => '보관됨',
    BlindMeetingStatus.cancelled => '취소됨',
  };
}

/// 추천 안내 배너를 한 번 노출하고 analytics 이벤트를 기록한다.
class _RecommendationBannerSlot extends StatefulWidget {
  final bool alcoholFree;
  final VoidCallback onShown;

  const _RecommendationBannerSlot({
    required this.alcoholFree,
    required this.onShown,
  });

  @override
  State<_RecommendationBannerSlot> createState() =>
      _RecommendationBannerSlotState();
}

class _RecommendationBannerSlotState extends State<_RecommendationBannerSlot> {
  @override
  void initState() {
    super.initState();
    widget.onShown();
  }

  @override
  Widget build(BuildContext context) {
    return BlindMeetingRecommendationBanner(alcoholFree: widget.alcoholFree);
  }
}
