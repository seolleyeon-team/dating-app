// =============================================================================
// 3:3 블라인드 취향 미팅 — 약속잡기 / 안전도장 / 참석 확인 / 5인 진행 액션
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_action_sheets.dart
//
// 최종 시간과 장소 확정, 안전도장 완료 판정, 5인 진행 승인은 모두 서버가 한다.
// 여기서는 사용자의 선택만 수집해서 callable로 넘긴다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../domain/blind_meeting_availability.dart';
import '../../domain/blind_meeting_slot.dart';
import '../theme/blind_meeting_palette.dart';
import 'blind_meeting_common.dart';

/// 약속 시간·장소 투표 결과.
class BlindMeetingScheduleVote {
  final List<String> preferredSlotIds;
  final String? preferredPlaceId;

  const BlindMeetingScheduleVote({
    required this.preferredSlotIds,
    this.preferredPlaceId,
  });
}

/// 약속잡기 투표 시트.
///
/// 날짜 후보는 참가 신청 단계에서 여섯 명이 공통으로 선택한 날짜
/// (`session.commonAvailableDateKeys`)만 쓴다. 구체적인 시간은 여기서 정한다.
///
/// 흐름: 날짜 하나 선택 → 그 날짜의 가능한 시간대 선택 → 장소 선택 → 투표.
Future<BlindMeetingScheduleVote?> showBlindMeetingScheduleVoteSheet(
  BuildContext context, {
  required List<String> candidateDateKeys,
  required List<BlindMeetingVenueOption> venueOptions,
  List<String> initialSlotIds = const <String>[],
  String? initialPlaceId,
}) {
  return showModalBottomSheet<BlindMeetingScheduleVote>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => _ScheduleVoteSheet(
      candidateDateKeys: BlindMeetingAvailability.normalizeDateKeys(
        candidateDateKeys,
      ),
      venueOptions: venueOptions,
      initialSlotIds: initialSlotIds,
      initialPlaceId: initialPlaceId,
    ),
  );
}

/// 장소 후보 (무알코올 미팅에 맞는 분류 표시 포함).
class BlindMeetingVenueOption {
  final String placeId;
  final String name;
  final String? category;
  final bool alcoholFreeFriendly;

  const BlindMeetingVenueOption({
    required this.placeId,
    required this.name,
    this.category,
    this.alcoholFreeFriendly = false,
  });
}

class _ScheduleVoteSheet extends StatefulWidget {
  final List<String> candidateDateKeys;
  final List<BlindMeetingVenueOption> venueOptions;
  final List<String> initialSlotIds;
  final String? initialPlaceId;

  const _ScheduleVoteSheet({
    required this.candidateDateKeys,
    required this.venueOptions,
    required this.initialSlotIds,
    this.initialPlaceId,
  });

  @override
  State<_ScheduleVoteSheet> createState() => _ScheduleVoteSheetState();
}

class _ScheduleVoteSheetState extends State<_ScheduleVoteSheet> {
  /// 선택한 날짜. 날짜를 먼저 정하고 그 날짜의 시간대를 고른다.
  String? _dateKey;

  /// 선택한 시간대 (선택한 날짜 기준).
  final Set<BlindMeetingTimeBlock> _timeBlocks = <BlindMeetingTimeBlock>{};

  String? _placeId;

  @override
  void initState() {
    super.initState();
    _placeId = widget.initialPlaceId;
    _restoreInitialSlots();
  }

  /// 기존 투표를 날짜 + 시간대 형태로 복구한다.
  void _restoreInitialSlots() {
    final slots = BlindMeetingSlot.parseList(
      widget.initialSlotIds,
    ).where((slot) => widget.candidateDateKeys.contains(slot.dateKey));
    if (slots.isEmpty) {
      _dateKey = widget.candidateDateKeys.length == 1
          ? widget.candidateDateKeys.first
          : null;
      return;
    }
    _dateKey = slots.first.dateKey;
    _timeBlocks.addAll(
      slots.where((s) => s.dateKey == _dateKey).map((s) => s.timeBlock),
    );
  }

  List<String> get _selectedSlotIds {
    final dateKey = _dateKey;
    if (dateKey == null || _timeBlocks.isEmpty) return const <String>[];
    final blocks = _timeBlocks.toList()
      ..sort((a, b) => a.index.compareTo(b.index));
    return blocks
        .map(
          (block) =>
              BlindMeetingSlot(dateKey: dateKey, timeBlock: block).slotId,
        )
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return SafeArea(
      top: false,
      child: Container(
        decoration: BoxDecoration(
          color: palette.background,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('약속잡기', style: BlindMeetingText.title(palette.ink)),
              const SizedBox(height: 6),
              Text(
                '여섯 명이 모두 가능한 날짜예요. 날짜와 시간을 골라주세요.\n'
                '투표를 모아 최종 시간과 장소를 확정해요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 18),
              Text('후보 날짜', style: BlindMeetingText.sectionTitle(palette.ink)),
              const SizedBox(height: 10),
              if (widget.candidateDateKeys.isEmpty)
                Text(
                  '선택할 수 있는 날짜가 없어요.',
                  style: BlindMeetingText.caption(palette.inkFaint),
                )
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: widget.candidateDateKeys.map((dateKey) {
                    final selected = _dateKey == dateKey;
                    return _chip(
                      palette,
                      label: BlindMeetingAvailability.shortLabel(dateKey),
                      selected: selected,
                      onTap: () => setState(() {
                        if (selected) {
                          _dateKey = null;
                        } else {
                          _dateKey = dateKey;
                        }
                        // 날짜가 바뀌면 시간 선택을 초기화한다.
                        _timeBlocks.clear();
                      }),
                    );
                  }).toList(),
                ),
              const SizedBox(height: 20),
              Text('후보 시간', style: BlindMeetingText.sectionTitle(palette.ink)),
              const SizedBox(height: 10),
              if (_dateKey == null)
                Text(
                  '날짜를 먼저 선택하면 시간을 고를 수 있어요.',
                  style: BlindMeetingText.caption(palette.inkFaint),
                )
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: BlindMeetingTimeBlock.values.map((block) {
                    final selected = _timeBlocks.contains(block);
                    return _chip(
                      palette,
                      label: block.label,
                      selected: selected,
                      onTap: () => setState(() {
                        if (selected) {
                          _timeBlocks.remove(block);
                        } else {
                          _timeBlocks.add(block);
                        }
                      }),
                    );
                  }).toList(),
                ),
              const SizedBox(height: 20),
              Text('후보 장소', style: BlindMeetingText.sectionTitle(palette.ink)),
              const SizedBox(height: 10),
              if (widget.venueOptions.isEmpty)
                Text(
                  '장소 후보는 단체 채팅에서 함께 정해요.',
                  style: BlindMeetingText.caption(palette.inkFaint),
                )
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: widget.venueOptions.map((option) {
                    final selected = _placeId == option.placeId;
                    return _chip(
                      palette,
                      label: option.alcoholFreeFriendly
                          ? '${option.name} · 무알코올'
                          : option.name,
                      selected: selected,
                      onTap: () => setState(
                        () => _placeId = selected ? null : option.placeId,
                      ),
                    );
                  }).toList(),
                ),
              const SizedBox(height: 24),
              BlindMeetingPrimaryButton(
                label: '투표하기',
                onPressed: _selectedSlotIds.isEmpty
                    ? null
                    : () => Navigator.of(context).pop(
                        BlindMeetingScheduleVote(
                          preferredSlotIds: _selectedSlotIds,
                          preferredPlaceId: _placeId,
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(
    BlindMeetingPalette palette, {
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 40),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected
                ? palette.accent.withValues(alpha: 0.12)
                : palette.surfaceMuted,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
              color: selected ? palette.accent : Colors.transparent,
            ),
          ),
          child: Text(
            label,
            style: BlindMeetingText.caption(
              selected ? palette.accent : palette.inkSoft,
            ),
          ),
        ),
      ),
    );
  }
}

/// 안전도장 안내 + 확인 다이얼로그.
///
/// 실제 완료 판정과 미팅 상태 전환은 서버가 수행한다.
Future<bool> confirmBlindMeetingSafetyStamp(
  BuildContext context, {
  required bool isCheckout,
}) async {
  final palette = BlindMeetingPalette.of(context);
  final result = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: palette.surface,
      title: Text(
        isCheckout ? '종료 안전도장' : '도착 안전도장',
        style: BlindMeetingText.sectionTitle(palette.ink),
      ),
      content: Text(
        isCheckout
            ? '미팅이 정상적으로 끝났다면 종료 안전도장을 찍어주세요.\n안전도장으로 만남을 마무리할 수 있어요.'
            : '장소에 도착했다면 도착 안전도장을 찍어주세요.\n전원이 완료되면 미팅이 시작돼요.',
        style: BlindMeetingText.body(palette.inkSoft),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: Text('나중에', style: BlindMeetingText.body(palette.inkSoft)),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: palette.accent),
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('안전도장 찍기'),
        ),
      ],
    ),
  );
  return result == true;
}

// =============================================================================
// 신청 취소 확인 (매칭 전 전용)
// =============================================================================

/// 매칭 전 "신청 취소하기" 확인. 매칭 후 참가 거절과는 다른 기능이다.
///
/// [refundable] 이면 신청에 쓴 하트가 정확히 한 번 돌아온다는 점을 안내한다.
Future<bool> showBlindMeetingCancelApplicationSheet(
  BuildContext context, {
  required int heartCost,
  required bool refundable,
}) async {
  final palette = BlindMeetingPalette.of(context);
  final result = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: palette.surface,
      title: Text(
        '신청을 취소할까요?',
        style: BlindMeetingText.sectionTitle(palette.ink),
      ),
      content: Text(
        refundable
            ? '매칭 전이라 지금 취소할 수 있어요.\n신청에 쓴 하트 $heartCost개는 바로 환불돼요.\n작성한 미팅 DNA와 날짜는 그대로 보관돼 다음 신청에 불러와요.'
            : '매칭 전이라 지금 취소할 수 있어요.\n작성한 미팅 DNA와 날짜는 그대로 보관돼 다음 신청에 불러와요.',
        style: BlindMeetingText.body(palette.inkSoft),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: Text('계속 기다릴게요', style: BlindMeetingText.body(palette.inkSoft)),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: palette.accent),
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('신청 취소'),
        ),
      ],
    ),
  );
  return result == true;
}

// =============================================================================
// 조건 완화 — 가능한 날짜 추가
// =============================================================================

/// 매칭 대기 중 '다른 날짜도 가능해요'를 고른 사용자가 날짜를 추가하는 시트.
///
/// 서버는 빈 목록을 거부하므로 이 시트 없이 완화를 요청하면 항상 실패한다.
Future<List<String>?> showBlindMeetingExtraDatesSheet(
  BuildContext context, {
  required Set<String> alreadySelected,
  DateTime? now,
}) {
  return showModalBottomSheet<List<String>>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => _ExtraDatesSheet(
      alreadySelected: alreadySelected,
      now: now ?? DateTime.now(),
    ),
  );
}

class _ExtraDatesSheet extends StatefulWidget {
  final Set<String> alreadySelected;
  final DateTime now;

  const _ExtraDatesSheet({required this.alreadySelected, required this.now});

  @override
  State<_ExtraDatesSheet> createState() => _ExtraDatesSheetState();
}

class _ExtraDatesSheetState extends State<_ExtraDatesSheet> {
  final Set<String> _picked = <String>{};

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    // 이미 신청한 날짜는 추가 대상이 아니다.
    final options = BlindMeetingAvailability.selectableDateKeys(
      widget.now,
    ).where((key) => !widget.alreadySelected.contains(key)).toList();

    return SafeArea(
      top: false,
      child: Container(
        decoration: BoxDecoration(
          color: palette.background,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('가능한 날짜 추가', style: BlindMeetingText.title(palette.ink)),
              const SizedBox(height: 6),
              Text(
                '날짜를 더 열어두면 팀이 더 빨리 만들어져요.\n'
                '이미 신청한 날짜는 그대로 유지돼요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 18),
              if (options.isEmpty)
                Text(
                  '추가할 수 있는 날짜가 없어요. 선택 가능한 기간의 모든 날짜를 이미 신청했어요.',
                  style: BlindMeetingText.caption(palette.inkFaint),
                )
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: options.map((key) {
                    final selected = _picked.contains(key);
                    return _PillChip(
                      label: BlindMeetingAvailability.shortLabel(key),
                      selected: selected,
                      onTap: () => setState(() {
                        if (selected) {
                          _picked.remove(key);
                        } else {
                          _picked.add(key);
                        }
                      }),
                    );
                  }).toList(),
                ),
              const SizedBox(height: 20),
              BlindMeetingPrimaryButton(
                label: _picked.isEmpty
                    ? '추가할 날짜를 선택해주세요'
                    : '${_picked.length}개 날짜 추가하기',
                onPressed: _picked.isEmpty
                    ? null
                    : () => Navigator.of(context).pop(
                        BlindMeetingAvailability.normalizeDateKeys(_picked),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 시트 안에서 쓰는 pill 형태 선택 chip.
class _PillChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _PillChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 40),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected
                ? palette.accent.withValues(alpha: 0.12)
                : palette.surfaceMuted,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
              color: selected ? palette.accent : Colors.transparent,
            ),
          ),
          child: Text(
            label,
            style: BlindMeetingText.caption(
              selected ? palette.accent : palette.ink,
            ),
          ),
        ),
      ),
    );
  }
}
