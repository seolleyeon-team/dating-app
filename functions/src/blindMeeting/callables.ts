/**
 * 3:3 블라인드 취향 미팅 — Callable functions
 * 경로: functions/src/blindMeeting/callables.ts
 *
 * 모든 handler는
 *  - Firebase Auth 세션(uid == kakaoUserId)과 학교 인증을 검증하고
 *  - 입력 schema를 검증하고
 *  - PII 없는 structured logging만 남긴다.
 */

import { FieldValue } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { requiresAlcoholFreeGroup } from "./matching";
import {
  acceptInvitation,
  applyRelaxationChoice,
  beginDeposit,
  confirmAttendance,
  declineInvitation,
  loadMyMutualMatches,
  loadSelectableTargets,
  markSafetyStamp,
  requestCancellation,
  respondReplacementOffer,
  runMatchingForSlot,
  submitFeedback,
  submitFollowUpChoice,
  voteFivePersonException,
  voteSchedule,
} from "./orchestrator";
import { db, requireVerifiedUser, setApplication } from "./store";
import {
  ALCOHOL_PREFERENCES,
  BLIND_MEETING_COLLECTIONS,
  CONVERSATION_ATMOSPHERES,
  CONVERSATION_INITIATIVES,
  DRINKING_LEVELS,
  MEETING_PURPOSES,
  SMOKING_PREFERENCES,
  SMOKING_STATUSES,
  asNum,
  asStr,
  asStrArray,
  asTrimmedOrNull,
  isRecord,
  isValidSlotId,
  oneOfOrNull,
} from "./types";

function getData(request: { data?: unknown }): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

function requireMeetingId(data: Record<string, unknown>): string {
  const meetingId = asTrimmedOrNull(data.meetingId);
  if (!meetingId) {
    throw new HttpsError("invalid-argument", "meetingId가 필요해요.");
  }
  return meetingId;
}

/** 참가 신청 제출: DNA 검증 → 비공개 저장 → 후보군 등록 → 즉시 매칭 시도 */
export const submitBlindMeetingApplication = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const dnaRaw = data.dna;
  if (!isRecord(dnaRaw)) {
    throw new HttpsError("invalid-argument", "dna가 필요해요.");
  }

  const atmosphere = oneOfOrNull(
    CONVERSATION_ATMOSPHERES,
    dnaRaw.conversationAtmosphere
  );
  const initiative = oneOfOrNull(
    CONVERSATION_INITIATIVES,
    dnaRaw.conversationInitiative
  );
  const purpose = oneOfOrNull(MEETING_PURPOSES, dnaRaw.meetingPurpose);
  const alcoholPreference = oneOfOrNull(
    ALCOHOL_PREFERENCES,
    dnaRaw.alcoholCompanionPreference
  );
  const smokingPreference = oneOfOrNull(
    SMOKING_PREFERENCES,
    dnaRaw.smokingCompanionPreference
  );
  if (
    !atmosphere ||
    !initiative ||
    !purpose ||
    !alcoholPreference ||
    !smokingPreference
  ) {
    throw new HttpsError("invalid-argument", "미팅 DNA 답변이 올바르지 않아요.");
  }

  const slotIds = asStrArray(dnaRaw.availableSlotIds ?? dnaRaw.availableSlots)
    .filter(isValidSlotId);
  if (slotIds.length === 0) {
    throw new HttpsError(
      "invalid-argument",
      "가능한 날짜와 시간을 한 개 이상 선택해주세요."
    );
  }

  // 관심사·음주·흡연·MBTI는 온보딩 프로필을 신뢰 소스로 사용한다.
  const onboardingRaw = user.data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};
  const lifestyleRaw = onboarding.lifestyle;
  const lifestyle = isRecord(lifestyleRaw) ? lifestyleRaw : {};

  const interestIds = asStrArray(onboarding.interests);
  if (interestIds.length === 0) {
    throw new HttpsError(
      "failed-precondition",
      "관심사를 먼저 등록해주세요."
    );
  }

  const drinkingLevel =
    oneOfOrNull(DRINKING_LEVELS, lifestyle.drinking) ?? null;
  const smokingStatus =
    oneOfOrNull(SMOKING_STATUSES, lifestyle.smoking) ?? null;
  if (drinkingLevel == null || smokingStatus == null) {
    throw new HttpsError(
      "failed-precondition",
      "프로필의 음주·흡연 정보를 먼저 등록해주세요."
    );
  }

  // 전원 비음주는 실제 프로필이 비음주일 때만 허용한다.
  if (alcoholPreference === "allSober" && drinkingLevel !== "none") {
    throw new HttpsError(
      "failed-precondition",
      "전원 비음주 미팅은 내 프로필의 음주 정도가 '전혀 안 함'일 때 선택할 수 있어요."
    );
  }

  const mbti = asTrimmedOrNull(onboarding.mbti)?.toUpperCase() ?? null;

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.dna)
    .doc(user.userId)
    .set(
      {
        userId: user.userId,
        schemaVersion: Math.max(1, Math.floor(asNum(dnaRaw.schemaVersion, 1))),
        conversationAtmosphere: atmosphere,
        conversationInitiative: initiative,
        meetingPurpose: purpose,
        alcoholCompanionPreference: alcoholPreference,
        smokingCompanionPreference: smokingPreference,
        interestIds,
        drinkingLevelSnapshot: drinkingLevel,
        smokingStatusSnapshot: smokingStatus,
        mbtiSnapshot: mbti,
        availableSlotIds: slotIds,
        waitlistOptIn: dnaRaw.waitlistOptIn !== false,
        updatedAt: FieldValue.serverTimestamp(),
        createdAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  const prefersAlcoholFree = requiresAlcoholFreeGroup({
    userId: user.userId,
    atmosphere,
    initiative,
    purpose,
    alcoholPreference,
    smokingPreference,
    drinkingLevel,
    smokingStatus,
    interestIds,
    mbti,
    availableSlotIds: slotIds,
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
  });

  await setApplication(user.userId, {
    status: "applied",
    stage: "searchingCandidates",
    open: true,
    meetingId: null,
    extra: {
      userId: user.userId,
      requestedSlotIds: slotIds,
      prefersAlcoholFree,
      waitlistOptIn: dnaRaw.waitlistOptIn !== false,
      appliedAt: FieldValue.serverTimestamp(),
    },
  });

  // 신청 즉시 해당 슬롯들에 대해 매칭을 시도한다.
  const createdMeetingIds: string[] = [];
  for (const slotId of slotIds) {
    const created = await runMatchingForSlot(slotId);
    createdMeetingIds.push(...created);
  }

  const applicationSnap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(user.userId)
    .get();
  const stage = asStr(applicationSnap.data()?.stage, "searchingCandidates");
  const meetingId = asTrimmedOrNull(applicationSnap.data()?.meetingId);

  logger.info("blindMeeting application submitted", {
    slotCount: slotIds.length,
    prefersAlcoholFree,
    createdMeetings: createdMeetingIds.length,
  });

  return { accepted: true, stage, meetingId };
});

export const cancelBlindMeetingApplication = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  await setApplication(user.userId, {
    status: "cancelled",
    stage: "cancelled",
    open: false,
    meetingId: null,
  });
  return { ok: true };
});

export const relaxBlindMeetingConditions = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  await applyRelaxationChoice({
    userId: user.userId,
    choice: asStr(data.choice, ""),
    additionalSlotIds: asStrArray(data.additionalSlotIds),
  });
  return { ok: true };
});

export const acceptBlindMeetingInvitation = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  await acceptInvitation(meetingId, user.userId);
  return { ok: true };
});

export const declineBlindMeetingInvitation = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await declineInvitation(meetingId, user.userId, asTrimmedOrNull(data.reason));
  return { ok: true };
});

export const startBlindMeetingDeposit = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const intent = await beginDeposit(meetingId, user.userId);
  return intent;
});

export const voteBlindMeetingSchedule = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await voteSchedule({
    meetingId,
    userId: user.userId,
    preferredSlotIds: asStrArray(data.preferredSlotIds),
    preferredPlaceId: asTrimmedOrNull(data.preferredPlaceId),
  });
  return { ok: true };
});

export const confirmBlindMeetingAttendance = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  const phase = asStr(data.phase, "");
  if (phase !== "24h" && phase !== "3h") {
    throw new HttpsError("invalid-argument", "phase는 24h 또는 3h여야 해요.");
  }
  await confirmAttendance({
    meetingId,
    userId: user.userId,
    phase,
    attending: data.attending === true,
  });
  return { ok: true };
});

export const respondBlindMeetingReplacementOffer = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const offerId = asTrimmedOrNull(data.offerId);
  if (!offerId) {
    throw new HttpsError("invalid-argument", "offerId가 필요해요.");
  }
  return respondReplacementOffer({
    offerId,
    userId: user.userId,
    accept: data.accept === true,
  });
});

export const voteBlindMeetingFivePersonException = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await voteFivePersonException({
    meetingId,
    userId: user.userId,
    agree: data.agree === true,
  });
  return { ok: true };
});

export const requestBlindMeetingCancellation = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await requestCancellation({
    meetingId,
    userId: user.userId,
    reason: asTrimmedOrNull(data.reason),
    emergency: data.emergency === true,
  });
  return { ok: true };
});

export const markBlindMeetingSafetyStamp = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  const phase = asStr(data.phase, "");
  if (phase !== "meetup" && phase !== "goodbye") {
    throw new HttpsError(
      "invalid-argument",
      "phase는 meetup 또는 goodbye여야 해요."
    );
  }
  await markSafetyStamp({
    meetingId,
    userId: user.userId,
    phase,
    verification: isRecord(data.verification) ? data.verification : null,
  });
  return { ok: true };
});

export const submitBlindMeetingFeedback = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  const ratingsRaw = data.ratings;
  if (!isRecord(ratingsRaw)) {
    throw new HttpsError("invalid-argument", "ratings가 필요해요.");
  }

  const allowed = [
    "ownTeamComfort",
    "opponentConversation",
    "venueAndAlcohol",
    "wouldJoinAgain",
  ];
  const ratings: Record<string, number> = {};
  for (const key of allowed) {
    const value = Math.round(asNum(ratingsRaw[key], 0));
    if (value < 1 || value > 5) {
      throw new HttpsError("invalid-argument", "모든 문항을 1~5로 채워주세요.");
    }
    ratings[key] = value;
  }

  await submitFeedback({
    meetingId,
    userId: user.userId,
    ratings,
    reasons: asStrArray(data.reasons),
    safetyConcernReported: data.safetyConcernReported === true,
    algorithmVersion: asStr(data.algorithmVersion, "unknown"),
  });
  return { ok: true };
});

export const submitBlindMeetingFollowUpChoice = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  return submitFollowUpChoice({
    meetingId,
    userId: user.userId,
    selectedUids: asStrArray(data.selectedUids),
  });
});

export const getBlindMeetingFollowUpTargets = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const targets = await loadSelectableTargets(meetingId, user.userId);
  return { targets };
});

/** 상호 선택 결과만 반환. 일방 선택 정보는 내려주지 않는다. */
export const getBlindMeetingMutualMatches = onCall(async (request) => {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const matches = await loadMyMutualMatches(meetingId, user.userId);
  return { matches };
});
