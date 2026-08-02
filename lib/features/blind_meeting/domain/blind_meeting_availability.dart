// =============================================================================
// 3:3 블라인드 취향 미팅 — 참여 가능 날짜 (date-only availability)
// 경로: lib/features/blind_meeting/domain/blind_meeting_availability.dart
//
// 정책
//  - 참가 신청 단계에서는 '날짜'만 고른다. 세부 시간은 팀 구성 후 단체 채팅방의
//    약속잡기에서 정한다.
//  - 선택 가능 범위는 내일부터 총 [blindMeetingAvailabilityWindowDays]일.
//  - 날짜 식별자는 KST(Asia/Seoul) 기준 `yyyy-MM-dd` 문자열이다.
//    Firestore Timestamp를 날짜 식별자로 쓰지 않는다 (timezone 오류 방지).
//
// 이 파일은 앱과 서버(functions/src/blindMeeting/types.ts)의 공통 계약이다.
// 두 구현의 창 길이와 date key 규칙은 반드시 동일해야 한다.
// =============================================================================

/// 참여 가능 날짜를 고를 수 있는 기간 (내일 포함 총 일수).
const int blindMeetingAvailabilityWindowDays = 21;

/// 신청 문서에 기록하는 availability 방식.
const String blindMeetingAvailabilityModeDateOnly = 'date_only';

/// 날짜 전용 선택으로 전환된 스키마 버전.
const int blindMeetingScheduleSelectionVersion = 2;

/// KST 기준 오프셋. 한국 서비스이므로 서버·앱 모두 이 기준을 쓴다.
const Duration _kstOffset = Duration(hours: 9);

final RegExp _dateKeyPattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

/// 참여 가능 날짜 관련 순수 계산 모음.
///
/// 모든 날짜 anchor는 `DateTime.utc(y, m, d)` 로 만든다. 로컬 타임존/DST 때문에
/// `add(Duration(days: n))` 결과가 하루 밀리는 문제를 막기 위한 것이다.
class BlindMeetingAvailability {
  const BlindMeetingAvailability._();

  /// [instant]가 KST에서 속하는 날짜의 자정(UTC anchor).
  static DateTime kstDayOf(DateTime instant) {
    final kst = instant.toUtc().add(_kstOffset);
    return DateTime.utc(kst.year, kst.month, kst.day);
  }

  /// KST 기준 오늘. 선택 불가 날짜다.
  static DateTime today(DateTime now) => kstDayOf(now);

  /// 선택 가능한 첫 날짜 (KST 기준 내일).
  static DateTime firstSelectableDate(DateTime now) =>
      kstDayOf(now).add(const Duration(days: 1));

  /// 선택 가능한 마지막 날짜 (내일 포함 21번째 날).
  static DateTime lastSelectableDate(DateTime now) => firstSelectableDate(
    now,
  ).add(const Duration(days: blindMeetingAvailabilityWindowDays - 1));

  /// 선택 가능한 날짜 전체 (오름차순, 총 [blindMeetingAvailabilityWindowDays]개).
  static List<DateTime> selectableDates(DateTime now) {
    final first = firstSelectableDate(now);
    return List<DateTime>.unmodifiable(
      List<DateTime>.generate(
        blindMeetingAvailabilityWindowDays,
        (i) => first.add(Duration(days: i)),
      ),
    );
  }

  /// 선택 가능한 날짜 key 전체 (오름차순).
  static List<String> selectableDateKeys(DateTime now) =>
      List<String>.unmodifiable(selectableDates(now).map(formatDateKey));

  /// `yyyy-MM-dd` 문자열로 변환한다.
  static String formatDateKey(DateTime date) {
    final year = date.year.toString().padLeft(4, '0');
    final month = date.month.toString().padLeft(2, '0');
    final day = date.day.toString().padLeft(2, '0');
    return '$year-$month-$day';
  }

  /// `yyyy-MM-dd`를 UTC anchor로 변환한다. 형식이나 달력상 존재하지 않는 날짜면 null.
  ///
  /// `2026-02-30`처럼 존재하지 않는 날짜는 round-trip 검증으로 걸러진다.
  static DateTime? parseDateKey(Object? raw) {
    final text = raw?.toString().trim() ?? '';
    if (!_dateKeyPattern.hasMatch(text)) return null;
    final parts = text.split('-');
    final year = int.tryParse(parts[0]);
    final month = int.tryParse(parts[1]);
    final day = int.tryParse(parts[2]);
    if (year == null || month == null || day == null) return null;
    if (month < 1 || month > 12 || day < 1 || day > 31) return null;
    final date = DateTime.utc(year, month, day);
    if (formatDateKey(date) != text) return null;
    return date;
  }

  static bool isValidDateKey(Object? raw) => parseDateKey(raw) != null;

  /// 유효한 날짜만 남기고 중복을 제거해 오름차순으로 정렬한다.
  static List<String> normalizeDateKeys(Object? raw) {
    if (raw is! Iterable) return const <String>[];
    final unique = <String>{};
    for (final item in raw) {
      final date = parseDateKey(item);
      if (date != null) unique.add(formatDateKey(date));
    }
    final sorted = unique.toList()..sort();
    return List<String>.unmodifiable(sorted);
  }

  /// legacy 슬롯 id(`2026-08-01#evening`)에서 날짜 부분만 추출한다.
  ///
  /// 세부 시간 정보는 버리고 날짜만 복원한다. 원본 문서는 수정하지 않는다.
  static List<String> dateKeysFromLegacySlots(Object? raw) {
    if (raw is! Iterable) return const <String>[];
    final unique = <String>{};
    for (final item in raw) {
      if (item is Map) {
        final date = parseDateKey(item['dateKey']);
        if (date != null) unique.add(formatDateKey(date));
        continue;
      }
      final text = item?.toString().trim() ?? '';
      if (text.isEmpty) continue;
      final date = parseDateKey(text.split('#').first.trim());
      if (date != null) unique.add(formatDateKey(date));
    }
    final sorted = unique.toList()..sort();
    return List<String>.unmodifiable(sorted);
  }

  /// 날짜 전용 필드를 우선 읽고, 없으면 legacy 슬롯에서 날짜를 복원한다.
  static List<String> readDateKeys({Object? dateKeys, Object? legacySlots}) {
    final direct = normalizeDateKeys(dateKeys);
    if (direct.isNotEmpty) return direct;
    return dateKeysFromLegacySlots(legacySlots);
  }

  /// 선택 가능 범위 안의 날짜인지. 오늘·과거·범위 밖은 false.
  static bool isWithinWindow(Object? raw, DateTime now) {
    final date = parseDateKey(raw);
    if (date == null) return false;
    final first = firstSelectableDate(now);
    final last = lastSelectableDate(now);
    return !date.isBefore(first) && !date.isAfter(last);
  }

  /// 범위 안의 날짜만 남긴다 (정렬·중복 제거 포함).
  static List<String> retainWithinWindow(Object? raw, DateTime now) {
    final normalized = normalizeDateKeys(raw);
    return List<String>.unmodifiable(
      normalized.where((key) => isWithinWindow(key, now)),
    );
  }

  /// 범위를 벗어나 만료된 날짜만 돌려준다 (자정 경과 안내용).
  static List<String> expiredKeys(Object? raw, DateTime now) {
    final normalized = normalizeDateKeys(raw);
    return List<String>.unmodifiable(
      normalized.where((key) => !isWithinWindow(key, now)),
    );
  }

  /// 여러 참가자의 가능 날짜 교집합. 하나라도 비어 있으면 결과도 비어 있다.
  static List<String> commonDateKeys(
    Iterable<Iterable<String>> perParticipant,
  ) {
    final groups = perParticipant.toList();
    if (groups.isEmpty) return const <String>[];
    Set<String>? intersection;
    for (final group in groups) {
      final normalized = normalizeDateKeys(group).toSet();
      if (normalized.isEmpty) return const <String>[];
      intersection = intersection == null
          ? normalized
          : intersection.intersection(normalized);
      if (intersection.isEmpty) return const <String>[];
    }
    final sorted = (intersection ?? <String>{}).toList()..sort();
    return List<String>.unmodifiable(sorted);
  }

  /// 선택 범위와 겹치는 월 목록 (캘린더 탐색 제한용, 오름차순).
  static List<DateTime> selectableMonths(DateTime now) {
    final first = firstSelectableDate(now);
    final last = lastSelectableDate(now);
    final months = <DateTime>[];
    var cursor = DateTime.utc(first.year, first.month);
    final end = DateTime.utc(last.year, last.month);
    while (!cursor.isAfter(end)) {
      months.add(cursor);
      cursor = cursor.month == 12
          ? DateTime.utc(cursor.year + 1, 1)
          : DateTime.utc(cursor.year, cursor.month + 1);
    }
    return List<DateTime>.unmodifiable(months);
  }

  /// 선택 범위가 두 달에 걸쳐 있는지 (analytics용, 개인 날짜는 보내지 않는다).
  static bool crossesMonthBoundary(DateTime now) =>
      selectableMonths(now).length > 1;

  static const List<String> weekdayLabels = ['월', '화', '수', '목', '금', '토', '일'];

  /// `7월 31일(금)` 형태의 짧은 라벨.
  static String shortLabel(Object? raw) {
    final date = parseDateKey(raw);
    if (date == null) return raw?.toString() ?? '';
    final weekday = weekdayLabels[date.weekday - 1];
    return '${date.month}월 ${date.day}일($weekday)';
  }

  /// `8월 2일 일요일` 형태의 접근성 라벨.
  static String accessibilityLabel(Object? raw) {
    final date = parseDateKey(raw);
    if (date == null) return raw?.toString() ?? '';
    final weekday = weekdayLabels[date.weekday - 1];
    return '${date.month}월 ${date.day}일 $weekday요일';
  }

  /// 선택 요약. 날짜가 많으면 앞 2개 + `외 N일`로 줄인다.
  static String selectionSummary(
    Iterable<String> dateKeys, {
    int visibleCount = 2,
  }) {
    final keys = normalizeDateKeys(dateKeys);
    if (keys.isEmpty) return '';
    if (keys.length <= visibleCount) {
      return keys.map(shortLabel).join(', ');
    }
    final head = keys.take(visibleCount).map(shortLabel).join(', ');
    return '$head 외 ${keys.length - visibleCount}일';
  }
}
