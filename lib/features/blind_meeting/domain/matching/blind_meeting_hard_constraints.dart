// =============================================================================
// 3:3 블라인드 취향 미팅 — 필수 조건 필터 (hard constraint)
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_hard_constraints.dart
//
// 여기 있는 조건은 가중치가 아니다. 매칭 전에 적용되고, 후보가 부족하더라도
// 자동으로 완화되지 않는다. 조건 완화는 사용자가 직접 선택해야 한다.
// =============================================================================

import '../blind_meeting_availability.dart';
import '../blind_meeting_enums.dart';
import 'blind_meeting_scoring.dart';
import 'blind_meeting_candidate.dart';

/// hard constraint 위반 사유.
enum BlindMeetingConstraintViolation {
  /// 학교 인증 미완료
  notSchoolVerified,

  /// 정지·탈퇴·제재·반복 노쇼 제한 상태
  notEligible,

  /// 해당 날짜에 참여 불가
  dateUnavailable,

  /// 여섯 명이 공통으로 가능한 날짜가 없음 (최종 구성 확정 단계에서만 판정)
  noCommonDate,

  /// 서로 차단했거나 안전 정책상 접촉 제한
  blockedContact,

  /// 최근 동일 미팅에서 만난 사용자
  recentlyMet,

  /// 전원 비음주를 원하지만 일반 미팅에 배정됨
  alcoholFreeGroupRequired,

  /// 무알코올 미팅인데 비음주가 아닌 참가자가 포함됨
  alcoholFreeGroupViolated,

  /// 비흡연자 전용 조건 위반
  smokingRejected,

  /// 직접 충돌하는 미팅 목적 (연애만 × 친구만)
  purposeConflict,

  /// 동일 사용자 중복 참가
  duplicateParticipant,

  /// 팀/그룹 인원 수가 맞지 않음
  invalidGroupSize,

  /// 한 팀(같은 편) 안에 서로 다른 성별이 섞임
  mixedGenderTeam,

  /// 여섯 명이 3남 + 3녀가 아님
  genderImbalance,

  /// 여섯 명이 함께 만날 수 있는 공통 생활권이 없음
  campusLifeZoneMismatch,

  /// 생활권 정보가 없어 판정할 수 없음 (fail-closed)
  campusLifeZoneMissing,
}

extension BlindMeetingConstraintViolationMessage
    on BlindMeetingConstraintViolation {
  /// 운영/로그용 짧은 사유. 사용자에게 그대로 노출하지 않는다.
  String get code => name;
}

/// 필수 조건 판정.
///
/// 정지·제재·반복 노쇼 같은 서비스 전역 매칭 대상 정책은 후보를 만들기 전에
/// [BlindMeetingCandidate.eligible] 로 이미 반영해서 넘긴다.
///
/// 성별은 예외다. 3:3 은 "남성 3명 + 여성 3명"이 상품 정의 자체이므로,
/// 팀은 동성 3명이어야 하고 그룹은 정확히 3남 + 3녀여야 한다. 이것은 누가
/// 누구를 좋아할 수 있는지에 대한 지향 정책이 아니라 좌석 구조 제약이며,
/// 점수로 완화되지 않는 hard constraint 다.
class BlindMeetingHardConstraints {
  const BlindMeetingHardConstraints._();

  /// 한 팀(같은 편)의 인원. 3:3 이므로 3명.
  static const int teamSize = 3;

  /// 한 미팅의 총 인원. 3남 + 3녀.
  static const int groupSize = 6;

  /// 성별별 인원 수.
  static ({int male, int female}) genderCounts(
    Iterable<BlindMeetingCandidate> members,
  ) {
    var male = 0;
    var female = 0;
    for (final member in members) {
      if (member.gender == BlindMeetingGender.male) {
        male++;
      } else {
        female++;
      }
    }
    return (male: male, female: female);
  }

  /// 개인 단위 조건.
  static Set<BlindMeetingConstraintViolation> checkCandidate(
    BlindMeetingCandidate candidate, {
    required String dateKey,
    required bool alcoholFreeGroup,
  }) {
    final violations = <BlindMeetingConstraintViolation>{};
    if (!candidate.schoolVerified) {
      violations.add(BlindMeetingConstraintViolation.notSchoolVerified);
    }
    if (!candidate.eligible) {
      violations.add(BlindMeetingConstraintViolation.notEligible);
    }
    if (!candidate.availableDateKeys.contains(dateKey)) {
      violations.add(BlindMeetingConstraintViolation.dateUnavailable);
    }
    if (candidate.requiresAlcoholFreeGroup && !alcoholFreeGroup) {
      violations.add(BlindMeetingConstraintViolation.alcoholFreeGroupRequired);
    }
    if (alcoholFreeGroup && !candidate.drinkingLevel.isSober) {
      violations.add(BlindMeetingConstraintViolation.alcoholFreeGroupViolated);
    }
    return violations;
  }

  /// 두 사람 사이 조건.
  static Set<BlindMeetingConstraintViolation> checkPair(
    BlindMeetingCandidate a,
    BlindMeetingCandidate b,
  ) {
    final violations = <BlindMeetingConstraintViolation>{};
    if (a.userId == b.userId) {
      violations.add(BlindMeetingConstraintViolation.duplicateParticipant);
      return violations;
    }
    if (a.blockedUserIds.contains(b.userId) ||
        b.blockedUserIds.contains(a.userId)) {
      violations.add(BlindMeetingConstraintViolation.blockedContact);
    }
    if (a.recentlyMetUserIds.contains(b.userId) ||
        b.recentlyMetUserIds.contains(a.userId)) {
      violations.add(BlindMeetingConstraintViolation.recentlyMet);
    }
    if (a.requiresAlcoholFreeGroup && !b.drinkingLevel.isSober ||
        b.requiresAlcoholFreeGroup && !a.drinkingLevel.isSober) {
      violations.add(BlindMeetingConstraintViolation.alcoholFreeGroupViolated);
    }
    if (a.requiresNonSmokersOnly && b.smokingStatus.isSmoker ||
        b.requiresNonSmokersOnly && a.smokingStatus.isSmoker) {
      violations.add(BlindMeetingConstraintViolation.smokingRejected);
    }
    if (purposeCompatibility(a.purpose, b.purpose).isDirectConflict) {
      violations.add(BlindMeetingConstraintViolation.purposeConflict);
    }
    return violations;
  }

  /// 팀 또는 그룹 전체 조건.
  static Set<BlindMeetingConstraintViolation> checkGroup(
    List<BlindMeetingCandidate> members, {
    required String dateKey,
    required bool alcoholFreeGroup,
    int? expectedSize,
  }) {
    final violations = <BlindMeetingConstraintViolation>{};
    if (expectedSize != null && members.length != expectedSize) {
      violations.add(BlindMeetingConstraintViolation.invalidGroupSize);
    }
    final seen = <String>{};
    for (final member in members) {
      if (!seen.add(member.userId)) {
        violations.add(BlindMeetingConstraintViolation.duplicateParticipant);
      }
      violations.addAll(
        checkCandidate(
          member,
          dateKey: dateKey,
          alcoholFreeGroup: alcoholFreeGroup,
        ),
      );
    }
    for (var i = 0; i < members.length; i++) {
      for (var j = i + 1; j < members.length; j++) {
        violations.addAll(checkPair(members[i], members[j]));
      }
    }
    // 생활권은 날짜와 달리 per-candidate proxy가 없는 진짜 그룹 속성이라
    // (개인은 여러 생활권을 가질 수 있다) 여기서 교집합을 직접 확인한다.
    // 실제로 함께 만나려면 전원이 최소 하나의 공통 생활권을 가져야 한다.
    if (members.isNotEmpty) {
      if (members.any((member) => _normalizedZones(member).isEmpty)) {
        violations.add(BlindMeetingConstraintViolation.campusLifeZoneMissing);
      } else if (sharedCampusLifeZones(members).isEmpty) {
        violations.add(BlindMeetingConstraintViolation.campusLifeZoneMismatch);
      }
    }
    // 성비는 3:3 상품 정의 자체다. 팀(3명)은 단일 성별이어야 하고
    // 그룹(6명)은 정확히 3남 + 3녀여야 한다. 점수가 아무리 높아도
    // 4M2F / 5M1F / 6M 구성은 만들지 않는다.
    if (members.isNotEmpty) {
      final counts = genderCounts(members);
      if (expectedSize == teamSize) {
        if (counts.male > 0 && counts.female > 0) {
          violations.add(BlindMeetingConstraintViolation.mixedGenderTeam);
        }
      } else if (expectedSize == groupSize) {
        if (counts.male != teamSize || counts.female != teamSize) {
          violations.add(BlindMeetingConstraintViolation.genderImbalance);
        }
      }
    }
    // 공통 가능 날짜 검사는 의도적으로 여기서 하지 않는다.
    // 전원이 [dateKey]를 갖고 있어야 통과하므로 교집합은 항상 dateKey를 포함한다.
    // 즉 여기서 교집합을 계산해도 판정이 달라지지 않으면서,
    // 모든 3인 조합과 팀 쌍마다 반복 실행되는 비용만 생긴다.
    // 최종 6인 구성에 대한 검사는 미팅 생성 시점([commonDateKeys] 호출부)에서 한다.
    return violations;
  }

  static Set<String> _normalizedZones(BlindMeetingCandidate candidate) {
    return candidate.campusLifeZones
        .map((zone) => zone.trim())
        .where((zone) => zone.isNotEmpty)
        .toSet();
  }

  /// 그룹 전원이 함께 만날 수 있는 공통 생활권.
  ///
  /// 다수결/대표자 기준이 아니라 반드시 교집합이다. 한 명이라도 생활권
  /// 정보가 없으면 빈 집합을 돌려준다 (fail-closed).
  static Set<String> sharedCampusLifeZones(
    List<BlindMeetingCandidate> members,
  ) {
    if (members.isEmpty) return <String>{};
    Set<String>? shared;
    for (final member in members) {
      final zones = _normalizedZones(member);
      if (zones.isEmpty) return <String>{};
      shared = shared == null ? zones : shared.intersection(zones);
      if (shared.isEmpty) return <String>{};
    }
    return shared ?? <String>{};
  }

  /// 그룹이 조건을 모두 만족하는지.
  static bool isGroupAllowed(
    List<BlindMeetingCandidate> members, {
    required String dateKey,
    required bool alcoholFreeGroup,
    int? expectedSize,
  }) {
    return checkGroup(
      members,
      dateKey: dateKey,
      alcoholFreeGroup: alcoholFreeGroup,
      expectedSize: expectedSize,
    ).isEmpty;
  }

  /// 구성원 전원이 공통으로 가능한 날짜 (오름차순).
  ///
  /// 이 목록이 비어 있으면 같은 미팅으로 확정하지 않는다. 확정된 미팅에서는
  /// 단체 채팅방 약속잡기의 날짜 후보로 그대로 쓰인다.
  static List<String> commonDateKeys(Iterable<BlindMeetingCandidate> members) {
    return BlindMeetingAvailability.commonDateKeys(
      members.map((m) => m.availableDateKeys),
    );
  }

  /// 무알코올 전용 후보군으로 분리한다.
  ///
  /// 후보가 부족해도 음주 사용자로 자동 대체하지 않는다.
  static List<BlindMeetingCandidate> alcoholFreePool(
    Iterable<BlindMeetingCandidate> pool,
  ) {
    return pool
        .where((c) => c.requiresAlcoholFreeGroup || c.drinkingLevel.isSober)
        .where((c) => c.drinkingLevel.isSober)
        .toList();
  }

  /// 일반(음주 허용) 미팅 후보군.
  ///
  /// 전원 비음주를 요구한 사용자는 절대 포함되지 않는다.
  static List<BlindMeetingCandidate> standardPool(
    Iterable<BlindMeetingCandidate> pool,
  ) {
    return pool.where((c) => !c.requiresAlcoholFreeGroup).toList();
  }

  /// 성별로 후보군을 나눈다 (점수 계산 이전 단계).
  static ({
    List<BlindMeetingCandidate> male,
    List<BlindMeetingCandidate> female,
  })
  splitByGender(Iterable<BlindMeetingCandidate> pool) {
    final male = <BlindMeetingCandidate>[];
    final female = <BlindMeetingCandidate>[];
    for (final candidate in pool) {
      if (candidate.gender == BlindMeetingGender.male) {
        male.add(candidate);
      } else {
        female.add(candidate);
      }
    }
    return (male: male, female: female);
  }
}
