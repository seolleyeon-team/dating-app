// =============================================================================
// 3:3 블라인드 취향 미팅 — 비공개 후속 선택
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_follow_up_screen.dart
//
// 선택 대상은 상대 팀 세 명뿐, 최대 2명, 24시간.
// 일방 선택 사실은 상대에게 알리지 않고, 누구에게도 선택받지 않았다는
// 메시지를 표시하지 않는다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../../chat/models/chat_room_data.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_followup.dart';
import '../../domain/blind_meeting_public_profile.dart';
import '../../domain/blind_meeting_session.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';
import '../widgets/blind_meeting_profile_card.dart';

class BlindMeetingFollowUpScreen extends StatefulWidget {
  final BlindMeetingMeetingArgs args;
  final BlindMeetingRepository? repository;
  final DateTime? now;

  const BlindMeetingFollowUpScreen({
    super.key,
    required this.args,
    this.repository,
    this.now,
  });

  @override
  State<BlindMeetingFollowUpScreen> createState() =>
      _BlindMeetingFollowUpScreenState();
}

class _BlindMeetingFollowUpScreenState
    extends State<BlindMeetingFollowUpScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  bool _loading = true;
  String? _error;
  bool _submitting = false;
  String? _submitError;

  BlindMeetingRecommendationView? _view;
  BlindMeetingFollowUpChoice? _choice;
  List<BlindMeetingMutualMatch> _mutualMatches =
      const <BlindMeetingMutualMatch>[];
  final Set<String> _selected = <String>{};

  DateTime get _now => widget.now ?? DateTime.now();

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
      final choice = await _repository
          .watchMyFollowUpChoice(widget.args.meetingId)
          .first;
      final matches = await _repository.loadMutualMatches(
        widget.args.meetingId,
      );
      if (!mounted) return;
      setState(() {
        _view = view;
        _choice = choice;
        _mutualMatches = matches;
        _selected
          ..clear()
          ..addAll(choice?.selectedUids ?? const <String>[]);
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

  BlindMeetingFollowUpState? _state() {
    final view = _view;
    final choice = _choice;
    if (view == null) return null;
    return BlindMeetingFollowUpState(
      selectableUids: view.opponentTeam.map((p) => p.userId).toList(),
      choice:
          choice ??
          BlindMeetingFollowUpChoice(
            meetingId: widget.args.meetingId,
            chooserUid: view.me?.userId ?? '',
          ),
      closesAt: view.session.followupClosesAt,
      chooserAttended: view.me?.checkedOut ?? true,
      mutualMatches: _mutualMatches,
    );
  }

  Future<void> _submit() async {
    final state = _state();
    if (state == null || _submitting) return;

    final violations = state.validate(_selected.toList(), now: _now);
    if (violations.isNotEmpty) {
      setState(() => _submitError = violations.first.message);
      return;
    }

    setState(() {
      _submitting = true;
      _submitError = null;
    });
    try {
      await _repository.submitFollowUpChoice(
        meetingId: widget.args.meetingId,
        selectedUids: _selected.toList(),
      );
      if (!mounted) return;
      await _load();
    } catch (error) {
      if (!mounted) return;
      setState(() => _submitError = '$error');
    } finally {
      if (mounted) setState(() => _submitting = false);
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
            title: '후속 대화 선택',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(child: _buildBody(palette)),
        ],
      ),
    );
  }

  Widget _buildBody(BlindMeetingPalette palette) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    final error = _error;
    if (error != null) {
      return _wrap(BlindMeetingErrorState(message: error, onRetry: _load));
    }

    final state = _state();
    final view = _view;
    if (state == null || view == null) {
      return _wrap(
        const BlindMeetingEmptyState(
          title: '선택할 수 있는 미팅이 없어요',
          description: '참가했던 미팅이 아니거나 선택 기간이 끝났어요.',
        ),
      );
    }

    final closed = !state.isOpenAt(_now);
    final submitted = state.choice.isSubmitted;

    return _wrap(
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '다시 대화해보고 싶은 사람을\n선택해주세요.',
            style: BlindMeetingText.title(palette.ink),
          ),
          const SizedBox(height: 10),
          Text(
            '최대 2명까지 선택할 수 있어요.\n'
            '선택 결과는 다른 사람에게 공개되지 않으며,\n'
            '서로 선택한 경우에만 1:1 채팅이 열려요.',
            style: BlindMeetingText.body(palette.inkSoft),
          ),
          const SizedBox(height: 20),
          if (_mutualMatches.isNotEmpty) _mutualCard(palette),
          if (_mutualMatches.isNotEmpty) const SizedBox(height: 16),
          if (!state.chooserAttended)
            BlindMeetingEmptyState(
              title: '선택할 수 없어요',
              description:
                  BlindMeetingFollowUpViolation.chooserNotAttended.message,
            )
          else ...[
            for (final profile in view.opponentTeam)
              _selectableCard(palette, profile, disabled: closed || submitted),
            const SizedBox(height: 8),
            if (submitted)
              Text(
                '선택을 제출했어요. 결과는 상호 선택이 확인되면 알려드려요.',
                style: BlindMeetingText.caption(palette.sage),
              )
            else if (closed)
              Text(
                BlindMeetingFollowUpViolation.windowClosed.message,
                style: BlindMeetingText.caption(palette.inkFaint),
              ),
            if (_submitError != null) ...[
              const SizedBox(height: 12),
              BlindMeetingErrorState(message: _submitError!),
            ],
            const SizedBox(height: 20),
            BlindMeetingPrimaryButton(
              label: _selected.isEmpty ? '선택하지 않고 마치기' : '선택 제출하기',
              loading: _submitting,
              onPressed: (closed || submitted) ? null : _submit,
            ),
          ],
          const SizedBox(height: 16),
          Text(
            '같은 팀원은 선택 대상이 아니에요.',
            style: BlindMeetingText.caption(palette.inkFaint),
          ),
        ],
      ),
    );
  }

  Widget _wrap(Widget child) => SingleChildScrollView(
    physics: const BouncingScrollPhysics(),
    padding: const EdgeInsets.only(top: 8, bottom: 48),
    child: BlindMeetingResponsiveBody(child: child),
  );

  Widget _mutualCard(BlindMeetingPalette palette) {
    return BlindMeetingCard(
      highlighted: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '서로 다시 대화해보고 싶어 했어요.',
            style: BlindMeetingText.sectionTitle(palette.ink),
          ),
          const SizedBox(height: 6),
          Text(
            '부담 없이 첫 대화를 시작해보세요.',
            style: BlindMeetingText.caption(palette.inkSoft),
          ),
          const SizedBox(height: 14),
          for (final match in _mutualMatches)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: BlindMeetingSecondaryButton(
                label: '1:1 채팅 열기',
                onPressed: () => Navigator.of(context).pushNamed(
                  RouteNames.chatRoom,
                  arguments: ChatRoomData(
                    chatRoomId: match.chatRoomId,
                    partnerId: match.partnerUid,
                    partnerName: _nicknameOf(match.partnerUid),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _nicknameOf(String userId) {
    final view = _view;
    if (view == null) return '상대';
    for (final profile in [...view.opponentTeam, ...view.myTeam]) {
      if (profile.userId == userId) return profile.nickname;
    }
    return '상대';
  }

  Widget _selectableCard(
    BlindMeetingPalette palette,
    BlindMeetingPublicProfile profile, {
    required bool disabled,
  }) {
    final selected = _selected.contains(profile.userId);

    return Semantics(
      button: true,
      selected: selected,
      enabled: !disabled,
      label: '${profile.nickname} 선택',
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: disabled
            ? null
            : () => setState(() {
                if (selected) {
                  _selected.remove(profile.userId);
                } else {
                  if (_selected.length >= blindMeetingFollowUpMaxSelections) {
                    _submitError =
                        BlindMeetingFollowUpViolation.tooManySelections.message;
                    return;
                  }
                  _submitError = null;
                  _selected.add(profile.userId);
                }
              }),
        child: Stack(
          children: [
            BlindMeetingProfileCard(profile: profile),
            Positioned(
              top: 16,
              right: 16,
              child: Icon(
                selected ? Icons.check_circle : Icons.circle_outlined,
                size: 22,
                color: selected ? palette.plum : palette.inkFaint,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
