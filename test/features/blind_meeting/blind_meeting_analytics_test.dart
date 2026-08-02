import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_analytics.dart';

void main() {
  group('analytics 이벤트 이름', () {
    test('명세에 정의된 이벤트 이름과 정확히 일치한다', () {
      const expected = <String>[
        'blind_meeting_card_viewed',
        'blind_meeting_intro_viewed',
        'blind_meeting_dna_started',
        'blind_meeting_dna_completed',
        // 날짜 전용 선택 (v2)
        'blind_meeting_schedule_viewed',
        'blind_meeting_date_selected',
        'blind_meeting_date_unselected',
        'blind_meeting_schedule_submitted',
        'blind_meeting_availability_relaxed',
        'blind_meeting_waitlisted',
        'blind_meeting_group_formed',
        'blind_meeting_recommendation_banner_shown',
        'blind_meeting_invitation_accepted',
        'blind_meeting_deposit_completed',
        'blind_meeting_group_chat_created',
        // 약속잡기 funnel
        'blind_meeting_schedule_vote_opened',
        'blind_meeting_schedule_vote_submitted',
        'blind_meeting_schedule_confirmed',
        'blind_meeting_confirmation_24h',
        'blind_meeting_confirmation_3h',
        'blind_meeting_replacement_triggered',
        'blind_meeting_replacement_completed',
        'blind_meeting_no_show',
        'blind_meeting_checkin_completed',
        'blind_meeting_checkout_completed',
        'blind_meeting_feedback_submitted',
        'blind_meeting_followup_prompt_opened',
        'blind_meeting_followup_submitted',
        'blind_meeting_mutual_match',
        'blind_meeting_one_to_one_chat_created',
      ];

      final actual = BlindMeetingAnalyticsEvent.values
          .map((e) => e.name)
          .toList();
      expect(actual, expected);
    });
  });

  group('개인정보 보호', () {
    test('허용되지 않은 파라미터는 제거된다', () {
      final sanitized = BlindMeetingAnalytics.sanitizeParams({
        'meetingId': 'm1',
        'nickname': '민지',
        'interests': ['커피'],
        'studentEmail': 'a@yonsei.ac.kr',
        'conversationAtmosphere': 'calm',
        'selectedDateCount': 3,
        'availabilityWindowDays': 21,
        'isAlcoholFree': true,
      });

      expect(sanitized.keys.toSet(), {
        'meetingId',
        'selectedDateCount',
        'availabilityWindowDays',
        'isAlcoholFree',
      });
      expect(sanitized.containsKey('nickname'), isFalse);
      expect(sanitized.containsKey('interests'), isFalse);
      expect(sanitized.containsKey('studentEmail'), isFalse);
      expect(sanitized.containsKey('conversationAtmosphere'), isFalse);
    });

    test('사용자 식별자는 해시로만 전송된다', () {
      final hash = BlindMeetingAnalytics.hashUserId('user-123');
      expect(hash.length, 16);
      expect(hash, isNot(contains('user-123')));
      expect(BlindMeetingAnalytics.hashUserId('user-123'), hash);
      expect(BlindMeetingAnalytics.hashUserId('user-124'), isNot(hash));
      expect(BlindMeetingAnalytics.hashUserId(''), '');
    });

    test('실제 선택 날짜와 시간대 키는 화이트리스트에 없다', () {
      for (final key in const [
        'availableDateKeys',
        'requestedDateKeys',
        'selectedDates',
        'dateKey',
        'selected_time_slot',
        'morning_selected',
        'afternoon_selected',
        'evening_selected',
        'slotCount',
        'preferredSlotIds',
        'commonAvailableDateKeys',
        'matchedDateKey',
      ]) {
        expect(
          blindMeetingAnalyticsAllowedParams.contains(key),
          isFalse,
          reason: key,
        );
      }
    });

    test('비공개 DNA 답변 키는 화이트리스트에 없다', () {
      for (final key in const [
        'conversationAtmosphere',
        'conversationInitiative',
        'meetingPurpose',
        'alcoholCompanionPreference',
        'smokingCompanionPreference',
        'interestIds',
        'drinkingLevelSnapshot',
        'smokingStatusSnapshot',
      ]) {
        expect(
          blindMeetingAnalyticsAllowedParams.contains(key),
          isFalse,
          reason: key,
        );
      }
    });

    test('sink 실패가 사용자 흐름을 막지 않는다', () async {
      final analytics = BlindMeetingAnalytics(sink: _FailingSink());
      await analytics.log(BlindMeetingAnalyticsEvent.cardViewed);
    });
  });
}

class _FailingSink implements BlindMeetingAnalyticsSink {
  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    throw StateError('boom');
  }
}
