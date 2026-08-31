/**
 * 3:3 블라인드 취향 미팅 — Callable functions
 * 경로: functions/src/blindMeeting/callables.ts
 *
 * 모든 handler는
 *  - Firebase Auth 세션(uid == kakaoUserId)과 학교 인증을 검증하고
 *  - 입력 schema를 검증하고
 *  - PII 없는 structured logging만 남긴다.
 */

import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import {
  isFreeBlindMeetingTestClient,
  isFreeBlindMeetingTestUser,
} from "./compatibility";
import { hasRequiredInterests } from "./eligibility";
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
  openChatWithoutDeposit,
  requestCancellation,
  respondReplacementOffer,
  runMatchingForDate,
  submitFeedback,
  submitFollowUpChoice,
  voteFivePersonException,
  voteSchedule,
} from "./orchestrator";
import { BLIND_MEETING_CALLABLE_OPTIONS } from "./runtime";
import {
  db,
  loadPolicy,
  requireVerifiedUser,
  cancelOpenApplication,
  claimFreeBlindMeetingTestSlot,
  updateApplicationForDnaEdit,
  createFreeBlindMeetingApplication,
  createPaidBlindMeetingApplication,
  startPaidBlindMeetingDna,
  saveBlindMeetingDnaDraft,
} from "./store";
import {
  ALCOHOL_PREFERENCES,
  BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
  BLIND_MEETING_AVAILABILITY_WINDOW_DAYS,
  BLIND_MEETING_COLLECTIONS,
  BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
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
  isDateKeyWithinWindow,
  isRecord,
  isValidDateKey,
  normalizeDateKeys,
  oneOfOrNull,
} from "./types";

/** dispatcher가 내부 handler에 넘기는 최소 요청 형태 */
export type BlindMeetingRequest = {
  auth?: { uid?: string; token?: Record<string, unknown> } | null;
  app?: { appId?: string; token?: Record<string, unknown> } | null;
  data?: unknown;
};

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
async function submitBlindMeetingApplicationHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const dnaRaw = data.dna;
  const editExistingApplication = data.editExistingApplication === true;
  const clientBuild = asStr(data.clientBuild, "").trim();
  const isFreeTestUser = isFreeBlindMeetingTestUser(user.userId);
  const isFreeTestBuild =
    !editExistingApplication && isFreeBlindMeetingTestClient(clientBuild);
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

  // ── 참여 가능 날짜 검증 ─────────────────────────────────────────────────
  // 클라이언트 시간이 아니라 서버 시간 기준 창으로 검증한다.
  // legacy 슬롯 필드로 검증을 우회할 수 없도록 날짜만 받는다.
  const rawDateKeys = dnaRaw.availableDateKeys;
  if (!Array.isArray(rawDateKeys)) {
    throw new HttpsError(
      "invalid-argument",
      "참여 가능한 날짜를 한 개 이상 선택해주세요."
    );
  }
  if (rawDateKeys.length > BLIND_MEETING_AVAILABILITY_WINDOW_DAYS) {
    // 문서 크기 악용 방지: 창 길이보다 많은 값은 받지 않는다.
    throw new HttpsError("invalid-argument", "선택한 날짜가 너무 많아요.");
  }
  if (rawDateKeys.some((item) => typeof item !== "string")) {
    throw new HttpsError("invalid-argument", "날짜 형식이 올바르지 않아요.");
  }
  for (const item of rawDateKeys) {
    if (!isValidDateKey(item)) {
      throw new HttpsError(
        "invalid-argument",
        "날짜 형식이 올바르지 않아요. (yyyy-MM-dd)"
      );
    }
  }

  const nowMs = Date.now();
  const dateKeys = normalizeDateKeys(rawDateKeys);
  if (dateKeys.length !== rawDateKeys.length) {
    throw new HttpsError("invalid-argument", "중복된 날짜가 포함되어 있어요.");
  }
  const outOfWindow = dateKeys.filter(
    (key) => !isDateKeyWithinWindow(key, nowMs)
  );
  if (outOfWindow.length > 0) {
    throw new HttpsError(
      "invalid-argument",
      `내일부터 ${BLIND_MEETING_AVAILABILITY_WINDOW_DAYS}일 안의 날짜만 선택할 수 있어요.`
    );
  }
  if (dateKeys.length === 0) {
    throw new HttpsError(
      "invalid-argument",
      "참여 가능한 날짜를 한 개 이상 선택해주세요."
    );
  }

  // 관심사·음주·흡연·MBTI는 온보딩 프로필을 신뢰 소스로 사용한다.
  const onboardingRaw = user.data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};
  const lifestyleRaw = onboarding.lifestyle;
  const lifestyle = isRecord(lifestyleRaw) ? lifestyleRaw : {};

  const interestIds = asStrArray(onboarding.interests);
  if (!hasRequiredInterests(interestIds)) {
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
    availableDateKeys: dateKeys,
    campusLifeZones: asStrArray(onboarding.campusLifeZones),
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
  });

  const dnaPayload = {
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
    // 날짜 전용 계약. 신규 신청에는 시간대 필드를 쓰지 않는다.
    availableDateKeys: dateKeys,
    availabilityMode: BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
    scheduleSelectionVersion: BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
    waitlistOptIn: dnaRaw.waitlistOptIn !== false,
  };

  if (editExistingApplication) {
    await updateApplicationForDnaEdit({
      userId: user.userId,
      dnaPayload,
      requestedDateKeys: dateKeys,
      prefersAlcoholFree,
      waitlistOptIn: dnaRaw.waitlistOptIn !== false,
    });
  } else if (isFreeTestUser) {
    // 수동 UID 예외는 build 슬롯과 무관하게 계속 허용한다.
    await createFreeBlindMeetingApplication({
      userId: user.userId,
      dnaPayload,
      requestedDateKeys: dateKeys,
      prefersAlcoholFree,
      waitlistOptIn: dnaRaw.waitlistOptIn !== false,
    });
  } else if (isFreeTestBuild) {
    // build 번호는 클라이언트 입력이므로 단독 보안 경계로 쓰지 않는다.
    // App Check가 통과한 요청만 여기까지 오며, 서버 트랜잭션이 동일 UID의
    // 재시도를 멱등 처리하고 전체 무료 슬롯을 서버 설정 한도 안에서 제한한다.
    await claimFreeBlindMeetingTestSlot({
      userId: user.userId,
      clientBuild,
    });
    await createFreeBlindMeetingApplication({
      userId: user.userId,
      dnaPayload,
      requestedDateKeys: dateKeys,
      prefersAlcoholFree,
      waitlistOptIn: dnaRaw.waitlistOptIn !== false,
    });
  } else {
    await createPaidBlindMeetingApplication({
      userId: user.userId,
      dnaPayload,
      requestedDateKeys: dateKeys,
      prefersAlcoholFree,
      waitlistOptIn: dnaRaw.waitlistOptIn !== false,
    });
  }

  // 신청 즉시 매칭을 시도하되 날짜 수만큼 선형으로 늘리지 않는다.
  // 날짜를 21개 고른 사용자 때문에 callable이 타임아웃되면
  // '많이 고르라'고 안내한 사용자가 오히려 실패하게 된다.
  // 나머지 날짜는 10분 주기 스케줄러가 이어서 처리한다.
  const policy = await loadPolicy();
  const inlineDateKeys = dateKeys.slice(
    0,
    Math.max(1, policy.inlineMatchingDateLimit)
  );
  const createdMeetingIds: string[] = [];
  for (const dateKey of inlineDateKeys) {
    const created = await runMatchingForDate(dateKey);
    createdMeetingIds.push(...created);
    // 이미 배정됐으면 남은 날짜를 더 볼 필요가 없다.
    if (created.length > 0) break;
  }

  const applicationSnap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(user.userId)
    .get();
  const stage = asStr(applicationSnap.data()?.stage, "searchingCandidates");
  const meetingId = asTrimmedOrNull(applicationSnap.data()?.meetingId);

  // 실제 날짜는 로그에 남기지 않는다 (생활 패턴 노출 방지).
  logger.info("blindMeeting application submitted", {
    selectedDateCount: dateKeys.length,
    availabilityWindowDays: BLIND_MEETING_AVAILABILITY_WINDOW_DAYS,
    prefersAlcoholFree,
    createdMeetings: createdMeetingIds.length,
    billingMode: isFreeTestBuild
      ? "free_test_build"
      : isFreeTestUser
        ? "free_test_user"
        : "paid",
  });

  return { accepted: true, stage, meetingId };
}

/** DNA 작성 진입 시 30H를 멱등적으로 차감하고 진행 상태를 만든다. */
async function startBlindMeetingDnaHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  return startPaidBlindMeetingDna(user.userId);
}

/** DNA wizard가 선택한 답변 일부를 저장한다. 결제는 이 경로에서 하지 않는다. */
async function saveBlindMeetingDnaDraftHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const rawFields = data.fields;
  if (!isRecord(rawFields)) {
    throw new HttpsError("invalid-argument", "저장할 DNA 답변이 필요해요.");
  }

  const fields: Record<string, string> = {};
  const readEnumField = <T extends string>(
    key: string,
    values: readonly T[]
  ): void => {
    if (!Object.prototype.hasOwnProperty.call(rawFields, key)) return;
    const value = oneOfOrNull(values, rawFields[key]);
    if (value == null) {
      throw new HttpsError("invalid-argument", "미팅 DNA 답변이 올바르지 않아요.");
    }
    fields[key] = value;
  };
  readEnumField("conversationAtmosphere", CONVERSATION_ATMOSPHERES);
  readEnumField("conversationInitiative", CONVERSATION_INITIATIVES);
  readEnumField("meetingPurpose", MEETING_PURPOSES);
  readEnumField("alcoholCompanionPreference", ALCOHOL_PREFERENCES);
  readEnumField("smokingCompanionPreference", SMOKING_PREFERENCES);
  if (Object.keys(fields).length === 0) {
    throw new HttpsError("invalid-argument", "저장할 DNA 답변이 필요해요.");
  }

  await saveBlindMeetingDnaDraft(user.userId, fields);
  return { ok: true };
}

async function cancelBlindMeetingApplicationHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  // 미팅에 배정된 신청은 여기서 취소할 수 없다 (store가 transaction으로 게이트).
  await cancelOpenApplication(user.userId);
  return { ok: true };
}

async function relaxBlindMeetingConditionsHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  await applyRelaxationChoice({
    userId: user.userId,
    choice: asStr(data.choice, ""),
    additionalDateKeys: asStrArray(data.additionalDateKeys),
  });
  return { ok: true };
}

async function acceptBlindMeetingInvitationHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  await acceptInvitation(meetingId, user.userId);
  return { ok: true };
}

async function declineBlindMeetingInvitationHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await declineInvitation(meetingId, user.userId, asTrimmedOrNull(data.reason));
  return { ok: true };
}

async function startBlindMeetingDepositHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const intent = await beginDeposit(meetingId, user.userId);
  return intent;
}

async function openBlindMeetingChatHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  await openChatWithoutDeposit(meetingId, user.userId);
  return { ok: true };
}

async function voteBlindMeetingScheduleHandler(request: BlindMeetingRequest) {
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
}

async function confirmBlindMeetingAttendanceHandler(request: BlindMeetingRequest) {
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
}

async function respondBlindMeetingReplacementOfferHandler(request: BlindMeetingRequest) {
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
}

async function voteBlindMeetingFivePersonExceptionHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  await voteFivePersonException({
    meetingId,
    userId: user.userId,
    agree: data.agree === true,
  });
  return { ok: true };
}

async function requestBlindMeetingCancellationHandler(request: BlindMeetingRequest) {
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
}

async function markBlindMeetingSafetyStampHandler(request: BlindMeetingRequest) {
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
}

async function submitBlindMeetingFeedbackHandler(request: BlindMeetingRequest) {
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
}

async function submitBlindMeetingFollowUpChoiceHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const data = getData(request);
  const meetingId = requireMeetingId(data);
  return submitFollowUpChoice({
    meetingId,
    userId: user.userId,
    selectedUids: asStrArray(data.selectedUids),
  });
}

async function getBlindMeetingFollowUpTargetsHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const targets = await loadSelectableTargets(meetingId, user.userId);
  return { targets };
}

/** 상호 선택 결과만 반환. 일방 선택 정보는 내려주지 않는다. */
async function getBlindMeetingMutualMatchesHandler(request: BlindMeetingRequest) {
  const user = await requireVerifiedUser(request);
  const meetingId = requireMeetingId(getData(request));
  const matches = await loadMyMutualMatches(meetingId, user.userId);
  return { matches };
}

// -----------------------------------------------------------------------------
// dispatcher
//
// 프로젝트의 region당 CPU 할당량이 빡빡해서 callable 16개를 개별 함수로 배포하면
// 기존 함수 업데이트까지 실패한다. action 하나로 라우팅하는 단일 함수로 모으고,
// 인증·입력 검증은 각 handler가 그대로 수행한다.
// region은 함수 옵션에 명시한다 (setGlobalOptions보다 import가 먼저 평가됨).
// -----------------------------------------------------------------------------

type BlindMeetingHandler = (
  request: BlindMeetingRequest
) => Promise<Record<string, unknown>>;

const HANDLERS: Record<string, BlindMeetingHandler> = {
  submitBlindMeetingApplication: submitBlindMeetingApplicationHandler,
  startBlindMeetingDna: startBlindMeetingDnaHandler,
  saveBlindMeetingDnaDraft: saveBlindMeetingDnaDraftHandler,
  cancelBlindMeetingApplication: cancelBlindMeetingApplicationHandler,
  relaxBlindMeetingConditions: relaxBlindMeetingConditionsHandler,
  acceptBlindMeetingInvitation: acceptBlindMeetingInvitationHandler,
  declineBlindMeetingInvitation: declineBlindMeetingInvitationHandler,
  startBlindMeetingDeposit: startBlindMeetingDepositHandler,
  openBlindMeetingChat: openBlindMeetingChatHandler,
  voteBlindMeetingSchedule: voteBlindMeetingScheduleHandler,
  confirmBlindMeetingAttendance: confirmBlindMeetingAttendanceHandler,
  respondBlindMeetingReplacementOffer:
    respondBlindMeetingReplacementOfferHandler,
  voteBlindMeetingFivePersonException:
    voteBlindMeetingFivePersonExceptionHandler,
  requestBlindMeetingCancellation: requestBlindMeetingCancellationHandler,
  markBlindMeetingSafetyStamp: markBlindMeetingSafetyStampHandler,
  submitBlindMeetingFeedback: submitBlindMeetingFeedbackHandler,
  submitBlindMeetingFollowUpChoice: submitBlindMeetingFollowUpChoiceHandler,
  getBlindMeetingFollowUpTargets: getBlindMeetingFollowUpTargetsHandler,
  getBlindMeetingMutualMatches: getBlindMeetingMutualMatchesHandler,
};

/** dispatcher가 받아들이는 action 목록 (앱과 공유되는 계약) */
export const BLIND_MEETING_ACTIONS = Object.keys(HANDLERS);

export const blindMeetingAction = onCall(
  BLIND_MEETING_CALLABLE_OPTIONS,
  async (request) => {
    const data = getData(request);
    const action = asStr(data.action, "");
    const handler = HANDLERS[action];
    if (!handler) {
      throw new HttpsError("invalid-argument", "지원하지 않는 요청이에요.");
    }
    logger.info("blindMeetingAction", { action });
    return handler(request);
  }
);
