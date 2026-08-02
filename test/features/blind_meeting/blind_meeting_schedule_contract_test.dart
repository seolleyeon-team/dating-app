// 3:3 블라인드 취향 미팅 — 날짜 전용 신청 계약 테스트
//
// 화면 → DNA payload → 신청 문서 → 매칭 후보로 이어지는 계약이
// 날짜만 다루는지 검증한다.

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_availability.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_session.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/blind_meeting_route_args.dart';

BlindMeetingDnaDraft draft() => BlindMeetingDnaDraft(
  profile: BlindMeetingProfileSnapshot(
    userId: 'u1',
    nickname: '민지',
    department: '컴퓨터과학과',
    mbti: 'ENFP',
    interests: const ['커피', '영화'],
    drinkingLevel: DrinkingLevel.sometimes,
    smokingStatus: SmokingStatus.nonSmoker,
    schoolVerified: true,
    onboardingUpdatedAt: DateTime.utc(2026, 7, 1),
  ),
  atmosphere: ConversationAtmosphere.calm,
  initiative: ConversationInitiative.adaptive,
  purpose: MeetingPurpose.both,
  alcoholPreference: AlcoholCompanionPreference.noPreference,
  smokingPreference: SmokingCompanionPreference.noPreference,
);

void main() {
  group('DNA draft → 날짜 전용 payload', () {
    test('선택 날짜만 저장하고 정렬·중복 제거한다', () {
      final dna = draft().toDna(
        dateKeys: const ['2026-08-05', '2026-08-01', '2026-08-05'],
        waitlistOptIn: true,
      );
      expect(dna.availableDateKeys, ['2026-08-01', '2026-08-05']);

      final payload = dna.toWritePayload();
      expect(payload['availableDateKeys'], ['2026-08-01', '2026-08-05']);
      expect(payload['availabilityMode'], blindMeetingAvailabilityModeDateOnly);
      expect(
        payload['scheduleSelectionVersion'],
        blindMeetingScheduleSelectionVersion,
      );
    });

    test('payload에 시간대 계약이 남아 있지 않다', () {
      final payload = draft()
          .toDna(dateKeys: const ['2026-08-01'], waitlistOptIn: true)
          .toWritePayload();
      for (final key in const [
        'availableSlots',
        'availableSlotIds',
        'requestedSlotIds',
        'timeBlock',
        'timeSlots',
      ]) {
        expect(payload.keys, isNot(contains(key)), reason: key);
      }
    });

    test('날짜가 비어 있으면 제출할 수 없다', () {
      final dna = draft().toDna(dateKeys: const [], waitlistOptIn: true);
      expect(dna.isValid, isFalse);
    });
  });

  group('신청 문서 복구', () {
    test('날짜 전용 필드를 읽는다', () {
      final application = BlindMeetingApplication.fromMap('u1', {
        'status': 'applied',
        'stage': 'searchingCandidates',
        'requestedDateKeys': ['2026-08-05', '2026-08-01'],
      });
      expect(application.requestedDateKeys, ['2026-08-01', '2026-08-05']);
    });

    test('legacy 슬롯 문서에서 날짜만 복원한다', () {
      final application = BlindMeetingApplication.fromMap('u1', {
        'status': 'applied',
        'stage': 'searchingCandidates',
        'requestedSlotIds': [
          '2026-08-01#evening',
          '2026-08-01#lunch',
          '2026-08-05#afternoon',
        ],
      });
      expect(application.requestedDateKeys, ['2026-08-01', '2026-08-05']);
    });
  });

  group('미팅 세션 → 약속잡기 날짜 후보', () {
    test('공통 가능 날짜를 후보로 넘긴다', () {
      final session = BlindMeetingSession.fromMap('m1', {
        'status': 'chatOpen',
        'matchedDateKey': '2026-08-02',
        'commonAvailableDateKeys': ['2026-08-05', '2026-08-02'],
        'participantIds': ['a1'],
      });
      expect(session.matchedDateKey, '2026-08-02');
      expect(session.scheduleDateCandidates, ['2026-08-02', '2026-08-05']);
      // 확정 전에는 최종 시간이 없다.
      expect(session.slot, isNull);
    });

    test('공통 날짜가 없으면 매칭 기준 날짜로 대체한다', () {
      final session = BlindMeetingSession.fromMap('m1', {
        'status': 'chatOpen',
        'matchedDateKey': '2026-08-02',
        'participantIds': ['a1'],
      });
      expect(session.scheduleDateCandidates, ['2026-08-02']);
    });

    test('legacy 미팅 문서는 slotId에서 날짜를 복원한다', () {
      final session = BlindMeetingSession.fromMap('m1', {
        'status': 'scheduleConfirmed',
        'slotId': '2026-08-02#evening',
        'participantIds': ['a1'],
      });
      expect(session.matchedDateKey, '2026-08-02');
      expect(session.scheduleDateCandidates, ['2026-08-02']);
      // 확정된 최종 시간은 그대로 유지된다.
      expect(session.slot?.slotId, '2026-08-02#evening');
    });
  });
}
