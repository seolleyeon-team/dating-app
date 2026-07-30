// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — analytics
// 경로: lib/features/event/meeting_icebreaker/data/meeting_icebreaker_analytics.dart
//
// blind_meeting_analytics.dart와 같은 패턴이다.
// 허용 목록에 없는 parameter는 전송 단계에서 버린다.
//
// 절대 기록하지 않는 값
//   - 실제 참가자 목록 / UID / 닉네임
//   - FCM token
//   - 실제 미팅 장소
//   - 폭탄의 숨겨진 시간
//   - 사용자의 음주 여부
//   - 채팅 내용
// =============================================================================

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

/// 기록 가능한 이벤트 이름.
enum MeetingIcebreakerAnalyticsEvent {
  promptScheduled('meeting_icebreaker_prompt_scheduled'),
  promptSent('meeting_icebreaker_prompt_sent'),
  promptOpened('meeting_icebreaker_prompt_opened'),
  promptOptedOut('meeting_icebreaker_prompt_opted_out'),
  promptStopped('meeting_icebreaker_prompt_stopped'),
  rouletteShown('meeting_roulette_shown'),
  rouletteSpinStarted('meeting_roulette_spin_started'),
  rouletteSpinCompleted('meeting_roulette_spin_completed'),
  gameResultShown('meeting_game_result_shown'),
  bombTimerOpened('bomb_timer_opened'),
  bombTimerStarted('bomb_timer_started'),
  bombTimerExploded('bomb_timer_exploded'),
  audioFailed('meeting_icebreaker_audio_failed');

  const MeetingIcebreakerAnalyticsEvent(this.name);

  final String name;
}

/// 허용 parameter 목록. 여기에 없는 키는 전송하지 않는다.
const Set<String> meetingIcebreakerAllowedParams = <String>{
  'meeting_type',
  'notification_sequence',
  'game_type',
  'spin_duration_bucket',
  'prompt_stop_reason',
  'entry_decision',
  'reduce_motion',
  'alcohol_free_copy',
  'audio_stage',
};

/// 절대 전송하지 않는 키 (실수 방지용 차단 목록).
const Set<String> meetingIcebreakerBlockedParams = <String>{
  'userId',
  'uid',
  'nickname',
  'participantIds',
  'place',
  'fcmToken',
  'hiddenSeconds',
  'bombSeconds',
  'hiddenDuration',
};

abstract class MeetingIcebreakerAnalyticsSink {
  Future<void> send(String event, Map<String, dynamic> params);
}

class DebugMeetingIcebreakerAnalyticsSink
    implements MeetingIcebreakerAnalyticsSink {
  const DebugMeetingIcebreakerAnalyticsSink();

  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    debugPrint('[ICEBREAKER][analytics] $event $params');
  }
}

class FirestoreMeetingIcebreakerAnalyticsSink
    implements MeetingIcebreakerAnalyticsSink {
  FirestoreMeetingIcebreakerAnalyticsSink({FirebaseFirestore? firestore})
    : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    await _firestore.collection('meetingIcebreakerAnalytics').add({
      'event': event,
      'params': params,
      'createdAt': FieldValue.serverTimestamp(),
    });
  }
}

/// 아이스브레이킹 룰렛 analytics.
///
/// 전송 실패가 게임 진행을 막지 않는다.
class MeetingIcebreakerAnalytics {
  MeetingIcebreakerAnalytics({MeetingIcebreakerAnalyticsSink? sink})
    : _sink = sink ?? const DebugMeetingIcebreakerAnalyticsSink();

  final MeetingIcebreakerAnalyticsSink _sink;

  /// 허용 목록 기반 필터링. 차단 키는 값이 있어도 버린다.
  static Map<String, dynamic> sanitizeParams(Map<String, dynamic> params) {
    final out = <String, dynamic>{};
    params.forEach((key, value) {
      if (meetingIcebreakerBlockedParams.contains(key)) return;
      if (!meetingIcebreakerAllowedParams.contains(key)) return;
      if (value == null) return;
      out[key] = value;
    });
    return out;
  }

  Future<void> log(
    MeetingIcebreakerAnalyticsEvent event, {
    Map<String, dynamic> params = const <String, dynamic>{},
  }) async {
    try {
      await _sink.send(event.name, sanitizeParams(params));
    } catch (error) {
      debugPrint('[ICEBREAKER][analytics] send failed: $error');
    }
  }
}
