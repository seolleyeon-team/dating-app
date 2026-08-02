// =============================================================================
// 3:3 블라인드 취향 미팅 — 미팅 후 만족도
// 경로: lib/features/blind_meeting/domain/blind_meeting_feedback.dart
//
// 이 데이터는 향후 matching algorithm 평가에만 사용한다.
// 초기 버전에서는 수집한 값으로 가중치를 자동 변경하지 않고,
// algorithmVersion별 성과 비교용으로만 축적한다.
// =============================================================================

/// 선택형 사유 태그.
enum BlindMeetingFeedbackReason {
  conversationTooQuiet,
  fewPeopleDominated,
  purposeMismatch,
  alcoholPressure,
  interestsMatchedWell,
  comfortableTeam,
}

extension BlindMeetingFeedbackReasonLabel on BlindMeetingFeedbackReason {
  String get label => switch (this) {
    BlindMeetingFeedbackReason.conversationTooQuiet => '대화 분위기가 너무 조용했어요',
    BlindMeetingFeedbackReason.fewPeopleDominated => '일부 사람만 대화를 주도했어요',
    BlindMeetingFeedbackReason.purposeMismatch => '미팅 목적이 서로 달랐어요',
    BlindMeetingFeedbackReason.alcoholPressure => '음주 분위기가 부담스러웠어요',
    BlindMeetingFeedbackReason.interestsMatchedWell => '관심사가 잘 맞았어요',
    BlindMeetingFeedbackReason.comfortableTeam => '우리 팀 구성이 편했어요',
  };

  /// 긍정 사유인지 (analytics 집계용).
  bool get isPositive => const {
    BlindMeetingFeedbackReason.interestsMatchedWell,
    BlindMeetingFeedbackReason.comfortableTeam,
  }.contains(this);
}

/// 필수 문항 4개.
enum BlindMeetingFeedbackQuestion {
  ownTeamComfort,
  opponentConversation,
  venueAndAlcohol,
  wouldJoinAgain,
}

extension BlindMeetingFeedbackQuestionLabel on BlindMeetingFeedbackQuestion {
  String get label => switch (this) {
    BlindMeetingFeedbackQuestion.ownTeamComfort => '우리 팀 분위기가 편했나요?',
    BlindMeetingFeedbackQuestion.opponentConversation => '상대 팀과 대화가 잘 이어졌나요?',
    BlindMeetingFeedbackQuestion.venueAndAlcohol => '음주·장소 분위기가 적절했나요?',
    BlindMeetingFeedbackQuestion.wouldJoinAgain => '다시 이런 미팅에 참여하고 싶나요?',
  };

  String get fieldName => switch (this) {
    BlindMeetingFeedbackQuestion.ownTeamComfort => 'ownTeamComfort',
    BlindMeetingFeedbackQuestion.opponentConversation => 'opponentConversation',
    BlindMeetingFeedbackQuestion.venueAndAlcohol => 'venueAndAlcohol',
    BlindMeetingFeedbackQuestion.wouldJoinAgain => 'wouldJoinAgain',
  };
}

/// 미팅 후 만족도 응답.
class BlindMeetingFeedback {
  final String meetingId;
  final String userId;

  /// 문항별 1~5 점수.
  final Map<BlindMeetingFeedbackQuestion, int> ratings;

  final Set<BlindMeetingFeedbackReason> reasons;

  /// 안전 관련 신고가 함께 제출되었는지 (서버가 별도 처리).
  final bool safetyConcernReported;

  final String algorithmVersion;

  const BlindMeetingFeedback({
    required this.meetingId,
    required this.userId,
    required this.ratings,
    this.reasons = const <BlindMeetingFeedbackReason>{},
    this.safetyConcernReported = false,
    this.algorithmVersion = 'unknown',
  });

  /// 필수 문항이 모두 1~5로 채워졌는지.
  bool get isComplete {
    for (final question in BlindMeetingFeedbackQuestion.values) {
      final value = ratings[question];
      if (value == null || value < 1 || value > 5) return false;
    }
    return true;
  }

  Map<String, dynamic> toWritePayload() => {
    'meetingId': meetingId,
    'userId': userId,
    'ratings': {
      for (final entry in ratings.entries)
        entry.key.fieldName: entry.value.clamp(1, 5),
    },
    'reasons': reasons.map((r) => r.name).toList(),
    'safetyConcernReported': safetyConcernReported,
    'algorithmVersion': algorithmVersion,
  };
}
