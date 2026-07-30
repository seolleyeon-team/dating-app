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
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_application.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingWaitingScreen extends StatefulWidget {
  final BlindMeetingRepository? repository;

  const BlindMeetingWaitingScreen({super.key, this.repository});

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
  String? _error;

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

  void _openMeeting(String meetingId) {
    Navigator.of(context).pushReplacementNamed(
      RouteNames.blindTasteMeetingResult,
      arguments: BlindMeetingMeetingArgs(
        meetingId: meetingId,
        showRecommendationBanner: true,
      ),
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
            title: '매칭 진행 상황',
            onBack: () => Navigator.of(context).maybePop(),
          ),
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

                final meetingId = application.meetingId;
                if (meetingId != null &&
                    meetingId.isNotEmpty &&
                    application.stage == BlindMeetingMatchingStage.matched) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (mounted) _openMeeting(meetingId);
                  });
                }

                return _wrap(_buildContent(palette, application));
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _wrap(Widget child) => SingleChildScrollView(
    physics: const BouncingScrollPhysics(),
    padding: const EdgeInsets.only(top: 8, bottom: 40),
    child: BlindMeetingResponsiveBody(child: child),
  );

  Widget _buildContent(
    BlindMeetingPalette palette,
    BlindMeetingApplication application,
  ) {
    final stage = application.stage;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(stage.label, style: BlindMeetingText.title(palette.ink)),
        const SizedBox(height: 8),
        Text(
          '조건에 맞는 참가자가 모이면 알림을 보내드려요.\n앱을 닫아도 진행 상황은 그대로 유지돼요.',
          style: BlindMeetingText.caption(palette.inkSoft),
        ),
        const SizedBox(height: 20),
        BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final step in const [
                BlindMeetingMatchingStage.searchingCandidates,
                BlindMeetingMatchingStage.formingOwnTeam,
                BlindMeetingMatchingStage.checkingCrossTeam,
                BlindMeetingMatchingStage.awaitingConfirmation,
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
                '가능한 시간 ${application.requestedSlots.length}개',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 4),
              Text(
                application.requestedSlots.map((s) => s.label).join(' · '),
                style: BlindMeetingText.caption(palette.ink),
              ),
              if (application.prefersAlcoholFree) ...[
                const SizedBox(height: 8),
                BlindMeetingBadge(
                  label: '무알코올 미팅',
                  icon: Icons.local_cafe_outlined,
                  color: palette.sage,
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
        BlindMeetingSecondaryButton(
          label: '신청 취소하기',
          onPressed: _busy
              ? null
              : () => _run(() async {
                  await _repository.cancelApplication();
                  if (mounted) Navigator.of(context).maybePop();
                }),
        ),
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
                      : () => _run(
                          () => _repository.applyRelaxationChoice(choice),
                        ),
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
        ? palette.sage
        : active
        ? palette.plum
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
                color: palette.plum,
              ),
            ),
        ],
      ),
    );
  }
}
