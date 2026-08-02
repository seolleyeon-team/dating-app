// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 알림 payload와 진입 판정
// 경로: lib/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart
//
// 서버 정의와 1:1 대응한다.
//   functions/src/meetingIcebreaker/types.ts
//   functions/src/meetingIcebreaker/notifications.ts
//   functions/src/meetingIcebreaker/policy.ts
//
// 알림 payload에는 참가자 목록, 상대방 UID, 미팅 장소 같은 민감 정보가 없다.
// 권한은 payload가 아니라 서버 callable이 매번 다시 검증한다.
// =============================================================================

/// 푸시 payload의 `type` 값.
const String kMeetingIcebreakerNotificationType = 'meeting_icebreaker_roulette';

/// 조용한 알림 전용 Android 채널 id (서버 payload의 channelId와 같아야 한다).
const String kMeetingIcebreakerQuietChannelId = 'meeting_icebreaker_quiet';

/// 사용자에게 보이는 채널 이름.
const String kMeetingIcebreakerQuietChannelName = '미팅 룰렛 안내 (무음)';

/// 사용자에게 보이는 채널 설명.
const String kMeetingIcebreakerQuietChannelDescription =
    '3:3 미팅 중 어색할 때 눌러볼 수 있는 조용한 안내예요. 소리와 진동이 울리지 않아요.';

/// 반복 알림 주기 (서버 정책 기본값과 같은 값. 안내 문구용).
const int kMeetingIcebreakerPromptIntervalMinutes = 15;

/// 반복 알림 최대 지속 시간 (서버 정책 기본값과 같은 값. 안내 문구용).
const int kMeetingIcebreakerMaxPromptDurationHours = 6;

/// 알림 제목 / 본문 (서버와 같은 문구).
const String kMeetingIcebreakerPromptTitle = '설레연 미팅 도우미';
const String kMeetingIcebreakerPromptBody = '미팅에서 어색할 때 눌러보세요!';

/// 아이스브레이킹 룰렛이 적용되는 미팅 종류.
///
/// 일반 이벤트, 1:1 추천, 일반 채팅, 커뮤니티에는 적용하지 않는다.
enum MeetingIcebreakerMeetingKind {
  /// 3:3 시즌 미팅 (chat 약속 안전도장 기반)
  seasonMeeting,

  /// 3:3 블라인드 취향 미팅 (blindMeetings 체크인/체크아웃 기반)
  blindTasteMeeting,
}

extension MeetingIcebreakerMeetingKindX on MeetingIcebreakerMeetingKind {
  /// 서버와 주고받는 문자열.
  String get wireName => switch (this) {
    MeetingIcebreakerMeetingKind.seasonMeeting => 'seasonMeeting',
    MeetingIcebreakerMeetingKind.blindTasteMeeting => 'blindTasteMeeting',
  };

  String get label => switch (this) {
    MeetingIcebreakerMeetingKind.seasonMeeting => '3:3 시즌 미팅',
    MeetingIcebreakerMeetingKind.blindTasteMeeting => '3:3 블라인드 취향 미팅',
  };
}

MeetingIcebreakerMeetingKind? meetingIcebreakerMeetingKindFromWire(
  String? value,
) {
  final name = value?.trim();
  if (name == null || name.isEmpty) return null;
  for (final kind in MeetingIcebreakerMeetingKind.values) {
    if (kind.wireName == name) return kind;
  }
  return null;
}

/// 룰렛 알림 payload.
class MeetingIcebreakerPromptPayload {
  const MeetingIcebreakerPromptPayload({
    required this.sessionId,
    required this.meetingId,
    required this.meetingKind,
    required this.notificationSequence,
    required this.notificationId,
  });

  final String sessionId;
  final String meetingId;
  final MeetingIcebreakerMeetingKind? meetingKind;
  final int notificationSequence;
  final String notificationId;

  /// 같은 알림을 두 번 처리하지 않기 위한 키.
  String get dedupeKey => notificationId.isNotEmpty
      ? notificationId
      : '$sessionId#$notificationSequence';

  /// 푸시 data map에서 payload를 복원한다.
  ///
  /// 룰렛 알림이 아니거나 식별자가 없으면 null을 돌려준다.
  static MeetingIcebreakerPromptPayload? tryParse(Map<String, dynamic>? data) {
    if (data == null) return null;
    final type = data['type']?.toString().trim() ?? '';
    if (type != kMeetingIcebreakerNotificationType) return null;

    final sessionId = data['sessionId']?.toString().trim() ?? '';
    final meetingId =
        data['meetingId']?.toString().trim() ??
        data['deeplinkId']?.toString().trim() ??
        '';
    if (sessionId.isEmpty && meetingId.isEmpty) return null;

    final sequenceRaw = data['notificationSequence']?.toString().trim() ?? '';
    return MeetingIcebreakerPromptPayload(
      sessionId: sessionId,
      meetingId: meetingId,
      meetingKind: meetingIcebreakerMeetingKindFromWire(
        data['meetingType']?.toString(),
      ),
      notificationSequence: int.tryParse(sequenceRaw) ?? 0,
      notificationId: data['notificationId']?.toString().trim() ?? '',
    );
  }

  @override
  String toString() =>
      'MeetingIcebreakerPromptPayload(session=$sessionId, seq=$notificationSequence)';
}

/// 서버가 돌려주는 진입 판정.
enum MeetingIcebreakerEntryDecision {
  allowed,
  unauthenticated,
  notFound,
  notParticipant,
  notStarted,
  meetingEnded,
  meetingCancelled,
  featureDisabled,

  /// 클라이언트 전용: 네트워크·서버 오류
  unavailable,
}

extension MeetingIcebreakerEntryDecisionX on MeetingIcebreakerEntryDecision {
  String get wireName => switch (this) {
    MeetingIcebreakerEntryDecision.allowed => 'allowed',
    MeetingIcebreakerEntryDecision.unauthenticated => 'unauthenticated',
    MeetingIcebreakerEntryDecision.notFound => 'not_found',
    MeetingIcebreakerEntryDecision.notParticipant => 'not_participant',
    MeetingIcebreakerEntryDecision.notStarted => 'not_started',
    MeetingIcebreakerEntryDecision.meetingEnded => 'meeting_ended',
    MeetingIcebreakerEntryDecision.meetingCancelled => 'meeting_cancelled',
    MeetingIcebreakerEntryDecision.featureDisabled => 'feature_disabled',
    MeetingIcebreakerEntryDecision.unavailable => 'unavailable',
  };

  /// 룰렛을 열 수 없을 때 보여줄 안내 문구.
  String get userMessage => switch (this) {
    MeetingIcebreakerEntryDecision.allowed => '',
    MeetingIcebreakerEntryDecision.unauthenticated => '로그인이 필요해요.',
    MeetingIcebreakerEntryDecision.notFound => '미팅 정보를 찾을 수 없어요.',
    MeetingIcebreakerEntryDecision.notParticipant => '참가 중인 미팅이 아니에요.',
    MeetingIcebreakerEntryDecision.notStarted => '미팅 시작 안전도장을 찍은 뒤에 열 수 있어요.',
    MeetingIcebreakerEntryDecision.meetingEnded => '이 미팅은 이미 종료되었어요.',
    MeetingIcebreakerEntryDecision.meetingCancelled => '이 미팅은 취소되었어요.',
    MeetingIcebreakerEntryDecision.featureDisabled => '지금은 미팅 룰렛을 사용할 수 없어요.',
    MeetingIcebreakerEntryDecision.unavailable => '잠시 후 다시 시도해주세요.',
  };
}

MeetingIcebreakerEntryDecision meetingIcebreakerEntryDecisionFromWire(
  String? value,
) {
  final name = value?.trim();
  if (name == null || name.isEmpty) {
    return MeetingIcebreakerEntryDecision.unavailable;
  }
  for (final decision in MeetingIcebreakerEntryDecision.values) {
    if (decision.wireName == name) return decision;
  }
  return MeetingIcebreakerEntryDecision.unavailable;
}

/// 룰렛 진입 검증 결과.
class MeetingIcebreakerEntry {
  const MeetingIcebreakerEntry({
    required this.decision,
    this.sessionId,
    this.meetingId,
    this.meetingKind,
    this.alcoholFreeCopy = false,
    this.optedOut = false,
    this.bombPassEnabled = true,
  });

  const MeetingIcebreakerEntry.denied(this.decision)
    : sessionId = null,
      meetingId = null,
      meetingKind = null,
      alcoholFreeCopy = false,
      optedOut = false,
      bombPassEnabled = false;

  final MeetingIcebreakerEntryDecision decision;
  final String? sessionId;
  final String? meetingId;
  final MeetingIcebreakerMeetingKind? meetingKind;

  /// true면 음주 벌칙 칸을 비음주 문구로 대체한다.
  final bool alcoholFreeCopy;

  /// true면 이번 미팅의 룰렛 알림을 받지 않기로 한 상태다.
  final bool optedOut;

  /// 폭탄 돌리기 타이머 게임 사용 가능 여부 (feature flag).
  final bool bombPassEnabled;

  bool get allowed => decision == MeetingIcebreakerEntryDecision.allowed;

  MeetingIcebreakerEntry copyWith({bool? optedOut}) {
    return MeetingIcebreakerEntry(
      decision: decision,
      sessionId: sessionId,
      meetingId: meetingId,
      meetingKind: meetingKind,
      alcoholFreeCopy: alcoholFreeCopy,
      optedOut: optedOut ?? this.optedOut,
      bombPassEnabled: bombPassEnabled,
    );
  }

  static MeetingIcebreakerEntry fromMap(Map<String, dynamic>? raw) {
    if (raw == null) {
      return const MeetingIcebreakerEntry.denied(
        MeetingIcebreakerEntryDecision.unavailable,
      );
    }
    return MeetingIcebreakerEntry(
      decision: meetingIcebreakerEntryDecisionFromWire(
        raw['decision']?.toString(),
      ),
      sessionId: raw['sessionId']?.toString(),
      meetingId: raw['meetingId']?.toString(),
      meetingKind: meetingIcebreakerMeetingKindFromWire(
        raw['meetingType']?.toString(),
      ),
      alcoholFreeCopy: raw['alcoholFreeCopy'] == true,
      optedOut: raw['optedOut'] == true,
      bombPassEnabled: raw['bombPassEnabled'] != false,
    );
  }
}

/// "이번 미팅에서는 룰렛 알림 받지 않기" 라벨.
const String kMeetingIcebreakerOptOutLabel = '이번 미팅에서는 룰렛 알림 받지 않기';
const String kMeetingIcebreakerOptInLabel = '이번 미팅 룰렛 알림 다시 받기';
const String kMeetingIcebreakerOptOutHint = '채팅·안전 알림은 그대로 받아요.';
