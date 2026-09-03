/**
 * 3:3 블라인드 취향 미팅 — 보증금 없는 전체 happy path E2E (Firestore Emulator).
 *
 * 실행 (repo root, Java 21 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-blind-nodeposit \
 *     "node --test functions/lib/blindMeeting/noDepositHappyPath.emulator-test.js"
 *
 * 실제 canonical 서버 진입점만 사용한다 (2026-09-03, 수락 단계 없음):
 *   runMatchingForDate → (매칭 tx 안에서 confirmed + 6인 채팅방) → chat_open
 *   → voteSchedule ×6 → schedule_confirmed → confirmAttendance
 *   → markSafetyStamp(meetup) ×6 → in_progress → markSafetyStamp(goodbye) ×6
 *   → completed
 *
 * 전체 과정에서
 *   - 결제 원장(blindMeetingDeposits) 문서 0
 *   - 미팅/참가자/신청 문서에 deposit 필드 0, 수락 대기 상태 0
 *   - 채팅방은 미팅당 정확히 1개 (재시도/복구에도 idempotent)
 *   - 3남 + 3녀 6인 유지
 * 를 확인하고, 신청 취소 vs 매칭 race 와 DNA/날짜 영속성을 함께 검증한다.
 */
import assert from "node:assert/strict";
import { test, before } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

initializeApp({ projectId: "demo-blind-nodeposit" });

import {
  confirmAttendance,
  markSafetyStamp,
  openGroupChatForConfirmedMeeting,
  requestCancellation,
  respondReplacementOffer,
  runMatchingForDate,
  settleCancellation,
  voteSchedule,
} from "./orchestrator";
import {
  BLIND_MEETING_HEART_COST,
  blindMeetingHeartSpendId,
  cancelOpenApplication,
  createPaidBlindMeetingApplication,
} from "./store";
import { readBlindMeetingGender } from "./genderBalance";
import { LEGACY_DEPOSIT_LEDGER_COLLECTION } from "./legacyDepositStatus";

let db: Firestore;
before(() => {
  db = getFirestore();
});

const DEPOSIT_FIELD_PATTERN = /deposit|refund/i;

function dateKeyInWindow(offsetDays: number): string {
  const base = new Date(Date.now() + offsetDays * 24 * 3600 * 1000);
  const yyyy = base.getUTCFullYear();
  const mm = String(base.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(base.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

type Seed = { userId: string; gender: "male" | "female" };

async function seedApplicant(seed: Seed, dateKey: string): Promise<void> {
  await db.collection("users").doc(seed.userId).set({
    isStudentVerified: true,
    isWithdrawn: false,
    loginDisabled: false,
    nickname: seed.userId,
    onboarding: {
      gender: seed.gender,
      campusLifeZones: ["sinchon"],
      lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
    },
  });
  await db.collection("blindMeetingDna").doc(seed.userId).set({
    userId: seed.userId,
    conversationAtmosphere: "calm",
    conversationInitiative: "adaptive",
    meetingPurpose: "both",
    alcoholCompanionPreference: "noPreference",
    smokingCompanionPreference: "noPreference",
    drinkingLevelSnapshot: "sometimes",
    smokingStatusSnapshot: "nonSmoker",
    interestIds: ["커피", "영화"],
    mbtiSnapshot: "ENFP",
    availableDateKeys: [dateKey],
  });
  await db.collection("blindMeetingApplications").doc(seed.userId).set({
    userId: seed.userId,
    open: true,
    status: "applied",
    serverStatus: "applied",
    stage: "searchingCandidates",
    requestedDateKeys: [dateKey],
    meetingId: null,
    appliedAt: new Date(),
  });
}

let runSeq = 0;

async function seedPool(
  males: number,
  females: number,
  dateKey: string
): Promise<Seed[]> {
  runSeq += 1;
  const tag = `nd${runSeq}_${Date.now()}`;
  const seeds: Seed[] = [
    ...Array.from({ length: males }, (_, i) => ({
      userId: `${tag}_m${i + 1}`,
      gender: "male" as const,
    })),
    ...Array.from({ length: females }, (_, i) => ({
      userId: `${tag}_f${i + 1}`,
      gender: "female" as const,
    })),
  ];
  for (const seed of seeds) await seedApplicant(seed, dateKey);
  return seeds;
}

async function meetingData(meetingId: string) {
  const snap = await db.collection("blindMeetings").doc(meetingId).get();
  return snap.data() ?? {};
}

async function participantData(meetingId: string, userId: string) {
  const snap = await db
    .collection("blindMeetings")
    .doc(meetingId)
    .collection("participants")
    .doc(userId)
    .get();
  return snap.data() ?? {};
}

async function applicationData(userId: string) {
  const snap = await db.collection("blindMeetingApplications").doc(userId).get();
  return snap.data() ?? {};
}

function assertNoDepositFields(
  data: Record<string, unknown>,
  label: string
): void {
  for (const key of Object.keys(data)) {
    assert.doesNotMatch(key, DEPOSIT_FIELD_PATTERN, `${label}.${key}`);
  }
  for (const value of Object.values(data)) {
    if (typeof value === "string") {
      assert.doesNotMatch(value, /awaiting_deposits|awaitingDeposits|deposit_pending|depositPending/, `${label} value ${value}`);
    }
  }
}

async function assertNoDepositAnywhere(
  meetingId: string,
  uids: string[]
): Promise<void> {
  const ledger = await db.collection(LEGACY_DEPOSIT_LEDGER_COLLECTION).get();
  assert.equal(ledger.size, 0, "deposit ledger must stay empty");
  assertNoDepositFields(await meetingData(meetingId), "meeting");
  for (const uid of uids) {
    assertNoDepositFields(await participantData(meetingId, uid), `participant ${uid}`);
    assertNoDepositFields(await applicationData(uid), `application ${uid}`);
  }
}

/** blindMeetingHistory/{uid}/metUsers 에 기록된 상대 uid 목록 */
async function metUserIds(uid: string): Promise<string[]> {
  const snap = await db
    .collection("blindMeetingHistory")
    .doc(uid)
    .collection("metUsers")
    .get();
  return snap.docs.map((d) => d.id).sort();
}

async function assertNoMetUsers(uids: string[], label: string): Promise<void> {
  for (const uid of uids) {
    assert.deepEqual(await metUserIds(uid), [], `${label}: ${uid} must have no metUsers yet`);
  }
}

async function assertThreeVsThree(meetingId: string): Promise<string[]> {
  const meeting = await meetingData(meetingId);
  const participantIds = meeting.participantIds as string[];
  assert.equal(participantIds.length, 6);
  assert.equal(new Set(participantIds).size, 6, "6 unique participants");
  let male = 0;
  let female = 0;
  for (const uid of participantIds) {
    const user = await db.collection("users").doc(uid).get();
    const gender = readBlindMeetingGender(user.data());
    if (gender === "male") male += 1;
    if (gender === "female") female += 1;
  }
  assert.equal(male, 3, "exactly 3 male");
  assert.equal(female, 3, "exactly 3 female");
  return participantIds;
}

/**
 * 매칭 → (수락 단계 없음) → 즉시 confirmed + 6인 채팅방 (같은 tx) → chat_open.
 *
 * 신규 canonical 흐름의 유일한 매칭 사후 조건이다. 매칭 tx 가 commit 되는
 * 순간 미팅·참가자·신청서가 confirmed 이고 채팅방 문서가 존재한다.
 */
async function assertConfirmedWithRoom(
  meetingId: string,
  uids: string[]
): Promise<void> {
  const confirmed = await meetingData(meetingId);
  assert.equal(confirmed.serverStatus, "chat_open");
  assert.equal(confirmed.groupChatId, `blind_${meetingId}`);
  assert.ok(confirmed.confirmedAt != null, "confirmedAt is set");
  assert.ok(confirmed.scheduleVoteDeadlineAt != null, "schedule vote deadline is set");
  // 매칭 tx 가 확정 시점 성별 스냅샷을 남긴다 (groupChatRepair 의 불변 근거).
  const genders = confirmed.participantGenders as Record<string, string>;
  assert.deepEqual(Object.keys(genders ?? {}).sort(), [...uids].sort());
  assert.equal(Object.values(genders).filter((g) => g === "male").length, 3);
  assert.equal(Object.values(genders).filter((g) => g === "female").length, 3);
  for (const uid of uids) {
    const participant = await participantData(meetingId, uid);
    assert.equal(participant.serverStatus, "confirmed");
    assert.ok(participant.confirmedAt != null, "participant confirmedAt is set");
    const application = await applicationData(uid);
    assert.equal(application.serverStatus, "confirmed");
    assert.equal(application.stage, "matched");
    assert.equal(application.open, false);
    assert.equal(application.meetingId, meetingId);
    // 매칭 claim 은 merge write 다 — 신청 당시 날짜/하트 정보가 남아야 한다.
    assert.ok(Array.isArray(application.requestedDateKeys), "requestedDateKeys preserved");
    assert.ok((application.requestedDateKeys as string[]).length > 0);
  }
  const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.equal(room.exists, true, "group chat room exists");
  assert.equal(room.data()?.roomType, "blind_meeting_group");
  assert.equal(room.data()?.meetingId, meetingId);
  assert.equal(room.data()?.writable, true);
  assert.deepEqual([...(room.data()?.participantIds as string[])].sort(), [...uids].sort());
  const info = room.data()?.participantInfo as Record<string, Record<string, unknown>>;
  for (const uid of uids) {
    assert.equal(info[uid]?.avatarUrl, "", "no face photo in a blind room");
    assert.ok(typeof info[uid]?.nickname === "string");
  }
  const rooms = await db.collection("chat_rooms").where("meetingId", "==", meetingId).get();
  assert.equal(rooms.size, 1, "exactly one room per meeting");
  await assertNoDepositAnywhere(meetingId, uids);
}

/** 매칭 → 즉시 확정 + 채팅방. 수락 단계는 존재하지 않는다. */
async function matchAndConfirm(): Promise<{
  meetingId: string;
  uids: string[];
  dateKey: string;
}> {
  const dateKey = dateKeyInWindow(3);
  await seedPool(3, 3, dateKey);
  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1, "exactly one meeting is created");
  const meetingId = created[0];
  const uids = await assertThreeVsThree(meetingId);
  await assertConfirmedWithRoom(meetingId, uids);
  return { meetingId, uids, dateKey };
}

/** 미팅/참가자/신청 문서 어디에도 수락 단계 상태가 없다. */
async function assertNoAcceptanceStage(meetingId: string, uids: string[]): Promise<void> {
  const banned = /awaiting_acceptance|awaitingAcceptance|acceptance_request/;
  const meeting = await meetingData(meetingId);
  for (const value of Object.values(meeting)) {
    if (typeof value === "string") assert.doesNotMatch(value, banned, `meeting ${value}`);
  }
  for (const uid of uids) {
    for (const doc of [await participantData(meetingId, uid), await applicationData(uid)]) {
      for (const value of Object.values(doc)) {
        if (typeof value === "string") {
          assert.doesNotMatch(value, /^(invited|accepted|awaiting_acceptance|awaitingConfirmation)$/, `${uid} ${value}`);
        }
      }
    }
  }
  // 인앱 알림은 users/{uid}/notifications 에 저장된다. 수락 요청 알림 0건.
  for (const uid of uids) {
    const notifications = await db
      .collection("users")
      .doc(uid)
      .collection("notifications")
      .where("meetingId", "==", meetingId)
      .get();
    assert.ok(notifications.size >= 1, `${uid} received meeting notifications`);
    for (const doc of notifications.docs) {
      const type = String(doc.data().type ?? "");
      assert.doesNotMatch(type, /acceptance/, type);
      const title = String(doc.data().title ?? "");
      assert.doesNotMatch(title, /수락|거절/, title);
    }
  }
}

test("full happy path: matching → confirmed + room in one commit → promise → safe stamps → completed, zero deposit, zero acceptance", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();
  await assertNoAcceptanceStage(meetingId, uids);

  // 매칭 직후 채팅방에는 시스템 환영 메시지가 있고, 사용자 메시지를 쓸 수 있다.
  const roomRef = db.collection("chat_rooms").doc(`blind_${meetingId}`);
  const systemMessages = await roomRef.collection("messages").where("type", "==", "system").get();
  assert.ok(systemMessages.size >= 1, "welcome system message");
  assert.match(String(systemMessages.docs[0].data().text), /매칭됐어요/);
  await roomRef.collection("messages").add({
    senderId: uids[0],
    text: "안녕하세요!",
    type: "text",
    readBy: [uids[0]],
    createdAt: new Date(),
  });

  // 매칭/확정/채팅방만으로는 "만난" 것이 아니다 — recentlyMet 기록 0.
  await assertNoMetUsers(uids, "after confirmation");

  // 약속잡기: 6명 투표 → schedule_confirmed.
  const slotId = `${dateKey}#evening`;
  for (const uid of uids) {
    await voteSchedule({
      meetingId,
      userId: uid,
      preferredSlotIds: [slotId],
      preferredPlaceId: null,
    });
  }
  const scheduled = await meetingData(meetingId);
  assert.equal(scheduled.serverStatus, "schedule_confirmed");
  assert.equal(scheduled.slotId, slotId);
  assert.ok(scheduled.scheduledStartAt != null);

  // 참석 재확인 (24h) — 전원 참석.
  for (const uid of uids) {
    await confirmAttendance({ meetingId, userId: uid, phase: "24h", attending: true });
  }

  // 약속 확정도 만남이 아니다.
  await assertNoMetUsers(uids, "after schedule confirmed");

  // 도착 안전도장 6명 → in_progress.
  for (const [index, uid] of uids.entries()) {
    await markSafetyStamp({
      meetingId,
      userId: uid,
      phase: "meetup",
      verification: { source: "test" },
    });
    const status = (await meetingData(meetingId)).serverStatus;
    if (index < 5) assert.equal(status, "checkin_open");
    assert.equal((await participantData(meetingId, uid)).serverStatus, "attended");
  }
  assert.equal((await meetingData(meetingId)).serverStatus, "in_progress");

  // 여섯 명이 실제로 도착(도착 안전도장)한 뒤에만 서로 recentlyMet 다.
  for (const uid of uids) {
    assert.deepEqual(
      await metUserIds(uid),
      uids.filter((other) => other !== uid).sort(),
      `${uid} met the other five attendees`
    );
  }

  // 종료 안전도장 6명 → completed.
  for (const uid of uids) {
    await markSafetyStamp({
      meetingId,
      userId: uid,
      phase: "goodbye",
      verification: { source: "test" },
    });
  }
  const completed = await meetingData(meetingId);
  assert.equal(completed.serverStatus, "completed");
  assert.ok(completed.completedAt != null);
  for (const uid of uids) {
    assert.equal((await participantData(meetingId, uid)).serverStatus, "completed");
    const application = await applicationData(uid);
    assert.equal(application.serverStatus, "completed");
    assert.equal(application.open, false);
  }

  await assertThreeVsThree(meetingId);
  await assertNoDepositAnywhere(meetingId, uids);
  await assertNoAcceptanceStage(meetingId, uids);
});

test("matching is idempotent: a second run for the same date creates no second meeting or room", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();
  const again = await runMatchingForDate(dateKey);
  assert.deepEqual(again, [], "no new meeting from already-claimed applications");
  const meetings = await db
    .collection("blindMeetings")
    .where("participantIds", "array-contains", uids[0])
    .get();
  assert.equal(meetings.size, 1);
  const rooms = await db.collection("chat_rooms").where("meetingId", "==", meetingId).get();
  assert.equal(rooms.size, 1);
  // 복구 경로 재실행도 방을 늘리지 않는다.
  assert.equal(await openGroupChatForConfirmedMeeting(meetingId), false, "already chat_open");
  const roomsAfter = await db.collection("chat_rooms").where("meetingId", "==", meetingId).get();
  assert.equal(roomsAfter.size, 1);
});

test("participant cancellation after confirmation settles without a payment subsystem", async () => {
  const { meetingId, uids } = await matchAndConfirm();
  const leaver = uids[0];

  await requestCancellation({
    meetingId,
    userId: leaver,
    reason: "일정 변경",
    emergency: false,
  });

  const leaverDoc = await participantData(meetingId, leaver);
  // 대체 후보가 없으므로 현재 FSM 정책대로 취소 확정 (cancel_requested 를 거쳐).
  assert.ok(
    ["cancelled", "replacement_pending"].includes(String(leaverDoc.serverStatus)),
    `unexpected leaver status ${leaverDoc.serverStatus}`
  );
  if (leaverDoc.serverStatus === "cancelled") {
    const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
    assert.equal(
      (room.data()?.participantIds as string[]).includes(leaver),
      false,
      "cancelled participant leaves the room"
    );
    const meeting = await meetingData(meetingId);
    assert.equal(meeting.fivePersonVoteOpen, true);
  }
  // 매칭 후 취소는 신청 취소가 아니다: 하트 환불이 발생하지 않는다.
  const refunds = await db
    .collection("heartTransactions")
    .where("uid", "==", leaver)
    .where("type", "==", "heart_refund")
    .get();
  assert.equal(refunds.size, 0, "no application-cancel refund after match");
  await assertNoDepositAnywhere(meetingId, uids);
});

test("replacement joins a confirmed meeting as confirmed and keeps 3M+3F (own-meeting recentlyMet is ignored)", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();

  // 같은 성별(남) 대체 후보 한 명을 열린 신청으로 심는다.
  const [spare] = await seedPool(1, 0, dateKey);
  const leaver = uids.find((uid) => uid.endsWith("_m1"))!;
  const stayers = uids.filter((uid) => uid !== leaver);

  await requestCancellation({ meetingId, userId: leaver, reason: "일정 변경", emergency: false });

  const offers = await db
    .collection("blindMeetingReplacementOffers")
    .where("meetingId", "==", meetingId)
    .where("candidateUid", "==", spare.userId)
    .get();
  assert.equal(offers.size, 1, "one replacement offer for the spare candidate");

  const result = await respondReplacementOffer({
    offerId: offers.docs[0].id,
    userId: spare.userId,
    accept: true,
  });
  assert.equal(result.ok, true, JSON.stringify(result));

  const meeting = await meetingData(meetingId);
  const participantIds = meeting.participantIds as string[];
  assert.equal(participantIds.includes(spare.userId), true);
  assert.equal(participantIds.includes(leaver), false);
  await assertThreeVsThree(meetingId);
  assert.equal((await participantData(meetingId, leaver)).serverStatus, "replaced");
  assert.equal((await participantData(meetingId, spare.userId)).serverStatus, "confirmed");
  assert.equal((await meetingData(meetingId)).serverStatus, "chat_open");

  const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  const members = room.data()?.participantIds as string[];
  assert.equal(members.includes(leaver), false, "leaver is not in the chat");
  assert.equal(members.includes(spare.userId), true, "replacement is in the chat");
  assert.deepEqual([...members].sort(), [...stayers, spare.userId].sort());
  assertNoDepositFields(await participantData(meetingId, leaver), "leaver");
});

// -----------------------------------------------------------------------------
// 신청 취소 vs 매칭 race — 결과는 둘 중 하나로만 수렴한다
// -----------------------------------------------------------------------------

async function seedChargeForApplicant(uid: string): Promise<void> {
  await db.collection("users").doc(uid).set(
    { heartBalance: 100 - BLIND_MEETING_HEART_COST },
    { merge: true }
  );
  await db.collection("heartTransactions").doc(blindMeetingHeartSpendId(uid, 1)).set({
    uid,
    feature: "blind_meeting",
    resourceId: uid,
    amount: BLIND_MEETING_HEART_COST,
    heartBalanceAfter: 100 - BLIND_MEETING_HEART_COST,
    createdAt: new Date(),
  });
  await db.collection("blindMeetingApplications").doc(uid).set(
    { heartCost: BLIND_MEETING_HEART_COST, heartChargeCount: 1 },
    { merge: true }
  );
}

async function refundCount(uid: string): Promise<number> {
  const snap = await db
    .collection("heartTransactions")
    .where("uid", "==", uid)
    .where("type", "==", "heart_refund")
    .get();
  return snap.size;
}

async function assertRaceConverged(
  uid: string,
  dateKey: string,
  created: string[],
  cancelOutcome: PromiseSettledResult<Awaited<ReturnType<typeof cancelOpenApplication>>>
): Promise<"cancel_won" | "match_won"> {
  const app = await applicationData(uid);
  const balance = Number((await db.collection("users").doc(uid).get()).data()?.heartBalance);
  const meetings = await db
    .collection("blindMeetings")
    .where("participantIds", "array-contains", uid)
    .get();
  const rooms = await db
    .collection("chat_rooms")
    .where("participantIds", "array-contains", uid)
    .where("roomType", "==", "blind_meeting_group")
    .get();

  if (app.serverStatus === "cancelled") {
    // A wins: 취소 + 환불, 미팅/방 없음
    assert.equal(cancelOutcome.status, "fulfilled", "cancel succeeded");
    assert.equal(created.length, 0, "no meeting when cancel won");
    assert.equal(meetings.size, 0);
    assert.equal(rooms.size, 0);
    assert.equal(balance, 100, "hearts refunded");
    assert.equal(await refundCount(uid), 1);
    return "cancel_won";
  }
  // B wins: 매칭 + 방, 취소 거부 + 환불 없음
  assert.equal(app.serverStatus, "confirmed", `incoherent status ${app.serverStatus}`);
  assert.equal(created.length, 1, "exactly one meeting when match won");
  assert.equal(meetings.size, 1);
  assert.equal(rooms.size, 1);
  assert.equal(app.meetingId, created[0]);
  assert.equal(cancelOutcome.status, "rejected", "cancel refused after match");
  if (cancelOutcome.status === "rejected") {
    assert.match(String((cancelOutcome.reason as Error).message), /CANNOT_CANCEL_ALREADY_MATCHED/);
  }
  assert.equal(balance, 100 - BLIND_MEETING_HEART_COST, "no refund when match won");
  assert.equal(await refundCount(uid), 0);
  return "match_won";
}

test("cancel-before-match: cancel wins, refund once, no meeting, no room", async () => {
  const dateKey = dateKeyInWindow(4);
  const seeds = await seedPool(3, 3, dateKey);
  const uid = seeds[0].userId;
  await seedChargeForApplicant(uid);

  const cancel = await Promise.allSettled([cancelOpenApplication(uid)]);
  const created = await runMatchingForDate(dateKey);
  assert.equal(await assertRaceConverged(uid, dateKey, created, cancel[0]), "cancel_won");
  // 나머지 다섯 명은 계속 열린 신청이다.
  for (const seed of seeds.slice(1)) {
    const app = await applicationData(seed.userId);
    assert.equal(app.open, true);
    assert.equal(app.serverStatus, "applied");
  }
});

test("match-before-cancel: match wins, cancel refused deterministically, no refund", async () => {
  const dateKey = dateKeyInWindow(5);
  const seeds = await seedPool(3, 3, dateKey);
  const uid = seeds[0].userId;
  await seedChargeForApplicant(uid);

  const created = await runMatchingForDate(dateKey);
  const cancel = await Promise.allSettled([cancelOpenApplication(uid)]);
  assert.equal(await assertRaceConverged(uid, dateKey, created, cancel[0]), "match_won");
});

test("concurrent cancel/match race converges to exactly one of the two outcomes", async () => {
  const outcomes = new Set<string>();
  for (let round = 0; round < 6; round++) {
    const dateKey = dateKeyInWindow(6 + round);
    const seeds = await seedPool(3, 3, dateKey);
    const uid = seeds[round % 6].userId;
    await seedChargeForApplicant(uid);

    // 매칭은 후보 로딩(read) 뒤에 트랜잭션을 연다. 취소를 그 사이 임의 시점에
    // 끼워 넣어 실제 경합을 만든다.
    const matchPromise = runMatchingForDate(dateKey);
    const delayMs = [0, 40, 120, 250, 400, 700][round];
    const cancelPromise = new Promise<Awaited<ReturnType<typeof cancelOpenApplication>>>(
      (resolve, reject) => {
        setTimeout(() => {
          cancelOpenApplication(uid).then(resolve, reject);
        }, delayMs);
      }
    );
    const [createdSettled, cancelSettled] = await Promise.allSettled([matchPromise, cancelPromise]);
    assert.equal(createdSettled.status, "fulfilled", "matching never throws on a race");
    const created = createdSettled.status === "fulfilled" ? createdSettled.value : [];
    outcomes.add(await assertRaceConverged(uid, dateKey, created, cancelSettled));
  }
  assert.ok(outcomes.size >= 1, `race outcomes: ${[...outcomes].join(",")}`);
});

// -----------------------------------------------------------------------------
// DNA / 날짜 영속성 — 신청·취소 lifecycle 과 분리된 재사용 DNA
// -----------------------------------------------------------------------------

test("submit persists DNA + dates; cancel keeps them; re-apply reads them back", async () => {
  const uid = `dna_${Date.now()}`;
  const dateKeys = [dateKeyInWindow(2), dateKeyInWindow(9)];
  await db.collection("users").doc(uid).set({
    isStudentVerified: true,
    heartBalance: 200,
    nickname: uid,
    onboarding: {
      gender: "female",
      campusLifeZones: ["sinchon"],
      lifestyle: { drinking: "none", smoking: "nonSmoker" },
    },
  });
  const dnaPayload = {
    userId: uid,
    schemaVersion: 2,
    conversationAtmosphere: "lively",
    conversationInitiative: "initiator",
    meetingPurpose: "romance",
    alcoholCompanionPreference: "lightOkay",
    smokingCompanionPreference: "nonSmokersOnly",
    interestIds: ["전시회", "러닝"],
    drinkingLevelSnapshot: "none",
    smokingStatusSnapshot: "nonSmoker",
    mbtiSnapshot: "INFJ",
    availableDateKeys: dateKeys,
    waitlistOptIn: false,
  };

  await createPaidBlindMeetingApplication({
    userId: uid,
    dnaPayload,
    requestedDateKeys: dateKeys,
    prefersAlcoholFree: false,
    waitlistOptIn: false,
  });

  const dnaAfterSubmit = (await db.collection("blindMeetingDna").doc(uid).get()).data() ?? {};
  assert.equal(dnaAfterSubmit.conversationAtmosphere, "lively");
  assert.equal(dnaAfterSubmit.meetingPurpose, "romance");
  assert.deepEqual(dnaAfterSubmit.availableDateKeys, dateKeys);
  assert.deepEqual(dnaAfterSubmit.interestIds, ["전시회", "러닝"]);
  const appAfterSubmit = await applicationData(uid);
  assert.deepEqual(appAfterSubmit.requestedDateKeys, dateKeys);
  assert.equal(appAfterSubmit.heartChargeCount, 1);
  const balanceAfterSubmit = Number((await db.collection("users").doc(uid).get()).data()?.heartBalance);
  assert.equal(balanceAfterSubmit, 200 - BLIND_MEETING_HEART_COST);

  // 취소 → DNA/날짜는 삭제되지 않고, 하트는 1회 환불된다.
  const cancelled = await cancelOpenApplication(uid);
  assert.equal(cancelled.outcome, "cancelled");
  assert.equal(cancelled.heartRefunded, BLIND_MEETING_HEART_COST);
  const dnaAfterCancel = (await db.collection("blindMeetingDna").doc(uid).get()).data() ?? {};
  assert.deepEqual(dnaAfterCancel.availableDateKeys, dateKeys, "dates survive cancel");
  assert.equal(dnaAfterCancel.conversationInitiative, "initiator", "answers survive cancel");
  const appAfterCancel = await applicationData(uid);
  assert.equal(appAfterCancel.serverStatus, "cancelled");
  assert.deepEqual(appAfterCancel.requestedDateKeys, dateKeys, "application dates survive cancel");

  // 재신청: 이전 답변 + 날짜를 그대로(또는 수정해) 다시 낼 수 있고, 새로 차감된다.
  const nextDates = [dateKeys[1], dateKeyInWindow(12)];
  await createPaidBlindMeetingApplication({
    userId: uid,
    dnaPayload: { ...dnaAfterCancel, availableDateKeys: nextDates, meetingPurpose: "both" },
    requestedDateKeys: nextDates,
    prefersAlcoholFree: false,
    waitlistOptIn: false,
  });
  const dnaAfterReapply = (await db.collection("blindMeetingDna").doc(uid).get()).data() ?? {};
  assert.deepEqual(dnaAfterReapply.availableDateKeys, nextDates, "edited dates are re-persisted");
  assert.equal(dnaAfterReapply.meetingPurpose, "both", "edited answer is re-persisted");
  assert.equal(dnaAfterReapply.conversationAtmosphere, "lively", "untouched answer is kept");
  const appAfterReapply = await applicationData(uid);
  assert.equal(appAfterReapply.serverStatus, "applied");
  assert.equal(appAfterReapply.open, true);
  assert.deepEqual(appAfterReapply.requestedDateKeys, nextDates);
  assert.equal(appAfterReapply.heartChargeCount, 2);
});

test("recentlyMet follows attendance: no_show is never recorded, attendees are, and re-stamps are idempotent", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();
  await assertNoMetUsers(uids, "after confirmation");

  const slotId = `${dateKey}#evening`;
  for (const uid of uids) {
    await voteSchedule({ meetingId, userId: uid, preferredSlotIds: [slotId], preferredPlaceId: null });
  }
  assert.equal((await meetingData(meetingId)).serverStatus, "schedule_confirmed");

  // 5명만 도착한다. 마지막 한 명은 나타나지 않는다.
  const absent = uids[5];
  const attendees = uids.slice(0, 5);
  for (const uid of attendees) {
    await markSafetyStamp({ meetingId, userId: uid, phase: "meetup", verification: { source: "test" } });
  }
  // 재전송(retry)은 같은 관계를 다시 만들지 않는다.
  await markSafetyStamp({ meetingId, userId: attendees[0], phase: "meetup", verification: { source: "retry" } });

  for (const uid of attendees) {
    assert.deepEqual(
      await metUserIds(uid),
      attendees.filter((other) => other !== uid).sort(),
      `${uid} met only the other attendees`
    );
    const met = await db.collection("blindMeetingHistory").doc(uid).collection("metUsers").get();
    assert.equal(met.size, 4, "exactly four relationships, no duplicates");
  }
  assert.deepEqual(await metUserIds(absent), [], "the absent participant met nobody");

  // 최종 노쇼 판정 뒤에도 노쇼는 recentlyMet 에 기록되지 않는다.
  await settleCancellation({
    meetingId,
    userId: absent,
    replacementFound: false,
    emergency: false,
    isNoShowWithoutContact: true,
  });
  assert.equal((await participantData(meetingId, absent)).serverStatus, "no_show");
  assert.deepEqual(await metUserIds(absent), []);
  for (const uid of attendees) {
    assert.equal((await metUserIds(uid)).includes(absent), false, "attendees did not meet the no_show");
  }
});

test("replacement candidate is not excluded by a match that never met: F4 replaces F3 after confirmation", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();
  await assertNoMetUsers(uids, "after confirmation");

  // F4: 차단 없음, 활성 미팅 없음, 기존 다섯 명과 실제로 만난 적 없음.
  const [f4] = await seedPool(0, 1, dateKey);
  const f3 = uids.find((uid) => uid.endsWith("_f3"))!;
  const stayers = uids.filter((uid) => uid !== f3);

  await requestCancellation({ meetingId, userId: f3, reason: "일정 변경", emergency: false });

  const offers = await db
    .collection("blindMeetingReplacementOffers")
    .where("meetingId", "==", meetingId)
    .where("candidateUid", "==", f4.userId)
    .get();
  assert.equal(offers.size, 1, "F4 receives a replacement offer");

  const result = await respondReplacementOffer({ offerId: offers.docs[0].id, userId: f4.userId, accept: true });
  assert.equal(result.ok, true, JSON.stringify(result));

  const participantIds = await assertThreeVsThree(meetingId);
  assert.deepEqual([...participantIds].sort(), [...stayers, f4.userId].sort());
  assert.equal((await participantData(meetingId, f4.userId)).serverStatus, "confirmed");
  assert.equal((await participantData(meetingId, f3)).serverStatus, "replaced");
  // 대체 합류 자체도 만남이 아니다.
  await assertNoMetUsers([...stayers, f4.userId, f3], "after replacement");
});

test("a candidate who actually met a seat holder before stays excluded (recentlyMet filter intact)", async () => {
  const { meetingId, uids, dateKey } = await matchAndConfirm();
  const [f5] = await seedPool(0, 1, dateKey);
  const f3 = uids.find((uid) => uid.endsWith("_f3"))!;
  const m1 = uids.find((uid) => uid.endsWith("_m1"))!;

  // F5 와 M1 은 다른 미팅에서 실제로 만났다 (양방향 이력, 최근).
  const now = new Date();
  await db.collection("blindMeetingHistory").doc(f5.userId).collection("metUsers").doc(m1)
    .set({ meetingId: "another_meeting", metAt: now });
  await db.collection("blindMeetingHistory").doc(m1).collection("metUsers").doc(f5.userId)
    .set({ meetingId: "another_meeting", metAt: now });

  await requestCancellation({ meetingId, userId: f3, reason: "일정 변경", emergency: false });

  const offers = await db
    .collection("blindMeetingReplacementOffers")
    .where("meetingId", "==", meetingId)
    .where("candidateUid", "==", f5.userId)
    .get();
  assert.equal(offers.size, 0, "F5 who really met M1 is not offered the seat");
});
