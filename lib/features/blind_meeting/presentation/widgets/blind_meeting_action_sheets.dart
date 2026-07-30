// =============================================================================
// 3:3 블라인드 취향 미팅 — 약속잡기 / 안전도장 / 참석 확인 / 5인 진행 액션
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_action_sheets.dart
//
// 최종 시간과 장소 확정, 안전도장 완료 판정, 5인 진행 승인은 모두 서버가 한다.
// 여기서는 사용자의 선택만 수집해서 callable로 넘긴다.
// =============================================================================

import 'package:flutter/material.dart';

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
/// 후보 시간은 내 DNA에 저장된 가능한 시간과 현재 배정된 시간을 합쳐 보여준다.
Future<BlindMeetingScheduleVote?> showBlindMeetingScheduleVoteSheet(
  BuildContext context, {
  required List<BlindMeetingSlot> candidateSlots,
  required List<BlindMeetingVenueOption> venueOptions,
  List<String> initialSlotIds = const <String>[],
  String? initialPlaceId,
}) {
  return showModalBottomSheet<BlindMeetingScheduleVote>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => _ScheduleVoteSheet(
      candidateSlots: candidateSlots,
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
  final List<BlindMeetingSlot> candidateSlots;
  final List<BlindMeetingVenueOption> venueOptions;
  final List<String> initialSlotIds;
  final String? initialPlaceId;

  const _ScheduleVoteSheet({
    required this.candidateSlots,
    required this.venueOptions,
    required this.initialSlotIds,
    this.initialPlaceId,
  });

  @override
  State<_ScheduleVoteSheet> createState() => _ScheduleVoteSheetState();
}

class _ScheduleVoteSheetState extends State<_ScheduleVoteSheet> {
  late final Set<String> _slotIds = {...widget.initialSlotIds};
  String? _placeId;

  @override
  void initState() {
    super.initState();
    _placeId = widget.initialPlaceId;
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
                '가능한 시간과 장소를 선택해주세요. 여섯 명의 투표를 모아 확정해요.',
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
              const SizedBox(height: 18),
              Text('후보 시간', style: BlindMeetingText.sectionTitle(palette.ink)),
              const SizedBox(height: 10),
              if (widget.candidateSlots.isEmpty)
                Text(
                  '선택할 수 있는 시간이 없어요.',
                  style: BlindMeetingText.caption(palette.inkFaint),
                )
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: widget.candidateSlots.map((slot) {
                    final selected = _slotIds.contains(slot.slotId);
                    return _chip(
                      palette,
                      label: slot.label,
                      selected: selected,
                      onTap: () => setState(() {
                        if (selected) {
                          _slotIds.remove(slot.slotId);
                        } else {
                          _slotIds.add(slot.slotId);
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
                onPressed: _slotIds.isEmpty
                    ? null
                    : () => Navigator.of(context).pop(
                        BlindMeetingScheduleVote(
                          preferredSlotIds: _slotIds.toList(),
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
            ? '미팅이 정상적으로 끝났다면 종료 안전도장을 찍어주세요.\n참가자 전원이 완료하면 보증금이 환급돼요.'
            : '장소에 도착했다면 도착 안전도장을 찍어주세요.\n전원이 완료되면 미팅이 시작돼요.',
        style: BlindMeetingText.body(palette.inkSoft),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: Text('나중에', style: BlindMeetingText.body(palette.inkSoft)),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: palette.plum),
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('안전도장 찍기'),
        ),
      ],
    ),
  );
  return result == true;
}
