// =============================================================================
// 3:3 블라인드 취향 미팅 — 매칭 후보 (알고리즘 입력)
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_candidate.dart
//
// 이 타입은 순수 도메인 값이며 Firestore/Flutter에 의존하지 않는다.
// 실제 매칭은 서버(Cloud Functions)에서 수행하고, 이 Dart 구현은 알고리즘 명세의
// 기준 구현 겸 단위 테스트 대상이다. 두 구현은
// functions/src/blindMeeting/matching.ts 와 동일한 가중치 설정을 공유한다.
// =============================================================================

import '../blind_meeting_enums.dart';

/// 3:3 상품이 지원하는 canonical 성별.
///
/// 3:3 은 "남성 3명 + 여성 3명"이 상품 정의 자체다. 이 값은 누가 누구를
/// 좋아할 수 있는지를 정하는 지향 정책이 아니라, 두 팀을 채우는 구조적
/// 제약이다. canonical 값을 확인할 수 없는 사용자는 후보에 넣지 않는다
/// (임의로 한쪽에 배정하지 않는다).
enum BlindMeetingGender { male, female }

/// 매칭 알고리즘이 필요한 참가자 정보 전부.
class BlindMeetingCandidate {
  final String userId;

  /// 분리할 수 없는 선결 파티. null이면 legacy 1인 파티다.
  final String? partyId;
  final Set<String> partyMemberIds;

  /// canonical 성별. 3남 + 3녀 불변식의 입력이다.
  final BlindMeetingGender gender;

  final ConversationAtmosphere atmosphere;
  final ConversationInitiative initiative;
  final MeetingPurpose purpose;
  final AlcoholCompanionPreference alcoholPreference;
  final SmokingCompanionPreference smokingPreference;

  final DrinkingLevel drinkingLevel;
  final SmokingStatus smokingStatus;

  final Set<String> interestIds;
  final String? mbti;

  /// 참여 가능한 날짜 집합 (KST `yyyy-MM-dd`).
  ///
  /// 세부 시간은 매칭 조건이 아니다. 팀 구성 후 단체 채팅방에서 정한다.
  final Set<String> availableDateKeys;

  /// 생활권 (`users/{uid}.onboarding.campusLifeZones` 에 저장된 값).
  ///
  /// 분류는 [CampusLifeZoneResolver] 가 담당하며 매칭기는 재계산하지 않는다.
  /// 한 사용자가 신촌·송도를 동시에 가질 수 있으므로 비교는 항상 교집합이다.
  final Set<String> campusLifeZones;

  /// 학교 인증 완료.
  final bool schoolVerified;

  /// 정지/탈퇴/제재/반복 노쇼 제한이 없는 상태.
  final bool eligible;

  /// 서로 차단했거나 안전 정책상 접촉 제한된 사용자 id (양방향 합집합).
  final Set<String> blockedUserIds;

  /// 최근 동일 미팅에서 만난 사용자 id (재매칭 제외 정책).
  final Set<String> recentlyMetUserIds;

  /// 대기 시간 (분). starvation 방지 보정에만 쓰이며 hard constraint를 넘지 못한다.
  final int waitedMinutes;

  const BlindMeetingCandidate({
    required this.userId,
    this.partyId,
    this.partyMemberIds = const <String>{},
    required this.gender,
    required this.atmosphere,
    required this.initiative,
    required this.purpose,
    required this.alcoholPreference,
    required this.smokingPreference,
    required this.drinkingLevel,
    required this.smokingStatus,
    required this.interestIds,
    this.mbti,
    required this.availableDateKeys,
    this.campusLifeZones = const <String>{},
    this.schoolVerified = true,
    this.eligible = true,
    this.blockedUserIds = const <String>{},
    this.recentlyMetUserIds = const <String>{},
    this.waitedMinutes = 0,
  });

  /// 무알코올 전용 후보군 대상인지.
  bool get requiresAlcoholFreeGroup =>
      alcoholPreference == AlcoholCompanionPreference.allSober &&
      drinkingLevel.isSober;

  /// 비흡연자만 만나겠다고 선택했는지.
  bool get requiresNonSmokersOnly =>
      smokingPreference == SmokingCompanionPreference.nonSmokersOnly;

  BlindMeetingCandidate copyWith({
    ConversationAtmosphere? atmosphere,
    ConversationInitiative? initiative,
    MeetingPurpose? purpose,
    AlcoholCompanionPreference? alcoholPreference,
    SmokingCompanionPreference? smokingPreference,
    DrinkingLevel? drinkingLevel,
    SmokingStatus? smokingStatus,
    Set<String>? interestIds,
    String? mbti,
    Set<String>? availableDateKeys,
    Set<String>? campusLifeZones,
    bool? schoolVerified,
    bool? eligible,
    Set<String>? blockedUserIds,
    Set<String>? recentlyMetUserIds,
    int? waitedMinutes,
    BlindMeetingGender? gender,
  }) {
    return BlindMeetingCandidate(
      userId: userId,
      partyId: partyId,
      partyMemberIds: partyMemberIds,
      gender: gender ?? this.gender,
      atmosphere: atmosphere ?? this.atmosphere,
      initiative: initiative ?? this.initiative,
      purpose: purpose ?? this.purpose,
      alcoholPreference: alcoholPreference ?? this.alcoholPreference,
      smokingPreference: smokingPreference ?? this.smokingPreference,
      drinkingLevel: drinkingLevel ?? this.drinkingLevel,
      smokingStatus: smokingStatus ?? this.smokingStatus,
      interestIds: interestIds ?? this.interestIds,
      mbti: mbti ?? this.mbti,
      availableDateKeys: availableDateKeys ?? this.availableDateKeys,
      campusLifeZones: campusLifeZones ?? this.campusLifeZones,
      schoolVerified: schoolVerified ?? this.schoolVerified,
      eligible: eligible ?? this.eligible,
      blockedUserIds: blockedUserIds ?? this.blockedUserIds,
      recentlyMetUserIds: recentlyMetUserIds ?? this.recentlyMetUserIds,
      waitedMinutes: waitedMinutes ?? this.waitedMinutes,
    );
  }
}
