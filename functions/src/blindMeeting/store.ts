/**
 * 3:3 블라인드 취향 미팅 — Firestore 접근 레이어
 * 경로: functions/src/blindMeeting/store.ts
 *
 * 클라이언트는 미팅 상태·팀 배열·결제·참석 상태를 직접 쓸 수 없다.
 * 모든 쓰기는 이 모듈을 통해 서버에서만 수행된다.
 */

import { createHash } from "crypto";
import { FieldValue, getFirestore, Timestamp } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { Candidate } from "./matching";
import {
  BlindMeetingPolicy,
  DEFAULT_POLICY,
  policyFromConfigDoc,
} from "./policy";
import {
  ALCOHOL_PREFERENCES,
  BLIND_MEETING_COLLECTIONS,
  BLIND_MEETING_SCHEMA_VERSION,
  BLIND_MEETING_TYPE,
  BlindMeetingStatus,
  CONVERSATION_ATMOSPHERES,
  CONVERSATION_INITIATIVES,
  DEPOSIT_STATUS_TO_APP,
  DRINKING_LEVELS,
  DepositStatus,
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
  canTransitionMeeting,
  holdsChatMembership,
  isRecord,
  isValidSlotId,
  oneOf,
  oneOfOrNull,
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
  if (data.isStudentVerified !== true) {
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
  requestedSlotIds: string[];
  prefersAlcoholFree: boolean;
  waitlistOptIn: boolean;
  meetingId: string | null;
  appliedAtMs: number;
};

export function readApplicationDoc(
  userId: string,
  raw: unknown
): ApplicationDoc | null {
  if (!isRecord(raw)) return null;
  const appliedAt = raw.appliedAt;
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
    requestedSlotIds: asStrArray(raw.requestedSlotIds).filter(isValidSlotId),
    prefersAlcoholFree: raw.prefersAlcoholFree === true,
    waitlistOptIn: raw.waitlistOptIn !== false,
    meetingId: asTrimmedOrNull(raw.meetingId),
    appliedAtMs:
      appliedAt instanceof Timestamp ? appliedAt.toMillis() : Date.now(),
  };
}

async function loadBlockedUserIds(userId: string): Promise<string[]> {
  try {
    const snap = await db()
      .collection("blocks")
      .doc(userId)
      .collection("targets")
      .get();
    return snap.docs.map((d) => d.id).filter((id) => id.length > 0);
  } catch (error) {
    logger.warn("blindMeeting block load failed", { userId, error });
    return [];
  }
}

async function loadRecentlyMetUserIds(
  userId: string,
  lookbackMs: number
): Promise<string[]> {
  const since = Timestamp.fromMillis(Date.now() - lookbackMs);
  try {
    const snap = await db()
      .collection(BLIND_MEETING_COLLECTIONS.matchHistory)
      .doc(userId)
      .collection("metUsers")
      .where("metAt", ">=", since)
      .get();
    return snap.docs.map((d) => d.id);
  } catch (error) {
    logger.warn("blindMeeting history load failed", { userId, error });
    return [];
  }
}

async function isRestricted(userId: string): Promise<boolean> {
  try {
    const snap = await db()
      .collection(BLIND_MEETING_COLLECTIONS.restrictions)
      .doc(userId)
      .get();
    if (!snap.exists) return false;
    const until = snap.data()?.restrictedUntil;
    if (until instanceof Timestamp) {
      return until.toMillis() > Date.now();
    }
    return snap.data()?.restricted === true;
  } catch (error) {
    logger.warn("blindMeeting restriction load failed", { userId, error });
    return false;
  }
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
  appliedAtMs: number
): Promise<Candidate | null> {
  const [dnaSnap, userSnap, blocked, recentlyMet, restricted] =
    await Promise.all([
      db().collection(BLIND_MEETING_COLLECTIONS.dna).doc(userId).get(),
      db().collection("users").doc(userId).get(),
      loadBlockedUserIds(userId),
      loadRecentlyMetUserIds(userId, policy.recentlyMetLookbackMs),
      isRestricted(userId),
    ]);

  const dna = dnaSnap.data();
  const user = userSnap.data();
  if (!isRecord(dna) || !isRecord(user)) return null;

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

  return {
    userId,
    atmosphere,
    initiative,
    purpose,
    alcoholPreference: oneOf(
      ALCOHOL_PREFERENCES,
      dna.alcoholCompanionPreference,
      "noPreference"
    ),
    smokingPreference: oneOf(
      SMOKING_PREFERENCES,
      dna.smokingCompanionPreference,
      "noPreference"
    ),
    drinkingLevel: oneOf(
      DRINKING_LEVELS,
      dna.drinkingLevelSnapshot,
      "sometimes"
    ),
    smokingStatus: oneOf(
      SMOKING_STATUSES,
      dna.smokingStatusSnapshot,
      "nonSmoker"
    ),
    interestIds: asStrArray(dna.interestIds),
    mbti: asTrimmedOrNull(dna.mbtiSnapshot),
    availableSlotIds: asStrArray(dna.availableSlotIds ?? dna.availableSlots)
      .filter(isValidSlotId),
    schoolVerified: user.isStudentVerified === true,
    eligible,
    blockedUserIds: blocked,
    recentlyMetUserIds: recentlyMet,
    waitedMinutes: Math.max(0, Math.floor((nowMs - appliedAtMs) / 60000)),
  };
}

/** 특정 슬롯에 신청한 활성 지원자 목록 */
export async function loadOpenApplications(
  slotId: string
): Promise<ApplicationDoc[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .where("requestedSlotIds", "array-contains", slotId)
    .where("open", "==", true)
    .get();

  const result: ApplicationDoc[] = [];
  for (const doc of snap.docs) {
    const application = readApplicationDoc(doc.id, doc.data());
    if (application == null) continue;
    if (
      application.status !== "applied" &&
      application.status !== "waitlisted"
    ) {
      continue;
    }
    result.push(application);
  }
  return result;
}

/** 대기 중인 모든 슬롯 id 수집 */
export async function loadOpenSlotIds(): Promise<string[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .where("open", "==", true)
    .get();
  const slots = new Set<string>();
  for (const doc of snap.docs) {
    for (const slotId of asStrArray(doc.data()?.requestedSlotIds)) {
      if (isValidSlotId(slotId)) slots.add(slotId);
    }
  }
  return [...slots].sort();
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
  slotId: string;
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

export async function updateParticipant(
  meetingId: string,
  userId: string,
  patch: {
    status?: ParticipantStatus;
    depositStatus?: DepositStatus;
    extra?: Record<string, unknown>;
  }
): Promise<void> {
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
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .collection(BLIND_MEETING_COLLECTIONS.participants)
    .doc(userId)
    .set(payload, { merge: true });
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

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId)
    .set(payload, { merge: true });
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
