// =============================================================================
// 3:3 블라인드 취향 미팅 — 일정 선택 및 신청 제출
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_dna.dart';
import '../../domain/blind_meeting_enums.dart';
import '../../domain/blind_meeting_slot.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingScheduleScreen extends StatefulWidget {
  final BlindMeetingDnaDraft draft;
  final BlindMeetingRepository? repository;

  /// 테스트에서 날짜를 고정하기 위한 기준 시각.
  final DateTime? now;

  const BlindMeetingScheduleScreen({
    super.key,
    required this.draft,
    this.repository,
    this.now,
  });

  @override
  State<BlindMeetingScheduleScreen> createState() =>
      _BlindMeetingScheduleScreenState();
}

class _BlindMeetingScheduleScreenState
    extends State<BlindMeetingScheduleScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  final Set<String> _selectedSlotIds = <String>{};
  bool _waitlistOptIn = true;
  bool _submitting = false;
  String? _error;

  /// 선택 가능한 날짜: 내일부터 14일.
  List<DateTime> get _dates {
    final base = widget.now ?? DateTime.now();
    final start = DateTime(base.year, base.month, base.day);
    return List.generate(14, (i) => start.add(Duration(days: i + 1)));
  }

  bool get _alcoholFreeRequested =>
      widget.draft.alcoholPreference == AlcoholCompanionPreference.allSober;

  String _dateKey(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';

  static const List<String> _weekdayLabels = [
    '월',
    '화',
    '수',
    '목',
    '금',
    '토',
    '일',
  ];

  Future<void> _submit() async {
    if (_selectedSlotIds.isEmpty || _submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });

    final slots = BlindMeetingSlot.parseList(_selectedSlotIds.toList());
    final dna = widget.draft.toDna(slots: slots, waitlistOptIn: _waitlistOptIn);

    final violations = dna.validate();
    if (violations.isNotEmpty) {
      setState(() {
        _submitting = false;
        _error = violations.first.message;
      });
      return;
    }

    try {
      final result = await _repository.submitApplication(dna);
      if (!mounted) return;
      if (!result.accepted) {
        setState(() {
          _submitting = false;
          _error = result.message ?? '신청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.';
        });
        return;
      }
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.blindTasteMeetingWaiting);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = '$error';
      });
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
            title: '가능한 일정',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.only(top: 8, bottom: 32),
              child: BlindMeetingResponsiveBody(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '가능한 날짜와 시간을\n모두 선택해주세요',
                      style: BlindMeetingText.title(palette.ink),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '많이 선택할수록 더 빨리 팀이 구성돼요.',
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                    const SizedBox(height: 20),
                    if (_alcoholFreeRequested)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: BlindMeetingCard(
                          background: palette.surfaceMuted,
                          child: Row(
                            children: [
                              Icon(
                                Icons.local_cafe_outlined,
                                size: 18,
                                color: palette.sage,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  '무알코올 미팅으로 신청돼요. 여섯 명 모두 비음주인 미팅만 배정됩니다.',
                                  style: BlindMeetingText.caption(palette.ink),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    for (final date in _dates) _dateCard(palette, date),
                    const SizedBox(height: 8),
                    BlindMeetingCard(
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '대기자로도 참여할게요',
                                  style: BlindMeetingText.body(palette.ink),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '정원이 차면 대기자로 등록되고, 빈자리가 생기면 먼저 제안을 받아요.',
                                  style: BlindMeetingText.caption(
                                    palette.inkSoft,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: _waitlistOptIn,
                            activeThumbColor: palette.plum,
                            onChanged: (value) =>
                                setState(() => _waitlistOptIn = value),
                          ),
                        ],
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      BlindMeetingErrorState(message: _error!),
                    ],
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: BlindMeetingResponsiveBody(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
              child: BlindMeetingPrimaryButton(
                label: _selectedSlotIds.isEmpty
                    ? '가능한 시간을 선택해주세요'
                    : '참가 신청하기 (${_selectedSlotIds.length}개 선택)',
                loading: _submitting,
                onPressed: _selectedSlotIds.isEmpty ? null : _submit,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _dateCard(BlindMeetingPalette palette, DateTime date) {
    final dateKey = _dateKey(date);
    final weekday = _weekdayLabels[date.weekday - 1];

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: BlindMeetingCard(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${date.month}월 ${date.day}일 ($weekday)',
              style: BlindMeetingText.sectionTitle(palette.ink),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: BlindMeetingTimeBlock.values.map((block) {
                final slotId = '$dateKey#${block.name}';
                final selected = _selectedSlotIds.contains(slotId);
                return _timeChip(
                  palette,
                  label: block.shortLabel,
                  selected: selected,
                  semanticsLabel: '${date.month}월 ${date.day}일 ${block.label}',
                  onTap: () => setState(() {
                    if (selected) {
                      _selectedSlotIds.remove(slotId);
                    } else {
                      _selectedSlotIds.add(slotId);
                    }
                  }),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _timeChip(
    BlindMeetingPalette palette, {
    required String label,
    required bool selected,
    required String semanticsLabel,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: selected,
      label: semanticsLabel,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 40, minWidth: 72),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected
                ? palette.plum.withValues(alpha: 0.12)
                : palette.surfaceMuted,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
              color: selected ? palette.plum : Colors.transparent,
            ),
          ),
          child: Text(
            label,
            style: BlindMeetingText.caption(
              selected ? palette.plum : palette.inkSoft,
            ),
          ),
        ),
      ),
    );
  }
}
