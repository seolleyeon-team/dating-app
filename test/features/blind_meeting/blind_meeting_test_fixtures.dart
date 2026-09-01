// 블라인드 취향 미팅 테스트용 후보 빌더

import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_candidate.dart';

/// 최종 확정 시간 테스트용 슬롯 id (약속잡기 단계에서만 쓰인다).
const String kSlot = '2026-08-01#evening';

/// 매칭 기준 날짜. 세부 시간은 매칭 조건이 아니다.
const String kDateKey = '2026-08-01';

BlindMeetingCandidate candidate(
  String userId, {
  BlindMeetingGender gender = BlindMeetingGender.male,
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
    gender: gender,
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

/// 균형 잡힌 동성 3인 팀 (주도 / 상황 / 경청).
///
/// 3:3 에서 "같은 편"은 동성 3명이다. 6인 pool 은 남성 팀 + 여성 팀으로
/// 조립해야 성비 불변식(3남 + 3녀)을 만족한다.
List<BlindMeetingCandidate> balancedTeam(
  String prefix, {
  BlindMeetingGender gender = BlindMeetingGender.male,
}) => [
  candidate(
    '${prefix}1',
    gender: gender,
    initiative: ConversationInitiative.initiator,
  ),
  candidate(
    '${prefix}2',
    gender: gender,
    initiative: ConversationInitiative.adaptive,
  ),
  candidate(
    '${prefix}3',
    gender: gender,
    initiative: ConversationInitiative.listener,
  ),
];
