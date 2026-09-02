// =============================================================================
// 3:3 블라인드 취향 미팅 — 팀 구성 optimizer
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_matcher.dart
//
// 1단계: 같은 편인 우리 팀 3명 구성
// 2단계: 완성된 두 팀 사이의 호환성 계산
//
// 결과는 항상 deterministic 하다. 동점일 때는 정렬된 참가자 id 문자열로
// tie-break 하므로 같은 입력에 대해 매번 같은 결과가 나온다.
// =============================================================================

import '../blind_meeting_enums.dart';
import 'blind_meeting_candidate.dart';
import 'blind_meeting_hard_constraints.dart';
import 'blind_meeting_matching_config.dart';
import 'blind_meeting_scoring.dart';

List<BlindMeetingCandidate> applyConservativeTeamPreferences(
  List<BlindMeetingCandidate> members,
) {
  if (members.isEmpty) return const [];
  final byParty = <String, List<BlindMeetingCandidate>>{};
  for (final member in members) {
    final key = member.partyId ?? 'solo:${member.userId}';
    byParty.putIfAbsent(key, () => []).add(member);
  }
  final effective =
      <
        String,
        ({
          MeetingPurpose purpose,
          AlcoholCompanionPreference alcohol,
          SmokingCompanionPreference smoking,
        })
      >{};
  for (final entry in byParty.entries) {
    final partyMembers = entry.value;
    final purpose =
        partyMembers.any(
          (member) => member.purpose == MeetingPurpose.friendship,
        )
        ? MeetingPurpose.friendship
        : partyMembers.any((member) => member.purpose == MeetingPurpose.both)
        ? MeetingPurpose.both
        : MeetingPurpose.romance;
    final alcohol =
        partyMembers.any(
          (member) =>
              member.alcoholPreference == AlcoholCompanionPreference.allSober,
        )
        ? AlcoholCompanionPreference.allSober
        : partyMembers.any(
            (member) =>
                member.alcoholPreference ==
                AlcoholCompanionPreference.lightOkay,
          )
        ? AlcoholCompanionPreference.lightOkay
        : AlcoholCompanionPreference.noPreference;
    final smoking =
        partyMembers.any(
          (member) =>
              member.smokingPreference ==
              SmokingCompanionPreference.nonSmokersOnly,
        )
        ? SmokingCompanionPreference.nonSmokersOnly
        : partyMembers.any(
            (member) =>
                member.smokingPreference ==
                SmokingCompanionPreference.noIndoorSmoking,
          )
        ? SmokingCompanionPreference.noIndoorSmoking
        : SmokingCompanionPreference.noPreference;
    effective[entry.key] = (
      purpose: purpose,
      alcohol: alcohol,
      smoking: smoking,
    );
  }
  return members
      .map((member) {
        final values = effective[member.partyId ?? 'solo:${member.userId}']!;
        return member.copyWith(
          purpose: values.purpose,
          alcoholPreference: values.alcohol,
          smokingPreference: values.smoking,
        );
      })
      .toList(growable: false);
}

bool preservesBlindMeetingPartyBoundaries(List<BlindMeetingCandidate> members) {
  final teamIds = members.map((member) => member.userId).toSet();
  for (final member in members) {
    final expected = member.partyMemberIds.isEmpty
        ? <String>{member.userId}
        : member.partyMemberIds;
    if (!teamIds.containsAll(expected)) return false;
    if (expected.length > 1) {
      final key = member.partyId ?? 'legacy:${member.userId}';
      for (final teammate in members.where(
        (item) => expected.contains(item.userId),
      )) {
        if ((teammate.partyId ?? 'legacy:${teammate.userId}') != key) {
          return false;
        }
      }
    }
  }
  return true;
}

/// 후보 팀 하나 (같은 편 3명).
class BlindMeetingTeamProposal {
  final List<BlindMeetingCandidate> members;

  /// 팀은 단일 성별이다 (3:3 에서 "같은 편"은 동성 3명).
  final BlindMeetingGender gender;
  final InternalTeamScoreBreakdown score;

  BlindMeetingTeamProposal({
    required List<BlindMeetingCandidate> members,
    required this.gender,
    required this.score,
  }) : members = List<BlindMeetingCandidate>.unmodifiable(members);

  /// 정렬된 참가자 id를 이어붙인 안정적인 키.
  String get key => (members.map((m) => m.userId).toList()..sort()).join('|');

  Set<String> get userIds => members.map((m) => m.userId).toSet();
}

/// 최종 6인 구성 제안.
class BlindMeetingGroupProposal {
  /// 이 구성을 만든 기준 날짜 (KST `yyyy-MM-dd`).
  final String dateKey;

  /// 여섯 명이 공통으로 가능한 날짜 전체 (오름차순).
  ///
  /// 단체 채팅방 약속잡기의 날짜 후보로 그대로 전달된다.
  final List<String> commonDateKeys;

  final bool alcoholFree;
  final String algorithmVersion;
  final BlindMeetingTeamProposal teamA;
  final BlindMeetingTeamProposal teamB;
  final BlindMeetingGroupScore score;

  /// 대기 시간 보정이 반영된 정렬용 점수. 사용자에게 노출하지 않는다.
  final double adjustedScore;

  BlindMeetingGroupProposal({
    required this.dateKey,
    required List<String> commonDateKeys,
    required this.alcoholFree,
    required this.algorithmVersion,
    required this.teamA,
    required this.teamB,
    required this.score,
    required this.adjustedScore,
  }) : commonDateKeys = List<String>.unmodifiable(commonDateKeys);

  List<String> get teamAUserIds => teamA.members.map((m) => m.userId).toList();
  List<String> get teamBUserIds => teamB.members.map((m) => m.userId).toList();
  List<String> get participantIds => [...teamAUserIds, ...teamBUserIds];

  /// 정렬된 6명 id 기반 tie-break 키.
  String get key => (participantIds.toList()..sort()).join('|');

  Map<String, dynamic> toMatchingResultMap() => {
    'algorithmVersion': algorithmVersion,
    'matchedDateKey': dateKey,
    'commonAvailableDateKeys': commonDateKeys,
    'isAlcoholFree': alcoholFree,
    'internalTeamScores': {
      'teamA': score.teamAInternal,
      'teamB': score.teamBInternal,
    },
    'crossTeamScore': score.crossTeamScore,
    'minimumParticipantScore': score.minimumParticipantScore,
    'finalGroupScore': score.finalGroupScore,
    'participantOpponentScores': score.participantOpponentScores,
  };
}

/// 대체 후보 평가 결과.
class BlindMeetingReplacementEvaluation {
  final BlindMeetingCandidate candidate;

  /// hard constraint 위반 사유. 비어 있으면 통과.
  final Set<BlindMeetingConstraintViolation> violations;

  /// 교체 후 재계산한 6인 구성 점수. 위반이 있으면 null.
  final BlindMeetingGroupScore? scoreAfterReplacement;

  /// 기존 구성 품질 대비 비율.
  final double qualityRatio;

  /// 대기 시간 보정이 포함된 정렬용 점수.
  final double adjustedScore;

  /// 임계값을 통과했는지.
  final bool accepted;

  const BlindMeetingReplacementEvaluation({
    required this.candidate,
    required this.violations,
    required this.scoreAfterReplacement,
    required this.qualityRatio,
    required this.adjustedScore,
    required this.accepted,
  });
}

/// 팀 구성 optimizer.
class BlindMeetingMatcher {
  final BlindMeetingMatchingConfig config;

  /// 후보 수가 이 값 이하면 3명 조합을 전부 열거한다.
  final int exhaustiveTeamPoolLimit;

  /// 2단계로 넘길 상위 팀 후보 개수.
  final int teamShortlistSize;

  /// 각 seed가 검사할 이웃 후보 수 (bounded greedy).
  final int neighborhoodSize;

  const BlindMeetingMatcher({
    this.config = BlindMeetingMatchingConfig.current,
    this.exhaustiveTeamPoolLimit = 14,
    this.teamShortlistSize = 40,
    this.neighborhoodSize = 12,
  });

  String get algorithmVersion => config.algorithmVersion;

  /// 1단계: 조건을 만족하는 우리 팀 3명 후보들을 만든다.
  ///
  /// 반환 목록은 (내부 점수 내림차순, key 오름차순) 으로 정렬된 deterministic 결과다.
  List<BlindMeetingTeamProposal> buildTeamProposals({
    required List<BlindMeetingCandidate> pool,
    required String dateKey,
    required bool alcoholFree,
  }) {
    final eligible = _eligiblePool(
      pool: pool,
      dateKey: dateKey,
      alcoholFree: alcoholFree,
    );
    if (eligible.length < BlindMeetingHardConstraints.teamSize) {
      return const <BlindMeetingTeamProposal>[];
    }

    final byKey = <String, BlindMeetingTeamProposal>{};

    void tryTeam(List<BlindMeetingCandidate> trio, BlindMeetingGender gender) {
      if (!preservesBlindMeetingPartyBoundaries(trio)) return;
      final effectiveTrio = applyConservativeTeamPreferences(trio);
      if (!BlindMeetingHardConstraints.isGroupAllowed(
        effectiveTrio,
        dateKey: dateKey,
        alcoholFreeGroup: alcoholFree,
        expectedSize: BlindMeetingHardConstraints.teamSize,
      )) {
        return;
      }
      final ordered = _orderTeamMembers(effectiveTrio);
      final proposal = BlindMeetingTeamProposal(
        members: ordered,
        gender: gender,
        score: internalTeamScore(
          ordered,
          config: config,
          alcoholFree: alcoholFree,
        ),
      );
      byKey[proposal.key] = proposal;
    }

    // 3:3 에서 한 팀은 동성 3명이므로 성별로 후보군을 먼저 나눈 뒤
    // 각 성별 안에서만 조합을 만든다. 전체 상위 6명을 뽑아놓고 나중에
    // 성비를 맞추는 ad-hoc post-processing 이 아니라, 제약을 탐색 공간
    // 자체에 넣는 constrained selection 이다.
    final crossWeights = config.crossWeightsFor(alcoholFree: alcoholFree);
    final byGender = BlindMeetingHardConstraints.splitByGender(eligible);

    for (final entry in <(BlindMeetingGender, List<BlindMeetingCandidate>)>[
      (BlindMeetingGender.male, byGender.male),
      (BlindMeetingGender.female, byGender.female),
    ]) {
      final gender = entry.$1;
      final sameGender = entry.$2;
      if (sameGender.length < BlindMeetingHardConstraints.teamSize) continue;

      if (sameGender.length <= exhaustiveTeamPoolLimit) {
        for (var i = 0; i < sameGender.length; i++) {
          for (var j = i + 1; j < sameGender.length; j++) {
            for (var k = j + 1; k < sameGender.length; k++) {
              tryTeam([sameGender[i], sameGender[j], sameGender[k]], gender);
            }
          }
        }
        continue;
      }

      for (var i = 0; i < sameGender.length; i++) {
        final seed = sameGender[i];
        final neighbors =
            sameGender.where((c) => c.userId != seed.userId).toList()
              ..sort((a, b) {
                final byAffinity = pairCompatibility(
                  seed,
                  b,
                  weights: crossWeights,
                ).compareTo(pairCompatibility(seed, a, weights: crossWeights));
                if (byAffinity != 0) return byAffinity;
                return a.userId.compareTo(b.userId);
              });
        final window = neighbors.take(neighborhoodSize).toList();
        for (var j = 0; j < window.length; j++) {
          for (var k = j + 1; k < window.length; k++) {
            tryTeam([seed, window[j], window[k]], gender);
          }
        }
      }
    }

    final proposals = byKey.values.toList()
      ..sort((a, b) {
        final diff = b.score.total - a.score.total;
        if (diff.abs() > config.tieEpsilon) return diff > 0 ? 1 : -1;
        return a.key.compareTo(b.key);
      });
    return List<BlindMeetingTeamProposal>.unmodifiable(proposals);
  }

  /// 2단계: 상위 팀 후보들을 짝지어 최종 6인 구성을 만든다.
  ///
  /// [maxGroups] 개까지 서로 겹치지 않는 구성을 점수 순으로 돌려준다.
  List<BlindMeetingGroupProposal> proposeGroups({
    required List<BlindMeetingCandidate> pool,
    required String dateKey,
    required bool alcoholFree,
    int maxGroups = 1,
  }) {
    final selected = <BlindMeetingGroupProposal>[];
    var remaining = pool;
    for (var round = 0; round < maxGroups; round++) {
      final group = _bestGroupFrom(
        pool: remaining,
        dateKey: dateKey,
        alcoholFree: alcoholFree,
      );
      if (group == null) break;
      selected.add(group);
      final used = group.participantIds.toSet();
      remaining = remaining
          .where((candidate) => !used.contains(candidate.userId))
          .toList();
    }
    return List<BlindMeetingGroupProposal>.unmodifiable(selected);
  }

  /// 가장 좋은 6인 구성 하나. 없으면 null.
  BlindMeetingGroupProposal? bestGroup({
    required List<BlindMeetingCandidate> pool,
    required String dateKey,
    required bool alcoholFree,
  }) {
    return _bestGroupFrom(
      pool: pool,
      dateKey: dateKey,
      alcoholFree: alcoholFree,
    );
  }

  BlindMeetingGroupProposal? _bestGroupFrom({
    required List<BlindMeetingCandidate> pool,
    required String dateKey,
    required bool alcoholFree,
  }) {
    final teams = buildTeamProposals(
      pool: pool,
      dateKey: dateKey,
      alcoholFree: alcoholFree,
    );
    if (teams.length < 2) return null;

    // 두 팀은 반드시 서로 다른 성별이다. 성별별로 상위 팀을 따로 추려서
    // 짝지으므로, 한쪽 성별이 점수 상위권을 독점해도 shortlist 가 한 성별로
    // 채워져 3:3 이 사라지는 일이 없다.
    final maleTeams = teams
        .where((t) => t.gender == BlindMeetingGender.male)
        .take(teamShortlistSize)
        .toList();
    final femaleTeams = teams
        .where((t) => t.gender == BlindMeetingGender.female)
        .take(teamShortlistSize)
        .toList();
    if (maleTeams.isEmpty || femaleTeams.isEmpty) return null;

    final groups = <BlindMeetingGroupProposal>[];

    for (var i = 0; i < maleTeams.length; i++) {
      for (var j = 0; j < femaleTeams.length; j++) {
        final left = maleTeams[i];
        final right = femaleTeams[j];
        // 같은 uid 가 남/여 양쪽 문서에 존재하는 손상 데이터 방어.
        if (left.userIds.intersection(right.userIds).isNotEmpty) continue;

        final members = [...left.members, ...right.members];
        // 비싼 6인 점수 계산 전에 생활권부터 거른다.
        if (BlindMeetingHardConstraints.sharedCampusLifeZones(
          members,
        ).isEmpty) {
          continue;
        }
        if (!BlindMeetingHardConstraints.isGroupAllowed(
          members,
          dateKey: dateKey,
          alcoholFreeGroup: alcoholFree,
          expectedSize: BlindMeetingHardConstraints.groupSize,
        )) {
          continue;
        }

        final score = groupScore(
          teamA: left.members,
          teamB: right.members,
          config: config,
          alcoholFree: alcoholFree,
        );
        final bonus = waitingTimeBonus(members, config: config);
        groups.add(
          BlindMeetingGroupProposal(
            dateKey: dateKey,
            commonDateKeys: BlindMeetingHardConstraints.commonDateKeys(members),
            alcoholFree: alcoholFree,
            algorithmVersion: algorithmVersion,
            teamA: left,
            teamB: right,
            score: score,
            adjustedScore: score.finalGroupScore + bonus,
          ),
        );
      }
    }

    if (groups.isEmpty) return null;

    groups.sort((a, b) {
      final diff = b.adjustedScore - a.adjustedScore;
      if (diff.abs() > config.tieEpsilon) return diff > 0 ? 1 : -1;
      return a.key.compareTo(b.key);
    });

    return groups.first;
  }

  /// 대체 후보 하나를 평가한다.
  ///
  /// 개인 pair 점수가 아니라, 해당 사용자를 넣었을 때 재계산되는
  /// 전체 6인 구성 점수를 기준으로 판정한다.
  BlindMeetingReplacementEvaluation evaluateReplacement({
    required List<BlindMeetingCandidate> teamA,
    required List<BlindMeetingCandidate> teamB,
    required String vacantUserId,
    required BlindMeetingCandidate candidate,
    required double baselineFinalGroupScore,
    required String dateKey,
    required bool alcoholFree,
    bool urgent = false,
  }) {
    final threshold = urgent
        ? config.replacementUrgentRatio
        : config.replacementNormalRatio;

    final nextA = _substitute(teamA, vacantUserId, candidate);
    final nextB = _substitute(teamB, vacantUserId, candidate);
    final members = [...nextA, ...nextB];

    final violations = <BlindMeetingConstraintViolation>{};
    // 빈자리가 실제로 존재하고 후보가 그 자리에 들어갔는지 확인한다.
    if (!members.any((m) => m.userId == candidate.userId) ||
        members.any((m) => m.userId == vacantUserId)) {
      violations.add(BlindMeetingConstraintViolation.invalidGroupSize);
    }
    violations.addAll(
      BlindMeetingHardConstraints.checkGroup(
        members,
        dateKey: dateKey,
        alcoholFreeGroup: alcoholFree,
        expectedSize: 6,
      ),
    );

    if (violations.isNotEmpty) {
      return BlindMeetingReplacementEvaluation(
        candidate: candidate,
        violations: Set.unmodifiable(violations),
        scoreAfterReplacement: null,
        qualityRatio: 0,
        adjustedScore: 0,
        accepted: false,
      );
    }

    final score = groupScore(
      teamA: nextA,
      teamB: nextB,
      config: config,
      alcoholFree: alcoholFree,
    );
    final ratio = baselineFinalGroupScore <= 0
        ? 1.0
        : score.finalGroupScore / baselineFinalGroupScore;
    final bonus = waitingTimeBonus([candidate], config: config);

    return BlindMeetingReplacementEvaluation(
      candidate: candidate,
      violations: const <BlindMeetingConstraintViolation>{},
      scoreAfterReplacement: score,
      qualityRatio: ratio,
      adjustedScore: score.finalGroupScore + bonus,
      accepted: ratio + config.tieEpsilon >= threshold,
    );
  }

  /// 대체 후보들을 평가하고 통과한 후보를 순위대로 돌려준다.
  List<BlindMeetingReplacementEvaluation> rankReplacements({
    required List<BlindMeetingCandidate> teamA,
    required List<BlindMeetingCandidate> teamB,
    required String vacantUserId,
    required List<BlindMeetingCandidate> candidates,
    required double baselineFinalGroupScore,
    required String dateKey,
    required bool alcoholFree,
    bool urgent = false,
    int limit = 3,
  }) {
    final evaluations = <BlindMeetingReplacementEvaluation>[];
    final seatUserIds = {
      ...teamA.map((m) => m.userId),
      ...teamB.map((m) => m.userId),
    };
    for (final candidate in candidates) {
      if (seatUserIds.contains(candidate.userId)) continue;
      final evaluation = evaluateReplacement(
        teamA: teamA,
        teamB: teamB,
        vacantUserId: vacantUserId,
        candidate: candidate,
        baselineFinalGroupScore: baselineFinalGroupScore,
        dateKey: dateKey,
        alcoholFree: alcoholFree,
        urgent: urgent,
      );
      if (evaluation.accepted) evaluations.add(evaluation);
    }

    evaluations.sort((a, b) {
      final diff = b.adjustedScore - a.adjustedScore;
      if (diff.abs() > config.tieEpsilon) return diff > 0 ? 1 : -1;
      return a.candidate.userId.compareTo(b.candidate.userId);
    });

    return List<BlindMeetingReplacementEvaluation>.unmodifiable(
      evaluations.take(limit),
    );
  }

  // ---------------------------------------------------------------------------
  // 내부 유틸
  // ---------------------------------------------------------------------------

  List<BlindMeetingCandidate> _eligiblePool({
    required List<BlindMeetingCandidate> pool,
    required String dateKey,
    required bool alcoholFree,
  }) {
    final seen = <String>{};
    final result = <BlindMeetingCandidate>[];
    for (final candidate in pool) {
      if (!seen.add(candidate.userId)) continue;
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate,
        dateKey: dateKey,
        alcoholFreeGroup: alcoholFree,
      );
      if (violations.isEmpty) result.add(candidate);
    }
    result.sort((a, b) => a.userId.compareTo(b.userId));
    return result;
  }

  /// 팀원 표시 순서를 `주도 → 상황에 맞춤 → 경청` 으로 안정화한다.
  List<BlindMeetingCandidate> _orderTeamMembers(
    List<BlindMeetingCandidate> members,
  ) {
    final ordered = members.toList()
      ..sort((a, b) {
        final byRole = a.initiative.index.compareTo(b.initiative.index);
        if (byRole != 0) return byRole;
        return a.userId.compareTo(b.userId);
      });
    return ordered;
  }

  List<BlindMeetingCandidate> _substitute(
    List<BlindMeetingCandidate> team,
    String vacantUserId,
    BlindMeetingCandidate candidate,
  ) {
    return team
        .map((m) => m.userId == vacantUserId ? candidate : m)
        .toList(growable: false);
  }
}
