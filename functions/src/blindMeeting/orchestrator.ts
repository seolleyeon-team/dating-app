/**
 * 3:3 블라인드 취향 미팅 — 서버 오케스트레이션
 * 경로: functions/src/blindMeeting/orchestrator.ts
 *
 * 매칭 실행, 참가 확정, 보증금, 단체 채팅 생성, 대체 충원, 노쇼 처리,
 * 후속 선택과 상호 선택 판정을 담당한다.
 * 중요한 상태 전환은 모두 여기(서버)에서만 수행한다.
 */

import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import {
  loadCampusLifeZoneActivation,
  loadCampusLifeZoneEnforced,
} from "../campusLifeZoneActivation";
import {
  BLIND_MEETING_GROUP_SIZE,
  BLIND_MEETING_TEAM_SIZE,
  readBlindMeetingGender,
  validateBlindThreeVsThreeParticipants,
} from "./genderBalance";
import {
  Candidate,
  GroupProposal,
  describeGenderAvailability,
  splitByGender,
  alcoholFreePool,
  bestGroup,
  groupScore,
  rankReplacements,
  requiresAlcoholFreeGroup,
  sharedCampusLifeZones,
  standardPool,
} from "./matching";
import { CURRENT_MATCHING_CONFIG } from "./matchingConfig";
import { notifyBlindMeeting } from "./notifications";
import {
  loadActivePartyForUser,
  withdrawMatchedBlindMeetingParty,
} from "./party";
import {
  BlindMeetingPolicy,
  refundAmountFor,
  resolveCancellation,
  resolveNoShowSanction,
} from "./policy";
import { refundDeposit } from "./payments";
import {
  onBlindMeetingCheckIn,
  onBlindMeetingCheckOut,
  stopBlindMeetingParticipantPrompts,
  stopBlindMeetingSessionPrompts,
} from "../meetingIcebreaker/blindMeetingHooks";
import {
  ApplicationDoc,
  MeetingDoc,
  addSafetyFlag,
  appendSystemMessage,
  applyRestriction,
  buildPublicProfile,
  createOpsReview,
  db,
  ensureDirectChat,
  ensureGroupChat,
  groupChatIdFor,
  incrementStats,
  loadCandidate,
  loadMeeting,
  readApplicationDoc,
  readMeetingDoc,
  loadOpenApplications,
  loadOpenDateKeys,
  loadParticipants,
  loadPolicy,
  loadRecentNoShowCount,
  loadSafetyFlags,
  pairKey,
  recordMetUsers,
  recordNoShow,
  reopenApplicationIfBoundTo,
  setApplication,
  setGroupChatWritable,
  syncGroupChatMembership,
  transitionMeetingStatus,
  updateParticipant,
} from "./store";
import {
  holdsChatMembership,
  BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
  BLIND_MEETING_COLLECTIONS,
  BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
  BLIND_MEETING_SCHEMA_VERSION,
  BLIND_MEETING_TYPE,
  DEPOSIT_STATUS_TO_APP,
  MEETING_STATUS_TO_APP,
  PARTICIPANT_STATUS_TO_APP,
  asStrArray,
  canTransitionParticipant,
  commonDateKeys,
  dateKeyOfSlotId,
  fallbackSlotIdFor,
  isDateKeyWithinWindow,
  isValidDateKey,
  isValidSlotId,
  normalizeDateKeys,
  readDateKeys,
  slotStartAt,
} from "./types";

// -----------------------------------------------------------------------------
// 매칭 실행
// -----------------------------------------------------------------------------

async function buildCandidatePool(
  applications: ApplicationDoc[],
  policy: BlindMeetingPolicy
): Promise<Candidate[]> {
  const now = Date.now();
  const candidates = await Promise.all(
    applications.map((application) =>
      loadCandidate(
        application.userId,
        policy,
        now,
        application.appliedAtMs,
        application.partyId,
        application.partyMemberIds
      )
    )
  );
  return candidates.filter((c): c is Candidate => c != null);
}

/** 파티 중 한 명이라도 무알코올을 요구하면 파티 전체를 같은 pool로 이동한다. */
function poolForAlcoholMode(pool: Candidate[], alcoholFree: boolean): Candidate[] {
  const byParty = new Map<string, Candidate[]>();
  for (const candidate of pool) {
    const partyId = candidate.partyId ?? `legacy:${candidate.userId}`;
    const members = byParty.get(partyId) ?? [];
    members.push(candidate);
    byParty.set(partyId, members);
  }
  const selected: Candidate[] = [];
  for (const members of byParty.values()) {
    const requiresAlcoholFree = members.some(requiresAlcoholFreeGroup);
    if (requiresAlcoholFree === alcoholFree) selected.push(...members);
  }
  return alcoholFree ? alcoholFreePool(selected) : standardPool(selected);
}

/**
 * 한 날짜에 대해 매칭을 시도한다.
 *
 * 세부 시간은 매칭 조건이 아니다. 여섯 명이 그 날짜에 모두 가능하고
 * 공통 가능 날짜가 최소 1개인 구성만 확정한다.
 *
 * 무알코올 후보군과 일반 후보군을 분리해서 각각 구성하고,
 * 후보가 부족하면 음주 사용자로 자동 대체하지 않는다.
 */
export async function runMatchingForDate(dateKey: string): Promise<string[]> {
  if (!isValidDateKey(dateKey)) return [];

  const policy = await loadPolicy();
  // 생활권 hard filter 의 rollout activation. OFF 면 생활권 조건만 비활성이고
  // DNA/가용일/차단/안전 등 나머지 조건은 전부 그대로 적용된다.
  const activation = await loadCampusLifeZoneActivation(db());
  if (activation.state === "unknown") {
    // 정책 상태를 모른 채 6인을 확정하지 않는다. OFF 로 가정하면 활성화된
    // 정책을 무시하고 cross-zone 미팅을 만들 수 있고, ON 으로 가정하면 준비
    // 단계에서 정상 신청자를 전부 떨어뜨린다. 이번 실행만 건너뛰고 다음
    // 스케줄에서 다시 시도한다 (신청은 그대로 열려 있다).
    logger.error("blindMeeting matching skipped: activation unknown", {
      code: "campusLifeZoneActivationReadFailure",
      campusLifeZoneActivationState: "unknown",
      dateKey,
    });
    return [];
  }
  const campusLifeZoneEnforced = activation.state === "enforced";
  const applications = await loadOpenApplications(dateKey);
  if (applications.length < 6) {
    await markStage(applications, "searchingCandidates");
    return [];
  }

  const pool = await buildCandidatePool(applications, policy);
  const createdMeetingIds: string[] = [];

  for (const alcoholFree of [true, false]) {
    const scopedPool = poolForAlcoholMode(pool, alcoholFree);
    if (scopedPool.length < BLIND_MEETING_GROUP_SIZE) continue;

    // 성비를 만족할 수 없으면 상위 점수 6명을 뽑는 것이 아니라
    // 아무 구성도 만들지 않는다. 실패 사유는 PII 없이 남긴다.
    const availability = describeGenderAvailability(
      scopedPool,
      dateKey,
      alcoholFree
    );
    if (availability.failure != null) {
      logger.info("blindMeeting matching skipped: unbalanced candidate pool", {
        code: availability.failure,
        dateKey,
        alcoholFree,
        eligibleMaleCount: availability.eligibleMaleCount,
        eligibleFemaleCount: availability.eligibleFemaleCount,
        scopedPoolSize: scopedPool.length,
      });
      continue;
    }

    let remaining = scopedPool;
    // 한 번의 실행에서 만들 수 있는 만큼 겹치지 않게 구성한다.
    for (let round = 0; round < 5; round++) {
      const proposal = bestGroup(
        remaining,
        dateKey,
        alcoholFree,
        CURRENT_MATCHING_CONFIG,
        campusLifeZoneEnforced
      );
      if (proposal == null) break;

      const used = new Set(proposal.key.split("|"));
      const meetingId = await createMeetingFromProposal(proposal);
      if (meetingId != null) {
        createdMeetingIds.push(meetingId);
      } else {
        // transaction 실패(이미 배정된 사용자가 pool에 남아 있는 경우 등)는
        // 해당 날짜의 매칭 전체를 중단시키면 안 된다. 그 구성만 버리고
        // 참여자를 pool에서 빼고 계속 시도한다.
        logger.info("blindMeeting proposal claim failed, retrying", {
          participants: used.size,
        });
      }

      remaining = remaining.filter((c) => !used.has(c.userId));
      if (remaining.length < BLIND_MEETING_GROUP_SIZE) break;
    }
  }

  // 아직 매칭되지 않은 신청자의 단계를 갱신한다.
  const stillOpen = await loadOpenApplications(dateKey);
  const stillOpenIds = new Set(stillOpen.map((a) => a.userId));
  const genderByUserId = new Map(pool.map((c) => [c.userId, c.gender]));
  const remainingByGender = splitByGender(
    pool.filter((c) => stillOpenIds.has(c.userId))
  );

  // 상대 성별이 3명을 못 채우면 이 신청자는 이 날짜에서 아무리 기다려도
  // 매칭될 수 없다. 계속 "후보를 찾는 중"으로 두면 영영 대기 화면에 머문다.
  // 조건 완화(날짜 추가 등)를 제안할 수 있도록 별도 단계로 표시한다.
  const blockedByOppositeGender: typeof stillOpen = [];
  const stillSearching: typeof stillOpen = [];
  for (const application of stillOpen) {
    const gender = genderByUserId.get(application.userId);
    if (gender == null) {
      // 후보로 hydrate 되지 않은 신청 (DNA/성별/안전 조건 미확인).
      // 성비 때문이라고 단정할 수 없으므로 기존 단계를 유지한다.
      stillSearching.push(application);
      continue;
    }
    const oppositeCount =
      gender === "male"
        ? remainingByGender.female.length
        : remainingByGender.male.length;
    if (oppositeCount < BLIND_MEETING_TEAM_SIZE) {
      blockedByOppositeGender.push(application);
    } else {
      stillSearching.push(application);
    }
  }

  if (blockedByOppositeGender.length > 0) {
    logger.info("blindMeeting applicants blocked by opposite gender shortage", {
      code: "INSUFFICIENT_BALANCED_CANDIDATES",
      dateKey,
      blockedCount: blockedByOppositeGender.length,
      remainingMaleCount: remainingByGender.male.length,
      remainingFemaleCount: remainingByGender.female.length,
    });
  }
  await markStage(blockedByOppositeGender, "insufficientCandidates");
  await markStage(
    stillSearching,
    stillSearching.length >= BLIND_MEETING_GROUP_SIZE
      ? "checkingCrossTeam"
      : "searchingCandidates"
  );

  return createdMeetingIds;
}

async function markStage(
  applications: ApplicationDoc[],
  stage: ApplicationDoc["stage"]
): Promise<void> {
  for (const application of applications) {
    if (application.stage === stage) continue;
    if (application.stage === "matched") continue;
    await setApplication(application.userId, { stage });
  }
}

/** 모든 열린 날짜에 대해 매칭을 시도한다 (스케줄러용) */
export async function runMatchingForAllDates(): Promise<string[]> {
  const dateKeys = await loadOpenDateKeys();
  const created: string[] = [];
  for (const dateKey of dateKeys) {
    const meetingIds = await runMatchingForDate(dateKey);
    created.push(...meetingIds);
  }
  return created;
}

/**
 * 제안된 6인 구성을 미팅 문서로 확정한다.
 *
 * 여섯 명의 신청 문서를 transaction으로 동시에 확보하므로
 * 같은 사용자가 두 미팅에 중복 배정되지 않는다.
 */
export async function createMeetingFromProposal(
  proposal: GroupProposal
): Promise<string | null> {
  const meetingRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc();
  const meetingId = meetingRef.id;

  const teamAIds = proposal.teamA.map((m) => m.userId);
  const teamBIds = proposal.teamB.map((m) => m.userId);
  const participantIds = [...teamAIds, ...teamBIds];
  const realPartyIds = [...new Set(
    [...proposal.teamA, ...proposal.teamB]
      .map((member) => member.partyId ?? `legacy:${member.userId}`)
      .filter((partyId) => partyId.length > 0 && !partyId.startsWith("legacy:"))
  )];

  // 최상위 불변식 1차 그물: 제안 자체가 3남 + 3녀 6인인지.
  // 알고리즘이 이미 보장하지만, 손상되거나 legacy 경로로 만들어진
  // 제안이 downstream 으로 새어 나가지 않도록 확정 직전에 다시 본다.
  const proposalBalance = validateBlindThreeVsThreeParticipants(
    [...proposal.teamA, ...proposal.teamB].map((m) => ({
      userId: m.userId,
      gender: m.gender,
    }))
  );
  // 총원 3남3녀뿐 아니라 각 팀이 단일 성별인지도 확인한다.
  // (teamA=[남,남,여], teamB=[여,여,남] 도 합계로는 3:3 이 된다.)
  const teamGenders = [proposal.teamA, proposal.teamB].map(
    (team) => new Set(team.map((m) => m.gender))
  );
  const teamsAreSingleGender =
    teamGenders.every((genders) => genders.size === 1) &&
    teamGenders[0].size === 1 &&
    teamGenders[1].size === 1 &&
    [...teamGenders[0]][0] !== [...teamGenders[1]][0];
  if (!teamsAreSingleGender) {
    logger.error("blindMeeting proposal rejected: teams are not single-gender", {
      code: "blindMeetingGenderInvariantViolated",
      dateKey: proposal.dateKey,
    });
    return null;
  }

  if (!proposalBalance.ok) {
    logger.error("blindMeeting proposal rejected: not 3M+3F", {
      code: "blindMeetingGenderInvariantViolated",
      violations: proposalBalance.violations,
      maleCount: proposalBalance.counts.male,
      femaleCount: proposalBalance.counts.female,
      unknownGenderCount: proposalBalance.counts.unknown,
      uniqueParticipantCount: proposalBalance.uniqueUserCount,
      dateKey: proposal.dateKey,
    });
    return null;
  }

  // 여섯 명이 공통으로 가능한 날짜가 없으면 확정하지 않는다.
  if (proposal.commonDateKeys.length === 0) {
    logger.warn("blindMeeting proposal rejected: no common date", {
      dateKey: proposal.dateKey,
    });
    return null;
  }

  // 최종 안전망: 여섯 명이 실제로 함께 만날 수 있는 공통 생활권이 있어야 한다.
  // 후보 생성 단계에서 이미 걸러지지만, 확정 직전에 다시 확인한다.
  // rollout activation 이 OFF 면 이 조건만 건너뛴다.
  const proposalZones = sharedCampusLifeZones([
    ...proposal.teamA,
    ...proposal.teamB,
  ]);
  // 최종 그물: 상태를 모르면 만들지 않는다 (확정은 되돌리기 어렵다).
  const creationActivation = await loadCampusLifeZoneActivation(db());
  if (creationActivation.state !== "off" && proposalZones.length === 0) {
    logger.warn("blindMeeting proposal rejected: no shared campus life zone", {
      dateKey: proposal.dateKey,
    });
    return null;
  }

  // 공개 프로필 스냅샷 (얼굴 사진 없음).
  // 미팅 문서와 같은 transaction 으로 써야 한다. 확정 직후 앱이 곧바로
  // 결과 화면을 열기 때문에, transaction 밖에서 순차 write 하면 그 사이에
  // 프로필이 비어 있는 미팅이 보이고 (그리고 중간에 실패하면 영영 비어 있고)
  // 이를 복구하는 스케줄도 없다.
  const publicProfiles = await Promise.all(
    participantIds.map((userId) => buildPublicProfile(userId))
  );

  const claimed = await db().runTransaction(async (tx) => {
    const refs = participantIds.map((userId) =>
      db().collection(BLIND_MEETING_COLLECTIONS.applications).doc(userId)
    );
    const userRefs = participantIds.map((userId) =>
      db().collection("users").doc(userId)
    );
    // transaction 안의 read 는 전부 write 이전에 끝내야 한다.
    const partyRefs = realPartyIds.map((partyId) =>
      db().collection(BLIND_MEETING_COLLECTIONS.parties).doc(partyId)
    );
    const [snaps, userSnaps, partySnaps] = await Promise.all([
      Promise.all(refs.map((ref) => tx.get(ref))),
      Promise.all(userRefs.map((ref) => tx.get(ref))),
      Promise.all(partyRefs.map((ref) => tx.get(ref))),
    ]);

    for (const snap of snaps) {
      const data = snap.data();
      if (!snap.exists || data?.open !== true) return false;
      if (typeof data?.meetingId === "string" && data.meetingId.length > 0) {
        return false;
      }
    }

    // 선결 파티는 ready roster 전체가 제안의 같은 편에 있어야 한다.
    for (let i = 0; i < partySnaps.length; i++) {
      const raw = partySnaps[i].data() ?? {};
      const members = asStrArray(raw.acceptedUserIds);
      if (!partySnaps[i].exists || raw.status !== "ready" || members.length < 1) {
        return false;
      }
      const entirelyInA = members.every((id) => teamAIds.includes(id));
      const entirelyInB = members.every((id) => teamBIds.includes(id));
      if ((!entirelyInA && !entirelyInB) || members.some((id) => !participantIds.includes(id))) {
        return false;
      }
    }

    // 최상위 불변식 2차 그물: 제안 snapshot 이 아니라 확정 시점의
    // authoritative users 문서를 다시 읽어 3남 + 3녀를 확인한다.
    // 제안 생성과 확정 사이에 성별/자격이 바뀌었을 수 있다.
    const authoritative = participantIds.map((userId, index) => ({
      userId,
      gender: readBlindMeetingGender(userSnaps[index].data()),
    }));
    const liveBalance = validateBlindThreeVsThreeParticipants(authoritative);
    if (!liveBalance.ok) {
      logger.error("blindMeeting claim rejected: live roster is not 3M+3F", {
        code: "blindMeetingGenderInvariantViolated",
        violations: liveBalance.violations,
        maleCount: liveBalance.counts.male,
        femaleCount: liveBalance.counts.female,
        unknownGenderCount: liveBalance.counts.unknown,
        dateKey: proposal.dateKey,
      });
      return false;
    }

    // 자격도 snapshot 이 아니라 확정 시점 값으로 다시 본다
    // (탈퇴·정지·학교 인증 해제는 되돌리기 어려운 확정을 막아야 한다).
    for (const userSnap of userSnaps) {
      const user = userSnap.data();
      if (
        !userSnap.exists ||
        user?.isStudentVerified !== true ||
        user?.isWithdrawn === true ||
        user?.loginDisabled === true
      ) {
        logger.info("blindMeeting claim rejected: participant no longer eligible", {
          code: "blindMeetingParticipantIneligibleAtClaim",
          dateKey: proposal.dateKey,
        });
        return false;
      }
    }

    tx.set(meetingRef, {
      meetingId,
      meetingType: BLIND_MEETING_TYPE,
      schemaVersion: BLIND_MEETING_SCHEMA_VERSION,
      algorithmVersion: proposal.algorithmVersion,
      status: MEETING_STATUS_TO_APP.awaiting_acceptance,
      serverStatus: "awaiting_acceptance",
      // 세부 시간은 단체 채팅방 약속잡기에서 정한다. 확정 전에는 비워둔다.
      slotId: null,
      matchedDateKey: proposal.dateKey,
      commonAvailableDateKeys: proposal.commonDateKeys,
      availabilityMode: BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
      scheduleSelectionVersion: BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
      isAlcoholFree: proposal.alcoholFree,
      teamAUserIds: teamAIds,
      teamBUserIds: teamBIds,
      participantIds,
      partyIds: realPartyIds,
      waitlistIds: [],
      groupChatId: null,
      venue: null,
      scheduledStartAt: null,
      fivePersonExceptionApproved: false,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });

    for (let i = 0; i < participantIds.length; i++) {
      const userId = participantIds[i];
      const team = teamAIds.includes(userId) ? "teamA" : "teamB";
      tx.set(
        meetingRef
          .collection(BLIND_MEETING_COLLECTIONS.participants)
          .doc(userId),
        {
          userId,
          team,
          role: "member",
          status: PARTICIPANT_STATUS_TO_APP.invited,
          serverStatus: "invited",
          depositStatus: DEPOSIT_STATUS_TO_APP.not_required,
          serverDepositStatus: "not_required",
          attendanceConfirmation24h: "pending",
          attendanceConfirmation3h: "pending",
          checkInStatus: "notOpen",
          checkOutStatus: "notOpen",
          isReplacement: false,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        }
      );

      // merge 필수. 통째로 쓰면 requestedDateKeys / appliedAt /
      // prefersAlcoholFree 가 사라지고, 이후 취소·거절로 신청이 다시 열려도
      // loadOpenApplications 의 날짜 쿼리에 영영 걸리지 않는다.
      tx.set(
        refs[i],
        {
          open: false,
          meetingId,
          status: PARTICIPANT_STATUS_TO_APP.invited,
          serverStatus: "invited",
          stage: "matched",
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    }


    for (let i = 0; i < partyRefs.length; i++) {
      tx.set(partyRefs[i], {
        status: "matched",
        meetingId,
        updatedAt: FieldValue.serverTimestamp(),
        matchedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    }

    // 내부 점수는 서버 전용 문서에만 저장한다.
    tx.set(
      meetingRef
        .collection(BLIND_MEETING_COLLECTIONS.matchingResult)
        .doc("summary"),
      {
        algorithmVersion: proposal.algorithmVersion,
        matchedDateKey: proposal.dateKey,
        commonAvailableDateKeys: proposal.commonDateKeys,
        isAlcoholFree: proposal.alcoholFree,
        internalTeamScores: {
          teamA: proposal.score.teamAInternal,
          teamB: proposal.score.teamBInternal,
        },
        crossTeamScore: proposal.score.crossTeamScore,
        minimumParticipantScore: proposal.score.minimumParticipantScore,
        finalGroupScore: proposal.score.finalGroupScore,
        participantOpponentScores: proposal.score.participantOpponentScores,
        constraintSummary: {
          alcoholFreeEnforced: proposal.alcoholFree,
          groupSize: participantIds.length,
        },
        createdAt: FieldValue.serverTimestamp(),
      }
    );

    for (let i = 0; i < participantIds.length; i++) {
      tx.set(
        meetingRef
          .collection(BLIND_MEETING_COLLECTIONS.publicProfiles)
          .doc(participantIds[i]),
        publicProfiles[i],
        { merge: true }
      );
    }

    return true;
  });

  if (!claimed) {
    logger.info("blindMeeting proposal claim failed (already matched)", {
      meetingId,
    });
    return null;
  }

  await notifyBlindMeeting({
    userIds: participantIds,
    meetingId,
    kind: "matched",
  });
  await notifyBlindMeeting({
    userIds: participantIds,
    meetingId,
    kind: "acceptance_request",
  });

  logger.info("blindMeeting created", {
    meetingId,
    commonDateCount: proposal.commonDateKeys.length,
    alcoholFree: proposal.alcoholFree,
    algorithmVersion: proposal.algorithmVersion,
  });

  return meetingId;
}

// -----------------------------------------------------------------------------
// 수락 / 확정 (블라인드 미팅은 보증금 없음)
// -----------------------------------------------------------------------------

export async function acceptInvitation(
  meetingId: string,
  userId: string
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  if (!meeting.participantIds.includes(userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }
  if (meeting.status !== "awaiting_acceptance") {
    throw new HttpsError(
      "failed-precondition",
      "지금은 수락할 수 있는 단계가 아니에요."
    );
  }

  await updateParticipant(meetingId, userId, {
    status: "accepted",
    extra: { acceptedAt: FieldValue.serverTimestamp() },
  });
  await setApplication(userId, { status: "accepted" });
  await advanceAfterAcceptance(meetingId);
}

export async function declineInvitation(
  meetingId: string,
  userId: string,
  reason: string | null
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  if (!meeting.participantIds.includes(userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }
  // 수락 대기/보증금 대기 단계까지만 거절할 수 있다.
  // 확정 이후에는 requestCancellation(취소 요청) 경로를 사용해야 한다.
  if (
    meeting.status !== "awaiting_acceptance" &&
    meeting.status !== "awaiting_deposits"
  ) {
    throw new HttpsError(
      "failed-precondition",
      "지금은 초대를 거절할 수 있는 단계가 아니에요. 참여가 어려우면 취소 요청을 이용해주세요."
    );
  }

  const party = await loadActivePartyForUser(userId);
  if (
    party &&
    party.status === "matched" &&
    party.meetingId === meetingId &&
    party.acceptedUserIds.length > 1
  ) {
    const withdrawnUserIds = await withdrawMatchedBlindMeetingParty({
      userId,
      partyId: party.partyId,
      meetingId,
      reason,
    });
    for (const vacantUserId of withdrawnUserIds) {
      await handleVacancy({ meetingId, vacantUserId, urgent: false });
    }
    return;
  }

  await updateParticipant(meetingId, userId, {
    status: "cancelled",
    extra: {
      cancelledAt: FieldValue.serverTimestamp(),
      cancelReason: reason,
    },
  });
  // 신청은 다시 열어 다음 미팅 후보로 둔다. 중복 거절이 도착했을 때
  // 이미 재오픈되어 다른 미팅에 재클레임된 신청은 덮어쓰지 않는다.
  await reopenApplicationIfBoundTo(userId, meetingId);
  await handleVacancy({ meetingId, vacantUserId: userId, urgent: false });
}

async function advanceAfterAcceptance(meetingId: string): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  const participants = await loadParticipants(meetingId);
  const seatCount = meeting.participantIds.length;
  const accepted = participants.filter(
    (p) => p.status === "accepted" || p.status === "confirmed"
  );
  if (accepted.length < seatCount) return;

  // 전원 수락이 끝나면 결제 단계를 만들지 않고 바로 단체 채팅을 연다.
  await advanceWithoutDeposit(meetingId);
}

/** 사용자가 화면에서 재시도할 수 있는 결제 없는 채팅방 복구 진입점. */
export async function openChatWithoutDeposit(
  meetingId: string,
  userId: string
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  if (!meeting.participantIds.includes(userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }
  const opened = await advanceWithoutDeposit(meetingId);
  if (!opened) {
    throw new HttpsError(
      "failed-precondition",
      "여섯 명의 참가 수락이 끝난 뒤 단체 채팅방을 열 수 있어요."
    );
  }
}

/**
 * 과거 클라이언트의 startBlindMeetingDeposit 호출과 이미 생성된
 * awaiting_deposits 문서를 안전하게 수습하기 위한 호환 경로.
 * 신규 블라인드 미팅에서는 이 함수가 결제 provider를 호출하지 않는다.
 */
export async function beginDeposit(
  meetingId: string,
  userId: string
): Promise<{
  status: string;
  provider: string;
  amount: number;
  checkoutUrl?: string;
  sandbox: boolean;
  message?: string;
}> {
  const meeting = await loadMeeting(meetingId);
  if (!meeting.participantIds.includes(userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }
  if (meeting.status === "awaiting_deposits") {
    const opened = await advanceWithoutDeposit(meetingId);
    if (!opened) {
      throw new HttpsError(
        "failed-precondition",
        "참가자 수락 상태를 확인한 뒤 단체 채팅방을 열 수 있어요."
      );
    }
    return {
      status: DEPOSIT_STATUS_TO_APP.not_required,
      provider: "none",
      amount: 0,
      sandbox: true,
      message: "블라인드 미팅은 보증금 없이 단체 채팅방이 열려요.",
    };
  }
  if (meeting.status === "awaiting_acceptance") {
    throw new HttpsError(
      "failed-precondition",
      "여섯 명의 참가 수락이 끝나면 보증금 없이 단체 채팅방이 열려요."
    );
  }

  throw new HttpsError(
    "failed-precondition",
    "이 블라인드 미팅은 이미 참가 확인 또는 채팅 단계예요."
  );
}

async function advanceWithoutDeposit(meetingId: string): Promise<boolean> {
  const meeting = await loadMeeting(meetingId);
  // 이전 버전의 awaiting_deposits 문서를 결제 없이 복구한다.
  if (
    meeting.status !== "awaiting_acceptance" &&
    meeting.status !== "awaiting_deposits" &&
    meeting.status !== "confirmed" &&
    meeting.status !== "chat_open"
  ) {
    return false;
  }
  const policy = await loadPolicy();
  const participants = await loadParticipants(meetingId);
  const seatCount = meeting.participantIds.length;
  const participantsById = new Map(
    participants.map((participant) => [participant.userId, participant])
  );
  const readyStatuses = new Set([
    "accepted",
    "deposit_pending",
    "confirmed",
  ]);
  const allParticipantsReady =
    seatCount > 0 &&
    meeting.participantIds.every((userId) => {
      const participant = participantsById.get(userId);
      return participant != null && readyStatuses.has(participant.status);
    });
  if (!allParticipantsReady) return false;

  const wasWaitingForConfirmation =
    meeting.status === "awaiting_acceptance" ||
    meeting.status === "awaiting_deposits";
  if (wasWaitingForConfirmation) {
    // FSM 전이를 먼저 통과시킨다. 동시 실행이면 최신 상태를 재확인한다.
    const confirmed = await transitionMeetingStatus(meetingId, "confirmed", {
      confirmedAt: FieldValue.serverTimestamp(),
    });
    if (!confirmed) {
      const latest = await loadMeeting(meetingId);
      if (latest.status !== "confirmed" && latest.status !== "chat_open") {
        return false;
      }
    }
  }

  for (const participant of participants) {
    const patch: {
      status: "confirmed";
      depositStatus?: "not_required";
      extra: Record<string, unknown>;
    } = {
      status: "confirmed",
      extra: { confirmedAt: FieldValue.serverTimestamp() },
    };
    // 미결제 pending/failed 상태만 not_required로 정리한다. 이미 결제된
    // 과거 참가자의 paid/refund 상태는 환불 정산을 위해 보존한다.
    if (
      participant.depositStatus === "pending" ||
      participant.depositStatus === "failed"
    ) {
      patch.depositStatus = "not_required";
    }
    await updateParticipant(meetingId, participant.userId, patch);
    await setApplication(participant.userId, { status: "confirmed" });
  }

  if (wasWaitingForConfirmation) {
    await notifyBlindMeeting({
      userIds: meeting.participantIds,
      meetingId,
      kind: "confirmed",
    });
  }

  const roomId = await ensureGroupChat({
    meetingId,
    memberIds: meeting.participantIds,
    isAlcoholFree: meeting.isAlcoholFree,
  });

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .set(
      {
        groupChatId: roomId,
        // 약속잡기 기한. 지나면 서버가 제출된 투표(없으면 기준 날짜)로 확정한다.
        // 이 값이 없으면 시간 미확정 상태로 무기한 방치된다.
        scheduleVoteDeadlineAt: Timestamp.fromMillis(
          Date.now() + policy.scheduleVoteWindowMs
        ),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  const current = await loadMeeting(meetingId);
  if (current.status === "confirmed") {
    await transitionMeetingStatus(meetingId, "chat_open");
  }
  await recordMetUsers(meetingId, meeting.participantIds);

  if (wasWaitingForConfirmation) {
    await notifyBlindMeeting({
      userIds: meeting.participantIds,
      meetingId,
      kind: "chat_created",
      deeplinkId: roomId,
      data: { roomId },
    });
    await notifyBlindMeeting({
      userIds: meeting.participantIds,
      meetingId,
      kind: "schedule_vote",
      deeplinkId: roomId,
      data: { roomId },
    });
  }
  return true;
}

/**
 * 확정된 미팅에 단체 채팅방을 열고 `chat_open` 으로 넘긴다.
 *
 * 확정 transaction 과 별개 단계라 중간에 실패하면 미팅이 `confirmed` 에서
 * 멈춘다 (채팅방도 약속잡기 기한도 없는 상태). scheduled 복구 tick 이
 * 되살릴 수 있도록 idempotent 하게 분리했다. `ensureGroupChat` 과
 * `transitionMeetingStatus` 모두 재실행에 안전하다.
 */
export async function openGroupChatForConfirmedMeeting(
  meetingId: string
): Promise<boolean> {
  const meeting = await loadMeeting(meetingId);
  if (meeting.status !== "confirmed") return false;
  const policy = await loadPolicy();

  const roomId = await ensureGroupChat({
    meetingId,
    memberIds: meeting.participantIds,
    isAlcoholFree: meeting.isAlcoholFree,
  });

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .set(
      {
        groupChatId: roomId,
        // 약속잡기 기한. 지나면 서버가 제출된 투표(없으면 기준 날짜)로 확정한다.
        // 이 값이 없으면 시간 미확정 상태로 무기한 방치된다.
        scheduleVoteDeadlineAt: Timestamp.fromMillis(
          Date.now() + policy.scheduleVoteWindowMs
        ),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  await transitionMeetingStatus(meetingId, "chat_open");
  await recordMetUsers(meetingId, meeting.participantIds);

  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "chat_created",
    deeplinkId: roomId,
    data: { roomId },
  });
  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "schedule_vote",
    deeplinkId: roomId,
    data: { roomId },
  });
  return true;
}


// -----------------------------------------------------------------------------
// 일정 확정
// -----------------------------------------------------------------------------

export async function voteSchedule(params: {
  meetingId: string;
  userId: string;
  preferredSlotIds: string[];
  preferredPlaceId: string | null;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  // 투표는 여섯 명이 공통으로 가능한 날짜 안에서만 유효하다.
  const allowedDates = new Set(
    meeting.commonAvailableDateKeys.length > 0
      ? meeting.commonAvailableDateKeys
      : [meeting.matchedDateKey].filter((d) => d.length > 0)
  );
  const preferredSlotIds = params.preferredSlotIds.filter((slotId) => {
    if (!isValidSlotId(slotId)) return false;
    const dateKey = dateKeyOfSlotId(slotId);
    return dateKey != null && allowedDates.has(dateKey);
  });
  if (preferredSlotIds.length === 0) {
    throw new HttpsError(
      "invalid-argument",
      "여섯 명이 모두 가능한 날짜 중에서 시간을 선택해주세요."
    );
  }

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .collection("scheduleVotes")
    .doc(params.userId)
    .set(
      {
        userId: params.userId,
        preferredSlotIds,
        preferredPlaceId: params.preferredPlaceId,
        votedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  await maybeConfirmSchedule(params.meetingId);
}

/**
 * 약속잡기 확정.
 *
 * 기본은 전원 투표 시 최다 득표로 확정한다. [force]가 true면 투표 기한이
 * 지난 경우이므로 제출된 투표만으로 확정하고, 투표가 하나도 없으면
 * 매칭 기준 날짜 + 기본 시간대로 fallback 한다.
 *
 * 어떤 경우에도 이미 지난 날짜로는 확정하지 않는다.
 */
async function maybeConfirmSchedule(
  meetingId: string,
  options: { force?: boolean } = {}
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  if (meeting.status !== "chat_open") return;

  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection("scheduleVotes")
    .get();
  if (!options.force && snap.size < meeting.participantIds.length) return;

  const slotTally = new Map<string, number>();
  const placeTally = new Map<string, number>();
  for (const doc of snap.docs) {
    for (const slotId of asStrArray(doc.data()?.preferredSlotIds)) {
      slotTally.set(slotId, (slotTally.get(slotId) ?? 0) + 1);
    }
    const placeId = doc.data()?.preferredPlaceId;
    if (typeof placeId === "string" && placeId.length > 0) {
      placeTally.set(placeId, (placeTally.get(placeId) ?? 0) + 1);
    }
  }

  // 동점이면 정렬된 key로 tie-break 하므로 결과는 deterministic 하다.
  const pickTop = (tally: Map<string, number>): string | null => {
    let best: string | null = null;
    let bestCount = -1;
    for (const key of [...tally.keys()].sort()) {
      const count = tally.get(key) ?? 0;
      if (count > bestCount) {
        best = key;
        bestCount = count;
      }
    }
    return best;
  };

  const now = Date.now();

  /// 아직 시작하지 않은 슬롯만 확정 대상으로 둔다.
  const isFutureSlot = (candidate: string): boolean => {
    if (!isValidSlotId(candidate)) return false;
    const start = slotStartAt(candidate);
    return start != null && start.getTime() > now;
  };

  // 득표 순으로 보면서 이미 지난 시간은 건너뛴다.
  const rankedSlots = [...slotTally.keys()]
    .sort()
    .sort((a, b) => (slotTally.get(b) ?? 0) - (slotTally.get(a) ?? 0));
  let slotId = rankedSlots.find(isFutureSlot) ?? null;

  // 투표가 없거나 전부 지난 시간이면 매칭 기준 날짜로 fallback 한다.
  if (slotId == null) {
    const fallbackDates = [
      meeting.matchedDateKey,
      ...meeting.commonAvailableDateKeys,
    ].filter((d) => d.length > 0);
    for (const dateKey of fallbackDates) {
      const candidate = fallbackSlotIdFor(dateKey);
      if (isFutureSlot(candidate)) {
        slotId = candidate;
        break;
      }
    }
  }

  // 후보 날짜가 모두 지났으면 확정할 수 없다. 미팅을 취소하고 전액 환급한다.
  if (slotId == null) {
    logger.warn("blindMeeting schedule expired without confirmation", {
      meetingId,
      voteCount: snap.size,
    });
    await cancelMeeting(meetingId, "schedule_window_expired");
    return;
  }

  const placeId = pickTop(placeTally);
  const startAt = slotStartAt(slotId);

  let venue: Record<string, unknown> | null = null;
  if (placeId) {
    const placeSnap = await db()
      .collection("place_catalog_items")
      .doc(placeId)
      .get();
    const place = placeSnap.data();
    if (place) {
      const category = typeof place.category === "string" ? place.category : null;
      venue = {
        placeId,
        name: typeof place.name === "string" ? place.name : placeId,
        address: typeof place.address === "string" ? place.address : null,
        category,
        lat: typeof place.lat === "number" ? place.lat : null,
        lng: typeof place.lng === "number" ? place.lng : null,
        // 무알코올 미팅은 주류 중심 장소를 권하지 않는다.
        alcoholFreeFriendly:
          category != null &&
          (category.trim().toLowerCase() !== "bar" && !/술|바|펍|포차/.test(category)),
      };
    }
  }

  // TOCTOU 방지: 일정 필드와 상태 전이를 단일 트랜잭션으로 묶는다.
  // 동시 실행에서 전이에 진 쪽은 일정 필드도 쓰지 않으므로,
  // 확정된 slotId는 항상 전이에 성공한 실행의 값이다.
  const moved = await transitionMeetingStatus(meetingId, "schedule_confirmed", {
    // 최종 확정 시간. 참가 신청 단계의 날짜 선택과 구분되는 값이다.
    slotId,
    confirmedDateKey: dateKeyOfSlotId(slotId),
    venue,
    scheduledStartAt: startAt ? Timestamp.fromDate(startAt) : null,
    scheduleConfirmedAt: FieldValue.serverTimestamp(),
  });
  if (!moved) return;

  if (meeting.groupChatId) {
    await appendSystemMessage(
      meeting.groupChatId,
      "약속이 확정됐어요. 시간과 장소를 확인해주세요."
    );
  }
  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "schedule_confirmed",
  });
}

// -----------------------------------------------------------------------------
// 참석 재확인
// -----------------------------------------------------------------------------

export async function confirmAttendance(params: {
  meetingId: string;
  userId: string;
  phase: "24h" | "3h";
  attending: boolean;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  const field =
    params.phase === "24h"
      ? "attendanceConfirmation24h"
      : "attendanceConfirmation3h";

  await updateParticipant(params.meetingId, params.userId, {
    extra: {
      [field]: params.attending ? "attending" : "unable",
      [`${field}RespondedAt`]: FieldValue.serverTimestamp(),
    },
  });

  if (!params.attending) {
    await requestCancellation({
      meetingId: params.meetingId,
      userId: params.userId,
      reason: `attendance_${params.phase}_unable`,
      emergency: false,
    });
  }
}

// -----------------------------------------------------------------------------
// 취소 / 대체 충원
// -----------------------------------------------------------------------------

export async function requestCancellation(params: {
  meetingId: string;
  userId: string;
  reason: string | null;
  emergency: boolean;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  await updateParticipant(params.meetingId, params.userId, {
    status: "cancel_requested",
    extra: {
      cancelRequestedAt: FieldValue.serverTimestamp(),
      cancelReason: params.reason,
      emergencyReviewRequested: params.emergency,
    },
  });

  const policy = await loadPolicy();
  // 시간 미확정 구간에서는 '긴급 취소'로 취급하지 않는다.
  const untilMeetingMs =
    meeting.scheduledStartAtMs == null
      ? null
      : meeting.scheduledStartAtMs - Date.now();
  const urgent =
    untilMeetingMs != null && untilMeetingMs < policy.lateCancellationBeforeMs;

  await handleVacancy({
    meetingId: params.meetingId,
    vacantUserId: params.userId,
    urgent,
    emergency: params.emergency,
    reason: params.reason,
  });
}

/**
 * 빈자리 대체 후보를 찾아 상위 후보에게 제안한다.
 *
 * 임의 대타는 허용되지 않으며, 모든 대체 후보는 학교 인증과
 * hard constraint 검증을 통과해야 한다. 긴급 상황에서도 완화하지 않는다.
 */
export async function handleVacancy(params: {
  meetingId: string;
  vacantUserId: string;
  urgent: boolean;
  emergency?: boolean;
  reason?: string | null;
}): Promise<number> {
  const meeting = await loadMeeting(params.meetingId);
  const policy = await loadPolicy();

  const seatIds = meeting.participantIds;
  // 확정된 시간이 있으면 그 날짜, 없으면 매칭 기준 날짜로 대체 후보를 찾는다.
  const vacancyDateKey =
    dateKeyOfSlotId(meeting.slotId) ?? meeting.matchedDateKey;
  const candidates = await buildCandidatePool(
    await loadOpenApplications(vacancyDateKey),
    policy
  );

  const seatCandidates = await Promise.all(
    seatIds.map((userId) =>
      loadCandidate(userId, policy, Date.now(), Date.now())
    )
  );
  const seatMap = new Map<string, Candidate>();
  for (const candidate of seatCandidates) {
    if (candidate) seatMap.set(candidate.userId, candidate);
  }

  const teamA = meeting.teamAUserIds
    .map((id) => seatMap.get(id))
    .filter((c): c is Candidate => c != null);
  const teamB = meeting.teamBUserIds
    .map((id) => seatMap.get(id))
    .filter((c): c is Candidate => c != null);

  if (teamA.length !== 3 || teamB.length !== 3) {
    logger.warn("blindMeeting vacancy: incomplete seat snapshot", {
      meetingId: params.meetingId,
    });
    return 0;
  }

  const baseline = groupScore(
    teamA,
    teamB,
    CURRENT_MATCHING_CONFIG,
    meeting.isAlcoholFree
  ).finalGroupScore;

  const eligibleCandidates = candidates.filter(
    (c) => !seatIds.includes(c.userId)
  );

  const ranked = rankReplacements({
    teamA,
    teamB,
    vacantUserId: params.vacantUserId,
    candidates: eligibleCandidates,
    baselineFinalGroupScore: baseline,
    dateKey: vacancyDateKey,
    alcoholFree: meeting.isAlcoholFree,
    urgent: params.urgent,
    limit: policy.replacementOfferWaveSize,
    // 대체 참가자 제안도 상태를 모르면 생활권을 강제한다 (제안은 보류 가능).
    campusLifeZoneEnforced: await loadCampusLifeZoneEnforced(db(), {
      unknownAs: "enforced",
    }),
  });

  // 이탈자 상태 표시는 FSM이 허용하는 경우에만 한다. 초대 거절자는 이미
  // cancelled(terminal)이므로 replacement_pending으로 되돌리지 않는다 —
  // 좌석 대체 탐색 자체는 상태와 무관하게 계속 진행한다.
  const vacancyParticipants = await loadParticipants(params.meetingId);
  const vacantParticipant = vacancyParticipants.find(
    (participant) => participant.userId === params.vacantUserId
  );
  if (
    vacantParticipant != null &&
    canTransitionParticipant(vacantParticipant.status, "replacement_pending")
  ) {
    await updateParticipant(params.meetingId, params.vacantUserId, {
      status: "replacement_pending",
    });
  }

  if (ranked.length === 0) {
    await finalizeCancellationWithoutReplacement({
      meetingId: params.meetingId,
      userId: params.vacantUserId,
      emergency: params.emergency === true,
      reason: params.reason ?? null,
    });
    return 0;
  }

  const expiresAt = Timestamp.fromMillis(
    Date.now() + policy.replacementOfferExpiryMs
  );

  for (const evaluation of ranked) {
    const offerRef = db()
      .collection(BLIND_MEETING_COLLECTIONS.replacementOffers)
      .doc(`${params.meetingId}_${params.vacantUserId}_${evaluation.candidate.userId}`);
    await offerRef.set(
      {
        replacementOfferId: offerRef.id,
        meetingId: params.meetingId,
        vacantParticipantId: params.vacantUserId,
        candidateUid: evaluation.candidate.userId,
        offerStatus: "offered",
        urgent: params.urgent,
        qualityRatio: evaluation.qualityRatio,
        expiresAt,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    await notifyBlindMeeting({
      userIds: [evaluation.candidate.userId],
      meetingId: params.meetingId,
      kind: "replacement_offer",
      deeplinkId: offerRef.id,
      dedupeSuffix: params.vacantUserId,
      data: { offerId: offerRef.id },
    });
  }

  return ranked.length;
}

/**
 * 대체 제안 수락. 동시 수락은 transaction으로 한 명만 확정한다.
 */
export async function respondReplacementOffer(params: {
  offerId: string;
  userId: string;
  accept: boolean;
}): Promise<{ ok: boolean; code?: string; meetingId?: string }> {
  const offerRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.replacementOffers)
    .doc(params.offerId);
  const offerSnap = await offerRef.get();
  const offer = offerSnap.data();
  if (!offerSnap.exists || !offer) return { ok: false, code: "not_found" };
  if (offer.candidateUid !== params.userId) {
    throw new HttpsError("permission-denied", "본인에게 온 제안만 응답할 수 있어요.");
  }

  if (!params.accept) {
    await offerRef.set(
      {
        offerStatus: "declined",
        respondedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    return { ok: true, code: "declined" };
  }

  const meetingId = String(offer.meetingId ?? "");
  const vacantUserId = String(offer.vacantParticipantId ?? "");
  if (!meetingId || !vacantUserId) return { ok: false, code: "invalid_offer" };

  const meetingRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId);

  const result = await db().runTransaction(async (tx) => {
    const freshOffer = await tx.get(offerRef);
    const offerData = freshOffer.data();
    if (!freshOffer.exists || offerData?.offerStatus !== "offered") {
      return { ok: false as const, code: "already_resolved" as const };
    }
    const expiresAt = offerData?.expiresAt;
    if (expiresAt instanceof Timestamp && expiresAt.toMillis() < Date.now()) {
      tx.set(offerRef, { offerStatus: "expired" }, { merge: true });
      return { ok: false as const, code: "expired" as const };
    }

    const meetingSnap = await tx.get(meetingRef);
    const meetingData = meetingSnap.data();
    if (!meetingSnap.exists || !meetingData) {
      return { ok: false as const, code: "meeting_missing" as const };
    }

    // 활성 단계에서만 대체 합류를 허용한다. 취소·완료·보관된 미팅의
    // 참가자 명단은 교체하지 않는다 (알 수 없는 상태 포함 fail-closed).
    const meetingServerStatus = String(
      meetingData.serverStatus ?? meetingData.status ?? ""
    );
    const replacementOpenStatuses = new Set([
      "awaiting_acceptance",
      "awaiting_deposits",
      "confirmed",
      "chat_open",
      "schedule_confirmed",
      "checkin_open",
    ]);
    if (!replacementOpenStatuses.has(meetingServerStatus)) {
      tx.set(
        offerRef,
        { offerStatus: "expired", updatedAt: FieldValue.serverTimestamp() },
        { merge: true }
      );
      return { ok: false as const, code: "meeting_closed" as const };
    }

    const participantIds = asStrArray(meetingData.participantIds);
    if (!participantIds.includes(vacantUserId)) {
      tx.set(offerRef, { offerStatus: "expired" }, { merge: true });
      return { ok: false as const, code: "seat_taken" as const };
    }
    if (participantIds.includes(params.userId)) {
      return { ok: false as const, code: "already_member" as const };
    }

    const applicationRef = db()
      .collection(BLIND_MEETING_COLLECTIONS.applications)
      .doc(params.userId);
    const joinerParticipantRef = meetingRef
      .collection(BLIND_MEETING_COLLECTIONS.participants)
      .doc(params.userId);
    const [applicationSnap, joinerParticipantSnap, joinerUserSnap, vacantUserSnap] =
      await Promise.all([
        tx.get(applicationRef),
        tx.get(joinerParticipantRef),
        tx.get(db().collection("users").doc(params.userId)),
        tx.get(db().collection("users").doc(vacantUserId)),
      ]);
    if (applicationSnap.data()?.open !== true) {
      return { ok: false as const, code: "not_available" as const };
    }

    // 매칭 확정 경로(createMeetingFromProposal)와 같은 claim 가드.
    // 이게 없으면 이미 다른 미팅에 묶인 신청서를 그대로 끌어와
    // 같은 사용자가 두 개의 active 미팅에 동시에 들어갈 수 있다.
    const joinerMeetingId = applicationSnap.data()?.meetingId;
    if (typeof joinerMeetingId === "string" && joinerMeetingId.length > 0) {
      return { ok: false as const, code: "not_available" as const };
    }
    const joinerApplicationStatus = String(
      applicationSnap.data()?.serverStatus ?? ""
    );
    if (
      joinerApplicationStatus !== "applied" &&
      joinerApplicationStatus !== "waitlisted"
    ) {
      return { ok: false as const, code: "not_available" as const };
    }

    // 이미 이 미팅에서 terminal 로 끝난 참가자 문서를 되살리지 않는다
    // (replaced 로 빠졌던 사용자가 같은 미팅에 다시 들어오는 경로).
    const joinerPriorStatus = String(
      joinerParticipantSnap.data()?.serverStatus ?? ""
    );
    if (
      joinerPriorStatus === "replaced" ||
      joinerPriorStatus === "cancelled" ||
      joinerPriorStatus === "no_show"
    ) {
      return { ok: false as const, code: "already_member" as const };
    }

    // 최상위 불변식: 대체 후에도 3남 + 3녀여야 한다.
    // 빈자리와 다른 성별이 들어오면 4M2F 가 되므로 거부한다.
    const joinerGender = readBlindMeetingGender(joinerUserSnap.data());
    const vacantGender = readBlindMeetingGender(vacantUserSnap.data());
    if (joinerGender == null || joinerGender !== vacantGender) {
      logger.info("blindMeeting replacement rejected: gender mismatch", {
        code: "blindMeetingGenderInvariantViolated",
        meetingId,
        hasJoinerGender: joinerGender != null,
        hasVacantGender: vacantGender != null,
      });
      return { ok: false as const, code: "not_available" as const };
    }

    const teamA = asStrArray(meetingData.teamAUserIds);
    const teamB = asStrArray(meetingData.teamBUserIds);
    const team = teamA.includes(vacantUserId) ? "teamA" : "teamB";
    const nextTeamA = teamA.map((id) =>
      id === vacantUserId ? params.userId : id
    );
    const nextTeamB = teamB.map((id) =>
      id === vacantUserId ? params.userId : id
    );
    const nextParticipants = participantIds.map((id) =>
      id === vacantUserId ? params.userId : id
    );

    // 대체 참가자가 들어오면 여섯 명의 공통 가능 날짜가 달라진다.
    // 갱신하지 않으면 새 참가자가 불가능한 날짜로 약속이 확정될 수 있다.
    // (교집합은 결합법칙이 성립하므로 기존 공통 날짜 ∩ 신규 참가자 날짜로 충분하다)
    const existingCommon = readDateKeys(
      meetingData.commonAvailableDateKeys,
      meetingData.candidateSlotIds
    );
    const joinerDates = readDateKeys(
      applicationSnap.data()?.requestedDateKeys,
      applicationSnap.data()?.requestedSlotIds
    );
    const nextCommon = commonDateKeys([existingCommon, joinerDates]);

    tx.set(
      meetingRef,
      {
        teamAUserIds: nextTeamA,
        teamBUserIds: nextTeamB,
        participantIds: nextParticipants,
        // 교집합이 비면(있을 수 없는 상태) 기존 값을 유지해 약속잡기를 막지 않는다.
        ...(nextCommon.length > 0
          ? { commonAvailableDateKeys: nextCommon }
          : {}),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    tx.set(
      meetingRef
        .collection(BLIND_MEETING_COLLECTIONS.participants)
        .doc(params.userId),
      {
        userId: params.userId,
        team,
        role: "member",
        status: PARTICIPANT_STATUS_TO_APP.confirmed,
        serverStatus: "confirmed",
        depositStatus: DEPOSIT_STATUS_TO_APP.not_required,
        serverDepositStatus: "not_required",
        attendanceConfirmation24h: "attending",
        attendanceConfirmation3h: "pending",
        checkInStatus: "notOpen",
        checkOutStatus: "notOpen",
        isReplacement: true,
        replacedUserId: vacantUserId,
        joinedChatAt: FieldValue.serverTimestamp(),
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    tx.set(
      meetingRef
        .collection(BLIND_MEETING_COLLECTIONS.participants)
        .doc(vacantUserId),
      {
        status: PARTICIPANT_STATUS_TO_APP.replaced,
        serverStatus: "replaced",
        replacementUserId: params.userId,
        replacedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    tx.set(offerRef, {
      offerStatus: "accepted",
      acceptedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });

    tx.set(
      applicationRef,
      {
        open: false,
        meetingId,
        status: PARTICIPANT_STATUS_TO_APP.confirmed,
        serverStatus: "confirmed",
        stage: "matched",
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    return { ok: true as const, meetingId };
  });

  if (!result.ok) return result;

  // 나머지 제안 자동 만료
  const siblings = await db()
    .collection(BLIND_MEETING_COLLECTIONS.replacementOffers)
    .where("meetingId", "==", meetingId)
    .where("vacantParticipantId", "==", vacantUserId)
    .where("offerStatus", "==", "offered")
    .get();
  const batch = db().batch();
  for (const doc of siblings.docs) {
    batch.set(
      doc.ref,
      { offerStatus: "expired", updatedAt: FieldValue.serverTimestamp() },
      { merge: true }
    );
  }
  await batch.commit();

  // 채팅 멤버십 갱신: 기존 참가자 즉시 제거, 대체 참가자 추가
  await syncGroupChatMembership(meetingId);
  const meeting = await loadMeeting(meetingId);
  const profile = await buildPublicProfile(params.userId);
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.publicProfiles)
    .doc(params.userId)
    .set(profile, { merge: true });

  if (meeting.groupChatId) {
    // 취소 이유는 공개하지 않는다.
    await appendSystemMessage(
      meeting.groupChatId,
      "참가자 한 분의 일정 변경으로 새로운 멤버가 합류했어요.\n미팅 시간과 장소는 그대로 진행됩니다."
    );
  }

  await notifyBlindMeeting({
    userIds: [params.userId],
    meetingId,
    kind: "replacement_confirmed",
  });

  // 취소자 환급 처리 (대체 성공)
  await settleCancellation({
    meetingId,
    userId: vacantUserId,
    replacementFound: true,
    emergency: false,
  });

  return result;
}

async function finalizeCancellationWithoutReplacement(params: {
  meetingId: string;
  userId: string;
  emergency: boolean;
  reason: string | null;
}): Promise<void> {
  await settleCancellation({
    meetingId: params.meetingId,
    userId: params.userId,
    replacementFound: false,
    emergency: params.emergency,
  });

  const meeting = await loadMeeting(params.meetingId);
  const remaining = meeting.participantIds.filter((id) => id !== params.userId);

  // 미팅 시작 전이면 다섯 명 진행 여부를 물어본다.
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .set(
      {
        fivePersonVoteOpen: true,
        fivePersonVacantUserId: params.userId,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  if (meeting.groupChatId) {
    await appendSystemMessage(
      meeting.groupChatId,
      "참가자 한 분이 참석하지 못했어요.\n다섯 명이서 계속 진행할지 함께 결정해주세요."
    );
  }

  await notifyBlindMeeting({
    userIds: remaining,
    meetingId: params.meetingId,
    kind: "cancelled",
    bodyOverride:
      "참가자 한 분이 참석하지 못했어요. 다섯 명으로 진행할지 선택해주세요.",
    dedupeSuffix: params.userId,
  });
}

/** 취소자 환급/제재 처리 */
export async function settleCancellation(params: {
  meetingId: string;
  userId: string;
  replacementFound: boolean;
  emergency: boolean;
  isNoShowWithoutContact?: boolean;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  const policy = await loadPolicy();
  // null = 약속잡기 미완료로 시작 시각이 없는 구간 (전액 환급 대상)
  const untilMeetingMs =
    meeting.scheduledStartAtMs == null
      ? null
      : meeting.scheduledStartAtMs - Date.now();

  const decision = resolveCancellation({
    policy,
    untilMeetingMs,
    replacementFound: params.replacementFound,
    isNoShowWithoutContact: params.isNoShowWithoutContact,
    emergencyReviewRequested: params.emergency,
  });

  if (decision.outcome === "ops_review") {
    await createOpsReview({
      meetingId: params.meetingId,
      userId: params.userId,
      kind: "emergency_cancellation",
      detail: { untilMeetingMs },
    });
    await updateParticipant(params.meetingId, params.userId, {
      depositStatus: "refund_pending",
    });
    return;
  }

  const refundAmount = refundAmountFor(
    policy.depositAmount,
    decision.refundBasisPoints
  );
  const refund = await refundDeposit({
    meetingId: params.meetingId,
    userId: params.userId,
    depositAmount: policy.depositAmount,
    refundAmount,
    reason: decision.outcome,
  });

  // 대체 성공 경로에서는 이탈자가 이미 transaction 안에서 `replaced` 로
  // 확정돼 있다. `replaced` 는 terminal 이라 FSM 이 cancelled 로의 전이를
  // 거부하므로, 여기서 상태를 다시 밀면 환급을 끝낸 뒤 예외가 나서
  // 신청서 분리·알림·통계가 전부 건너뛰어진다 (이탈자가 영구히 잠긴다).
  // 이미 terminal 이면 동반 필드만 갱신한다.
  const settlingParticipant = (
    await loadParticipants(params.meetingId)
  ).find((p) => p.userId === params.userId);
  const alreadySettled =
    settlingParticipant?.status === "replaced" ||
    settlingParticipant?.status === "cancelled" ||
    settlingParticipant?.status === "no_show";

  await updateParticipant(params.meetingId, params.userId, {
    status: alreadySettled
      ? undefined
      : params.isNoShowWithoutContact
        ? "no_show"
        : "cancelled",
    depositStatus: refund.status,
    extra: {
      cancelledAt: FieldValue.serverTimestamp(),
      refundOutcome: decision.outcome,
      refundedAmount: refund.refundedAmount,
    },
  });


  // 미팅을 떠난 사람은 단체 채팅방에서도 빠져야 한다.
  // 대체 경로는 respondReplacementOffer 에서 이미 sync 하지만, 대체 없이
  // 취소로 끝나는 경로에는 sync 가 없어서 이탈자가 남은 다섯 명의 대화를
  // 계속 읽고 쓸 수 있었다. holdsChatMembership 이 cancelled/replaced/no_show
  // 를 제외하므로 두 경로가 같은 정의를 공유한다.
  //
  // 최종 노쇼도 여기서 빠진다. 나타나지 않은 사람이 남은 참가자들의 대화를
  // 계속 읽고 쓸 수 있으면 안 된다 (CHAT_MEMBERSHIP_STATUSES 주석 참고).
  //
  // 이 단계 실패가 아래 신청서 분리·제재·통계를 막으면 안 된다.
  // 사용자가 잠기는 쪽이 채팅방이 늦게 정리되는 쪽보다 훨씬 나쁘다.
  try {
    await syncGroupChatMembership(params.meetingId);
  } catch (error) {
    logger.error("blindMeeting chat membership sync failed", {
      meetingId: params.meetingId,
      error,
    });
  }

  // 노쇼·취소·교체된 참가자에게는 아이스브레이킹 알림을 보내지 않는다.
  await stopBlindMeetingParticipantPrompts({
    meetingId: params.meetingId,
    userId: params.userId,
    reason: params.isNoShowWithoutContact
      ? "participant_no_show"
      : "participant_left",
  });

  // 신청서가 이미 이 미팅에서 분리됐다면(예: 초대 거절로 재오픈된 신청)
  // 뒤늦은 정산이 새 신청을 cancelled로 덮어쓰지 않는다.
  const settledApplicationSnap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(params.userId)
    .get();
  const settledApplicationMeetingId = String(
    settledApplicationSnap.data()?.meetingId ?? ""
  ).trim();
  if (settledApplicationMeetingId === params.meetingId) {
    await setApplication(params.userId, {
      status: params.isNoShowWithoutContact ? "no_show" : "cancelled",
      stage: "cancelled",
      open: false,
      meetingId: null,
    });
  } else {
    logger.info("blindMeeting settle skipped detached application", {
      meetingId: params.meetingId,
    });
  }

  if (decision.appliesRestriction) {
    await recordNoShow(params.userId, params.meetingId);
    const count = await loadRecentNoShowCount(
      params.userId,
      policy.noShowLookbackMs
    );
    const sanction = resolveNoShowSanction(policy, count);
    await applyRestriction({
      userId: params.userId,
      days: sanction.restrictedDays,
      reason: "no_show",
      requiresOpsReview: sanction.requiresOpsReview,
    });
    await incrementStats(params.userId, { noShowCount: 1 });
  } else {
    await incrementStats(params.userId, {
      earlyCancellationCount: 1,
    });
  }

  if (refund.refundedAmount > 0) {
    await notifyBlindMeeting({
      userIds: [params.userId],
      meetingId: params.meetingId,
      kind: "refunded",
      bodyOverride: `보증금 ${refund.refundedAmount}원이 환급 처리됐어요.`,
    });
  }
}

/** 다섯 명 진행 투표 */
export async function voteFivePersonException(params: {
  meetingId: string;
  userId: string;
  agree: boolean;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  // participantIds 는 좌석 명부라 노쇼·취소된 사람도 그대로 남는다.
  // 그것만 확인하면 결원을 만든 당사자가 "거부"를 던져 남은 다섯 명의
  // 진행 결정을 뒤집고 미팅을 취소시킬 수 있다 (아래 veto 로직 참고).
  // 투표권은 지금도 자리를 지키고 있는 참가자에게만 있다.
  const voters = await loadParticipants(params.meetingId);
  const voter = voters.find((p) => p.userId === params.userId);
  if (voter == null || !holdsChatMembership(voter.status)) {
    throw new HttpsError(
      "permission-denied",
      "이 미팅의 참가자가 아니에요."
    );
  }

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .collection("fivePersonVotes")
    .doc(params.userId)
    .set(
      { userId: params.userId, agree: params.agree, votedAt: FieldValue.serverTimestamp() },
      { merge: true }
    );

  const votes = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .collection("fivePersonVotes")
    .get();

  const participants = await loadParticipants(params.meetingId);
  const active = participants.filter(
    (p) => p.status === "confirmed" || p.status === "attended"
  );

  // 한 명이라도 거부하면 미팅을 취소하고 우선 재매칭을 제공한다.
  if (votes.docs.some((doc) => doc.data()?.agree === false)) {
    await cancelMeeting(params.meetingId, "five_person_rejected");
    return;
  }

  if (votes.size < active.length) return;

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .set(
      {
        fivePersonExceptionApproved: true,
        fivePersonVoteOpen: false,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  if (meeting.groupChatId) {
    await appendSystemMessage(
      meeting.groupChatId,
      "다섯 명이서 미팅을 계속 진행해요. 시간과 장소는 그대로예요."
    );
  }
}

export async function cancelMeeting(
  meetingId: string,
  reason: string
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  const participants = await loadParticipants(meetingId);
  const policy = await loadPolicy();

  for (const participant of participants) {
    // terminal 상태(replaced/cancelled/completed/no_show/restricted 등)는
    // FSM상 cancelled 전이가 불가능하므로 건너뛴다.
    if (!canTransitionParticipant(participant.status, "cancelled")) {
      continue;
    }
    // 정상 참석 예정자에게는 전액 환급 + 다음 미팅 우선권
    const refund = await refundDeposit({
      meetingId,
      userId: participant.userId,
      depositAmount: policy.depositAmount,
      refundAmount: policy.depositAmount,
      reason: `meeting_cancelled:${reason}`,
    });
    await updateParticipant(meetingId, participant.userId, {
      status: "cancelled",
      depositStatus: refund.status,
    });
    // 이 미팅에 아직 귀속된 신청만 재오픈한다 (먼저 거절해 다른 미팅에
    // 재클레임된 참가자의 새 link 를 취소 정리가 덮어쓰지 않도록).
    await reopenApplicationIfBoundTo(participant.userId, meetingId, {
      priorityRematch: true,
    });
  }

  await transitionMeetingStatus(meetingId, "cancelled", {
    cancelledAt: FieldValue.serverTimestamp(),
    cancelReason: reason,
  });

  // 미팅이 취소되면 예약된 아이스브레이킹 알림도 모두 취소한다.
  await stopBlindMeetingSessionPrompts({
    meetingId,
    reason: "meeting_cancelled",
  });

  if (meeting.groupChatId) {
    await setGroupChatWritable(meeting.groupChatId, false, "read_only");
  }

  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "cancelled",
    dedupeSuffix: reason,
  });
}

// -----------------------------------------------------------------------------
// 안전도장 / 만족도
// -----------------------------------------------------------------------------

export async function markSafetyStamp(params: {
  meetingId: string;
  userId: string;
  phase: "meetup" | "goodbye";
  verification: Record<string, unknown> | null;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  // 안전도장 횟수는 다른 참가자에게 보이는 공개 신뢰 지표
  // (publicProfile.safetyStampSummary) 로 이어진다. 같은 도장을 다시 보내도
  // 카운터가 두 번 오르지 않도록 현재 참가자 문서를 먼저 읽는다.
  const stampParticipant = (await loadParticipants(params.meetingId)).find(
    (p) => p.userId === params.userId
  );
  if (stampParticipant == null) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  // 최종 노쇼 판정을 받은 참가자는 더 이상 이 미팅의 활성 참가자가 아니다.
  // FSM 에서 no_show -> attended edge 도 제거했지만, 도장 경로에서 명시적으로
  // 막아 두어야 실패 사유가 사용자에게 정확히 전달된다.
  if (
    stampParticipant.status === "no_show" ||
    stampParticipant.status === "cancelled" ||
    stampParticipant.status === "replaced"
  ) {
    throw new HttpsError(
      "permission-denied",
      "이 미팅의 참가자가 아니에요."
    );
  }

  if (params.phase === "meetup") {
    if (
      meeting.status !== "schedule_confirmed" &&
      meeting.status !== "checkin_open" &&
      meeting.status !== "in_progress"
    ) {
      throw new HttpsError(
        "failed-precondition",
        "지금은 도착 안전도장을 찍을 수 없어요."
      );
    }
    await updateParticipant(params.meetingId, params.userId, {
      status: "attended",
      extra: {
        checkInStatus: "completed",
        checkInAt: FieldValue.serverTimestamp(),
        checkInVerification: params.verification,
      },
    });
    // 재전송이면 상태만 그대로 두고 카운터는 올리지 않는다.
    if (!stampParticipant.checkedIn) {
      await incrementStats(params.userId, { checkinCompleted: 1 });
    }
    await transitionMeetingStatus(params.meetingId, "checkin_open");
    await maybeStartMeeting(params.meetingId);
    // 시작 안전도장 완료 → 15분 뒤부터 아이스브레이킹 룰렛 알림
    await onBlindMeetingCheckIn({
      meetingId: params.meetingId,
      userId: params.userId,
      isAlcoholFree: meeting.isAlcoholFree,
    });
    return;
  }

  // 종료 도장은 도착 도장 이후에만 의미가 있다. 선행 조건이 없으면
  // 미팅 며칠 전에도 checkOut 을 완료로 표시해 본인 알림을 영구히 끄고
  // 실제로 만나지 않은 미팅을 완료처럼 보이게 만들 수 있다.
  if (!stampParticipant.checkedIn) {
    throw new HttpsError(
      "failed-precondition",
      "도착 안전도장을 먼저 찍어주세요."
    );
  }
  if (meeting.status !== "checkin_open" && meeting.status !== "in_progress") {
    throw new HttpsError(
      "failed-precondition",
      "지금은 종료 안전도장을 찍을 수 없어요."
    );
  }

  await updateParticipant(params.meetingId, params.userId, {
    extra: {
      checkOutStatus: "completed",
      checkOutAt: FieldValue.serverTimestamp(),
      checkOutVerification: params.verification,
    },
  });
  if (!stampParticipant.checkedOut) {
    await incrementStats(params.userId, { checkoutCompleted: 1 });
  }
  // 종료 안전도장 완료 → 해당 참가자 반복 알림 즉시 종료
  await onBlindMeetingCheckOut({
    meetingId: params.meetingId,
    userId: params.userId,
  });
  await maybeCompleteMeeting(params.meetingId);
}

async function maybeStartMeeting(meetingId: string): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  const participants = await loadParticipants(meetingId);
  const expected = meeting.fivePersonExceptionApproved
    ? meeting.participantIds.length - 1
    : meeting.participantIds.length;
  const checkedIn = participants.filter((p) => p.checkedIn).length;
  if (checkedIn < expected) return;
  await transitionMeetingStatus(meetingId, "in_progress", {
    startedAt: FieldValue.serverTimestamp(),
  });
}

async function maybeCompleteMeeting(meetingId: string): Promise<void> {
  const participants = await loadParticipants(meetingId);
  const attended = participants.filter((p) => p.checkedIn);
  if (attended.length === 0) return;
  if (attended.some((p) => !p.checkedOut)) return;

  const moved = await transitionMeetingStatus(meetingId, "completed", {
    completedAt: FieldValue.serverTimestamp(),
  });
  if (!moved) return;

  // 미팅 전체가 종료됐으면 남아 있는 아이스브레이킹 알림도 모두 정리한다.
  await stopBlindMeetingSessionPrompts({
    meetingId,
    reason: "meeting_completed",
  });

  const policy = await loadPolicy();
  for (const participant of attended) {
    const refund = await refundDeposit({
      meetingId,
      userId: participant.userId,
      depositAmount: policy.depositAmount,
      refundAmount: policy.depositAmount,
      reason: "attended_and_checked_out",
    });
    await updateParticipant(meetingId, participant.userId, {
      status: "completed",
      depositStatus: refund.status,
    });
    await incrementStats(participant.userId, { completedMeetings: 1 });
    await setApplication(participant.userId, {
      status: "completed",
      open: false,
    });
  }

  await notifyBlindMeeting({
    userIds: attended.map((p) => p.userId),
    meetingId,
    kind: "refunded",
  });
}

export async function submitFeedback(params: {
  meetingId: string;
  userId: string;
  ratings: Record<string, number>;
  reasons: string[];
  safetyConcernReported: boolean;
  algorithmVersion: string;
}): Promise<void> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.feedback)
    .doc(params.userId)
    .set(
      {
        userId: params.userId,
        ratings: params.ratings,
        reasons: params.reasons,
        safetyConcernReported: params.safetyConcernReported,
        algorithmVersion: meeting.algorithmVersion,
        submittedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  if (params.safetyConcernReported) {
    // 심각한 신고가 있으면 후속 선택과 1:1 채팅 생성을 막는다.
    for (const otherId of meeting.participantIds) {
      if (otherId === params.userId) continue;
      await addSafetyFlag({
        meetingId: params.meetingId,
        reporterId: params.userId,
        reportedId: otherId,
      });
    }
    await createOpsReview({
      meetingId: params.meetingId,
      userId: params.userId,
      kind: "safety_concern",
      detail: { reasons: params.reasons },
    });
  }
}

// -----------------------------------------------------------------------------
// 후속 선택 / 상호 선택
// -----------------------------------------------------------------------------

export async function openFollowUp(meetingId: string): Promise<boolean> {
  const meeting = await loadMeeting(meetingId);
  if (meeting.status !== "completed") return false;

  const policy = await loadPolicy();
  const closesAt = Timestamp.fromMillis(Date.now() + policy.followUpWindowMs);
  const moved = await transitionMeetingStatus(meetingId, "followup_open", {
    followupOpenedAt: FieldValue.serverTimestamp(),
    followupClosesAt: closesAt,
  });
  if (!moved) return false;

  const participants = await loadParticipants(meetingId);
  const flags = await loadSafetyFlags(meetingId);
  const eligible = participants
    .filter((p) => p.checkedIn && p.status !== "replaced")
    .map((p) => p.userId)
    .filter((id) => !flags.restrictedUserIds.includes(id));

  await notifyBlindMeeting({
    userIds: eligible,
    meetingId,
    kind: "follow_up",
  });
  return true;
}

/** 선택 가능한 상대 팀 목록 (참석자, 미차단, 미교체) */
export async function loadSelectableTargets(
  meetingId: string,
  userId: string
): Promise<string[]> {
  const meeting = await loadMeeting(meetingId);
  const participants = await loadParticipants(meetingId);
  const flags = await loadSafetyFlags(meetingId);

  const opponentIds = meeting.teamAUserIds.includes(userId)
    ? meeting.teamBUserIds
    : meeting.teamBUserIds.includes(userId)
      ? meeting.teamAUserIds
      : [];

  const byId = new Map(participants.map((p) => [p.userId, p]));
  const result: string[] = [];
  for (const opponentId of opponentIds) {
    const participant = byId.get(opponentId);
    if (!participant) continue;
    if (participant.status === "replaced") continue;
    if (!participant.checkedIn) continue;
    if (flags.restrictedUserIds.includes(opponentId)) continue;
    if (flags.blockedPairs.includes(pairKey(userId, opponentId))) continue;
    result.push(opponentId);
  }
  return result;
}

export async function submitFollowUpChoice(params: {
  meetingId: string;
  userId: string;
  selectedUids: string[];
}): Promise<{ ok: boolean; code?: string }> {
  const meeting = await loadMeeting(params.meetingId);
  if (!meeting.participantIds.includes(params.userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }

  const closesAt = meeting.raw.followupClosesAt;
  if (closesAt instanceof Timestamp && closesAt.toMillis() < Date.now()) {
    return { ok: false, code: "window_closed" };
  }
  if (meeting.status !== "followup_open") {
    return { ok: false, code: "not_open" };
  }

  const unique = [...new Set(params.selectedUids.filter((u) => u.length > 0))];
  if (unique.length > 2) {
    throw new HttpsError("invalid-argument", "최대 2명까지 선택할 수 있어요.");
  }
  if (unique.includes(params.userId)) {
    throw new HttpsError("invalid-argument", "자기 자신은 선택할 수 없어요.");
  }

  const selectable = await loadSelectableTargets(
    params.meetingId,
    params.userId
  );
  for (const uid of unique) {
    if (!selectable.includes(uid)) {
      throw new HttpsError("invalid-argument", "선택할 수 없는 상대예요.");
    }
  }

  const participants = await loadParticipants(params.meetingId);
  const me = participants.find((p) => p.userId === params.userId);
  if (!me?.checkedIn) {
    throw new HttpsError(
      "failed-precondition",
      "미팅에 참석한 분만 선택할 수 있어요."
    );
  }

  const choiceRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.followUpChoices)
    .doc(params.userId);

  const written = await db().runTransaction(async (tx) => {
    const snap = await tx.get(choiceRef);
    if (snap.exists && snap.data()?.submittedAt) return false;
    tx.set(
      choiceRef,
      {
        meetingId: params.meetingId,
        chooserUid: params.userId,
        selectedUids: unique,
        submittedAt: FieldValue.serverTimestamp(),
        expiresAt: closesAt ?? null,
      },
      { merge: true }
    );
    return true;
  });

  if (!written) return { ok: false, code: "already_submitted" };

  await resolveMutualMatches(params.meetingId, params.userId, unique);
  return { ok: true };
}

/**
 * 상호 선택 검사와 1:1 채팅 생성.
 *
 * 두 사용자가 서로 선택한 경우에만 채팅방을 만들고,
 * 일방 선택 정보는 어디에도 노출하지 않는다.
 */
export async function resolveMutualMatches(
  meetingId: string,
  chooserUid: string,
  selectedUids: string[]
): Promise<string[]> {
  const flags = await loadSafetyFlags(meetingId);
  const created: string[] = [];

  for (const partnerUid of selectedUids) {
    if (flags.restrictedUserIds.includes(partnerUid)) continue;
    if (flags.blockedPairs.includes(pairKey(chooserUid, partnerUid))) continue;
    if (await isBlockedEitherWay(chooserUid, partnerUid)) continue;

    const partnerChoiceSnap = await db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .doc(meetingId)
      .collection(BLIND_MEETING_COLLECTIONS.followUpChoices)
      .doc(partnerUid)
      .get();
    const partnerSelected = asStrArray(partnerChoiceSnap.data()?.selectedUids);
    if (!partnerSelected.includes(chooserUid)) continue;

    const matchRef = db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .doc(meetingId)
      .collection("mutualMatches")
      .doc(pairKey(chooserUid, partnerUid));

    const isNew = await db().runTransaction(async (tx) => {
      const snap = await tx.get(matchRef);
      if (snap.exists) return false;
      tx.set(matchRef, {
        meetingId,
        userIds: [chooserUid, partnerUid].sort(),
        matchedAt: FieldValue.serverTimestamp(),
      });
      return true;
    });
    if (!isNew) continue;

    const roomId = await ensureDirectChat(chooserUid, partnerUid);
    await matchRef.set({ chatRoomId: roomId }, { merge: true });
    created.push(roomId);

    await notifyBlindMeeting({
      userIds: [chooserUid, partnerUid],
      meetingId,
      kind: "mutual_match",
      deeplinkId: roomId,
      dedupeSuffix: pairKey(chooserUid, partnerUid),
      data: { roomId },
    });
  }

  return created;
}

async function isBlockedEitherWay(a: string, b: string): Promise<boolean> {
  const [x, y] = await Promise.all([
    db().collection("blocks").doc(a).collection("targets").doc(b).get(),
    db().collection("blocks").doc(b).collection("targets").doc(a).get(),
  ]);
  return x.exists || y.exists;
}

/** 내 상호 선택 결과만 돌려준다 (일방 선택 정보 없음) */
/**
 * 약속잡기 기한이 지난 미팅을 서버가 확정한다.
 *
 * 날짜 전용 정책에서는 미팅 생성 시점에 `scheduledStartAt`이 없다.
 * 이 단계가 없으면 투표하지 않은 그룹은 보증금이 묶인 채로 무기한 방치되고,
 * lifecycle 스케줄러(참석 재확인·노쇼·후속)도 시작 시각이 없어 전부 건너뛴다.
 */
export async function finalizeExpiredScheduleVotes(): Promise<number> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .where("serverStatus", "==", "chat_open")
    .where("scheduleVoteDeadlineAt", "<=", Timestamp.now())
    .get();

  let finalized = 0;
  for (const doc of snap.docs) {
    const meeting = readMeetingDoc(doc.id, doc.data());
    if (meeting == null) continue;
    // 이미 확정된 시간이 있으면 건너뛴다.
    if (meeting.scheduledStartAtMs != null) continue;
    try {
      await maybeConfirmSchedule(meeting.meetingId, { force: true });
      finalized++;
    } catch (error) {
      logger.error("blindMeeting schedule auto-confirm failed", {
        meetingId: meeting.meetingId,
        error,
      });
    }
  }
  return finalized;
}

export async function loadMyMutualMatches(
  meetingId: string,
  userId: string
): Promise<{ partnerUid: string; chatRoomId: string }[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection("mutualMatches")
    .where("userIds", "array-contains", userId)
    .get();

  const result: { partnerUid: string; chatRoomId: string }[] = [];
  for (const doc of snap.docs) {
    const userIds = asStrArray(doc.data()?.userIds);
    const partnerUid = userIds.find((id) => id !== userId);
    const chatRoomId = doc.data()?.chatRoomId;
    if (partnerUid && typeof chatRoomId === "string") {
      result.push({ partnerUid, chatRoomId });
    }
  }
  return result;
}

// -----------------------------------------------------------------------------
// 채팅 lifecycle
// -----------------------------------------------------------------------------

export async function applyChatLifecycle(meeting: MeetingDoc): Promise<void> {
  if (!meeting.groupChatId) return;
  const policy = await loadPolicy();
  const completedAt = meeting.raw.completedAt;
  if (!(completedAt instanceof Timestamp)) return;

  const elapsed = Date.now() - completedAt.toMillis();
  if (elapsed >= policy.groupChatArchiveAfterMeetingMs) {
    await setGroupChatWritable(meeting.groupChatId, false, "archived");
    await transitionMeetingStatus(meeting.meetingId, "read_only");
    await transitionMeetingStatus(meeting.meetingId, "archived", {
      archivedAt: FieldValue.serverTimestamp(),
    });
    return;
  }
  if (elapsed >= policy.groupChatWritableAfterMeetingMs) {
    await setGroupChatWritable(meeting.groupChatId, false, "read_only");
    await transitionMeetingStatus(meeting.meetingId, "read_only");
  }
}

/** 조건 완화 선택 (사용자가 직접 선택한 경우에만 적용) */
export async function applyRelaxationChoice(params: {
  userId: string;
  choice: string;
  additionalDateKeys: string[];
  nowMs?: number;
}): Promise<void> {
  const nowMs = params.nowMs ?? Date.now();

  // 이미 배정된 사용자가 신청을 다시 열면 매칭 pool을 오염시키고
  // 매 라운드 transaction 실패를 유발한다. 대기 중일 때만 허용한다.
  const applicationSnap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(params.userId)
    .get();
  const application = readApplicationDoc(params.userId, applicationSnap.data());
  if (application == null) {
    throw new HttpsError("failed-precondition", "진행 중인 신청이 없어요.");
  }
  if (
    application.meetingId != null ||
    (application.status !== "applied" && application.status !== "waitlisted")
  ) {
    throw new HttpsError(
      "failed-precondition",
      "이미 미팅이 배정돼 조건을 바꿀 수 없어요."
    );
  }

  switch (params.choice) {
    case "waitForAlcoholFree":
      await setApplication(params.userId, {
        stage: "searchingCandidates",
        open: true,
        extra: { relaxationChoice: params.choice },
      });
      return;
    case "openToOtherDates": {
      // 클라이언트 값이 아니라 서버 기준 창으로 다시 검증한다.
      const valid = normalizeDateKeys(params.additionalDateKeys).filter((key) =>
        isDateKeyWithinWindow(key, nowMs)
      );
      if (valid.length === 0) {
        throw new HttpsError("invalid-argument", "추가로 가능한 날짜를 선택해주세요.");
      }
      await db()
        .collection(BLIND_MEETING_COLLECTIONS.dna)
        .doc(params.userId)
        .set(
          {
            availableDateKeys: FieldValue.arrayUnion(...valid),
            availabilityMode: BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
            scheduleSelectionVersion:
              BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      await setApplication(params.userId, {
        stage: "searchingCandidates",
        open: true,
        extra: {
          requestedDateKeys: FieldValue.arrayUnion(...valid),
          relaxationChoice: params.choice,
        },
      });
      return;
    }
    case "allowLightDrinking":
      await db()
        .collection(BLIND_MEETING_COLLECTIONS.dna)
        .doc(params.userId)
        .set(
          {
            alcoholCompanionPreference: "lightOkay",
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      await setApplication(params.userId, {
        stage: "searchingCandidates",
        open: true,
        extra: {
          prefersAlcoholFree: false,
          relaxationChoice: params.choice,
        },
      });
      return;
    default:
      throw new HttpsError("invalid-argument", "알 수 없는 선택이에요.");
  }
}

export { groupChatIdFor };
