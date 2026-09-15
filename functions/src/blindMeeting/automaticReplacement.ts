/** Automatic, no-acceptance replacement for blind meeting chat departures. */
import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { createHash } from "node:crypto";
import { HttpsError } from "firebase-functions/v2/https";

import { loadCampusLifeZoneEnforced } from "../campusLifeZoneActivation";
import { Candidate, checkGroupConstraints, groupCommonDateKeys } from "./matching";
import { notifyBlindMeeting } from "./notifications";
import {
  ApplicationDoc,
  appendSystemMessage,
  buildPublicProfile,
  db,
  loadAllOpenApplications,
  loadCandidate,
  loadMeeting,
  loadPolicy,
} from "./store";
import {
  BLIND_MEETING_COLLECTIONS,
  PARTICIPANT_STATUS_TO_APP,
  asStrArray,
  formatDateKey,
  kstDayOf,
} from "./types";

type Vacancy = { userId: string; team: "teamA" | "teamB" };
type PartyUnit = { members: Candidate[]; appliedAtMs: number; partyId: string };

function futureCommonDates(members: Candidate[]): string[] {
  const today = formatDateKey(kstDayOf(Date.now()));
  return groupCommonDateKeys(members).filter((key) => key >= today);
}

function partyUnits(
  applications: ApplicationDoc[],
  candidates: Map<string, Candidate>
): PartyUnit[] {
  const appsByUid = new Map(applications.map((app) => [app.userId, app]));
  const byParty = new Map<string, ApplicationDoc[]>();
  for (const app of applications) {
    const list = byParty.get(app.partyId) ?? [];
    list.push(app);
    byParty.set(app.partyId, list);
  }
  const result: PartyUnit[] = [];
  for (const [partyId, apps] of byParty) {
    const declared = apps[0]?.partyMemberIds ?? [];
    // A friend party may only enter as its complete, still-waiting unit.
    if (declared.length === 0 || declared.some((uid) => !appsByUid.has(uid))) continue;
    const members = declared.map((uid) => candidates.get(uid)).filter((c): c is Candidate => c != null);
    if (members.length !== declared.length) continue;
    result.push({
      partyId,
      members,
      appliedAtMs: Math.min(...apps.map((app) => app.appliedAtMs)),
    });
  }
  // When multiple seats are empty, a fitting friend party is preferred over
  // splitting the space with earlier solo applications. Within a class FIFO wins.
  return result.sort(
    (a, b) => b.members.length - a.members.length || a.appliedAtMs - b.appliedAtMs || a.partyId.localeCompare(b.partyId)
  );
}

function assignParty(
  unit: PartyUnit,
  vacancies: Vacancy[],
  roster: Map<string, Candidate>,
  alcoholFree: boolean,
  campusLifeZoneEnforced: boolean
): { assignments: Map<string, Candidate>; commonDates: string[] } | null {
  if (unit.members.length > vacancies.length) return null;
  const available = [...vacancies];
  const assignments = new Map<string, Candidate>();
  for (const member of unit.members) {
    const index = available.findIndex((seat) => {
      const old = roster.get(seat.userId);
      return old != null && old.gender === member.gender;
    });
    if (index < 0) return null;
    const [seat] = available.splice(index, 1);
    assignments.set(seat.userId, member);
  }
  const next = new Map(roster);
  assignments.forEach((candidate, departedUid) => next.set(departedUid, candidate));
  const members = [...next.values()];
  const commonDates = futureCommonDates(members);
  if (commonDates.length === 0) return null;
  if (checkGroupConstraints(members, commonDates[0], alcoholFree, 6, campusLifeZoneEnforced).length > 0) {
    return null;
  }
  return { assignments, commonDates };
}

/** A participant leaves the group room immediately; no heart refund is issued. */
export async function leaveBlindMeeting(params: { meetingId: string; userId: string }): Promise<void> {
  const firestore = db();
  const policy = await loadPolicy();
  const meetingRef = firestore.collection(BLIND_MEETING_COLLECTIONS.meetings).doc(params.meetingId);
  const participantRef = meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).doc(params.userId);
  await firestore.runTransaction(async (tx) => {
    const [meetingSnap, participantSnap] = await Promise.all([tx.get(meetingRef), tx.get(participantRef)]);
    if (!meetingSnap.exists || !participantSnap.exists) throw new HttpsError("not-found", "참가 중인 미팅을 찾을 수 없어요.");
    const meeting = meetingSnap.data() ?? {};
    if (!asStrArray(meeting.participantIds).includes(params.userId)) throw new HttpsError("permission-denied", "참가 중인 미팅이 아니에요.");
    const status = String(participantSnap.data()?.serverStatus ?? "");
    if (status !== "confirmed") throw new HttpsError("failed-precondition", "현재는 미팅에서 나갈 수 없어요.");
    const roomId = String(meeting.groupChatId ?? "");
    if (!roomId) throw new HttpsError("failed-precondition", "채팅방을 찾을 수 없어요.");
    const roomRef = firestore.collection("chat_rooms").doc(roomId);
    const roomSnap = await tx.get(roomRef);
    const room = roomSnap.data() ?? {};
    const memberIds = asStrArray(room.participantIds).filter((uid) => uid !== params.userId);
    const info = { ...(room.participantInfo as Record<string, unknown> ?? {}) };
    const nickname = (info[params.userId] as Record<string, unknown> | undefined)?.nickname;
    const leaveMessage = `${typeof nickname === "string" && nickname.trim().length > 0 ? nickname.trim() : "참가자 한 분"}님이 나갔습니다. 설레연이 곧 대타를 구해서 초대할게요.`;
    delete info[params.userId];
    const messageRef = roomRef.collection("messages").doc();
    const deadline = meeting.replacementSearchDeadlineAt instanceof Timestamp
      ? meeting.replacementSearchDeadlineAt
      : Timestamp.fromMillis(Date.now() + policy.replacementSearchWindowMs);
    tx.set(participantRef, {
      status: PARTICIPANT_STATUS_TO_APP.cancelled,
      serverStatus: "cancelled",
      leftByUser: true,
      replacementSearchActive: true,
      leftAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.set(meetingRef, {
      replacementSearchActive: true,
      replacementSearchDeadlineAt: deadline,
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.set(roomRef, {
      participantIds: memberIds,
      participantInfo: info,
      lastMessage: leaveMessage,
      lastMessageAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    tx.create(messageRef, {
      senderId: "system",
      type: "system",
      text: leaveMessage,
      readBy: [],
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.set(firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(params.userId), {
      status: PARTICIPANT_STATUS_TO_APP.cancelled,
      serverStatus: "cancelled",
      stage: "cancelled",
      open: false,
      meetingId: null,
      leftMeetingAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
  });
  await fillBlindMeetingVacancies(params.meetingId);
}

/** Finds FIFO eligible replacement units and commits every selected member atomically. */
export async function fillBlindMeetingVacancies(meetingId: string): Promise<number> {
  const [meeting, policy, applications] = await Promise.all([loadMeeting(meetingId), loadPolicy(), loadAllOpenApplications()]);
  if (!meeting.raw.replacementSearchActive || meeting.status === "cancelled") return 0;
  const participantSnap = await db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId).collection(BLIND_MEETING_COLLECTIONS.participants).get();
  const vacancies: Vacancy[] = participantSnap.docs
    .filter((doc) => doc.data()?.replacementSearchActive === true && doc.data()?.serverStatus === "cancelled")
    .map((doc) => ({ userId: doc.id, team: doc.data()?.team === "teamB" ? "teamB" : "teamA" }));
  if (vacancies.length === 0) return 0;
  const allSeatCandidates = await Promise.all(meeting.participantIds.map((uid) => loadCandidate(uid, policy, Date.now(), Date.now())));
  const roster = new Map(allSeatCandidates.filter((c): c is Candidate => c != null).map((c) => [c.userId, c]));
  if (roster.size !== meeting.participantIds.length) return 0;
  const candidateRows = await Promise.all(applications.map(async (app) => [app.userId, await loadCandidate(app.userId, policy, Date.now(), app.appliedAtMs, app.partyId, app.partyMemberIds)] as const));
  const candidateMap = new Map(candidateRows.filter((row): row is readonly [string, Candidate] => row[1] != null));
  const enforced = await loadCampusLifeZoneEnforced(db(), { unknownAs: "enforced" });
  let remaining = [...vacancies];
  let nextRoster = new Map(roster);
  const selections = new Map<string, Candidate>();
  let commonDates = futureCommonDates([...nextRoster.values()]);
  for (const unit of partyUnits(applications, candidateMap)) {
    const assignment = assignParty(unit, remaining, nextRoster, meeting.isAlcoholFree, enforced);
    if (assignment == null) continue;
    assignment.assignments.forEach((candidate, departedUid) => selections.set(departedUid, candidate));
    nextRoster = new Map(nextRoster);
    assignment.assignments.forEach((candidate, departedUid) => nextRoster.set(departedUid, candidate));
    remaining = remaining.filter((seat) => !assignment.assignments.has(seat.userId));
    commonDates = assignment.commonDates;
    if (remaining.length === 0) break;
  }
  if (selections.size === 0) return 0;
  const profiles = await Promise.all([...selections.values()].map((candidate) => buildPublicProfile(candidate.userId)));
  const committed = await db().runTransaction(async (tx) => {
    const meetingRef = db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
    const roomRef = db().collection("chat_rooms").doc(meeting.groupChatId!);
    const departedIds = [...selections.keys()];
    const [freshMeeting, roomSnap, ...records] = await Promise.all([
      tx.get(meetingRef),
      tx.get(roomRef),
      ...departedIds.map((uid) => tx.get(meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).doc(uid))),
      ...[...selections.values()].map((candidate) => tx.get(db().collection(BLIND_MEETING_COLLECTIONS.applications).doc(candidate.userId))),
    ]);
    const departed = records.slice(0, departedIds.length);
    const apps = records.slice(departedIds.length);
    if (
      !freshMeeting.exists ||
      !roomSnap.exists ||
      departed.some((snap) => snap.data()?.serverStatus !== "cancelled" || snap.data()?.replacementSearchActive !== true) ||
      apps.some((snap) => snap.data()?.open !== true)
    ) {
      return false;
    }
    const data = freshMeeting.data() ?? {};
    if (data.replacementSearchActive !== true) return false;
    const nextIds = asStrArray(data.participantIds).map((uid) => selections.get(uid)?.userId ?? uid);
    const nextA = asStrArray(data.teamAUserIds).map((uid) => selections.get(uid)?.userId ?? uid);
    const nextB = asStrArray(data.teamBUserIds).map((uid) => selections.get(uid)?.userId ?? uid);
    const info = { ...((roomSnap.data()?.participantInfo as Record<string, unknown>) ?? {}) };
    selections.forEach((candidate, departedUid) => delete info[departedUid]);
    profiles.forEach((profile) => { info[profile.userId] = { nickname: profile.nickname, avatarUrl: "", avatarSeed: profile.avatarSeed }; });
    const oldDate = String(data.slotId ?? "").split("#")[0];
    const reschedule = oldDate.length > 0 && !commonDates.includes(oldDate);
    // 아직 약속을 정하는 중인 방은 새 참가자의 가능 날짜에 맞춰 처음부터
    // 투표해야 한다. 이미 확정된 시간이 새 참가자에게도 가능할 때만 유지한다.
    const resetVotes =
      reschedule ||
      String(data.serverStatus ?? "") === "chat_open" ||
      String(data.status ?? "") === "chatOpen";
    tx.set(meetingRef, {
      participantIds: nextIds,
      teamAUserIds: nextA,
      teamBUserIds: nextB,
      commonAvailableDateKeys: commonDates,
      replacementSearchActive: remaining.length > 0,
      ...(reschedule ? {
        status: "chatOpen",
        serverStatus: "chat_open",
        slotId: "",
        scheduledStartAt: FieldValue.delete(),
        confirmedDateKey: FieldValue.delete(),
        scheduleConfirmedAt: FieldValue.delete(),
        venue: null,
      } : {}),
      ...(resetVotes ? {
        scheduleVoteDeadlineAt: Timestamp.fromMillis(Date.now() + policy.scheduleVoteWindowMs),
        scheduleVoteRound: Math.max(0, Math.floor(Number(data.scheduleVoteRound ?? 0))) + 1,
        ...(reschedule
          ? { scheduleResetAt: FieldValue.serverTimestamp() }
          : { scheduleVoteRosterChangedAt: FieldValue.serverTimestamp() }),
      } : {}),
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    const roomMembers = asStrArray(roomSnap.data()?.participantIds);
    selections.forEach((candidate, departedUid) => {
      tx.set(meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).doc(departedUid), { replacementSearchActive: false, replacementUserId: candidate.userId, replacedAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      tx.set(meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).doc(candidate.userId), { userId: candidate.userId, team: nextA.includes(candidate.userId) ? "teamA" : "teamB", gender: candidate.gender, status: PARTICIPANT_STATUS_TO_APP.confirmed, serverStatus: "confirmed", isReplacement: true, joinedChatAt: FieldValue.serverTimestamp(), createdAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      tx.set(db().collection(BLIND_MEETING_COLLECTIONS.applications).doc(candidate.userId), { open: false, meetingId, status: PARTICIPANT_STATUS_TO_APP.confirmed, serverStatus: "confirmed", stage: "matched", updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      tx.set(meetingRef.collection(BLIND_MEETING_COLLECTIONS.publicProfiles).doc(candidate.userId), profiles.find((p) => p.userId === candidate.userId)!, { merge: true });
    });
    tx.set(roomRef, { participantIds: [...new Set([...roomMembers, ...[...selections.values()].map((c) => c.userId)])], participantInfo: info, updatedAt: FieldValue.serverTimestamp() }, { merge: true });
    return true;
  });
  if (!committed) return 0;
  for (const candidate of selections.values()) {
    const profile = profiles.find((item) => item.userId === candidate.userId);
    await appendSystemMessage(meeting.groupChatId!, `${profile?.nickname ?? "새 참가자"}님이 초대되었어요.`);
    await notifyBlindMeeting({ userIds: [candidate.userId], meetingId, kind: "matched", dedupeSuffix: `replacement_${candidate.userId}` });
  }
  return selections.size;
}

/** Re-runs matching until the configured deadline, then cancels and refunds remaining members 30H. */
export async function processBlindMeetingReplacementSearches(): Promise<void> {
  const snap = await db().collection(BLIND_MEETING_COLLECTIONS.meetings).where("replacementSearchActive", "==", true).get();
  for (const doc of snap.docs) {
    const deadline = doc.data()?.replacementSearchDeadlineAt;
    if (deadline instanceof Timestamp && deadline.toMillis() <= Date.now()) {
      await cancelReplacementFailedMeeting(doc.id);
    } else {
      await fillBlindMeetingVacancies(doc.id);
    }
  }
}

async function cancelReplacementFailedMeeting(meetingId: string): Promise<void> {
  const firestore = db();
  const meetingRef = firestore.collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
  const participantSnap = await meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).get();
  const remaining = participantSnap.docs.filter((doc) => doc.data()?.serverStatus === "confirmed").map((doc) => doc.id);
  await firestore.runTransaction(async (tx) => {
    const meetingSnap = await tx.get(meetingRef);
    if (!meetingSnap.exists || meetingSnap.data()?.serverStatus === "cancelled") return;
    const reads = await Promise.all(remaining.flatMap((uid) => [tx.get(firestore.collection("users").doc(uid)), tx.get(firestore.collection("heartTransactions").doc(createHash("sha256").update(`blind_meeting_replacement_cancel:${meetingId}:${uid}`).digest("hex")))]));
    tx.set(meetingRef, { status: "cancelled", serverStatus: "cancelled", replacementSearchActive: false, cancelledAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp() }, { merge: true });
    tx.set(firestore.collection("chat_rooms").doc(String(meetingSnap.data()?.groupChatId ?? "")), { participantIds: [], writable: false, status: "archived", updatedAt: FieldValue.serverTimestamp() }, { merge: true });
    remaining.forEach((uid, index) => {
      const user = reads[index * 2]; const refund = reads[index * 2 + 1];
      if (user.exists && !refund.exists) {
        const balance = Math.max(0, Math.floor(Number(user.data()?.heartBalance ?? 0))) + 30;
        tx.set(user.ref, { heartBalance: balance, heartBalanceUpdatedAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp() }, { merge: true });
        tx.create(refund.ref, { uid, feature: "blind_meeting", type: "meeting_cancel_refund", resourceId: meetingId, amount: 30, heartBalanceAfter: balance, createdAt: FieldValue.serverTimestamp() });
      }
      tx.set(meetingRef.collection(BLIND_MEETING_COLLECTIONS.participants).doc(uid), { status: PARTICIPANT_STATUS_TO_APP.cancelled, serverStatus: "cancelled", updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      tx.set(firestore.collection(BLIND_MEETING_COLLECTIONS.applications).doc(uid), { status: PARTICIPANT_STATUS_TO_APP.cancelled, serverStatus: "cancelled", open: false, meetingId: null, updatedAt: FieldValue.serverTimestamp() }, { merge: true });
    });
  });
  if (remaining.length > 0) await notifyBlindMeeting({ userIds: remaining, meetingId, kind: "cancelled", bodyOverride: "대타를 찾지 못해 미팅이 취소되었어요. 하트 30개를 돌려드렸어요.", dedupeSuffix: "replacement_timeout" });
}
