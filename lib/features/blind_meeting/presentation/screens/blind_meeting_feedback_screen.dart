// =============================================================================
// 3:3 블라인드 취향 미팅 — 미팅 후 만족도
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_feedback_screen.dart
// =============================================================================

import 'package:flutter/material.dart';

import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_feedback.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingFeedbackScreen extends StatefulWidget {
  final BlindMeetingMeetingArgs args;
  final BlindMeetingRepository? repository;

  const BlindMeetingFeedbackScreen({
    super.key,
    required this.args,
    this.repository,
  });

  @override
  State<BlindMeetingFeedbackScreen> createState() =>
      _BlindMeetingFeedbackScreenState();
}

class _BlindMeetingFeedbackScreenState
    extends State<BlindMeetingFeedbackScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  final Map<BlindMeetingFeedbackQuestion, int> _ratings = {};
  final Set<BlindMeetingFeedbackReason> _reasons = {};
  bool _safetyConcern = false;
  bool _submitting = false;
  String? _error;
  bool _done = false;

  bool get _complete =>
      BlindMeetingFeedbackQuestion.values.every((q) => _ratings[q] != null);

  Future<void> _submit() async {
    if (!_complete || _submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final userId = await _repository.currentUserId();
      await _repository.submitFeedback(
        BlindMeetingFeedback(
          meetingId: widget.args.meetingId,
          userId: userId ?? '',
          ratings: _ratings,
          reasons: _reasons,
          safetyConcernReported: _safetyConcern,
        ),
      );
      if (!mounted) return;
      setState(() => _done = true);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '$error');
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
            title: '미팅 만족도',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.only(top: 8, bottom: 40),
              child: BlindMeetingResponsiveBody(
                child: _done
                    ? BlindMeetingCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '소중한 의견 고맙습니다',
                              style: BlindMeetingText.title(palette.ink),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '남겨주신 내용은 다음 팀 구성을 더 정확하게 만드는 데 사용해요.',
                              style: BlindMeetingText.caption(palette.inkSoft),
                            ),
                          ],
                        ),
                      )
                    : _buildForm(palette),
              ),
            ),
          ),
          if (!_done)
            SafeArea(
              top: false,
              child: BlindMeetingResponsiveBody(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                child: BlindMeetingPrimaryButton(
                  label: '만족도 제출하기',
                  loading: _submitting,
                  onPressed: _complete ? _submit : null,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildForm(BlindMeetingPalette palette) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final question in BlindMeetingFeedbackQuestion.values)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: BlindMeetingCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    question.label,
                    style: BlindMeetingText.body(palette.ink),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      for (var score = 1; score <= 5; score++)
                        _scoreButton(palette, question, score),
                    ],
                  ),
                ],
              ),
            ),
          ),
        BlindMeetingCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '해당되는 내용이 있다면 알려주세요 (선택)',
                style: BlindMeetingText.body(palette.ink),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: BlindMeetingFeedbackReason.values.map((reason) {
                  final selected = _reasons.contains(reason);
                  return Semantics(
                    button: true,
                    selected: selected,
                    label: reason.label,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(999),
                      onTap: () => setState(() {
                        if (selected) {
                          _reasons.remove(reason);
                        } else {
                          _reasons.add(reason);
                        }
                      }),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: selected
                              ? palette.plum.withValues(alpha: 0.10)
                              : palette.surfaceMuted,
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(
                            color: selected ? palette.plum : Colors.transparent,
                          ),
                        ),
                        child: Text(
                          reason.label,
                          style: BlindMeetingText.caption(
                            selected ? palette.plum : palette.inkSoft,
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        BlindMeetingCard(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '안전과 관련해 알릴 내용이 있어요',
                      style: BlindMeetingText.body(palette.ink),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '체크하시면 운영팀이 별도로 확인하고, 관련 참가자와의 후속 연결을 막아요.',
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                  ],
                ),
              ),
              Switch(
                value: _safetyConcern,
                activeThumbColor: palette.mutedRose,
                onChanged: (value) => setState(() => _safetyConcern = value),
              ),
            ],
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 16),
          BlindMeetingErrorState(message: _error!),
        ],
      ],
    );
  }

  Widget _scoreButton(
    BlindMeetingPalette palette,
    BlindMeetingFeedbackQuestion question,
    int score,
  ) {
    final selected = _ratings[question] == score;
    return Semantics(
      button: true,
      selected: selected,
      label: '${question.label} $score점',
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: () => setState(() => _ratings[question] = score),
        child: Container(
          width: 48,
          height: 48,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: selected
                ? palette.plum.withValues(alpha: 0.12)
                : palette.surfaceMuted,
            border: Border.all(
              color: selected ? palette.plum : Colors.transparent,
            ),
          ),
          child: Text(
            '$score',
            style: BlindMeetingText.body(
              selected ? palette.plum : palette.inkSoft,
            ),
          ),
        ),
      ),
    );
  }
}
