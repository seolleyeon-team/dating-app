// =============================================================================
// 3:3 블라인드 취향 미팅 — 도메인 enum
// 경로: lib/features/blind_meeting/domain/blind_meeting_enums.dart
//
// Firestore에는 enum의 `name` 문자열이 저장된다. 이름을 바꾸면 기존 문서와
// 어긋나므로 반드시 migration을 함께 준비해야 한다.
// =============================================================================

/// 미팅 종류. 기존 랜덤 미팅 문서와의 호환을 위해 legacy 값을 함께 인식한다.
enum BlindMeetingType {
  /// 신규 3:3 블라인드 취향 미팅.
  blindTasteMeeting,

  /// 이전 3:3 랜덤 미팅 (읽기 호환 전용, 신규 생성 금지).
  randomMeeting,
}

/// 대화 분위기 선호.
enum ConversationAtmosphere {
  /// 차분하게 이야기하는 분위기
  calm,

  /// 활발하고 에너지 있는 분위기
  lively,

  /// 둘 다 괜찮아요
  either,
}

/// 대화 시작 성향.
enum ConversationInitiative {
  /// 먼저 대화를 시작하는 편이에요
  initiator,

  /// 상황에 따라 달라요
  adaptive,

  /// 먼저 듣고 반응하는 편이에요
  listener,
}

/// 미팅 목적.
enum MeetingPurpose {
  /// 연애 가능성이 있는 만남
  romance,

  /// 새로운 친구
  friendship,

  /// 연애와 친구 모두 열려 있어요
  both,
}

/// 음주 동석 선호.
enum AlcoholCompanionPreference {
  /// 여섯 명 모두 비음주였으면 좋겠어요
  allSober,

  /// 저는 마시지 않지만 다른 사람이 가볍게 마시는 것은 괜찮아요
  lightOkay,

  /// 상관없어요
  noPreference,
}

/// 흡연 동석 선호.
enum SmokingCompanionPreference {
  /// 비흡연자만 만나고 싶어요
  nonSmokersOnly,

  /// 실내에서 피우지 않으면 괜찮아요
  noIndoorSmoking,

  /// 상관없어요
  noPreference,
}

/// 온보딩 `lifestyle.drinking` 값과 1:1 대응.
enum DrinkingLevel { none, sometimes, weekly1_2, often }

/// 온보딩 `lifestyle.smoking` 값과 1:1 대응.
enum SmokingStatus { nonSmoker, smoker, quitting }

/// 미팅 세션 상태.
enum BlindMeetingStatus {
  applicationOpen,
  forming,
  awaitingAcceptance,
  awaitingDeposits,
  confirmed,
  chatOpen,
  scheduleConfirmed,
  checkinOpen,
  inProgress,
  completed,
  followupOpen,
  readOnly,
  archived,
  cancelled,
}

/// 참가자 상태.
enum BlindMeetingParticipantStatus {
  applied,
  waitlisted,
  invited,
  accepted,
  depositPending,
  confirmed,
  cancelRequested,
  cancelled,
  replacementPending,
  replaced,
  noShow,
  attended,
  completed,
  restricted,
}

/// 개인별 보증금 상태.
enum BlindMeetingDepositStatus {
  notRequired,
  pending,
  authorized,
  paid,
  refundPending,
  refunded,
  partiallyRefunded,
  forfeited,
  failed,
  cancelled,
}

/// 참석 재확인 응답.
enum AttendanceConfirmation {
  /// 아직 응답하지 않음
  pending,

  /// 참석할게요 / 예정대로 참석해요
  attending,

  /// 참석이 어려워요 / 문제가 생겼어요
  unable,
}

/// 안전도장 단계 상태.
enum SafetyStampPhaseStatus { notOpen, open, completed, missed }

/// 팀 식별자.
enum BlindMeetingTeam { teamA, teamB }

// -----------------------------------------------------------------------------
// 문자열 ↔ enum 변환 (Firestore 직렬화)
// -----------------------------------------------------------------------------

/// 이름이 일치하는 enum 값을 찾고, 없으면 [fallback]을 돌려준다.
T enumFromName<T extends Enum>(
  List<T> values,
  Object? raw, {
  required T fallback,
}) {
  if (raw is T) return raw;
  final name = raw?.toString().trim();
  if (name == null || name.isEmpty) return fallback;
  for (final value in values) {
    if (value.name == name) return value;
  }
  return fallback;
}

/// 이름이 일치하는 enum 값을 찾고, 없으면 null을 돌려준다.
T? enumFromNameOrNull<T extends Enum>(List<T> values, Object? raw) {
  if (raw is T) return raw;
  final name = raw?.toString().trim();
  if (name == null || name.isEmpty) return null;
  for (final value in values) {
    if (value.name == name) return value;
  }
  return null;
}

// -----------------------------------------------------------------------------
// 사용자 노출 라벨
// -----------------------------------------------------------------------------

extension ConversationAtmosphereLabel on ConversationAtmosphere {
  String get label => switch (this) {
    ConversationAtmosphere.calm => '차분하게 이야기하는 분위기',
    ConversationAtmosphere.lively => '활발하고 에너지 있는 분위기',
    ConversationAtmosphere.either => '둘 다 괜찮아요',
  };
}

extension ConversationInitiativeLabel on ConversationInitiative {
  String get label => switch (this) {
    ConversationInitiative.initiator => '먼저 대화를 시작하는 편이에요',
    ConversationInitiative.adaptive => '상황에 따라 달라요',
    ConversationInitiative.listener => '먼저 듣고 반응하는 편이에요',
  };
}

extension MeetingPurposeLabel on MeetingPurpose {
  String get label => switch (this) {
    MeetingPurpose.romance => '연애 가능성이 있는 만남',
    MeetingPurpose.friendship => '새로운 친구',
    MeetingPurpose.both => '연애와 친구 모두 열려 있어요',
  };
}

extension AlcoholCompanionPreferenceLabel on AlcoholCompanionPreference {
  String get label => switch (this) {
    AlcoholCompanionPreference.allSober => '여섯 명 모두 비음주였으면 좋겠어요',
    AlcoholCompanionPreference.lightOkay => '저는 마시지 않지만 다른 사람이 가볍게 마시는 것은 괜찮아요',
    AlcoholCompanionPreference.noPreference => '상관없어요',
  };
}

extension SmokingCompanionPreferenceLabel on SmokingCompanionPreference {
  String get label => switch (this) {
    SmokingCompanionPreference.nonSmokersOnly => '비흡연자만 만나고 싶어요',
    SmokingCompanionPreference.noIndoorSmoking => '실내에서 피우지 않으면 괜찮아요',
    SmokingCompanionPreference.noPreference => '상관없어요',
  };
}

extension DrinkingLevelHelpers on DrinkingLevel {
  /// 프로필상 비음주로 볼 수 있는지.
  bool get isSober => this == DrinkingLevel.none;

  String get label => switch (this) {
    DrinkingLevel.none => '전혀 안 함',
    DrinkingLevel.sometimes => '가끔',
    DrinkingLevel.weekly1_2 => '주 1-2회',
    DrinkingLevel.often => '자주 즐김',
  };
}

extension SmokingStatusHelpers on SmokingStatus {
  /// 흡연 거부 조건 판정에서 흡연자로 볼지 여부.
  ///
  /// `quitting`(금연 중)은 흡연자로 보지 않는다.
  bool get isSmoker => this == SmokingStatus.smoker;

  String get label => switch (this) {
    SmokingStatus.nonSmoker => '비흡연',
    SmokingStatus.smoker => '흡연',
    SmokingStatus.quitting => '금연 중',
  };
}

extension BlindMeetingStatusHelpers on BlindMeetingStatus {
  /// 참가자가 단체 채팅에 글을 쓸 수 있는 단계인지.
  bool get allowsGroupChatWrite => const {
    BlindMeetingStatus.chatOpen,
    BlindMeetingStatus.scheduleConfirmed,
    BlindMeetingStatus.checkinOpen,
    BlindMeetingStatus.inProgress,
    BlindMeetingStatus.completed,
    BlindMeetingStatus.followupOpen,
  }.contains(this);

  /// 미팅이 종료(정상/취소)된 상태인지.
  bool get isTerminal => const {
    BlindMeetingStatus.archived,
    BlindMeetingStatus.cancelled,
  }.contains(this);
}

extension BlindMeetingParticipantStatusHelpers
    on BlindMeetingParticipantStatus {
  /// 단체 채팅 멤버십을 가질 수 있는 상태인지.
  ///
  /// noShow 는 포함하지 않는다. 최종 노쇼 판정을 받은 참가자는 더 이상 활성
  /// 참가자가 아니며 서버가 방에서 제외한다 (functions/src/blindMeeting/types.ts
  /// CHAT_MEMBERSHIP_STATUSES 와 같은 정의).
  bool get holdsChatMembership => const {
    BlindMeetingParticipantStatus.confirmed,
    BlindMeetingParticipantStatus.attended,
    BlindMeetingParticipantStatus.completed,
  }.contains(this);

  /// 미팅 자리에서 빠진 상태인지 (대체 후보 탐색 대상).
  bool get isVacant => const {
    BlindMeetingParticipantStatus.cancelled,
    BlindMeetingParticipantStatus.replaced,
    BlindMeetingParticipantStatus.replacementPending,
  }.contains(this);
}
