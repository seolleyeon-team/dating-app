// 블라인드 취향 미팅 테스트용 후보 빌더

import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_candidate.dart';

/// 최종 확정 시간 테스트용 슬롯 id (약속잡기 단계에서만 쓰인다).
const String kSlot = '2026-08-01#evening';

/// 매칭 기준 날짜. 세부 시간은 매칭 조건이 아니다.
const String kDateKey = '2026-08-01';

BlindMeetingCandidate candidate(
  String userId, {
  ConversationAtmosphere atmosphere = ConversationAtmosphere.calm,
  ConversationInitiative initiative = ConversationInitiative.adaptive,
  MeetingPurpose purpose = MeetingPurpose.both,
  AlcoholCompanionPreference alcoholPreference =
      AlcoholCompanionPreference.noPreference,
  SmokingCompanionPreference smokingPreference =
      SmokingCompanionPreference.noPreference,
  DrinkingLevel drinkingLevel = DrinkingLevel.sometimes,
  SmokingStatus smokingStatus = SmokingStatus.nonSmoker,
  Set<String> interests = const {'커피', '영화'},
  String? mbti = 'ENFP',
  Set<String>? dateKeys,
  Set<String> campusLifeZones = const {'sinchon'},
  bool schoolVerified = true,
  bool eligible = true,
  Set<String> blocked = const <String>{},
  Set<String> recentlyMet = const <String>{},
  int waitedMinutes = 0,
}) {
  return BlindMeetingCandidate(
    userId: userId,
    atmosphere: atmosphere,
    initiative: initiative,
    purpose: purpose,
    alcoholPreference: alcoholPreference,
    smokingPreference: smokingPreference,
    drinkingLevel: drinkingLevel,
    smokingStatus: smokingStatus,
    interestIds: interests,
    mbti: mbti,
    availableDateKeys: dateKeys ?? const {kDateKey},
    campusLifeZones: campusLifeZones,
    schoolVerified: schoolVerified,
    eligible: eligible,
    blockedUserIds: blocked,
    recentlyMetUserIds: recentlyMet,
    waitedMinutes: waitedMinutes,
  );
}

/// 균형 잡힌 3인 팀 (주도 / 상황 / 경청).
List<BlindMeetingCandidate> balancedTeam(String prefix) => [
  candidate('${prefix}1', initiative: ConversationInitiative.initiator),
  candidate('${prefix}2', initiative: ConversationInitiative.adaptive),
  candidate('${prefix}3', initiative: ConversationInitiative.listener),
];
