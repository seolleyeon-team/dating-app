/**
 * 블라인드 취향 미팅 선결 파티(1~3명).
 *
 * 파티는 최종 teamA/teamB와 다르다. 친구끼리 함께 신청하기 위한 원자적
 * 단위이며, 서버가 잠근 roster는 한 미팅의 같은 편으로만 이동한다.
 */
import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { readBlindMeetingGender, type BlindMeetingGender } from "./genderBalance";
import {
  ALCOHOL_PREFERENCES,
  BLIND_MEETING_COLLECTIONS,
  MEETING_PURPOSES,
  SMOKING_PREFERENCES,
  asStr,
  asStrArray,
  asTrimmedOrNull,
  isRecord,
  normalizeDateKeys,
  oneOfOrNull,
  type AlcoholCompanionPreference,
  type MeetingPurpose,
  type SmokingCompanionPreference,
} from "./types";
import { db } from "./store";
import { notifyBlindMeetingParty } from "./notifications";

async function notifyPartyBestEffort(
  params: Parameters<typeof notifyBlindMeetingParty>[0]
): Promise<void> {
  try {
    await notifyBlindMeetingParty(params);
  } catch {
    // 파티 상태 트랜잭션은 이미 성공했으므로 알림 장애로 사용자의 재시도가
    // 중복 초대/중복 응답처럼 보이게 만들지 않는다.
    logger.warn("blind meeting party notification failed", {
      kind: params.kind,
    });
  }
}

export type BlindMeetingPartyStatus =
  | "forming"
  | "locked"
  | "ready"
  | "matched"
  | "cancelled";

export type BlindMeetingPartyDoc = {
  partyId: string;
  leaderUserId: string;
  acceptedUserIds: string[];
  pendingInviteeIds: string[];
  pendingInviteIds: string[];
  canonicalGender: BlindMeetingGender;
  status: BlindMeetingPartyStatus;
  rosterVersion: number;
  completedApplicationUserIds: string[];
  meetingId: string | null;
};

export type EffectivePartyPreferences = {
  meetingPurpose: MeetingPurpose;
  alcoholCompanionPreference: AlcoholCompanionPreference;
  smokingCompanionPreference: SmokingCompanionPreference;
  waitlistOptIn: boolean;
};

const ACTIVE_PARTY_STATUSES = new Set<BlindMeetingPartyStatus>([
  "forming",
  "locked",
  "ready",
  "matched",
]);

function membershipRef(userId: string) {
  return db().collection(BLIND_MEETING_COLLECTIONS.partyMemberships).doc(userId);
}

function partyRef(partyId: string) {
  return db().collection(BLIND_MEETING_COLLECTIONS.parties).doc(partyId);
}

function readParty(partyId: string, raw: unknown): BlindMeetingPartyDoc | null {
  if (!isRecord(raw)) return null;
  const acceptedUserIds = asStrArray(raw.acceptedUserIds).slice(0, 3);
  const canonicalGender = readBlindMeetingGender({ gender: raw.canonicalGender });
  const status = asStr(raw.status, "") as BlindMeetingPartyStatus;
  const leaderUserId = asTrimmedOrNull(raw.leaderUserId);
  if (
    !leaderUserId ||
    acceptedUserIds.length < 1 ||
    acceptedUserIds.length > 3 ||
    !acceptedUserIds.includes(leaderUserId) ||
    canonicalGender == null ||
    !ACTIVE_PARTY_STATUSES.has(status) && status !== "cancelled"
  ) {
    return null;
  }
  return {
    partyId,
    leaderUserId,
    acceptedUserIds,
    pendingInviteeIds: asStrArray(raw.pendingInviteeIds).slice(0, 2),
    pendingInviteIds: asStrArray(raw.pendingInviteIds).slice(0, 2),
    canonicalGender,
    status,
    rosterVersion: Math.max(1, Math.floor(Number(raw.rosterVersion) || 1)),
    completedApplicationUserIds: asStrArray(raw.completedApplicationUserIds),
    meetingId: asTrimmedOrNull(raw.meetingId),
  };
}

function profileSnapshot(userId: string, user: Record<string, unknown>) {
  const onboarding = isRecord(user.onboarding) ? user.onboarding : {};
  const photos = Array.isArray(onboarding.photoUrls)
    ? onboarding.photoUrls.filter((item): item is string => typeof item === "string")
    : [];
  return {
    userId,
    nickname: asStr(onboarding.nickname ?? user.nickname ?? "친구", "친구").slice(0, 40),
    profileImageUrl: asStr(
      photos[0] ?? user.profileImageUrl ?? onboarding.representativeImageUrl ?? "",
      ""
    ).slice(0, 2048),
    mbti: asStr(onboarding.mbti ?? "", "").slice(0, 8),
  };
}

export function aggregatePartyPreferences(
  dnaDocs: Record<string, unknown>[]
): EffectivePartyPreferences | null {
  if (dnaDocs.length === 0) return null;
  const purposes: MeetingPurpose[] = [];
  const alcohol: AlcoholCompanionPreference[] = [];
  const smoking: SmokingCompanionPreference[] = [];
  let waitlistOptIn = true;
  for (const dna of dnaDocs) {
    const purpose = oneOfOrNull(MEETING_PURPOSES, dna.meetingPurpose);
    const alcoholPreference = oneOfOrNull(
      ALCOHOL_PREFERENCES,
      dna.alcoholCompanionPreference
    );
    const smokingPreference = oneOfOrNull(
      SMOKING_PREFERENCES,
      dna.smokingCompanionPreference
    );
    if (!purpose || !alcoholPreference || !smokingPreference) return null;
    purposes.push(purpose);
    alcohol.push(alcoholPreference);
    smoking.push(smokingPreference);
    waitlistOptIn = waitlistOptIn && dna.waitlistOptIn !== false;
  }
  return {
    meetingPurpose: purposes.includes("friendship")
      ? "friendship"
      : purposes.includes("both")
        ? "both"
        : "romance",
    alcoholCompanionPreference: alcohol.includes("allSober")
      ? "allSober"
      : alcohol.includes("lightOkay")
        ? "lightOkay"
        : "noPreference",
    smokingCompanionPreference: smoking.includes("nonSmokersOnly")
      ? "nonSmokersOnly"
      : smoking.includes("noIndoorSmoking")
        ? "noIndoorSmoking"
        : "noPreference",
    waitlistOptIn,
  };
}

function commonDates(dateLists: string[][]): string[] {
  if (dateLists.length === 0) return [];
  let shared = new Set(normalizeDateKeys(dateLists[0]));
  for (const dates of dateLists.slice(1)) {
    const next = new Set(normalizeDateKeys(dates));
    shared = new Set([...shared].filter((date) => next.has(date)));
  }
  return [...shared].sort();
}

export async function loadActivePartyForUser(
  userId: string
): Promise<BlindMeetingPartyDoc | null> {
  const membership = await membershipRef(userId).get();
  const partyId = asTrimmedOrNull(membership.data()?.partyId);
  if (!partyId || membership.data()?.active !== true) return null;
  const snap = await partyRef(partyId).get();
  const party = readParty(partyId, snap.data());
  if (!party || !ACTIVE_PARTY_STATUSES.has(party.status)) return null;
  if (!party.acceptedUserIds.includes(userId)) return null;
  return party;
}

export async function ensureBlindMeetingParty(userId: string): Promise<BlindMeetingPartyDoc> {
  const existing = await loadActivePartyForUser(userId);
  if (existing) return existing;

  const firestore = db();
  const userRef = firestore.collection("users").doc(userId);
  const applicationRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.applications)
    .doc(userId);
  const draftRef = firestore.collection(BLIND_MEETING_COLLECTIONS.dnaDrafts).doc(userId);
  const newPartyRef = firestore.collection(BLIND_MEETING_COLLECTIONS.parties).doc();

  return firestore.runTransaction(async (tx) => {
    const [membership, user, application, draft] = await Promise.all([
      tx.get(membershipRef(userId)),
      tx.get(userRef),
      tx.get(applicationRef),
      tx.get(draftRef),
    ]);
    if (membership.data()?.active === true) {
      const linkedId = asTrimmedOrNull(membership.data()?.partyId);
      if (linkedId) {
        const linked = await tx.get(partyRef(linkedId));
        const parsed = readParty(linkedId, linked.data());
        if (parsed && ACTIVE_PARTY_STATUSES.has(parsed.status)) return parsed;
      }
    }
    if (!user.exists) throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    const userData = (user.data() ?? {}) as Record<string, unknown>;
    const gender = readBlindMeetingGender(userData);
    if (!gender) {
      throw new HttpsError("failed-precondition", "블라인드 미팅 성별 정보를 확인할 수 없어요.");
    }
    const applicationData = application.data() ?? {};
    if (
      application.exists &&
      applicationData.serverStatus !== "cancelled" &&
      applicationData.status !== "cancelled"
    ) {
      throw new HttpsError("failed-precondition", "이미 진행 중인 블라인드 미팅 신청이 있어요.");
    }
    if (draft.exists && draft.data()?.status === "in_progress") {
      throw new HttpsError("failed-precondition", "작성 중인 미팅 DNA를 먼저 이어서 완료해주세요.");
    }
    const partyId = newPartyRef.id;
    tx.create(newPartyRef, {
      partyId,
      leaderUserId: userId,
      acceptedUserIds: [userId],
      pendingInviteeIds: [],
      pendingInviteIds: [],
      memberCount: 1,
      canonicalGender: gender,
      status: "forming",
      rosterVersion: 1,
      completedApplicationUserIds: [],
      memberProfiles: { [userId]: profileSnapshot(userId, userData) },
      meetingId: null,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
      lockedAt: null,
      readyAt: null,
    });
    tx.set(membershipRef(userId), {
      userId,
      partyId,
      active: true,
      rosterVersion: 1,
      updatedAt: FieldValue.serverTimestamp(),
    });
    return readParty(partyId, {
      partyId,
      leaderUserId: userId,
      acceptedUserIds: [userId],
      pendingInviteeIds: [],
      pendingInviteIds: [],
      canonicalGender: gender,
      status: "forming",
      rosterVersion: 1,
      completedApplicationUserIds: [],
      meetingId: null,
    })!;
  });
}

export async function createBlindMeetingPartyInvite(params: {
  userId: string;
  partyId: string;
  inviteeUserId: string;
}): Promise<{ inviteId: string }> {
  if (!params.inviteeUserId || params.inviteeUserId === params.userId) {
    throw new HttpsError("invalid-argument", "초대할 친구를 확인해주세요.");
  }
  const firestore = db();
  const inviteRef = firestore.collection(BLIND_MEETING_COLLECTIONS.partyInvites).doc();
  const pRef = partyRef(params.partyId);
  await firestore.runTransaction(async (tx) => {
    const [partySnap, friendSnap, inviteeSnap, inviteeMembership, inviteeApp] =
      await Promise.all([
        tx.get(pRef),
        tx.get(
          firestore
            .collection("users")
            .doc(params.userId)
            .collection("friends")
            .doc(params.inviteeUserId)
        ),
        tx.get(firestore.collection("users").doc(params.inviteeUserId)),
        tx.get(membershipRef(params.inviteeUserId)),
        tx.get(
          firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(params.inviteeUserId)
        ),
      ]);
    const party = readParty(params.partyId, partySnap.data());
    if (!party || party.status !== "forming" || party.leaderUserId !== params.userId) {
      throw new HttpsError("permission-denied", "이 팀에서는 친구를 초대할 수 없어요.");
    }
    if (!friendSnap.exists) {
      throw new HttpsError("failed-precondition", "설레연 친구만 초대할 수 있어요.");
    }
    if (!inviteeSnap.exists) throw new HttpsError("not-found", "친구 정보를 찾을 수 없어요.");
    const invitee = (inviteeSnap.data() ?? {}) as Record<string, unknown>;
    if (
      invitee.isStudentVerified !== true ||
      invitee.isWithdrawn === true ||
      invitee.loginDisabled === true ||
      readBlindMeetingGender(invitee) !== party.canonicalGender
    ) {
      throw new HttpsError("failed-precondition", "같은 편으로 참가할 수 있는 친구만 초대할 수 있어요.");
    }
    if (inviteeMembership.data()?.active === true) {
      throw new HttpsError("already-exists", "이미 다른 블라인드 팀에 참여 중인 친구예요.");
    }
    if (
      inviteeApp.exists &&
      inviteeApp.data()?.serverStatus !== "cancelled" &&
      inviteeApp.data()?.status !== "cancelled"
    ) {
      throw new HttpsError("failed-precondition", "이미 블라인드 미팅을 신청한 친구예요.");
    }
    if (
      party.acceptedUserIds.length + party.pendingInviteeIds.length >= 3 ||
      party.pendingInviteeIds.includes(params.inviteeUserId)
    ) {
      throw new HttpsError("failed-precondition", "초대할 수 있는 자리가 없거나 이미 초대했어요.");
    }
    tx.create(inviteRef, {
      inviteId: inviteRef.id,
      partyId: party.partyId,
      inviterUserId: params.userId,
      inviteeUserId: params.inviteeUserId,
      rosterVersion: party.rosterVersion,
      status: "pending",
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
      expiresAt: Timestamp.fromMillis(Date.now() + 7 * 24 * 60 * 60 * 1000),
    });
    tx.update(pRef, {
      pendingInviteeIds: [...party.pendingInviteeIds, params.inviteeUserId],
      pendingInviteIds: [...party.pendingInviteIds, inviteRef.id],
      updatedAt: FieldValue.serverTimestamp(),
    });
  });
  await notifyPartyBestEffort({
    userIds: [params.inviteeUserId],
    partyId: params.partyId,
    kind: "party_invite",
    dedupeSuffix: inviteRef.id,
  });
  return { inviteId: inviteRef.id };
}

export async function respondBlindMeetingPartyInvite(params: {
  userId: string;
  inviteId: string;
  accept: boolean;
}): Promise<{ partyId: string; status: string }> {
  const firestore = db();
  const inviteRef = firestore.collection(BLIND_MEETING_COLLECTIONS.partyInvites).doc(params.inviteId);
  const result = await firestore.runTransaction(async (tx) => {
    const inviteSnap = await tx.get(inviteRef);
    const invite = inviteSnap.data() ?? {};
    const partyId = asTrimmedOrNull(invite.partyId);
    const inviterUserId = asTrimmedOrNull(invite.inviterUserId);
    if (
      !partyId ||
      !inviterUserId ||
      invite.inviteeUserId !== params.userId ||
      invite.status !== "pending"
    ) {
      throw new HttpsError("failed-precondition", "응답할 수 없는 초대예요.");
    }
    const pRef = partyRef(partyId);
    const [partySnap, membership, userSnap, applicationSnap, friendshipSnap] =
      await Promise.all([
        tx.get(pRef),
        tx.get(membershipRef(params.userId)),
        tx.get(firestore.collection("users").doc(params.userId)),
        tx.get(
          firestore
            .collection(BLIND_MEETING_COLLECTIONS.applications)
            .doc(params.userId)
        ),
        tx.get(
          firestore
            .collection("users")
            .doc(inviterUserId)
            .collection("friends")
            .doc(params.userId)
        ),
      ]);
    const party = readParty(partyId, partySnap.data());
    if (!party || party.status !== "forming" || party.rosterVersion !== invite.rosterVersion) {
      throw new HttpsError("failed-precondition", "팀 구성이 변경되어 초대가 만료됐어요.");
    }
    const pendingInviteeIds = party.pendingInviteeIds.filter((id) => id !== params.userId);
    const pendingInviteIds = party.pendingInviteIds.filter((id) => id !== params.inviteId);
    if (!params.accept) {
      tx.update(inviteRef, {
        status: "declined",
        respondedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });
      tx.update(pRef, { pendingInviteeIds, pendingInviteIds, updatedAt: FieldValue.serverTimestamp() });
      return {
        partyId,
        status: "declined",
        leaderUserId: party.leaderUserId,
      };
    }
    if (membership.data()?.active === true) {
      throw new HttpsError("already-exists", "이미 다른 블라인드 팀에 참여 중이에요.");
    }
    if (!friendshipSnap.exists) {
      throw new HttpsError(
        "failed-precondition",
        "현재 설레연 친구인 경우에만 초대를 수락할 수 있어요."
      );
    }
    const application = applicationSnap.data() ?? {};
    if (
      applicationSnap.exists &&
      application.serverStatus !== "cancelled" &&
      application.status !== "cancelled"
    ) {
      throw new HttpsError("failed-precondition", "진행 중인 블라인드 미팅 신청이 있어요.");
    }
    const user = (userSnap.data() ?? {}) as Record<string, unknown>;
    if (
      !userSnap.exists ||
      user.isStudentVerified !== true ||
      user.isWithdrawn === true ||
      user.loginDisabled === true ||
      readBlindMeetingGender(user) !== party.canonicalGender ||
      party.acceptedUserIds.length >= 3
    ) {
      throw new HttpsError("failed-precondition", "현재 이 팀에 참여할 수 없어요.");
    }
    const nextVersion = party.rosterVersion + 1;
    tx.update(inviteRef, {
      status: "accepted",
      respondedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.update(pRef, {
      acceptedUserIds: [...party.acceptedUserIds, params.userId],
      pendingInviteeIds,
      pendingInviteIds,
      memberCount: party.acceptedUserIds.length + 1,
      rosterVersion: nextVersion,
      [`memberProfiles.${params.userId}`]: profileSnapshot(params.userId, user),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.set(membershipRef(params.userId), {
      userId: params.userId,
      partyId,
      active: true,
      rosterVersion: nextVersion,
      updatedAt: FieldValue.serverTimestamp(),
    });
    return {
      partyId,
      status: "accepted",
      leaderUserId: party.leaderUserId,
    };
  });
  if (result.status === "accepted") {
    await notifyPartyBestEffort({
      userIds: [result.leaderUserId],
      partyId: result.partyId,
      kind: "party_joined",
      dedupeSuffix: params.inviteId,
    });
  }
  return { partyId: result.partyId, status: result.status };
}

export async function lockBlindMeetingParty(
  userId: string,
  partyId: string
): Promise<BlindMeetingPartyDoc> {
  const firestore = db();
  const pRef = partyRef(partyId);
  const result = await firestore.runTransaction(async (tx) => {
    const partySnap = await tx.get(pRef);
    const party = readParty(partyId, partySnap.data());
    if (!party || party.leaderUserId !== userId || party.status !== "forming") {
      throw new HttpsError("failed-precondition", "현재 팀 구성을 확정할 수 없어요.");
    }
    const inviteRefs = party.pendingInviteIds.map((id) =>
      firestore.collection(BLIND_MEETING_COLLECTIONS.partyInvites).doc(id)
    );
    const inviteSnaps = await Promise.all(inviteRefs.map((ref) => tx.get(ref)));
    for (let i = 0; i < inviteRefs.length; i++) {
      if (inviteSnaps[i].data()?.status === "pending") {
        tx.update(inviteRefs[i], {
          status: "cancelled",
          updatedAt: FieldValue.serverTimestamp(),
        });
      }
    }
    const nextVersion = party.rosterVersion + 1;
    tx.update(pRef, {
      status: "locked",
      pendingInviteeIds: [],
      pendingInviteIds: [],
      rosterVersion: nextVersion,
      lockedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    for (const memberId of party.acceptedUserIds) {
      tx.set(membershipRef(memberId), {
        userId: memberId,
        partyId,
        active: true,
        rosterVersion: nextVersion,
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    }
    return {
      ...party,
      status: "locked" as const,
      pendingInviteeIds: [],
      pendingInviteIds: [],
      rosterVersion: nextVersion,
    };
  });
  await notifyPartyBestEffort({
    userIds: result.acceptedUserIds,
    partyId: result.partyId,
    kind: "party_locked",
    dedupeSuffix: String(result.rosterVersion),
  });
  return result;
}

/**
 * 모든 멤버 신청을 읽어 파티 readiness를 한 트랜잭션에서 맞춘다.
 * 반환된 날짜에 대해서만 inline matcher를 실행해야 한다.
 */
export async function reconcileBlindMeetingParty(
  partyId: string
): Promise<{ ready: boolean; commonDateKeys: string[]; completedCount: number; memberCount: number }> {
  const firestore = db();
  const pRef = partyRef(partyId);
  const result = await firestore.runTransaction(async (tx) => {
    const partySnap = await tx.get(pRef);
    const party = readParty(partyId, partySnap.data());
    if (!party || (party.status !== "locked" && party.status !== "ready")) {
      throw new HttpsError("failed-precondition", "잠긴 블라인드 팀을 찾을 수 없어요.");
    }
    const applicationRefs = party.acceptedUserIds.map((id) =>
      firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(id)
    );
    const dnaRefs = party.acceptedUserIds.map((id) =>
      firestore.collection(BLIND_MEETING_COLLECTIONS.dna).doc(id)
    );
    const [applications, dnaSnaps] = await Promise.all([
      Promise.all(applicationRefs.map((ref) => tx.get(ref))),
      Promise.all(dnaRefs.map((ref) => tx.get(ref))),
    ]);
    const completedIds: string[] = [];
    const dateLists: string[][] = [];
    const dnaDocs: Record<string, unknown>[] = [];
    for (let i = 0; i < party.acceptedUserIds.length; i++) {
      const application = applications[i].data() ?? {};
      if (application.dnaApplicationCompleted === true && dnaSnaps[i].exists) {
        completedIds.push(party.acceptedUserIds[i]);
        dateLists.push(asStrArray(application.requestedDateKeys));
        dnaDocs.push((dnaSnaps[i].data() ?? {}) as Record<string, unknown>);
      }
    }
    const allCompleted = completedIds.length === party.acceptedUserIds.length;
    const sharedDates = allCompleted ? commonDates(dateLists) : [];
    const effective = allCompleted ? aggregatePartyPreferences(dnaDocs) : null;
    const ready = allCompleted && sharedDates.length > 0 && effective != null;
    const stage = !allCompleted
      ? "waitingForPartyMembers"
      : sharedDates.length === 0
        ? "waitingForCommonDates"
        : "searchingCandidates";

    tx.set(pRef, {
      status: ready ? "ready" : "locked",
      completedApplicationUserIds: completedIds,
      memberCount: party.acceptedUserIds.length,
      commonDateCount: sharedDates.length,
      updatedAt: FieldValue.serverTimestamp(),
      ...(ready ? { readyAt: FieldValue.serverTimestamp() } : { readyAt: null }),
    }, { merge: true });
    for (let i = 0; i < applications.length; i++) {
      if (!applications[i].exists) continue;
      tx.set(applicationRefs[i], {
        partyId,
        partyMemberIds: party.acceptedUserIds,
        partySize: party.acceptedUserIds.length,
        partyRosterVersion: party.rosterVersion,
        partyReady: ready,
        partyCommonDateKeys: sharedDates,
        open: ready,
        stage,
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    }
    const matchingRef = firestore.collection(BLIND_MEETING_COLLECTIONS.partyMatching).doc(partyId);
    if (ready && effective) {
      tx.set(matchingRef, {
        partyId,
        rosterVersion: party.rosterVersion,
        memberUserIds: party.acceptedUserIds,
        commonDateKeys: sharedDates,
        effectivePreferences: effective,
        policyVersion: "blind_party_conservative_v1",
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    } else {
      tx.delete(matchingRef);
    }
    return {
      ready,
      commonDateKeys: sharedDates,
      completedCount: completedIds.length,
      memberCount: party.acceptedUserIds.length,
      memberUserIds: party.acceptedUserIds,
      rosterVersion: party.rosterVersion,
    };
  });
  await notifyPartyBestEffort({
    userIds: result.memberUserIds,
    partyId,
    kind: result.ready ? "party_ready" : "party_member_completed",
    dedupeSuffix: `${result.rosterVersion}:${result.completedCount}`,
  });
  return {
    ready: result.ready,
    commonDateKeys: result.commonDateKeys,
    completedCount: result.completedCount,
    memberCount: result.memberCount,
  };
}

export async function cancelBlindMeetingParty(userId: string, partyId: string): Promise<void> {
  const firestore = db();
  const pRef = partyRef(partyId);
  await firestore.runTransaction(async (tx) => {
    const partySnap = await tx.get(pRef);
    const party = readParty(partyId, partySnap.data());
    if (!party || !party.acceptedUserIds.includes(userId)) return;
    if (party.status === "matched") {
      throw new HttpsError("failed-precondition", "이미 배정된 미팅에서는 팀 신청을 취소할 수 없어요.");
    }
    const applicationRefs = party.acceptedUserIds.map((id) =>
      firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(id)
    );
    const applicationSnaps = await Promise.all(applicationRefs.map((ref) => tx.get(ref)));
    tx.set(pRef, {
      status: "cancelled",
      meetingId: null,
      updatedAt: FieldValue.serverTimestamp(),
      cancelledAt: FieldValue.serverTimestamp(),
      cancelledByUserId: userId,
    }, { merge: true });
    for (let i = 0; i < party.acceptedUserIds.length; i++) {
      tx.set(membershipRef(party.acceptedUserIds[i]), {
        active: false,
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      if (applicationSnaps[i].exists && !asTrimmedOrNull(applicationSnaps[i].data()?.meetingId)) {
        tx.set(applicationRefs[i], {
          open: false,
          status: "cancelled",
          serverStatus: "cancelled",
          stage: "cancelled",
          updatedAt: FieldValue.serverTimestamp(),
        }, { merge: true });
      }
    }
    tx.delete(firestore.collection(BLIND_MEETING_COLLECTIONS.partyMatching).doc(partyId));
  });
}

/**
 * 매칭 초대 단계에서 파티 한 명이 거절하면 해당 파티 전원을 그 미팅에서
 * 함께 철회한다. 이 경로에서는 자동 재신청하지 않아 이후 서로 다른 미팅에
 * 배정되는 상황을 원천 차단한다.
 */
export async function withdrawMatchedBlindMeetingParty(params: {
  userId: string;
  partyId: string;
  meetingId: string;
  reason: string | null;
}): Promise<string[]> {
  const firestore = db();
  const pRef = partyRef(params.partyId);
  return firestore.runTransaction(async (tx) => {
    const partySnap = await tx.get(pRef);
    const party = readParty(params.partyId, partySnap.data());
    if (
      !party ||
      party.status !== "matched" ||
      party.meetingId !== params.meetingId ||
      !party.acceptedUserIds.includes(params.userId) ||
      party.acceptedUserIds.length < 2
    ) {
      throw new HttpsError(
        "failed-precondition",
        "함께 배정된 친구 팀을 확인할 수 없어요."
      );
    }
    const applicationRefs = party.acceptedUserIds.map((memberId) =>
      firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(memberId)
    );
    const participantRefs = party.acceptedUserIds.map((memberId) =>
      firestore
        .collection(BLIND_MEETING_COLLECTIONS.meetings)
        .doc(params.meetingId)
        .collection("participants")
        .doc(memberId)
    );
    const [applications, participants] = await Promise.all([
      Promise.all(applicationRefs.map((ref) => tx.get(ref))),
      Promise.all(participantRefs.map((ref) => tx.get(ref))),
    ]);
    if (
      applications.some(
        (snap) => !snap.exists || snap.data()?.meetingId !== params.meetingId
      ) ||
      participants.some((snap) => !snap.exists)
    ) {
      throw new HttpsError(
        "failed-precondition",
        "친구 팀의 미팅 배정 상태가 일치하지 않아요."
      );
    }
    tx.set(
      pRef,
      {
        status: "cancelled",
        meetingId: null,
        cancelledByUserId: params.userId,
        cancelledAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    for (let i = 0; i < party.acceptedUserIds.length; i++) {
      const memberId = party.acceptedUserIds[i];
      tx.set(
        membershipRef(memberId),
        { active: false, updatedAt: FieldValue.serverTimestamp() },
        { merge: true }
      );
      tx.set(
        applicationRefs[i],
        {
          open: false,
          status: "cancelled",
          serverStatus: "cancelled",
          stage: "cancelled",
          meetingId: params.meetingId,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      tx.set(
        participantRefs[i],
        {
          status: "cancelled",
          serverStatus: "cancelled",
          cancelReason:
            memberId === params.userId
              ? params.reason
              : "friend_party_member_declined",
          cancelledAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    }
    return party.acceptedUserIds;
  });
}
