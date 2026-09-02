/**
 * 3:3 블라인드 취향 미팅 — Firestore 접근 레이어
 * 경로: functions/src/blindMeeting/store.ts
 *
 * 클라이언트는 미팅 상태·팀 배열·결제·참석 상태를 직접 쓸 수 없다.
 * 모든 쓰기는 이 모듈을 통해 서버에서만 수행된다.
 */

import { readPersistedCampusLifeZones } from "../campusLifeZones";
import { createHash } from "crypto";
import {
  DocumentSnapshot,
  FieldValue,
  getFirestore,
  Timestamp,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import {
  hasRequiredLifestyle,
  isStrictStudentVerification,
} from "./eligibility";
import {
  readBlindMeetingGender,
  validateBlindThreeVsThreeParticipants,
} from "./genderBalance";
import {
  buildBlindMeetingApplicationEditPatch,
  BlindMeetingApplicationEditState,
} from "./editPolicy";
import { Candidate } from "./matching";
import {
  BlindMeetingPolicy,
  DEFAULT_POLICY,
  policyFromConfigDoc,
} from "./policy";
import {
  ACTIVE_APPLICATION_STATUSES,
  ALCOHOL_PREFERENCES,
  BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
  BLIND_MEETING_COLLECTIONS,
  BLIND_MEETING_SCHEMA_VERSION,
  BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
  BLIND_MEETING_TYPE,
  BlindMeetingStatus,
  CONVERSATION_ATMOSPHERES,
  CONVERSATION_INITIATIVES,
  DEPOSIT_STATUS_TO_APP,
  DRINKING_LEVELS,
  DepositStatus,
  MEETING_BOUND_APPLICATION_STATUSES,
  MEETING_PURPOSES,
  MEETING_STATUS_TO_APP,
  MatchingStage,
  PARTICIPANT_STATUS_TO_APP,
  ParticipantStatus,
  SMOKING_PREFERENCES,
  SMOKING_STATUSES,
  asNum,
  asStr,
  asStrArray,
  asTrimmedOrNull,
  canTransitionApplication,
  canTransitionMeeting,
  canTransitionParticipant,
  holdsChatMembership,
  isMeetingSettled,
  isRecord,
  isValidDateKey,
  legacySlotIdsForDate,
  oneOf,
  oneOfOrNull,
  readDateKeys,
  slotStartAt,
} from "./types";

export function db() {
  return getFirestore();
}

// -----------------------------------------------------------------------------
// 인증
// -----------------------------------------------------------------------------

export type BlindMeetingUser = {
  userId: string;
  data: Record<string, unknown>;
};

/**
 * 블라인드 미팅 callable 공통 인증.
 *
 * 비공개 DNA와 후속 선택을 다루므로 Firebase Auth 세션(uid == kakaoUserId)을
 * 반드시 요구한다. 앱은 호출 전에 ensureFirebaseSessionForKakao로 세션을 만든다.
 */
export async function requireVerifiedUser(request: {
  auth?: { uid?: string } | null;
}): Promise<BlindMeetingUser> {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }
  const snap = await db().collection("users").doc(uid).get();
  if (!snap.exists) {
    throw new HttpsError("failed-precondition", "가입 정보를 찾을 수 없어요.");
  }
  const data = (snap.data() ?? {}) as Record<string, unknown>;
  if (!isStrictStudentVerification(data.isStudentVerified)) {
    throw new HttpsError(
      "failed-precondition",
      "학교 인증을 완료한 계정만 참가할 수 있어요."
    );
  }
  if (data.isWithdrawn === true || data.loginDisabled === true) {
    throw new HttpsError("permission-denied", "현재 계정으로는 참가할 수 없어요.");
  }
  return { userId: uid, data };
}

// -----------------------------------------------------------------------------
// 정책
// -----------------------------------------------------------------------------

export async function loadPolicy(): Promise<BlindMeetingPolicy> {
  try {
    const snap = await db()
      .collection(BLIND_MEETING_COLLECTIONS.config)
      .doc("current")
      .get();
    return policyFromConfigDoc(snap.data(), DEFAULT_POLICY);
  } catch (error) {
    logger.warn("blindMeeting policy load failed, using defaults", { error });
    return DEFAULT_POLICY;
  }
}

// -----------------------------------------------------------------------------
// 후보 로딩
// -----------------------------------------------------------------------------

export type ApplicationDoc = {
  userId: string;
  status: ParticipantStatus;
  stage: MatchingStage;
  /** 신청한 참여 가능 날짜 (KST `yyyy-MM-dd`, 오름차순) */
  requestedDateKeys: string[];
  prefersAlcoholFree: boolean;
  waitlistOptIn: boolean;
  meetingId: string | null;
  appliedAtMs: number;
  /** 잠긴 친구 파티. legacy 신청은 자기 자신만 든 가상 파티로 읽는다. */
  partyId: string;
  partyMemberIds: string[];
};

export function readApplicationDoc(
  userId: string,
  raw: unknown
): ApplicationDoc | null {
  if (!isRecord(raw)) return null;
  const appliedAt = raw.appliedAt;
  const partyMemberIds = asStrArray(raw.partyMemberIds);
  return {
    userId,
    status: oneOf(
      [
        "applied",
        "waitlisted",
        "invited",
        "accepted",
        "deposit_pending",
        "confirmed",
        "cancel_requested",
        "cancelled",
        "replacement_pending",
        "replaced",
        "no_show",
        "attended",
        "completed",
        "restricted",
      ] as ParticipantStatus[],
      raw.serverStatus ?? raw.status,
      "applied"
    ),
    stage: oneOf(
      [
        "waitingForPartyMembers",
        "waitingForCommonDates",
        "searchingCandidates",
        "formingOwnTeam",
        "checkingCrossTeam",
        "awaitingConfirmation",
        "matched",
        "insufficientCandidates",
        "cancelled",
      ] as MatchingStage[],
      raw.stage,
      "searchingCandidates"
    ),
    // 날짜 전용 필드를 우선 읽고, 없으면 legacy 슬롯에서 날짜만 복원한다.
    requestedDateKeys: readDateKeys(
      raw.requestedDateKeys,
      raw.requestedSlotIds
    ),
    prefersAlcoholFree: raw.prefersAlcoholFree === true,
    waitlistOptIn: raw.waitlistOptIn !== false,
    meetingId: asTrimmedOrNull(raw.meetingId),
    appliedAtMs:
      appliedAt instanceof Timestamp ? appliedAt.toMillis() : Date.now(),
    partyId: asTrimmedOrNull(raw.partyId) ?? `legacy:${userId}`,
    partyMemberIds: partyMemberIds.length > 0 ? partyMemberIds : [userId],
  };
}

// 차단·제재 조회는 안전 게이트다. Firestore 오류를 삼켜 빈 목록/false 로
// 되돌리면(fail-open) 서로 차단한 사용자가 매칭되거나 제재 사용자가 게이트를
// 통과한다. 그래서 오류를 그대로 전파해(fail-closed) 후보 로딩과 매칭 실행을
// 중단시키고 다음 스케줄 tick 에서 재시도하게 한다.
// (dna/user 문서 read 도 이미 같은 방식으로 예외를 전파한다.)
// database 인자는 테스트에서 오류 주입을 위한 seam 이며 기본값은 실제 db() 다.
export async function loadBlockedUserIds(
  userId: string,
  database: ReturnType<typeof db> = db()
): Promise<string[]> {
  const snap = await database
    .collection("blocks")
    .doc(userId)
    .collection("targets")
    .get();
  return snap.docs.map((d) => d.id).filter((id) => id.length > 0);
}

export async function loadRecentlyMetUserIds(
  userId: string,
  lookbackMs: number,
  database: ReturnType<typeof db> = db()
): Promise<string[]> {
  const since = Timestamp.fromMillis(Date.now() - lookbackMs);
  const snap = await database
    .collection(BLIND_MEETING_COLLECTIONS.matchHistory)
    .doc(userId)
    .collection("metUsers")
    .where("metAt", ">=", since)
    .get();
  return snap.docs.map((d) => d.id);
}

export async function isRestricted(
  userId: string,
  database: ReturnType<typeof db> = db()
): Promise<boolean> {
  const snap = await database
    .collection(BLIND_MEETING_COLLECTIONS.restrictions)
    .doc(userId)
    .get();
  if (!snap.exists) return false;
  const until = snap.data()?.restrictedUntil;
  if (until instanceof Timestamp) {
    return until.toMillis() > Date.now();
  }
  return snap.data()?.restricted === true;
}

/**
 * 비공개 DNA + 프로필 + 차단/제재 정보를 합쳐 매칭 후보를 만든다.
 *
 * DNA가 없거나 필수 값이 빠져 있으면 null (후보에서 제외).
 */
export async function loadCandidate(
  userId: string,
  policy: BlindMeetingPolicy,
  nowMs: number,
  appliedAtMs: number,
  partyId: string = `legacy:${userId}`,
  partyMemberIds: string[] = [userId]
): Promise<Candidate | null> {
  const [dnaSnap, userSnap, blocked, recentlyMet, restricted] =
    await Promise.all([
      db().collection(BLIND_MEETING_COLLECTIONS.dna).doc(userId).get(),
      db().collection("users").doc(userId).get(),
      loadBlockedUserIds(userId),
      loadRecentlyMetUserIds(userId, policy.recentlyMetLookbackMs),
      isRestricted(userId),
    ]);

  return buildCandidate({
    userId,
    dna: dnaSnap.data(),
    user: userSnap.data(),
    blockedUserIds: blocked,
    recentlyMetUserIds: recentlyMet,
    restricted,
    nowMs,
    appliedAtMs,
    partyId,
    partyMemberIds,
  });
}

/**
 * 읽어온 문서들로 매칭 후보를 만든다 (순수 함수, I/O 없음).
 *
 * 여기가 후보 hydration 의 fail-closed 관문이다. 성별·안전 조건을 확인할 수
 * 없는 사용자는 점수 계산과 상위 랭킹 이전에 여기서 제외된다
 * (filter-before-rank).
 */
export function buildCandidate(params: {
  userId: string;
  dna: unknown;
  user: unknown;
  blockedUserIds: string[];
  recentlyMetUserIds: string[];
  restricted: boolean;
  nowMs: number;
  appliedAtMs: number;
  partyId?: string;
  partyMemberIds?: string[];
}): Candidate | null {
  const {
    userId,
    blockedUserIds: blocked,
    recentlyMetUserIds: recentlyMet,
    restricted,
    nowMs,
    appliedAtMs,
  } = params;
  const dna = params.dna;
  const user = params.user;
  if (!isRecord(dna) || !isRecord(user)) return null;

  // 3:3 은 3남 + 3녀가 상품 정의다. canonical 성별을 확인할 수 없으면
  // 어느 팀에도 임의로 배정하지 않고 후보에서 제외한다 (fail-closed).
  // 여기서 걸러야 점수 계산과 상위 랭킹 이전에 부적격자가 사라진다.
  const gender = readBlindMeetingGender(user);
  if (gender == null) {
    logger.info("blindMeeting candidate skipped: gender not canonical", {
      code: "blindMeetingGenderNotCanonical",
    });
    return null;
  }

  const atmosphere = oneOfOrNull(
    CONVERSATION_ATMOSPHERES,
    dna.conversationAtmosphere
  );
  const initiative = oneOfOrNull(
    CONVERSATION_INITIATIVES,
    dna.conversationInitiative
  );
  const purpose = oneOfOrNull(MEETING_PURPOSES, dna.meetingPurpose);
  if (!atmosphere || !initiative || !purpose) return null;

  const eligible =
    user.isStudentVerified === true &&
    user.isWithdrawn !== true &&
    user.loginDisabled !== true &&
    !restricted;

  // 음주·흡연 관련 네 필드는 안전 조건이다. 값이 없거나 손상됐을 때
  // 가장 관대한 기본값으로 보정하면 (실제 흡연자 → nonSmoker,
  // allSober 사용자 → noPreference) 잘못된 자리에 앉힐 수 있다.
  // 하나라도 canonical 이 아니면 후보에서 제외한다 (fail-closed).
  const onboarding = isRecord(user.onboarding)
    ? (user.onboarding as Record<string, unknown>)
    : {};
  const lifestyle = isRecord(onboarding.lifestyle)
    ? (onboarding.lifestyle as Record<string, unknown>)
    : {};

  const alcoholPreference = oneOfOrNull(
    ALCOHOL_PREFERENCES,
    dna.alcoholCompanionPreference
  );
  const smokingPreference = oneOfOrNull(
    SMOKING_PREFERENCES,
    dna.smokingCompanionPreference
  );
  // 음주 정도·흡연 여부는 프로필이 원본이고 DNA 문서는 신청 시점 사본이다.
  // 신청 이후 프로필을 바꿔도 사본은 갱신되지 않으므로 live 값을 먼저 본다
  // (users 문서는 위에서 이미 읽었으므로 추가 read 비용이 없다).
  const drinkingLevel =
    oneOfOrNull(DRINKING_LEVELS, lifestyle.drinking) ??
    oneOfOrNull(DRINKING_LEVELS, dna.drinkingLevelSnapshot);
  const smokingStatus =
    oneOfOrNull(SMOKING_STATUSES, lifestyle.smoking) ??
    oneOfOrNull(SMOKING_STATUSES, dna.smokingStatusSnapshot);

  if (
    alcoholPreference == null ||
    smokingPreference == null ||
    drinkingLevel == null ||
    smokingStatus == null
  ) {
    logger.info("blindMeeting candidate skipped: safety fields not canonical", {
      code: "blindMeetingSafetyFieldNotCanonical",
      hasAlcoholPreference: alcoholPreference != null,
      hasSmokingPreference: smokingPreference != null,
      hasDrinkingLevel: drinkingLevel != null,
      hasSmokingStatus: smokingStatus != null,
    });
    return null;
  }

  // 신청 시점에는 "전원 비음주"를 고를 수 있는 조건(본인도 비음주)이었지만
  // 그 뒤 프로필을 음주로 바꾼 경우. 여기서 그냥 넘기면 requiresAlcoholFreeGroup
  // 이 false 가 되어 일반(음주) 미팅에 배정되는데, 신청서와 앱 화면은 여전히
  // 무알코올 미팅을 약속하고 있다. 조용히 등급을 낮추지 않고 제외한다.
  // (사용자가 DNA 를 다시 제출하면 정상 후보로 돌아온다.)
  if (alcoholPreference === "allSober" && drinkingLevel !== "none") {
    logger.info("blindMeeting candidate skipped: alcohol-free promise broken", {
      code: "blindMeetingAlcoholFreePromiseBroken",
    });
    return null;
  }

  return {
    userId,
    partyId: params.partyId ?? `legacy:${userId}`,
    partyMemberIds:
      params.partyMemberIds && params.partyMemberIds.length > 0
        ? params.partyMemberIds
        : [userId],
    gender,
    atmosphere,
    initiative,
    purpose,
    alcoholPreference,
    smokingPreference,
    drinkingLevel,
    smokingStatus,
    interestIds: asStrArray(dna.interestIds),
    mbti: asTrimmedOrNull(dna.mbtiSnapshot),
    // 생활권은 온보딩에서 계산되어 users/{uid}.onboarding 에 저장된 값을
    // 그대로 읽는다 (grade/department 로 재계산하지 않는다).
    // users 문서는 위에서 이미 읽었으므로 추가 read 비용이 없다.
    campusLifeZones: readPersistedCampusLifeZones(onboarding.campusLifeZones),
    // 날짜 전용 필드를 우선 읽고, 없으면 legacy 슬롯에서 날짜만 복원한다.
    availableDateKeys: readDateKeys(
      dna.availableDateKeys,
      dna.availableSlotIds ?? dna.availableSlots
    ),
    schoolVerified: user.isStudentVerified === true,
    eligible,
    blockedUserIds: blocked,
    recentlyMetUserIds: recentlyMet,
    waitedMinutes: Math.max(0, Math.floor((nowMs - appliedAtMs) / 60000)),
  };
}

/**
 * 특정 날짜에 신청한 활성 지원자 목록.
 *
 * 신규 문서는 `requestedDateKeys`로 색인되고, legacy 문서(`requestedSlotIds`만
 * 가진 문서)는 별도 쿼리로 모아 날짜로 정규화한 뒤 합친다.
 */
export async function loadOpenApplications(
  dateKey: string
): Promise<ApplicationDoc[]> {
  if (!isValidDateKey(dateKey)) return [];

  const byDate = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .where("requestedDateKeys", "array-contains", dateKey)
    .where("open", "==", true)
    .get();

  const byId = new Map<string, ApplicationDoc>();
  const collect = (docId: string, raw: unknown) => {
    const application = readApplicationDoc(docId, raw);
    if (application == null) return;
    if (!application.requestedDateKeys.includes(dateKey)) return;
    if (
      application.status !== "applied" &&
      application.status !== "waitlisted"
    ) {
      return;
    }
    byId.set(docId, application);
  };

  for (const doc of byDate.docs) collect(doc.id, doc.data());

  // legacy 호환: 날짜 필드가 없는 기존 신청도 매칭 대상에 남긴다.
  // 이 쿼리는 날짜마다 한 번 더 컬렉션을 읽으므로 읽기 비용이 2배가 된다.
  // 날짜 전용 backfill이 끝나면 policy.legacySlotCompatEnabled를 0으로 내린다.
  const policy = await loadPolicy();
  if (policy.legacySlotCompatEnabled > 0) {
    const legacy = await db()
      .collection(BLIND_MEETING_COLLECTIONS.applications)
      .where(
        "requestedSlotIds",
        "array-contains-any",
        legacySlotIdsForDate(dateKey)
      )
      .where("open", "==", true)
      .get();
    for (const doc of legacy.docs) {
      if (byId.has(doc.id)) continue;
      collect(doc.id, doc.data());
    }
  }

  return [...byId.values()].sort((a, b) => a.userId.localeCompare(b.userId));
}

/** 대기 중인 모든 날짜 key 수집 */
export async function loadOpenDateKeys(): Promise<string[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .where("open", "==", true)
    .get();
  const dates = new Set<string>();
  for (const doc of snap.docs) {
    const raw = doc.data();
    for (const dateKey of readDateKeys(
      raw?.requestedDateKeys,
      raw?.requestedSlotIds
    )) {
      dates.add(dateKey);
    }
  }
  return [...dates].sort();
}

// -----------------------------------------------------------------------------
// 공개 프로필 스냅샷
// -----------------------------------------------------------------------------

/** 얼굴 사진을 쓰지 않는 결정적 아바타 seed */
export function avatarSeedFor(userId: string): string {
  return createHash("sha256").update(userId).digest("hex").slice(0, 16);
}

export type PublicProfileSnapshot = {
  userId: string;
  nickname: string;
  department: string | null;
  mbti: string | null;
  topInterestIds: string[];
  avatarSeed: string;
  schoolVerified: boolean;
  safetyStampSummary: {
    completedMeetings: number;
    allCheckinsCompleted: boolean;
    allCheckoutsCompleted: boolean;
  };
  oneLineIntro: string | null;
};

/**
 * 공개용 스냅샷 생성.
 *
 * 실제 사진 URL, 비공개 DNA, 음주·흡연 상세, 매칭 점수, 연락처,
 * 학교 이메일, 신고 정보, 내부 신뢰 점수는 절대 포함하지 않는다.
 */
export async function buildPublicProfile(
  userId: string
): Promise<PublicProfileSnapshot> {
  const [userSnap, statsSnap] = await Promise.all([
    db().collection("users").doc(userId).get(),
    db().collection(BLIND_MEETING_COLLECTIONS.stats).doc(userId).get(),
  ]);
  const user = (userSnap.data() ?? {}) as Record<string, unknown>;
  const onboarding = isRecord(user.onboarding) ? user.onboarding : {};
  const stats = (statsSnap.data() ?? {}) as Record<string, unknown>;

  const completedMeetings = Math.max(0, Math.floor(asNum(stats.completedMeetings, 0)));
  const checkins = Math.max(0, Math.floor(asNum(stats.checkinCompleted, 0)));
  const checkouts = Math.max(0, Math.floor(asNum(stats.checkoutCompleted, 0)));

  return {
    userId,
    nickname: asStr(onboarding.nickname ?? user.nickname ?? "익명", "익명"),
    department:
      asTrimmedOrNull(onboarding.department) ??
      asTrimmedOrNull(onboarding.major),
    mbti: asTrimmedOrNull(onboarding.mbti)?.toUpperCase() ?? null,
    topInterestIds: asStrArray(onboarding.interests).slice(0, 3),
    avatarSeed: avatarSeedFor(userId),
    schoolVerified: user.isStudentVerified === true,
    safetyStampSummary: {
      completedMeetings,
      allCheckinsCompleted:
        completedMeetings > 0 && checkins >= completedMeetings,
      allCheckoutsCompleted:
        completedMeetings > 0 && checkouts >= completedMeetings,
    },
    oneLineIntro: asTrimmedOrNull(onboarding.selfIntroduction),
  };
}

// -----------------------------------------------------------------------------
// 미팅 문서
// -----------------------------------------------------------------------------

export type MeetingDoc = {
  meetingId: string;
  status: BlindMeetingStatus;

  /** 단체 채팅방 약속잡기로 확정된 최종 시간. 확정 전에는 빈 문자열. */
  slotId: string;

  /** 매칭 기준 날짜 (KST `yyyy-MM-dd`) */
  matchedDateKey: string;

  /** 여섯 명이 공통으로 가능한 날짜 (약속잡기 후보) */
  commonAvailableDateKeys: string[];

  isAlcoholFree: boolean;
  teamAUserIds: string[];
  teamBUserIds: string[];
  participantIds: string[];
  waitlistIds: string[];
  groupChatId: string | null;
  algorithmVersion: string;
  scheduledStartAtMs: number | null;
  fivePersonExceptionApproved: boolean;
  raw: Record<string, unknown>;
};

function toServerStatus(raw: unknown): BlindMeetingStatus {
  const appValue = asStr(raw, "");
  for (const [server, app] of Object.entries(MEETING_STATUS_TO_APP)) {
    if (app === appValue || server === appValue) {
      return server as BlindMeetingStatus;
    }
  }
  return "application_open";
}

export function readMeetingDoc(
  meetingId: string,
  raw: unknown
): MeetingDoc | null {
  if (!isRecord(raw)) return null;
  const scheduledStartAt = raw.scheduledStartAt;
  return {
    meetingId,
    status: toServerStatus(raw.status),
    slotId: asStr(raw.slotId, ""),
    // legacy 미팅 문서는 매칭 날짜를 slotId 안에만 갖고 있다.
    matchedDateKey:
      readDateKeys([raw.matchedDateKey], [raw.slotId])[0] ?? "",
    commonAvailableDateKeys: readDateKeys(
      raw.commonAvailableDateKeys,
      raw.candidateSlotIds
    ),
    isAlcoholFree: raw.isAlcoholFree === true,
    teamAUserIds: asStrArray(raw.teamAUserIds),
    teamBUserIds: asStrArray(raw.teamBUserIds),
    participantIds: asStrArray(raw.participantIds),
    waitlistIds: asStrArray(raw.waitlistIds),
    groupChatId: asTrimmedOrNull(raw.groupChatId),
    algorithmVersion: asStr(raw.algorithmVersion, "unknown"),
    scheduledStartAtMs:
      scheduledStartAt instanceof Timestamp
        ? scheduledStartAt.toMillis()
        : slotStartAt(asStr(raw.slotId, ""))?.getTime() ?? null,
    fivePersonExceptionApproved: raw.fivePersonExceptionApproved === true,
    raw,
  };
}

export async function loadMeeting(meetingId: string): Promise<MeetingDoc> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .get();
  const meeting = readMeetingDoc(meetingId, snap.data());
  if (meeting == null) {
    throw new HttpsError("not-found", "미팅 정보를 찾을 수 없어요.");
  }
  return meeting;
}

export function assertParticipant(meeting: MeetingDoc, userId: string): void {
  if (!meeting.participantIds.includes(userId)) {
    throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
  }
}

/** 미팅 상태를 검증된 전환만 허용해 변경한다. */
export async function transitionMeetingStatus(
  meetingId: string,
  to: BlindMeetingStatus,
  extra: Record<string, unknown> = {}
): Promise<boolean> {
  const ref = db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
  return db().runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const meeting = readMeetingDoc(meetingId, snap.data());
    if (meeting == null) return false;
    if (meeting.status === to) return false;
    if (!canTransitionMeeting(meeting.status, to)) {
      logger.warn("blindMeeting illegal transition blocked", {
        meetingId,
        from: meeting.status,
        to,
      });
      return false;
    }
    tx.update(ref, {
      status: MEETING_STATUS_TO_APP[to],
      serverStatus: to,
      ...extra,
      updatedAt: FieldValue.serverTimestamp(),
    });
    return true;
  });
}

function buildParticipantPatchPayload(patch: {
  status?: ParticipantStatus;
  depositStatus?: DepositStatus;
  extra?: Record<string, unknown>;
}): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    ...(patch.extra ?? {}),
    updatedAt: FieldValue.serverTimestamp(),
  };
  if (patch.status) {
    payload.status = PARTICIPANT_STATUS_TO_APP[patch.status];
    payload.serverStatus = patch.status;
  }
  if (patch.depositStatus) {
    payload.depositStatus = DEPOSIT_STATUS_TO_APP[patch.depositStatus];
    payload.serverDepositStatus = patch.depositStatus;
  }
  return payload;
}

/**
 * 참가자 문서의 유일한 사후 status writer (choke point).
 *
 * status가 포함된 patch는 단일 트랜잭션 안에서
 *   participant/meeting read → 상태 파싱(fail-closed) → 참가자 FSM 검증
 *   → terminal meeting 게이트 → write
 * 를 수행한다. status가 없는 patch(depositStatus/extra)는 기존처럼 merge.
 *
 * 예외(참가자 FSM을 통과하지 않는 write)는 두 곳뿐이다:
 * - createMeetingFromProposal: 참가자 문서 최초 생성 (invited)
 * - respondReplacementOffer tx: 대체 합류(confirmed 생성) + 이탈자(replaced)
 * 둘 다 자체 트랜잭션에서 선행 검증을 마친 INITIAL/전용 경로다.
 */
export async function updateParticipant(
  meetingId: string,
  userId: string,
  patch: {
    status?: ParticipantStatus;
    depositStatus?: DepositStatus;
    extra?: Record<string, unknown>;
  }
): Promise<void> {
  const participantRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.participants)
    .doc(userId);

  if (!patch.status) {
    await participantRef.set(buildParticipantPatchPayload(patch), {
      merge: true,
    });
    return;
  }

  const to = patch.status;
  const meetingRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId);

  await db().runTransaction(async (tx) => {
    const [meetingSnap, participantSnap] = await Promise.all([
      tx.get(meetingRef),
      tx.get(participantRef),
    ]);
    if (!meetingSnap.exists) {
      throw new HttpsError("failed-precondition", "blind_meeting_missing");
    }
    if (!participantSnap.exists) {
      throw new HttpsError("failed-precondition", "blind_participant_missing");
    }

    const rawFrom = String(participantSnap.data()?.serverStatus ?? "");
    if (!(rawFrom in PARTICIPANT_STATUS_TO_APP)) {
      // 알 수 없는 상태는 정상 상태로 보정하지 않는다 (fail-closed).
      logger.error("blindMeeting participant status unknown", {
        meetingId,
        rawStatusLength: rawFrom.length,
      });
      throw new HttpsError(
        "failed-precondition",
        `blind_participant_status_unknown:${rawFrom}`
      );
    }
    const from = rawFrom as ParticipantStatus;

    // terminal meeting 게이트: 보관된 미팅은 어떤 참가자 전이도 불가,
    // 취소된 미팅은 취소 정산 계열 전이만 허용한다.
    const meetingRaw = String(
      meetingSnap.data()?.serverStatus ?? meetingSnap.data()?.status ?? ""
    );
    if (meetingRaw === "archived") {
      throw new HttpsError(
        "failed-precondition",
        "blind_meeting_archived_participant_frozen"
      );
    }
    if (
      meetingRaw === "cancelled" &&
      to !== "cancelled" &&
      to !== "no_show"
    ) {
      throw new HttpsError(
        "failed-precondition",
        `blind_meeting_cancelled_participant_transition_rejected:${from}->${to}`
      );
    }

    if (from === to) {
      // idempotent 재시도: 동반 필드(depositStatus/extra)만 갱신한다.
      tx.set(participantRef, buildParticipantPatchPayload(patch), {
        merge: true,
      });
      return;
    }
    if (!canTransitionParticipant(from, to)) {
      throw new HttpsError(
        "failed-precondition",
        `blind_participant_transition_rejected:${from}->${to}`
      );
    }
    tx.set(participantRef, buildParticipantPatchPayload(patch), {
      merge: true,
    });
  });
}

export type ParticipantDoc = {
  userId: string;
  status: ParticipantStatus;
  depositStatus: DepositStatus;
  team: "teamA" | "teamB";
  checkedIn: boolean;
  checkedOut: boolean;
  attendance24h: string;
  attendance3h: string;
  isReplacement: boolean;
};

export function readParticipantDoc(
  userId: string,
  raw: unknown
): ParticipantDoc | null {
  if (!isRecord(raw)) return null;
  return {
    userId,
    status: oneOf(
      Object.keys(PARTICIPANT_STATUS_TO_APP) as ParticipantStatus[],
      raw.serverStatus,
      "applied"
    ),
    depositStatus: oneOf(
      Object.keys(DEPOSIT_STATUS_TO_APP) as DepositStatus[],
      raw.serverDepositStatus,
      "not_required"
    ),
    team: raw.team === "teamB" ? "teamB" : "teamA",
    checkedIn: raw.checkInStatus === "completed",
    checkedOut: raw.checkOutStatus === "completed",
    attendance24h: asStr(raw.attendanceConfirmation24h, "pending"),
    attendance3h: asStr(raw.attendanceConfirmation3h, "pending"),
    isReplacement: raw.isReplacement === true,
  };
}

export async function loadParticipants(
  meetingId: string
): Promise<ParticipantDoc[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.participants)
    .get();
  const result: ParticipantDoc[] = [];
  for (const doc of snap.docs) {
    const participant = readParticipantDoc(doc.id, doc.data());
    if (participant) result.push(participant);
  }
  result.sort((a, b) => a.userId.localeCompare(b.userId));
  return result;
}

// -----------------------------------------------------------------------------
// 신청 문서
// -----------------------------------------------------------------------------

/** camelCase(앱 표기) → snake_case(서버 표기) 역매핑. 레거시 문서 파싱용. */
const APP_STATUS_TO_SERVER: Record<string, ParticipantStatus> = Object.fromEntries(
  (Object.entries(PARTICIPANT_STATUS_TO_APP) as [ParticipantStatus, string][])
    .flatMap(([server, app]) => [
      [server, server],
      [app, server],
    ])
) as Record<string, ParticipantStatus>;

function buildApplicationPatchPayload(patch: {
  status?: ParticipantStatus;
  stage?: MatchingStage;
  open?: boolean;
  meetingId?: string | null;
  extra?: Record<string, unknown>;
}): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    ...(patch.extra ?? {}),
    updatedAt: FieldValue.serverTimestamp(),
  };
  if (patch.status) {
    payload.status = PARTICIPANT_STATUS_TO_APP[patch.status];
    payload.serverStatus = patch.status;
  }
  if (patch.stage) payload.stage = patch.stage;
  if (patch.open !== undefined) payload.open = patch.open;
  if (patch.meetingId !== undefined) payload.meetingId = patch.meetingId;
  return payload;
}

/**
 * 신청서 문서의 유일한 status writer (choke point).
 *
 * status가 포함된 patch는 단일 트랜잭션 안에서
 *   read → 상태 파싱(fail-closed) → 신청서 FSM 검증 → write
 * 를 수행한다. 문서가 없으면 최초 신청(`applied`)만 생성을 허용한다.
 * status가 없는 patch(stage/open/extra)는 기존처럼 merge.
 *
 * FSM을 통과하지 않는 예외는 자체 트랜잭션에서 검증을 마친 곳뿐:
 * - createMeetingFromProposal (open 신청 6개의 원자적 invited 클레임)
 * - respondReplacementOffer (open 신청의 confirmed 직접 합류)
 * - cancelOpenApplication (아래 전용 helper — applied/waitlisted→cancelled)
 * - submitNewApplication (아래 전용 helper — 신규 submit 의 재신청
 *   invariant + FSM 검증을 연결 미팅 read 와 같은 트랜잭션에서 수행)
 */
export async function setApplication(
  userId: string,
  patch: {
    status?: ParticipantStatus;
    stage?: MatchingStage;
    open?: boolean;
    meetingId?: string | null;
    extra?: Record<string, unknown>;
  }
): Promise<void> {
  const ref = db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId);

  if (!patch.status) {
    await ref.set(buildApplicationPatchPayload(patch), { merge: true });
    return;
  }

  const to = patch.status;
  await db().runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    if (!snap.exists) {
      // 최초 신청만 문서 생성을 허용한다.
      if (to !== "applied") {
        throw new HttpsError(
          "failed-precondition",
          `blind_application_missing_for_transition:${to}`
        );
      }
      tx.set(ref, buildApplicationPatchPayload(patch), { merge: true });
      return;
    }

    const rawFrom = String(
      snap.data()?.serverStatus ?? snap.data()?.status ?? ""
    );
    const from = APP_STATUS_TO_SERVER[rawFrom];
    if (from == null) {
      logger.error("blindMeeting application status unknown", {
        rawStatusLength: rawFrom.length,
      });
      throw new HttpsError(
        "failed-precondition",
        `blind_application_status_unknown:${rawFrom}`
      );
    }

    if (from === to) {
      tx.set(ref, buildApplicationPatchPayload(patch), { merge: true });
      return;
    }
    if (!canTransitionApplication(from, to)) {
      throw new HttpsError(
        "failed-precondition",
        `blind_application_transition_rejected:${from}->${to}`
      );
    }
    tx.set(ref, buildApplicationPatchPayload(patch), { merge: true });
  });
}

const BLIND_MEETING_HEART_COST = 30;

function heartBalanceFromSnapshot(snapshot: DocumentSnapshot): number {
  const raw = snapshot.get("heartBalance");
  return typeof raw === "number" && Number.isFinite(raw) && raw >= 0
    ? Math.floor(raw)
    : 0;
}

type BlindMeetingDnaDraftFields = {
  conversationAtmosphere?: string;
  conversationInitiative?: string;
  meetingPurpose?: string;
  alcoholCompanionPreference?: string;
  smokingCompanionPreference?: string;
};

/**
 * DNA 작성 시작 시 30H를 한 번만 차감하고, 작성 진행 문서를 만든다.
 *
 * 이 상태는 실제 신청(open 후보군)과 분리되어 있어 작성 중인 사용자가
 * 매칭에 노출되지 않는다. 같은 진행 문서로 재시도하면 잔액을 다시
 * 차감하지 않고 기존 상태를 반환한다.
 */
export async function startPaidBlindMeetingDna(userId: string): Promise<{
  charged: boolean;
  heartBalance: number;
  heartChargeCount: number;
}> {
  const firestore = db();
  const draftRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.dnaDrafts)
    .doc(userId);
  const applicationRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId);
  const userRef = firestore.collection("users").doc(userId);

  return firestore.runTransaction(async (tx) => {
    const [draftSnap, applicationSnap, userSnap] = await Promise.all([
      tx.get(draftRef),
      tx.get(applicationRef),
      tx.get(userRef),
    ]);
    if (!userSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }
    const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
    // 결제 트랜잭션 안에서 최신 프로필을 확인한다. 이 검사를 차감보다 먼저
    // 수행해야 음주·흡연 정보가 비어 있는 사용자의 하트가 줄지 않는다.
    if (!hasRequiredLifestyle(userData.onboarding)) {
      throw new HttpsError(
        "failed-precondition",
        "프로필의 음주·흡연 정보를 먼저 등록해주세요."
      );
    }

    const existingApplication =
      (applicationSnap.data() ?? {}) as Record<string, unknown>;
    const applicationMeetingId = asTrimmedOrNull(
      existingApplication.meetingId
    );
    if (applicationSnap.exists && existingApplication.open === true && !applicationMeetingId) {
      throw new HttpsError(
        "failed-precondition",
        "이미 진행 중인 블라인드 미팅 신청이 있어요."
      );
    }

    const existingDraft = (draftSnap.data() ?? {}) as Record<string, unknown>;
    const existingDraftStatus = asStr(existingDraft.status, "");
    const existingDraftChargeCount = Math.max(
      0,
      Math.floor(asNum(existingDraft.heartChargeCount, 0))
    );
    const applicationCompleted = existingApplication.dnaApplicationCompleted === true;
    if (
      draftSnap.exists &&
      existingDraftStatus === "in_progress" &&
      existingDraftChargeCount > 0 &&
      !applicationCompleted
    ) {
      return {
        charged: false,
        heartBalance: heartBalanceFromSnapshot(userSnap),
        heartChargeCount: existingDraftChargeCount,
      };
    }

    // 최종 신청과 초안 삭제가 분리된 legacy/복구 데이터가 남아 있어도
    // 완료된 신청의 초안을 이어쓰기 상태로 노출하지 않는다.
    if (applicationCompleted && draftSnap.exists) {
      tx.delete(draftRef);
    }

    const previousApplicationChargeCount = Math.max(
      0,
      Math.floor(asNum(existingApplication.heartChargeCount, 0))
    );
    const chargeCount = Math.max(
      previousApplicationChargeCount,
      existingDraftChargeCount
    ) + 1;
    const spendRef = firestore
      .collection("heartTransactions")
      .doc(
        createHash("sha256")
          .update(`blind_meeting:${userId}:${chargeCount}`)
          .digest("hex")
      );
    const spendSnap = await tx.get(spendRef);
    if (spendSnap.exists) {
      throw new HttpsError(
        "already-exists",
        "이미 처리된 블라인드 미팅 결제가 있어요. 잠시 후 다시 시도해주세요."
      );
    }

    let heartBalance = Math.max(0, Math.floor(heartBalanceFromSnapshot(userSnap)));
    if (heartBalance < BLIND_MEETING_HEART_COST) {
      throw new HttpsError(
        "resource-exhausted",
        `하트가 부족해요. 3:3 블라인드 신청에는 ${BLIND_MEETING_HEART_COST}H가 필요해요.`
      );
    }
    heartBalance -= BLIND_MEETING_HEART_COST;
    tx.set(
      userRef,
      {
        heartBalance,
        heartBalanceUpdatedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    tx.create(spendRef, {
      uid: userId,
      feature: "blind_meeting",
      resourceId: userId,
      amount: BLIND_MEETING_HEART_COST,
      heartBalanceAfter: heartBalance,
      createdAt: FieldValue.serverTimestamp(),
    });
    tx.set(
      draftRef,
      {
        userId,
        status: "in_progress",
        heartCost: BLIND_MEETING_HEART_COST,
        heartChargeCount: chargeCount,
        updatedAt: FieldValue.serverTimestamp(),
        ...(!draftSnap.exists
          ? { createdAt: FieldValue.serverTimestamp() }
          : {}),
      },
      { merge: true }
    );
    return {
      charged: true,
      heartBalance,
      heartChargeCount: chargeCount,
    };
  });
}

/** 작성 중인 DNA 답변을 저장한다. 결제·신청 상태는 이 함수에서 변경하지 않는다. */
export async function saveBlindMeetingDnaDraft(
  userId: string,
  fields: BlindMeetingDnaDraftFields
): Promise<void> {
  const draftRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.dnaDrafts)
    .doc(userId);
  await db().runTransaction(async (tx) => {
    const draftSnap = await tx.get(draftRef);
    const raw = (draftSnap.data() ?? {}) as Record<string, unknown>;
    if (
      !draftSnap.exists ||
      asStr(raw.status, "") !== "in_progress" ||
      asNum(raw.heartChargeCount, 0) <= 0
    ) {
      throw new HttpsError(
        "failed-precondition",
        "진행 중인 미팅 DNA 작성을 찾을 수 없어요."
      );
    }
    tx.set(
      draftRef,
      {
        ...fields,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  });
}

/**
 * 신규 블라인드 미팅 신청·DNA 저장·30H 차감을 하나의 트랜잭션으로
 * 처리한다. 네트워크 재시도로 이미 열린 신청을 다시 제출하면 재차감하지
 * 않고, 취소/완료 후 새 신청은 새로 차감한다.
 */
export async function createPaidBlindMeetingApplication(params: {
  userId: string;
  dnaPayload: Record<string, unknown>;
  requestedDateKeys: string[];
  prefersAlcoholFree: boolean;
  waitlistOptIn: boolean;
  partyId?: string | null;
  partyMemberIds?: string[];
}): Promise<void> {
  const heartCost = BLIND_MEETING_HEART_COST;
  const firestore = db();
  const applicationRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(params.userId);
  const dnaRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.dna)
    .doc(params.userId);
  const draftRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.dnaDrafts)
    .doc(params.userId);
  const userRef = firestore.collection("users").doc(params.userId);

  await firestore.runTransaction(async (tx) => {
    const [applicationSnap, userSnap, draftSnap] = await Promise.all([
      tx.get(applicationRef),
      tx.get(userRef),
      tx.get(draftRef),
    ]);
    if (!userSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }

    const existing = (applicationSnap.data() ?? {}) as Record<string, unknown>;
    const existingMeetingId = asTrimmedOrNull(existing.meetingId);
    const isOpenRetry =
      applicationSnap.exists && existing.open === true && !existingMeetingId;
    const isSamePartyWaitingRetry =
      applicationSnap.exists &&
      existing.open !== true &&
      !existingMeetingId &&
      typeof params.partyId === "string" &&
      params.partyId.length > 0 &&
      existing.partyId === params.partyId &&
      (existing.stage === "waitingForPartyMembers" ||
        existing.stage === "waitingForCommonDates");
    if (applicationSnap.exists && !isOpenRetry && !isSamePartyWaitingRetry) {
      const rawStatus = asStr(existing.serverStatus ?? existing.status, "");
      const previous = APP_STATUS_TO_SERVER[rawStatus];
      if (previous == null) {
        throw new HttpsError(
          "failed-precondition",
          "현재 신청 상태에서는 새로 신청할 수 없어요."
        );
      }
      // 재신청 invariant: FSM 전이표만 보면 invited/accepted/confirmed→applied
      // 가 합법이지만(초대 거절·미팅 취소 재오픈 경로), 신규 유료 신청이 이
      // edge 를 타면 active invitation/meeting 에 귀속된 신청이 덮어써져
      // 미팅과 신청 lifecycle 이 분리된다. 신청서와 연결 미팅을 같은
      // 트랜잭션에서 읽어 business invariant 를 먼저 fail-closed 로 검증한다.
      if (ACTIVE_APPLICATION_STATUSES.includes(previous)) {
        if (existingMeetingId == null) {
          if (MEETING_BOUND_APPLICATION_STATUSES.includes(previous)) {
            logger.error(
              "blindMeeting submit blocked: active application without meeting link",
              { status: previous }
            );
            throw new HttpsError(
              "failed-precondition",
              `blind_application_active_without_meeting:${previous}`
            );
          }
          // applied/waitlisted open pool — 아래 FSM 검증으로 진행.
        } else {
          const meetingSnap = await tx.get(
            firestore
              .collection(BLIND_MEETING_COLLECTIONS.meetings)
              .doc(existingMeetingId)
          );
          const meeting = readMeetingDoc(existingMeetingId, meetingSnap.data());
          if (meeting == null) {
            logger.error("blindMeeting submit blocked: linked meeting missing", {
              status: previous,
            });
            throw new HttpsError(
              "failed-precondition",
              `blind_application_meeting_link_missing:${previous}`
            );
          }
          if (!isMeetingSettled(meeting.status)) {
            throw new HttpsError(
              "failed-precondition",
              "이미 진행 중인 미팅이 있어 새로 신청할 수 없어요. " +
                "미팅 화면에서 거절 또는 취소 요청을 이용해주세요. " +
                `(blind_reapplication_blocked_active_meeting:${previous})`
            );
          }
          logger.error(
            "blindMeeting submit blocked: active application on settled meeting",
            { applicationStatus: previous, meetingStatus: meeting.status }
          );
          throw new HttpsError(
            "failed-precondition",
            `blind_application_stale_meeting_link:${previous}->${meeting.status}`
          );
        }
      }
      if (!canTransitionApplication(previous, "applied")) {
        throw new HttpsError(
          "failed-precondition",
          "현재 신청 상태에서는 새로 신청할 수 없어요."
        );
      }
    }

    let heartBalance = asNum(userSnap.get("heartBalance"), 0);
    let chargeCount = Math.max(
      0,
      Math.floor(asNum(existing.heartChargeCount, 0))
    );
    const draft = (draftSnap.data() ?? {}) as Record<string, unknown>;
    const draftChargeCount = Math.max(
      0,
      Math.floor(asNum(draft.heartChargeCount, 0))
    );
    const hasPaidDraft =
      draftSnap.exists &&
      asStr(draft.status, "") === "in_progress" &&
      draftChargeCount > 0;
    chargeCount = Math.max(chargeCount, draftChargeCount);
    if (!isOpenRetry && !isSamePartyWaitingRetry && !hasPaidDraft) {
      heartBalance = Math.max(0, Math.floor(heartBalance));
      if (heartBalance < heartCost) {
        throw new HttpsError(
          "resource-exhausted",
          `하트가 부족해요. 3:3 블라인드 신청에는 ${heartCost}H가 필요해요.`
        );
      }
      heartBalance -= heartCost;
      chargeCount += 1;
      tx.set(
        userRef,
        {
          heartBalance,
          heartBalanceUpdatedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      const spendRef = firestore
        .collection("heartTransactions")
        .doc(
          createHash("sha256")
            .update(`blind_meeting:${params.userId}:${chargeCount}`)
            .digest("hex")
        );
      tx.create(spendRef, {
        uid: params.userId,
        feature: "blind_meeting",
        resourceId: params.userId,
        amount: heartCost,
        heartBalanceAfter: heartBalance,
        createdAt: FieldValue.serverTimestamp(),
      });
    }

    tx.set(
      dnaRef,
      {
        ...params.dnaPayload,
        updatedAt: FieldValue.serverTimestamp(),
        ...(!applicationSnap.exists
          ? { createdAt: FieldValue.serverTimestamp() }
          : {}),
      },
      { merge: true }
    );
    tx.set(
      applicationRef,
      buildApplicationPatchPayload({
        status: "applied",
        stage: params.partyId ? "waitingForPartyMembers" : "searchingCandidates",
        open: !params.partyId,
        meetingId: null,
        extra: {
          userId: params.userId,
          requestedDateKeys: params.requestedDateKeys,
          availabilityMode: BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
          scheduleSelectionVersion: BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
          prefersAlcoholFree: params.prefersAlcoholFree,
          waitlistOptIn: params.waitlistOptIn,
          appliedAt: FieldValue.serverTimestamp(),
          heartCost,
          heartChargeCount: chargeCount,
          dnaApplicationCompleted: true,
          partyId: params.partyId ?? null,
          partyMemberIds:
            params.partyMemberIds && params.partyMemberIds.length > 0
              ? params.partyMemberIds
              : [params.userId],
          partySize: Math.max(1, params.partyMemberIds?.length ?? 1),
          partyReady: !params.partyId,
        },
      }),
      { merge: true }
    );
    if (draftSnap.exists) {
      // 최종 신청이 완료되면 작성 중 상태를 제거해 다음 신청은 새 결제로
      // 시작하도록 한다. 트랜잭션 안에서 신청 저장과 함께 처리된다.
      tx.delete(draftRef);
    }
  });
}

/**
 * 미팅에 귀속된 신청서를 시스템이 open pool 로 재오픈한다 (초대 거절·미팅
 * 취소 경로). 이미 재오픈됐거나 다른 미팅에 귀속됐으면 덮어쓰지 않고,
 * terminal 상태는 사용자가 직접 재신청해야 하며 시스템이 되살리지 않는다.
 */
export async function reopenApplicationIfBoundTo(
  userId: string,
  meetingId: string,
  extra: Record<string, unknown> = {}
): Promise<boolean> {
  const ref = db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId);
  return db().runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    if (!snap.exists) return false;
    const raw = (snap.data() ?? {}) as Record<string, unknown>;

    const boundMeetingId =
      typeof raw.meetingId === "string" ? raw.meetingId.trim() : "";
    if (boundMeetingId !== meetingId) {
      logger.info("blindMeeting application reopen skipped: not bound", {
        stillBound: boundMeetingId.length > 0,
      });
      return false;
    }

    const rawStatus = String(raw.serverStatus ?? raw.status ?? "");
    const from = APP_STATUS_TO_SERVER[rawStatus];
    if (from == null) {
      logger.error("blindMeeting application status unknown", {
        rawStatusLength: rawStatus.length,
      });
      throw new HttpsError(
        "failed-precondition",
        `blind_application_status_unknown:${rawStatus}`
      );
    }
    if (
      !MEETING_BOUND_APPLICATION_STATUSES.includes(from) ||
      !canTransitionApplication(from, "applied")
    ) {
      logger.info("blindMeeting application reopen skipped", { from });
      return false;
    }

    tx.set(
      ref,
      buildApplicationPatchPayload({
        status: "applied",
        stage: "searchingCandidates",
        open: true,
        meetingId: null,
        extra,
      }),
      { merge: true }
    );
    return true;
  });
}

/**
 * 신청 취소는 아직 미팅에 배정되지 않은 신청에만 허용한다 (transaction 게이트).
 * 미팅에 배정된(meetingId 존재) 신청을 여기서 취소하면 참가자 문서·미팅 정원·
 * 보증금 상태와 조용히 어긋나므로, 그 경우 초대 거절(decline) 또는
 * 취소 요청(requestCancellation) 경로를 사용하도록 명시적으로 거부한다.
 */
export async function cancelOpenApplication(userId: string): Promise<void> {
  const ref = db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId);
  await db().runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    if (!snap.exists) return; // 취소할 신청이 없으면 idempotent 성공
    const raw = snap.data() ?? {};
    const serverStatus = String(raw.serverStatus ?? raw.status ?? "");
    if (serverStatus === "cancelled") return; // 이미 취소됨 — idempotent
    const meetingId =
      typeof raw.meetingId === "string" ? raw.meetingId.trim() : "";
    if (meetingId.length > 0) {
      throw new HttpsError(
        "failed-precondition",
        "이미 매칭된 미팅이 있어요. 미팅 화면에서 거절 또는 취소 요청을 이용해주세요."
      );
    }
    tx.set(
      ref,
      {
        status: PARTICIPANT_STATUS_TO_APP.cancelled,
        serverStatus: "cancelled",
        stage: "cancelled",
        open: false,
        meetingId: null,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  });
}

/**
 * Updates an open application and its private DNA atomically.
 *
 * The application document is read inside the transaction so a concurrent
 * matcher claim causes a retry and is rejected instead of being overwritten.
 */
export async function updateApplicationForDnaEdit(params: {
  userId: string;
  dnaPayload: Record<string, unknown>;
  requestedDateKeys: string[];
  prefersAlcoholFree: boolean;
  waitlistOptIn: boolean;
}): Promise<void> {
  const applicationRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(params.userId);
  const dnaRef = db()
    .collection(BLIND_MEETING_COLLECTIONS.dna)
    .doc(params.userId);

  await db().runTransaction(async (tx) => {
    const applicationSnap = await tx.get(applicationRef);
    if (!applicationSnap.exists) {
      throw new HttpsError(
        "failed-precondition",
        "수정할 진행 중인 신청을 찾을 수 없어요."
      );
    }

    const raw = (applicationSnap.data() ?? {}) as Record<string, unknown>;
    const status = oneOfOrNull(
      [
        "applied",
        "waitlisted",
        "invited",
        "accepted",
        "deposit_pending",
        "confirmed",
        "cancel_requested",
        "cancelled",
        "replacement_pending",
        "replaced",
        "no_show",
        "attended",
        "completed",
        "restricted",
      ] as ParticipantStatus[],
      raw.serverStatus ?? raw.status
    );
    const stage = oneOfOrNull(
      [
        "searchingCandidates",
        "formingOwnTeam",
        "checkingCrossTeam",
        "awaitingConfirmation",
        "matched",
        "insufficientCandidates",
        "cancelled",
      ] as MatchingStage[],
      raw.stage
    );
    if (status == null || stage == null) {
      throw new HttpsError(
        "failed-precondition",
        "현재 신청 상태를 확인할 수 없어 미팅 DNA를 수정할 수 없어요."
      );
    }

    const current: BlindMeetingApplicationEditState = {
      status,
      stage,
      open: raw.open === true,
      meetingId: asTrimmedOrNull(raw.meetingId),
    };
    const patch = buildBlindMeetingApplicationEditPatch(current, {
      requestedDateKeys: params.requestedDateKeys,
      prefersAlcoholFree: params.prefersAlcoholFree,
      waitlistOptIn: params.waitlistOptIn,
    });
    if (patch == null) {
      throw new HttpsError(
        "failed-precondition",
        "현재 신청 상태에서는 미팅 DNA를 수정할 수 없어요."
      );
    }

    tx.set(
      dnaRef,
      {
        ...params.dnaPayload,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    tx.set(
      applicationRef,
      {
        status: PARTICIPANT_STATUS_TO_APP[patch.status],
        serverStatus: patch.status,
        stage: patch.stage,
        open: patch.open,
        meetingId: patch.meetingId,
        requestedDateKeys: patch.requestedDateKeys,
        availabilityMode: BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY,
        scheduleSelectionVersion: BLIND_MEETING_SCHEDULE_SELECTION_VERSION,
        prefersAlcoholFree: patch.prefersAlcoholFree,
        waitlistOptIn: patch.waitlistOptIn,
        appliedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  });
}

// -----------------------------------------------------------------------------
// 단체 채팅
// -----------------------------------------------------------------------------

export function groupChatIdFor(meetingId: string): string {
  return `blind_${meetingId}`;
}

/**
 * 단체 채팅방을 생성한다 (idempotent).
 *
 * 여섯 명이 모두 확정되고 필요한 보증금 결제가 끝난 뒤에만 호출된다.
 * participantIds는 서버만 설정하며, 교체된 참가자는 즉시 제외된다.
 */
export async function ensureGroupChat(params: {
  meetingId: string;
  memberIds: string[];
  isAlcoholFree: boolean;
}): Promise<string> {
  const roomId = groupChatIdFor(params.meetingId);
  const roomRef = db().collection("chat_rooms").doc(roomId);

  // 최상위 불변식 3차 그물: 채팅방도 canonical 6인(3남 + 3녀)에서만 만든다.
  // 미팅 문서가 손상됐거나 수동으로 편집됐다면 여기서 멈춘다.
  // (채팅방이 열리면 참가자들이 서로를 보게 되므로 되돌리기 어렵다.)
  const userSnaps = await db().getAll(
    ...params.memberIds.map((userId) =>
      db().collection("users").doc(userId)
    )
  );
  const balance = validateBlindThreeVsThreeParticipants(
    params.memberIds.map((userId, index) => ({
      userId,
      gender: readBlindMeetingGender(userSnaps[index]?.data()),
    }))
  );
  if (!balance.ok) {
    logger.error("blindMeeting group chat rejected: roster is not 3M+3F", {
      code: "blindMeetingGenderInvariantViolated",
      meetingId: params.meetingId,
      violations: balance.violations,
      maleCount: balance.counts.male,
      femaleCount: balance.counts.female,
      unknownGenderCount: balance.counts.unknown,
      uniqueParticipantCount: balance.uniqueUserCount,
    });
    throw new HttpsError(
      "failed-precondition",
      "미팅 구성이 올바르지 않아 채팅방을 만들 수 없어요."
    );
  }

  const participantInfo: Record<string, unknown> = {};
  for (const userId of params.memberIds) {
    const profile = await buildPublicProfile(userId);
    participantInfo[userId] = {
      nickname: profile.nickname,
      // 블라인드 미팅에서는 얼굴 사진을 공유하지 않는다.
      avatarUrl: "",
      avatarSeed: profile.avatarSeed,
    };
  }

  const created = await db().runTransaction(async (tx) => {
    const snap = await tx.get(roomRef);
    if (snap.exists) {
      // 방 id 는 meetingId 에서 결정되므로 불일치는 손상 신호다.
      const existingMeetingId = snap.data()?.meetingId;
      if (
        typeof existingMeetingId === "string" &&
        existingMeetingId.length > 0 &&
        existingMeetingId !== params.meetingId
      ) {
        throw new HttpsError(
          "failed-precondition",
          "채팅방 정보가 올바르지 않아요."
        );
      }
      tx.set(
        roomRef,
        {
          participantIds: params.memberIds,
          participantInfo,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      return false;
    }
    tx.set(roomRef, {
      roomId,
      roomType: "blind_meeting_group",
      meetingId: params.meetingId,
      status: "active",
      isAlcoholFree: params.isAlcoholFree,
      participantIds: params.memberIds,
      participantInfo,
      writable: true,
      lastMessage: "",
      lastMessageAt: null,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    return true;
  });

  if (created) {
    await appendSystemMessage(
      roomId,
      "여섯 명이 모두 확정됐어요. 시간과 장소를 함께 정해보세요."
    );
  }

  return roomId;
}

export async function appendSystemMessage(
  roomId: string,
  text: string
): Promise<void> {
  const roomRef = db().collection("chat_rooms").doc(roomId);
  const messageRef = roomRef.collection("messages").doc();
  const batch = db().batch();
  batch.set(messageRef, {
    senderId: "system",
    text,
    type: "system",
    readBy: [],
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
  });
  batch.set(
    roomRef,
    {
      lastMessage: text,
      lastMessageAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );
  await batch.commit();
}

/** 참가자 교체 시 채팅 멤버십을 갱신한다. */
export async function syncGroupChatMembership(
  meetingId: string
): Promise<void> {
  const meeting = await loadMeeting(meetingId);
  if (!meeting.groupChatId) return;
  const participants = await loadParticipants(meetingId);
  const memberIds = participants
    .filter((p) => holdsChatMembership(p.status))
    .map((p) => p.userId)
    .sort();

  await db()
    .collection("chat_rooms")
    .doc(meeting.groupChatId)
    .set(
      {
        participantIds: memberIds,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

export async function setGroupChatWritable(
  roomId: string,
  writable: boolean,
  status: "active" | "read_only" | "archived"
): Promise<void> {
  await db()
    .collection("chat_rooms")
    .doc(roomId)
    .set(
      {
        writable,
        status,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

/** 상호 선택 성공 시 1:1 채팅방을 만든다 (idempotent). */
export async function ensureDirectChat(
  userA: string,
  userB: string
): Promise<string> {
  const ids = [userA, userB].sort();
  const roomId = `dm_${ids[0]}_${ids[1]}`;
  const roomRef = db().collection("chat_rooms").doc(roomId);

  const [profileA, profileB] = await Promise.all([
    buildPublicProfile(ids[0]),
    buildPublicProfile(ids[1]),
  ]);

  await db().runTransaction(async (tx) => {
    const snap = await tx.get(roomRef);
    if (snap.exists) return;
    tx.set(roomRef, {
      roomId,
      roomType: "blind_meeting_direct",
      status: "active",
      participantIds: ids,
      participantInfo: {
        [ids[0]]: { nickname: profileA.nickname, avatarUrl: "" },
        [ids[1]]: { nickname: profileB.nickname, avatarUrl: "" },
      },
      writable: true,
      // 단체 채팅 메시지는 복사하지 않는다.
      lastMessage: "",
      lastMessageAt: null,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
  });

  return roomId;
}

// -----------------------------------------------------------------------------
// 안전 / 제재 / 이력
// -----------------------------------------------------------------------------

export async function recordMetUsers(
  meetingId: string,
  userIds: string[]
): Promise<void> {
  const batch = db().batch();
  for (const userId of userIds) {
    for (const otherId of userIds) {
      if (userId === otherId) continue;
      batch.set(
        db()
          .collection(BLIND_MEETING_COLLECTIONS.matchHistory)
          .doc(userId)
          .collection("metUsers")
          .doc(otherId),
        {
          meetingId,
          metAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    }
  }
  await batch.commit();
}

export async function applyRestriction(params: {
  userId: string;
  days: number;
  reason: string;
  requiresOpsReview: boolean;
}): Promise<void> {
  const until = Timestamp.fromMillis(
    Date.now() + params.days * 24 * 60 * 60 * 1000
  );
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.restrictions)
    .doc(params.userId)
    .set(
      {
        restricted: params.days > 0,
        restrictedUntil: until,
        reason: params.reason,
        requiresOpsReview: params.requiresOpsReview,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

export async function incrementStats(
  userId: string,
  patch: Record<string, number>
): Promise<void> {
  const payload: Record<string, unknown> = {
    updatedAt: FieldValue.serverTimestamp(),
  };
  for (const [key, value] of Object.entries(patch)) {
    payload[key] = FieldValue.increment(value);
  }
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.stats)
    .doc(userId)
    .set(payload, { merge: true });
}

export async function loadRecentNoShowCount(
  userId: string,
  lookbackMs: number
): Promise<number> {
  const since = Timestamp.fromMillis(Date.now() - lookbackMs);
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.stats)
    .doc(userId)
    .collection("noShows")
    .where("occurredAt", ">=", since)
    .get();
  return snap.size;
}

export async function recordNoShow(
  userId: string,
  meetingId: string
): Promise<void> {
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.stats)
    .doc(userId)
    .collection("noShows")
    .doc(meetingId)
    .set(
      {
        meetingId,
        occurredAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

export type SafetyFlags = {
  restrictedUserIds: string[];
  blockedPairs: string[];
};

export function pairKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

export async function loadSafetyFlags(
  meetingId: string
): Promise<SafetyFlags> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.safetyFlags)
    .doc(meetingId)
    .get();
  const data = snap.data();
  return {
    restrictedUserIds: asStrArray(data?.restrictedUserIds),
    blockedPairs: asStrArray(data?.blockedPairs),
  };
}

export async function addSafetyFlag(params: {
  meetingId: string;
  reporterId: string;
  reportedId: string;
}): Promise<void> {
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.safetyFlags)
    .doc(params.meetingId)
    .set(
      {
        meetingId: params.meetingId,
        restrictedUserIds: FieldValue.arrayUnion(params.reportedId),
        blockedPairs: FieldValue.arrayUnion(
          pairKey(params.reporterId, params.reportedId)
        ),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

export async function createOpsReview(params: {
  meetingId: string;
  userId: string;
  kind: string;
  detail: Record<string, unknown>;
}): Promise<void> {
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.opsReviews)
    .doc(`${params.meetingId}_${params.userId}_${params.kind}`)
    .set(
      {
        meetingId: params.meetingId,
        userId: params.userId,
        kind: params.kind,
        detail: params.detail,
        status: "open",
        createdAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

/** 두 사용자가 서로 차단했는지 */
export async function isMutuallyBlocked(
  userA: string,
  userB: string
): Promise<boolean> {
  const [a, b] = await Promise.all([
    db().collection("blocks").doc(userA).collection("targets").doc(userB).get(),
    db().collection("blocks").doc(userB).collection("targets").doc(userA).get(),
  ]);
  return a.exists || b.exists;
}

export const BLIND_MEETING_DEFAULTS = {
  type: BLIND_MEETING_TYPE,
  schemaVersion: BLIND_MEETING_SCHEMA_VERSION,
};
