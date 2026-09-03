// =============================================================================
// 3:3 블라인드 취향 미팅 — 매칭 대기 화면
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart
//
// 무한 spinner만 보여주지 않고 현재 단계를 명확히 표시한다.
// 상태는 blindMeetingApplications/{uid} 문서에서 오므로 앱을 종료하거나
// 다시 로그인해도 정확히 복구된다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_analytics.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_application.dart';
import '../../domain/blind_meeting_availability.dart';
import '../../domain/blind_meeting_party.dart';
import '../blind_meeting_route_args.dart';
import '../blind_meeting_navigation.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_action_sheets.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingWaitingScreen extends StatefulWidget {
  final BlindMeetingRepository? repository;
  final BlindMeetingAnalytics? analytics;

  const BlindMeetingWaitingScreen({super.key, this.repository, this.analytics});

  @override
  State<BlindMeetingWaitingScreen> createState() =>
      _BlindMeetingWaitingScreenState();
}

class _BlindMeetingWaitingScreenState extends State<BlindMeetingWaitingScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();
  late final Stream<BlindMeetingApplication?> _stream = _repository
      .watchMyApplication();

  bool _busy = false;
  bool _leaving = false;
  String? _error;

  /// 취소 성공 안내 (서버 응답 기준). 화면 메모리가 아니라 문서 상태와 함께
  /// 보여준다.
  BlindMeetingCancelResult? _cancelResult;

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// 조건 완화 적용.
  ///
  /// '다른 날짜도 가능해요'는 추가 날짜가 반드시 있어야 한다.
  /// 서버가 빈 목록을 거부하므로 날짜를 먼저 고르게 한다.
  Future<void> _applyRelaxation(
    BlindMeetingRelaxationChoice choice,
    BlindMeetingApplication application,
  ) async {
    var additionalDateKeys = const <String>[];

    if (choice == BlindMeetingRelaxationChoice.openToOtherDates) {
      final picked = await showBlindMeetingExtraDatesSheet(
        context,
        alreadySelected: application.requestedDateKeys.toSet(),
      );
      if (picked == null || picked.isEmpty) return;
      additionalDateKeys = picked;
    }

    await _run(
      () => _repository.applyRelaxationChoice(
        choice,
        additionalDateKeys: additionalDateKeys,
      ),
    );

    (widget.analytics ?? BlindMeetingAnalytics()).log(
      BlindMeetingAnalyticsEvent.availabilityRelaxed,
      params: {
        'relaxationChoice': choice.name,
        'addedDateCount': additionalDateKeys.length,
      },
    );
  }

  void _openMeeting(String meetingId) {
    if (_leaving) return;
    _leaving = true;
    Navigator.of(context).pushReplacementNamed(
      RouteNames.blindTasteMeetingResult,
      arguments: BlindMeetingMeetingArgs(
        meetingId: meetingId,
        showRecommendationBanner: true,
      ),
    );
  }

  void _handleExit() {
    if (!mounted || _leaving) return;
    _leaving = true;
    returnToBlindMeetingIntro(context);
  }

  /// 매칭 전 신청 취소.
  ///
  /// 서버가 신청 문서를 cancelled 로 옮기고 하트를 정확히 한 번 돌려준다.
  /// 취소 버튼을 누른 순간 서버에서 매칭 tx 가 이미 commit 됐을 수 있다 —
  /// 그 경우 서버는 CANNOT_CANCEL_ALREADY_MATCHED 로 거부하고, 여기서는
  /// "취소 성공" 으로 거짓 응답하지 않고 매칭 결과(채팅)로 복구한다.
  Future<void> _cancelApplication(BlindMeetingApplication application) async {
    if (_busy || !application.canCancel) return;
    final confirmed = await showBlindMeetingCancelApplicationSheet(
      context,
      heartCost: application.heartCost,
      refundable: application.heartChargeCount > 0 && application.heartCost > 0,
    );
    if (!confirmed || !mounted) return;

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await _repository.cancelApplication();
      if (!mounted) return;
      (widget.analytics ?? BlindMeetingAnalytics()).log(
        BlindMeetingAnalyticsEvent.applicationCancelled,
        params: {
          'cancelOutcome': result.outcome,
          'heartRefunded': result.heartRefunded,
        },
      );
      setState(() => _cancelResult = result);
    } on BlindMeetingAlreadyMatchedException catch (error) {
      if (!mounted) return;
      // 매칭이 먼저 commit 됨: 취소 불가. canonical 상태로 복구한다.
      final meetingId = error.meetingId ?? application.meetingId;
      if (meetingId != null && meetingId.isNotEmpty) {
        _openMeeting(meetingId);
        return;
      }
      setState(() => _error = error.toString());
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openDnaEditor(BlindMeetingApplication application) async {
    if (_busy || !application.canEditDna) return;
    await _run(() async {
      final profile = await _repository.loadProfileSnapshot();
      if (profile == null) {
        throw StateError('프로필 정보를 불러오지 못했어요.');
      }
      if (!mounted) return;
      await Navigator.of(context, rootNavigator: true).pushNamed(
        RouteNames.blindTasteMeetingDna,
        arguments: BlindMeetingDnaRouteArgs(
          profile: profile,
          mode: BlindMeetingDnaMode.editExistingApplication,
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _handleExit();
      },
      child: Scaffold(
        backgroundColor: palette.background,
        body: Column(
          children: [
            BlindMeetingAppBar(title: '매칭 진행 상황', onBack: _handleExit),
            Expanded(
              child: StreamBuilder<BlindMeetingApplication?>(
                stream: _stream,
                builder: (context, snapshot) {
                  if (snapshot.hasError) {
                    return _wrap(
                      BlindMeetingErrorState(message: '${snapshot.error}'),
                    );
                  }
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  final application = snapshot.data;
                  if (application == null) {
                    return _wrap(
                      const BlindMeetingEmptyState(
                        title: '진행 중인 신청이 없어요',
                        description: '블라인드 취향 미팅에 새로 신청해보세요.',
                      ),
                    );
                  }

                  // 매칭 = 확정. 수락 화면 없이 곧바로 매칭 결과(채팅 진입)로 간다.
                  // 앱을 껐다 켜도 문서가 matched 이면 같은 경로로 복구된다.
                  if (application.isMatched) {
                    final meetingId = application.meetingId!;
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      if (mounted) _openMeeting(meetingId);
                    });
                    return _wrap(_matchedContent(palette));
                  }

                  // 취소된 신청은 "진행 중" 이 아니다. 서버 문서(canonical)가
                  // cancelled 이면 대기 UI/취소 버튼을 다시 보여주지 않는다.
                  if (application.isCancelled) {
                    return _wrap(_cancelledContent(palette, application));
                  }

                  if (!application.isAwaitingMatch) {
                    return _wrap(
                      const BlindMeetingEmptyState(
                        title: '진행 중인 신청이 없어요',
                        description: '블라인드 취향 미팅에 새로 신청해보세요.',
                      ),
                    );
                  }

                  return _wrap(_buildContent(palette, application));
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _wrap(Widget child) => SingleChildScrollView(
    physics: const BouncingScrollPhysics(),
    padding: const EdgeInsets.only(top: 8, bottom: 40),
    child: BlindMeetingResponsiveBody(child: child),
  );

  /// 매칭 직후 잠깐 보이는 안내 (곧 결과 화면으로 넘어간다).
  Widget _matchedContent(BlindMeetingPalette palette) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('3:3 미팅이 매칭됐어요!', style: BlindMeetingText.title(palette.ink)),
        const SizedBox(height: 8),
        Text(
          '새로운 3:3 채팅방이 열렸어요. 매칭 결과로 이동할게요.',
          style: BlindMeetingText.caption(palette.inkSoft),
        ),
      ],
    );
  }

  /// 취소 완료 상태. 더 이상 "신청 진행 중" 이 아니며 재신청할 수 있다.
  Widget _cancelledContent(
    BlindMeetingPalette palette,
    BlindMeetingApplication application,
  ) {
    final result = _cancelResult;
    final refunded = result?.heartRefunded ?? application.heartRefundedAmount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('신청이 취소됐어요.', style: BlindMeetingText.title(palette.ink)),
        const SizedBox(height: 8),
        Text(
          refunded > 0
              ? '신청에 쓴 하트 $refunded개를 환불했어요. 작성한 미팅 DNA와 날짜는 그대로 보관돼요.'
              : '작성한 미팅 DNA와 날짜는 그대로 보관돼요.',
          style: BlindMeetingText.caption(palette.inkSoft),
        ),
        const SizedBox(height: 20),
        BlindMeetingPrimaryButton(
          key: const ValueKey('blind-meeting-reapply'),
          label: '미팅 신청하기',
          onPressed: _handleExit,
        ),
      ],
    );
  }

  Widget _buildContent(
    BlindMeetingPalette palette,
    BlindMeetingApplication application,
  ) {
    final stage = application.stage;
    final waitingForParty =
        stage == BlindMeetingMatchingStage.waitingForPartyMembers ||
        stage == BlindMeetingMatchingStage.waitingForCommonDates;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('매칭 준비 중', style: BlindMeetingText.title(palette.ink)),
        const SizedBox(height: 4),
        Text(stage.label, style: BlindMeetingText.sectionTitle(palette.ink)),
        const SizedBox(height: 8),
        Text(
          waitingForParty
              ? '함께 시작한 친구 전원이 날짜 신청을 마쳐야 같은 미팅으로 배정돼요.\n앱을 닫아도 진행 상황은 그대로 유지돼요.'
              : '조건에 맞는 여섯 명이 모이면 바로 미팅이 확정되고 3:3 채팅방이 열려요.\n앱을 닫아도 진행 상황은 그대로 유지돼요.',
          style: BlindMeetingText.caption(palette.inkSoft),
        ),
        const SizedBox(height: 20),
        if (waitingForParty && application.partyId != null)
          StreamBuilder<BlindMeetingParty?>(
            stream: _repository.watchParty(application.partyId!),
            builder: (context, snapshot) {
              final party = snapshot.data;
              final completed = party?.completedApplicationUserIds.length ?? 0;
              final total =
                  party?.memberCount ?? application.partyMemberIds.length;
              return BlindMeetingCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$completed/$total명 날짜 신청 완료',
                      style: BlindMeetingText.sectionTitle(palette.ink),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: total <= 0 ? 0 : completed / total,
                      color: palette.accent,
                      backgroundColor: palette.surfaceMuted,
                    ),
                    if (stage ==
                        BlindMeetingMatchingStage.waitingForCommonDates) ...[
                      const SizedBox(height: 10),
                      Text(
                        '전원이 선택한 날짜 중 겹치는 날이 없어요. DNA 수정에서 날짜를 추가해주세요.',
                        style: BlindMeetingText.caption(palette.inkSoft),
                      ),
                    ],
                  ],
                ),
              );
            },
          )
        else
          BlindMeetingCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 수락 단계가 없으므로 "참가자 확정 대기" 단계는 없다.
                // 상대 팀 확인이 끝나면 곧바로 확정 + 채팅방이다.
                for (final step in const [
                  BlindMeetingMatchingStage.searchingCandidates,
                  BlindMeetingMatchingStage.formingOwnTeam,
                  BlindMeetingMatchingStage.checkingCrossTeam,
                ])
                  _stageRow(
                    palette,
                    label: step.label,
                    done:
                        stage.stepIndex > step.stepIndex ||
                        stage == BlindMeetingMatchingStage.matched,
                    active: stage.stepIndex == step.stepIndex,
                  ),
              ],
            ),
          ),
        const SizedBox(height: 16),
        BlindMeetingCard(
          background: palette.surfaceMuted,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('신청 정보', style: BlindMeetingText.sectionTitle(palette.ink)),
              const SizedBox(height: 10),
              Text(
                '참여 가능한 날짜 ${application.requestedDateKeys.length}개',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 4),
              Text(
                application.requestedDateKeys
                    .map(BlindMeetingAvailability.shortLabel)
                    .join(' · '),
                style: BlindMeetingText.caption(palette.ink),
              ),
              const SizedBox(height: 8),
              Text(
                '구체적인 시간은 팀이 구성된 뒤 단체 채팅방에서 함께 정해요.',
                style: BlindMeetingText.caption(palette.inkFaint),
              ),
              if (application.prefersAlcoholFree) ...[
                const SizedBox(height: 8),
                BlindMeetingBadge(
                  label: '무알코올 미팅',
                  icon: Icons.local_cafe_outlined,
                  color: palette.positive,
                ),
              ],
            ],
          ),
        ),
        if (application.needsRelaxationChoice) ...[
          const SizedBox(height: 16),
          _relaxationCard(palette, application),
        ],
        if (_error != null) ...[
          const SizedBox(height: 16),
          BlindMeetingErrorState(message: _error!),
        ],
        const SizedBox(height: 20),
        if (application.canCancel)
          BlindMeetingSecondaryButton(
            key: const ValueKey('blind-meeting-cancel-application'),
            label: '신청 취소하기',
            onPressed: _busy ? null : () => _cancelApplication(application),
          ),
        if (application.canEditDna) ...[
          const SizedBox(height: 12),
          BlindMeetingSecondaryButton(
            key: const ValueKey('blind-meeting-dna-edit'),
            label: 'DNA 수정하기',
            onPressed: _busy ? null : () => _openDnaEditor(application),
          ),
        ],
      ],
    );
  }

  Widget _relaxationCard(
    BlindMeetingPalette palette,
    BlindMeetingApplication application,
  ) {
    return BlindMeetingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '아직 조건에 맞는 참가자가 충분하지 않아요.',
            style: BlindMeetingText.sectionTitle(palette.ink),
          ),
          const SizedBox(height: 6),
          Text(
            '조건은 자동으로 바뀌지 않아요. 원하는 방향을 직접 선택해주세요.',
            style: BlindMeetingText.caption(palette.inkSoft),
          ),
          const SizedBox(height: 14),
          for (final choice in BlindMeetingRelaxationChoice.values)
            if (choice != BlindMeetingRelaxationChoice.allowLightDrinking ||
                application.prefersAlcoholFree)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: BlindMeetingSecondaryButton(
                  label: choice.label,
                  onPressed: _busy
                      ? null
                      : () => _applyRelaxation(choice, application),
                ),
              ),
        ],
      ),
    );
  }

  Widget _stageRow(
    BlindMeetingPalette palette, {
    required String label,
    required bool done,
    required bool active,
  }) {
    final color = done
        ? palette.positive
        : active
        ? palette.accent
        : palette.inkFaint;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(
            done
                ? Icons.check_circle
                : active
                ? Icons.radio_button_checked
                : Icons.radio_button_unchecked,
            size: 18,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              label,
              style: BlindMeetingText.body(
                active ? palette.ink : palette.inkSoft,
              ),
            ),
          ),
          if (active)
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: palette.accent,
              ),
            ),
        ],
      ),
    );
  }
}
