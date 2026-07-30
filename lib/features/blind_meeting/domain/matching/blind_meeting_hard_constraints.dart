// =============================================================================
// 3:3 블라인드 취향 미팅 — 필수 조건 필터 (hard constraint)
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_hard_constraints.dart
//
// 여기 있는 조건은 가중치가 아니다. 매칭 전에 적용되고, 후보가 부족하더라도
// 자동으로 완화되지 않는다. 조건 완화는 사용자가 직접 선택해야 한다.
// =============================================================================

import '../blind_meeting_enums.dart';
import 'blind_meeting_scoring.dart';
import 'blind_meeting_candidate.dart';

/// hard constraint 위반 사유.
enum BlindMeetingConstraintViolation {
  /// 학교 인증 미완료
  notSchoolVerified,

  /// 정지·탈퇴·제재·반복 노쇼 제한 상태
  notEligible,

  /// 해당 날짜/시간에 참여 불가
  slotUnavailable,

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
}

extension BlindMeetingConstraintViolationMessage
    on BlindMeetingConstraintViolation {
  /// 운영/로그용 짧은 사유. 사용자에게 그대로 노출하지 않는다.
  String get code => name;
}

/// 필수 조건 판정.
///
/// 성별·관계 지향 등 서비스 전역 매칭 대상 정책은 앱의 기존 정책을 그대로
/// 존중해야 하므로, 후보를 만들기 전에 [BlindMeetingCandidate.eligible] 로
/// 이미 반영해서 넘긴다. 여기서 이성애 관계를 hardcode 하지 않는다.
class BlindMeetingHardConstraints {
  const BlindMeetingHardConstraints._();

  /// 개인 단위 조건.
  static Set<BlindMeetingConstraintViolation> checkCandidate(
    BlindMeetingCandidate candidate, {
    required String slotId,
    required bool alcoholFreeGroup,
  }) {
    final violations = <BlindMeetingConstraintViolation>{};
    if (!candidate.schoolVerified) {
      violations.add(BlindMeetingConstraintViolation.notSchoolVerified);
    }
    if (!candidate.eligible) {
      violations.add(BlindMeetingConstraintViolation.notEligible);
    }
    if (!candidate.availableSlotIds.contains(slotId)) {
      violations.add(BlindMeetingConstraintViolation.slotUnavailable);
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
    required String slotId,
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
          slotId: slotId,
          alcoholFreeGroup: alcoholFreeGroup,
        ),
      );
    }
    for (var i = 0; i < members.length; i++) {
      for (var j = i + 1; j < members.length; j++) {
        violations.addAll(checkPair(members[i], members[j]));
      }
    }
    return violations;
  }

  /// 그룹이 조건을 모두 만족하는지.
  static bool isGroupAllowed(
    List<BlindMeetingCandidate> members, {
    required String slotId,
    required bool alcoholFreeGroup,
    int? expectedSize,
  }) {
    return checkGroup(
      members,
      slotId: slotId,
      alcoholFreeGroup: alcoholFreeGroup,
      expectedSize: expectedSize,
    ).isEmpty;
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
}
