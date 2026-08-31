// =============================================================================
// 3:3 블라인드 취향 미팅 — 라우트 인자
// 경로: lib/features/blind_meeting/presentation/blind_meeting_route_args.dart
// =============================================================================

import '../data/blind_meeting_profile_snapshot.dart';
import '../domain/blind_meeting_dna.dart';
import '../domain/blind_meeting_enums.dart';

/// DNA 작성 흐름의 목적.
enum BlindMeetingDnaMode {
  create,

  /// 이미 30H를 차감한 작성 진행 상태를 이어간다.
  resumePaidDraft,

  editExistingApplication,
}

/// DNA route가 신규 작성인지 기존 신청 수정인지 명시한다.
class BlindMeetingDnaRouteArgs {
  final BlindMeetingProfileSnapshot profile;
  final BlindMeetingDnaMode mode;

  /// 새 신청의 30H가 DNA 화면 진입 전에 이미 차감됐는지 여부.
  final bool heartCharged;

  /// 답변을 작성할 때 서버 진행 문서를 갱신할지 여부.
  final bool persistProgress;

  const BlindMeetingDnaRouteArgs({
    required this.profile,
    this.mode = BlindMeetingDnaMode.create,
    this.heartCharged = false,
    this.persistProgress = false,
  });
}

/// DNA wizard가 만든 답변 초안. 일정 선택 화면으로 전달된다.
class BlindMeetingDnaDraft {
  final BlindMeetingProfileSnapshot profile;
  final BlindMeetingDnaMode mode;
  final ConversationAtmosphere atmosphere;
  final ConversationInitiative initiative;
  final MeetingPurpose purpose;
  final AlcoholCompanionPreference alcoholPreference;
  final SmokingCompanionPreference smokingPreference;

  /// DNA 화면 진입 단계에서 이미 30H를 차감한 흐름인지 여부.
  final bool heartCharged;

  const BlindMeetingDnaDraft({
    required this.profile,
    this.mode = BlindMeetingDnaMode.create,
    required this.atmosphere,
    required this.initiative,
    required this.purpose,
    required this.alcoholPreference,
    required this.smokingPreference,
    this.heartCharged = false,
  });

  /// 참여 가능한 날짜까지 고른 뒤 최종 DNA로 만든다.
  ///
  /// 세부 시간은 여기서 정하지 않는다 (팀 구성 후 단체 채팅방에서 결정).
  BlindMeetingDna toDna({
    required List<String> dateKeys,
    required bool waitlistOptIn,
  }) {
    return BlindMeetingDna(
      userId: profile.userId,
      conversationAtmosphere: atmosphere,
      conversationInitiative: initiative,
      meetingPurpose: purpose,
      alcoholCompanionPreference: alcoholPreference,
      smokingCompanionPreference: smokingPreference,
      interestIds: profile.interests,
      drinkingLevelSnapshot: profile.drinkingLevel ?? DrinkingLevel.sometimes,
      smokingStatusSnapshot: profile.smokingStatus ?? SmokingStatus.nonSmoker,
      mbtiSnapshot: profile.mbti,
      availableDateKeys: dateKeys,
      waitlistOptIn: waitlistOptIn,
    );
  }
}

/// 추천 결과 / 후속 선택 화면 인자.
class BlindMeetingMeetingArgs {
  final String meetingId;

  /// 매칭 직후 진입이면 안내 배너를 한 번 보여준다.
  final bool showRecommendationBanner;

  const BlindMeetingMeetingArgs({
    required this.meetingId,
    this.showRecommendationBanner = false,
  });
}
