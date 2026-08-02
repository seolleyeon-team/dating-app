// 3:3 블라인드 취향 미팅 — 참여 가능 날짜 계약 테스트
//
// 앱과 서버(functions/src/blindMeeting/types.ts)가 같은 규칙을 써야 하므로
// 창 길이·date key 형식·교집합 계산을 여기서 고정한다.

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_availability.dart';

void main() {
  // KST 2026-07-30 12:00 (UTC 2026-07-30 03:00)
  final now = DateTime.utc(2026, 7, 30, 3);

  group('선택 가능 범위', () {
    test('내일부터 21일, 총 21개 날짜', () {
      final dates = BlindMeetingAvailability.selectableDates(now);
      expect(blindMeetingAvailabilityWindowDays, 21);
      expect(dates.length, 21);
      expect(BlindMeetingAvailability.formatDateKey(dates.first), '2026-07-31');
      expect(BlindMeetingAvailability.formatDateKey(dates.last), '2026-08-20');
    });

    test('첫 날짜는 내일, 마지막 날짜는 21번째 날', () {
      expect(
        BlindMeetingAvailability.formatDateKey(
          BlindMeetingAvailability.firstSelectableDate(now),
        ),
        '2026-07-31',
      );
      expect(
        BlindMeetingAvailability.formatDateKey(
          BlindMeetingAvailability.lastSelectableDate(now),
        ),
        '2026-08-20',
      );
    });

    test('오늘과 과거, 범위 밖 날짜를 거부한다', () {
      expect(
        BlindMeetingAvailability.isWithinWindow('2026-07-30', now),
        isFalse,
      );
      expect(
        BlindMeetingAvailability.isWithinWindow('2026-07-29', now),
        isFalse,
      );
      expect(
        BlindMeetingAvailability.isWithinWindow('2026-07-31', now),
        isTrue,
      );
      expect(
        BlindMeetingAvailability.isWithinWindow('2026-08-20', now),
        isTrue,
      );
      expect(
        BlindMeetingAvailability.isWithinWindow('2026-08-21', now),
        isFalse,
      );
    });

    test('월 경계를 넘어간다', () {
      final keys = BlindMeetingAvailability.selectableDateKeys(now);
      expect(keys, contains('2026-07-31'));
      expect(keys, contains('2026-08-01'));
      expect(BlindMeetingAvailability.crossesMonthBoundary(now), isTrue);
      expect(BlindMeetingAvailability.selectableMonths(now).length, 2);
    });

    test('연도 경계를 넘어간다', () {
      final yearEnd = DateTime.utc(2026, 12, 20, 3);
      final keys = BlindMeetingAvailability.selectableDateKeys(yearEnd);
      expect(keys.first, '2026-12-21');
      expect(keys.last, '2027-01-10');
      expect(BlindMeetingAvailability.selectableMonths(yearEnd).length, 2);
    });

    test('윤년 2월을 정확히 다룬다', () {
      final leap = DateTime.utc(2028, 2, 20, 3);
      final keys = BlindMeetingAvailability.selectableDateKeys(leap);
      expect(keys, contains('2028-02-29'));
      expect(keys.first, '2028-02-21');
      expect(keys.last, '2028-03-12');
    });

    test('범위가 한 달 안에 들어가면 월이 하나만 나온다', () {
      final midMonth = DateTime.utc(2026, 8, 1, 3);
      expect(BlindMeetingAvailability.selectableMonths(midMonth).length, 1);
      expect(BlindMeetingAvailability.crossesMonthBoundary(midMonth), isFalse);
    });
  });

  group('KST 기준 처리', () {
    test('로컬 시간이 아니라 KST 날짜를 쓴다', () {
      // UTC 2026-07-30 15:30 == KST 2026-07-31 00:30
      final afterKstMidnight = DateTime.utc(2026, 7, 30, 15, 30);
      expect(
        BlindMeetingAvailability.formatDateKey(
          BlindMeetingAvailability.today(afterKstMidnight),
        ),
        '2026-07-31',
      );
      expect(
        BlindMeetingAvailability.selectableDateKeys(afterKstMidnight).first,
        '2026-08-01',
      );
    });

    test('KST 자정 직전에는 날짜가 넘어가지 않는다', () {
      // UTC 2026-07-30 14:59 == KST 2026-07-30 23:59
      final beforeKstMidnight = DateTime.utc(2026, 7, 30, 14, 59);
      expect(
        BlindMeetingAvailability.selectableDateKeys(beforeKstMidnight).first,
        '2026-07-31',
      );
    });

    test('같은 순간을 다른 타임존으로 표현해도 결과가 같다', () {
      final utc = DateTime.utc(2026, 7, 30, 3);
      final local = utc.toLocal();
      expect(
        BlindMeetingAvailability.selectableDateKeys(local),
        BlindMeetingAvailability.selectableDateKeys(utc),
      );
    });
  });

  group('date key 형식', () {
    test('yyyy-MM-dd 왕복 변환', () {
      final date = BlindMeetingAvailability.parseDateKey('2026-08-05');
      expect(date, DateTime.utc(2026, 8, 5));
      expect(BlindMeetingAvailability.formatDateKey(date!), '2026-08-05');
    });

    test('달력에 없는 날짜를 거부한다', () {
      expect(BlindMeetingAvailability.isValidDateKey('2026-02-30'), isFalse);
      expect(BlindMeetingAvailability.isValidDateKey('2026-13-01'), isFalse);
      expect(BlindMeetingAvailability.isValidDateKey('2026-00-10'), isFalse);
      expect(BlindMeetingAvailability.isValidDateKey('2027-02-29'), isFalse);
      expect(BlindMeetingAvailability.isValidDateKey('2028-02-29'), isTrue);
    });

    test('형식이 틀린 값을 거부한다', () {
      for (final bad in const [
        '20260801',
        '2026-8-1',
        '2026/08/01',
        '2026-08-01#evening',
        '',
        'today',
      ]) {
        expect(
          BlindMeetingAvailability.isValidDateKey(bad),
          isFalse,
          reason: bad,
        );
      }
    });
  });

  group('정규화', () {
    test('중복을 제거하고 오름차순으로 정렬한다', () {
      expect(
        BlindMeetingAvailability.normalizeDateKeys([
          '2026-08-05',
          '2026-08-01',
          '2026-08-05',
          '2026-08-03',
        ]),
        ['2026-08-01', '2026-08-03', '2026-08-05'],
      );
    });

    test('잘못된 값은 조용히 걸러진다', () {
      expect(
        BlindMeetingAvailability.normalizeDateKeys([
          '2026-08-01',
          'bad',
          null,
          42,
          '2026-02-30',
        ]),
        ['2026-08-01'],
      );
    });

    test('범위 밖 날짜만 남겨 만료 안내에 쓴다', () {
      final selected = ['2026-07-29', '2026-07-30', '2026-08-01'];
      expect(BlindMeetingAvailability.retainWithinWindow(selected, now), [
        '2026-08-01',
      ]);
      expect(BlindMeetingAvailability.expiredKeys(selected, now), [
        '2026-07-29',
        '2026-07-30',
      ]);
    });
  });

  group('legacy 슬롯 호환', () {
    test('슬롯 id에서 날짜만 추출한다', () {
      expect(
        BlindMeetingAvailability.dateKeysFromLegacySlots([
          '2026-08-05#lunch',
          '2026-08-01#evening',
          '2026-08-01#lateEvening',
        ]),
        ['2026-08-01', '2026-08-05'],
      );
    });

    test('맵 형태 슬롯도 읽는다', () {
      expect(
        BlindMeetingAvailability.dateKeysFromLegacySlots([
          {'dateKey': '2026-08-02', 'timeBlock': 'evening'},
        ]),
        ['2026-08-02'],
      );
    });

    test('날짜 전용 필드가 있으면 legacy를 무시한다', () {
      expect(
        BlindMeetingAvailability.readDateKeys(
          dateKeys: ['2026-08-09'],
          legacySlots: ['2026-08-02#evening'],
        ),
        ['2026-08-09'],
      );
    });

    test('날짜 전용 필드가 없으면 legacy에서 복원한다', () {
      expect(
        BlindMeetingAvailability.readDateKeys(
          dateKeys: null,
          legacySlots: ['2026-08-02#evening'],
        ),
        ['2026-08-02'],
      );
    });
  });

  group('공통 날짜 교집합', () {
    test('여섯 명의 공통 날짜를 계산한다', () {
      final common = BlindMeetingAvailability.commonDateKeys([
        ['2026-08-01', '2026-08-02', '2026-08-03'],
        ['2026-08-02', '2026-08-03'],
        ['2026-08-02', '2026-08-03', '2026-08-09'],
        ['2026-08-03', '2026-08-02'],
        ['2026-08-02', '2026-08-03'],
        ['2026-08-02', '2026-08-05'],
      ]);
      expect(common, ['2026-08-02']);
    });

    test('공통 날짜가 없으면 빈 목록', () {
      expect(
        BlindMeetingAvailability.commonDateKeys([
          ['2026-08-01'],
          ['2026-08-02'],
        ]),
        isEmpty,
      );
    });

    test('한 명이라도 가능 날짜가 없으면 빈 목록', () {
      expect(
        BlindMeetingAvailability.commonDateKeys([
          ['2026-08-01'],
          <String>[],
        ]),
        isEmpty,
      );
    });

    test('입력 순서와 무관하게 같은 결과 (deterministic)', () {
      final a = [
        ['2026-08-03', '2026-08-01'],
        ['2026-08-01', '2026-08-03'],
      ];
      expect(
        BlindMeetingAvailability.commonDateKeys(a),
        BlindMeetingAvailability.commonDateKeys(a.reversed),
      );
      expect(BlindMeetingAvailability.commonDateKeys(a), [
        '2026-08-01',
        '2026-08-03',
      ]);
    });
  });

  group('라벨', () {
    test('짧은 라벨과 접근성 라벨', () {
      expect(BlindMeetingAvailability.shortLabel('2026-07-31'), '7월 31일(금)');
      expect(
        BlindMeetingAvailability.accessibilityLabel('2026-08-02'),
        '8월 2일 일요일',
      );
    });

    test('선택 요약은 개수가 많으면 줄인다', () {
      expect(
        BlindMeetingAvailability.selectionSummary(['2026-07-31', '2026-08-02']),
        '7월 31일(금), 8월 2일(일)',
      );
      expect(
        BlindMeetingAvailability.selectionSummary([
          '2026-07-31',
          '2026-08-02',
          '2026-08-05',
          '2026-08-06',
          '2026-08-07',
        ]),
        '7월 31일(금), 8월 2일(일) 외 3일',
      );
      expect(BlindMeetingAvailability.selectionSummary(const []), '');
    });
  });
}
