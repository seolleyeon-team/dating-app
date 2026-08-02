// =============================================================================
// 3:3 블라인드 취향 미팅 — 가능한 날짜/시간 슬롯
// 경로: lib/features/blind_meeting/domain/blind_meeting_slot.dart
// =============================================================================

/// 미팅 시간 블록.
enum BlindMeetingTimeBlock {
  /// 점심 (12:00~14:00)
  lunch,

  /// 오후 (15:00~17:00)
  afternoon,

  /// 저녁 (18:00~20:00)
  evening,

  /// 늦은 저녁 (20:00~22:00)
  lateEvening,
}

extension BlindMeetingTimeBlockLabel on BlindMeetingTimeBlock {
  String get label => switch (this) {
    BlindMeetingTimeBlock.lunch => '점심 12:00~14:00',
    BlindMeetingTimeBlock.afternoon => '오후 15:00~17:00',
    BlindMeetingTimeBlock.evening => '저녁 18:00~20:00',
    BlindMeetingTimeBlock.lateEvening => '늦은 저녁 20:00~22:00',
  };

  String get shortLabel => switch (this) {
    BlindMeetingTimeBlock.lunch => '점심',
    BlindMeetingTimeBlock.afternoon => '오후',
    BlindMeetingTimeBlock.evening => '저녁',
    BlindMeetingTimeBlock.lateEvening => '늦은 저녁',
  };

  /// 해당 블록의 시작 시각(시).
  int get startHour => switch (this) {
    BlindMeetingTimeBlock.lunch => 12,
    BlindMeetingTimeBlock.afternoon => 15,
    BlindMeetingTimeBlock.evening => 18,
    BlindMeetingTimeBlock.lateEvening => 20,
  };
}

/// 참가 가능한 (날짜, 시간 블록) 조합.
///
/// [dateKey]는 KST 기준 `yyyy-MM-dd`.
class BlindMeetingSlot implements Comparable<BlindMeetingSlot> {
  final String dateKey;
  final BlindMeetingTimeBlock timeBlock;

  const BlindMeetingSlot({required this.dateKey, required this.timeBlock});

  /// Firestore/쿼리에 사용하는 안정적인 슬롯 id (`2026-08-01#evening`).
  String get slotId => '$dateKey#${timeBlock.name}';

  static BlindMeetingSlot? tryParse(Object? raw) {
    if (raw is BlindMeetingSlot) return raw;
    if (raw is Map) {
      final dateKey = raw['dateKey']?.toString().trim() ?? '';
      final blockName = raw['timeBlock']?.toString().trim() ?? '';
      return _build(dateKey, blockName);
    }
    final text = raw?.toString().trim() ?? '';
    if (text.isEmpty) return null;
    final parts = text.split('#');
    if (parts.length != 2) return null;
    return _build(parts[0].trim(), parts[1].trim());
  }

  static BlindMeetingSlot? _build(String dateKey, String blockName) {
    if (!_dateKeyPattern.hasMatch(dateKey)) return null;
    for (final block in BlindMeetingTimeBlock.values) {
      if (block.name == blockName) {
        return BlindMeetingSlot(dateKey: dateKey, timeBlock: block);
      }
    }
    return null;
  }

  static final RegExp _dateKeyPattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

  /// 문자열/맵 리스트를 정렬·중복 제거된 슬롯 목록으로 변환한다.
  static List<BlindMeetingSlot> parseList(Object? raw) {
    if (raw is! Iterable) return const <BlindMeetingSlot>[];
    final byId = <String, BlindMeetingSlot>{};
    for (final item in raw) {
      final slot = tryParse(item);
      if (slot != null) byId[slot.slotId] = slot;
    }
    final list = byId.values.toList()..sort();
    return List<BlindMeetingSlot>.unmodifiable(list);
  }

  String get label {
    final parts = dateKey.split('-');
    if (parts.length != 3) return '$dateKey ${timeBlock.shortLabel}';
    final month = int.tryParse(parts[1]);
    final day = int.tryParse(parts[2]);
    if (month == null || day == null) {
      return '$dateKey ${timeBlock.shortLabel}';
    }
    return '$month월 $day일 ${timeBlock.shortLabel}';
  }

  Map<String, dynamic> toMap() => {
    'dateKey': dateKey,
    'timeBlock': timeBlock.name,
    'slotId': slotId,
  };

  @override
  int compareTo(BlindMeetingSlot other) {
    final byDate = dateKey.compareTo(other.dateKey);
    if (byDate != 0) return byDate;
    return timeBlock.index.compareTo(other.timeBlock.index);
  }

  @override
  bool operator ==(Object other) =>
      other is BlindMeetingSlot && other.slotId == slotId;

  @override
  int get hashCode => slotId.hashCode;

  @override
  String toString() => slotId;
}
