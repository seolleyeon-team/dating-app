// =============================================================================
// 3:3 블라인드 취향 미팅 — analytics
// 경로: lib/features/blind_meeting/data/blind_meeting_analytics.dart
//
// 원칙
//  - 비공개 DNA 원문, 관심사 라벨, 닉네임 등 개인정보는 절대 보내지 않는다.
//  - 사용자 식별자는 해시로만 보낸다.
//  - 파라미터는 화이트리스트된 비민감 필드만 허용한다.
// =============================================================================

import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

/// 블라인드 미팅 analytics 이벤트 이름.
enum BlindMeetingAnalyticsEvent {
  cardViewed('blind_meeting_card_viewed'),
  introViewed('blind_meeting_intro_viewed'),
  dnaStarted('blind_meeting_dna_started'),
  dnaCompleted('blind_meeting_dna_completed'),

  // ── 날짜 전용 선택 (v2) ────────────────────────────────────────────────
  scheduleViewed('blind_meeting_schedule_viewed'),
  dateSelected('blind_meeting_date_selected'),
  dateUnselected('blind_meeting_date_unselected'),
  scheduleSubmitted('blind_meeting_schedule_submitted'),

  /// 매칭 대기 중 조건 완화로 가능 날짜를 넓힘
  availabilityRelaxed('blind_meeting_availability_relaxed'),
  waitlisted('blind_meeting_waitlisted'),
  groupFormed('blind_meeting_group_formed'),
  recommendationBannerShown('blind_meeting_recommendation_banner_shown'),
  invitationAccepted('blind_meeting_invitation_accepted'),
  depositCompleted('blind_meeting_deposit_completed'),
  groupChatCreated('blind_meeting_group_chat_created'),

  /// 약속잡기 funnel: 시트 열림 → 투표 제출 → 확정
  scheduleVoteOpened('blind_meeting_schedule_vote_opened'),
  scheduleVoteSubmitted('blind_meeting_schedule_vote_submitted'),
  scheduleConfirmed('blind_meeting_schedule_confirmed'),
  confirmation24h('blind_meeting_confirmation_24h'),
  confirmation3h('blind_meeting_confirmation_3h'),
  replacementTriggered('blind_meeting_replacement_triggered'),
  replacementCompleted('blind_meeting_replacement_completed'),
  noShow('blind_meeting_no_show'),
  checkinCompleted('blind_meeting_checkin_completed'),
  checkoutCompleted('blind_meeting_checkout_completed'),
  feedbackSubmitted('blind_meeting_feedback_submitted'),
  followupPromptOpened('blind_meeting_followup_prompt_opened'),
  followupSubmitted('blind_meeting_followup_submitted'),
  mutualMatch('blind_meeting_mutual_match'),
  oneToOneChatCreated('blind_meeting_one_to_one_chat_created');

  const BlindMeetingAnalyticsEvent(this.name);

  /// 전송되는 이벤트 이름.
  final String name;
}

/// analytics 파라미터로 허용되는 비민감 키.
///
/// 여기 없는 키는 전송하지 않는다.
/// 실제로 선택한 날짜 목록이나 생활 패턴이 드러나는 값은 넣지 않는다.
/// 날짜 관련 파라미터는 개수·창 길이·월 경계 여부만 허용한다.
const Set<String> blindMeetingAnalyticsAllowedParams = {
  'meetingId',
  'isAlcoholFree',
  'selectedDateCount',
  'availabilityWindowDays',
  'crossesMonthBoundary',
  // 조건 완화 / 약속잡기 funnel (실제 날짜는 절대 넣지 않는다)
  'relaxationChoice',
  'addedDateCount',
  'candidateDateCount',
  'votedDateCount',
  'stage',
  'selectionCount',
  'depositStatus',
  'phase',
  'urgent',
  'algorithmVersion',
  'ratingAverage',
};

/// analytics 이벤트를 실제로 내보내는 sink.
abstract class BlindMeetingAnalyticsSink {
  Future<void> send(String event, Map<String, dynamic> params);
}

/// 디버그 빌드에서 콘솔로만 출력하는 sink.
class DebugBlindMeetingAnalyticsSink implements BlindMeetingAnalyticsSink {
  const DebugBlindMeetingAnalyticsSink();

  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    debugPrint('[BlindMeetingAnalytics] $event $params');
  }
}

/// Firestore에 적재하는 sink (개인정보 없이 집계용).
class FirestoreBlindMeetingAnalyticsSink implements BlindMeetingAnalyticsSink {
  FirestoreBlindMeetingAnalyticsSink({FirebaseFirestore? firestore})
    : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    await _firestore.collection('blindMeetingAnalytics').add({
      'event': event,
      'params': params,
      'createdAt': FieldValue.serverTimestamp(),
    });
  }
}

/// 블라인드 미팅 analytics 로거.
class BlindMeetingAnalytics {
  BlindMeetingAnalytics({BlindMeetingAnalyticsSink? sink})
    : _sink = sink ?? const DebugBlindMeetingAnalyticsSink();

  final BlindMeetingAnalyticsSink _sink;

  /// 사용자 식별자를 해시로만 전송한다.
  static String hashUserId(String userId) {
    if (userId.isEmpty) return '';
    return sha256.convert(utf8.encode(userId)).toString().substring(0, 16);
  }

  /// 허용된 키만 남긴다.
  static Map<String, dynamic> sanitizeParams(Map<String, dynamic> params) {
    final result = <String, dynamic>{};
    params.forEach((key, value) {
      if (!blindMeetingAnalyticsAllowedParams.contains(key)) return;
      if (value is String || value is num || value is bool) {
        result[key] = value;
      }
    });
    return result;
  }

  Future<void> log(
    BlindMeetingAnalyticsEvent event, {
    String? userId,
    Map<String, dynamic> params = const <String, dynamic>{},
  }) async {
    final payload = sanitizeParams(params);
    if (userId != null && userId.isNotEmpty) {
      payload['userHash'] = hashUserId(userId);
    }
    try {
      await _sink.send(event.name, payload);
    } catch (error) {
      // analytics 실패가 사용자 흐름을 막지 않도록 한다.
      debugPrint(
        '[BlindMeetingAnalytics] send failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }
  }
}
