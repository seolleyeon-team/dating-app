/**
 * 블라인드 3:3 participant/application FSM — Firestore Emulator 통합 테스트.
 *
 * 실행 (repo root, Java 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-blind-fsm \
 *     "node --test functions/lib/blindMeeting/blindMeetingFsm.emulator-test.js"
 *
 * store choke point(updateParticipant/setApplication/cancelOpenApplication)와
 * legacy 수락 대기 정규화(legacyAcceptance)를 실제 Firestore 트랜잭션 위에서
 * 검증한다. 매칭 후 accept/decline 진입점은 2026-09-03 에 제거됐다
 * (매칭 = 확정). 신규 매칭 E2E 는 noDepositHappyPath.emulator-test.ts.
 */
import assert from "node:assert/strict";
import { test, before } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { FieldValue, getFirestore, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

initializeApp({ projectId: "demo-blind-fsm" });

import {
  BLIND_MEETING_HEART_COST,
  blindMeetingHeartRefundId,
  blindMeetingHeartSpendId,
  createPaidBlindMeetingApplication,
  reopenApplicationIfBoundTo,
  setApplication,
  updateParticipant,
  cancelOpenApplication,
  startPaidBlindMeetingDna,
} from "./store";
import {
  cancelMeeting,
  settleCancellation,
  voteFivePersonException,
} from "./orchestrator";
import { cancelBlindMeetingParty } from "./party";
import {
  confirmLegacyAwaitingAcceptanceMeeting,
  repairLegacyAwaitingAcceptanceMeetings,
} from "./legacyAcceptance";
import { repairConfirmedMeetingGroupChat } from "./meetingConfirmation";
import { repairLegacyMeetingStatus } from "./legacyDepositNormalizer";
import {
  LEGACY_DEPOSIT_LEDGER_COLLECTION,
  LEGACY_MEETING_STATUS_AWAITING_DEPOSITS,
  LEGACY_MEETING_STATUS_AWAITING_DEPOSITS_APP,
  LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING,
  LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING_APP,
} from "./legacyDepositStatus";
import {
  CANCEL_ALREADY_MATCHED_CODE,
  MEETING_STATUS_TO_APP,
  PARTICIPANT_STATUS_TO_APP,
  type BlindMeetingStatus,
  type ParticipantStatus,
} from "./types";

let db: Firestore;
before(() => {
  db = getFirestore();
});

let seq = 0;
function uniqueId(prefix: string): string {
  seq += 1;
  return `${prefix}_${seq}`;
}

async function seedMeeting(
  meetingId: string,
  status: BlindMeetingStatus,
  participantIds: string[]
): Promise<void> {
  await db.collection("blindMeetings").doc(meetingId).set({
    status: MEETING_STATUS_TO_APP[status],
    serverStatus: status,
    participantIds,
    teamAUserIds: participantIds.slice(0, 3),
    teamBUserIds: participantIds.slice(3, 6),
    commonAvailableDateKeys: ["20260901"],
    matchedDateKey: "20260901",
    isAlcoholFree: false,
  });
}

async function seedParticipant(
  meetingId: string,
  userId: string,
  status: ParticipantStatus,
  extra: Record<string, unknown> = {}
): Promise<void> {
  await db
    .collection("blindMeetings")
    .doc(meetingId)
    .collection("participants")
    .doc(userId)
    .set({
      userId,
      status: PARTICIPANT_STATUS_TO_APP[status],
      serverStatus: status,
      ...extra,
    });
}

/** 성비 검증(3남+3녀)에 필요한 users 문서를 심는다. index 0-2 남, 3-5 여. */
async function seedGenderedUsers(uids: string[]): Promise<void> {
  for (const [index, uid] of uids.entries()) {
    await db
      .collection("users")
      .doc(uid)
      .set(
        {
          isStudentVerified: true,
          nickname: uid,
          onboarding: { gender: index < 3 ? "male" : "female" },
        },
        { merge: true }
      );
  }
}

/** 이 미팅과 관련해 결제 원장이 하나도 만들어지지 않았는지. */
async function assertNoDepositLedger(meetingId: string): Promise<void> {
  const ledger = await db
    .collection(LEGACY_DEPOSIT_LEDGER_COLLECTION)
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(ledger.size, 0, "deposit ledger must stay empty");
}

const DEPOSIT_FIELD_PATTERN = /deposit|refund/i;

function assertNoDepositFields(data: Record<string, unknown> | undefined): void {
  for (const key of Object.keys(data ?? {})) {
    assert.doesNotMatch(key, DEPOSIT_FIELD_PATTERN, key);
  }
}

async function seedApplication(
  userId: string,
  status: ParticipantStatus,
  patch: Record<string, unknown> = {}
): Promise<void> {
  await db.collection("blindMeetingApplications").doc(userId).set({
    userId,
    status: PARTICIPANT_STATUS_TO_APP[status],
    serverStatus: status,
    open: false,
    ...patch,
  });
}

async function participantStatus(meetingId: string, userId: string) {
  const snap = await db
    .collection("blindMeetings")
    .doc(meetingId)
    .collection("participants")
    .doc(userId)
    .get();
  return snap.data()?.serverStatus;
}

async function applicationStatus(userId: string) {
  const snap = await db
    .collection("blindMeetingApplications")
    .doc(userId)
    .get();
  return snap.data();
}

// -----------------------------------------------------------------------------
// updateParticipant choke point
// -----------------------------------------------------------------------------

test("participant: valid transition succeeds, illegal transition fails closed", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "awaiting_acceptance", [uid]);
  await seedParticipant(meetingId, uid, "invited");

  await updateParticipant(meetingId, uid, { status: "accepted" });
  assert.equal(await participantStatus(meetingId, uid), "accepted");

  // invited 단계를 건너뛴 confirmed 직행은 불가 — 상태가 오염되지 않아야 한다.
  await assert.rejects(
    updateParticipant(meetingId, uid, { status: "attended" }),
    /blind_participant_transition_rejected:accepted->attended/
  );
  assert.equal(await participantStatus(meetingId, uid), "accepted");
});

test("participant: terminal states reject business transitions", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "chat_open", [uid]);
  await seedParticipant(meetingId, uid, "replaced");

  await assert.rejects(
    updateParticipant(meetingId, uid, { status: "confirmed" }),
    /blind_participant_transition_rejected:replaced->confirmed/
  );

  await seedParticipant(meetingId, uid, "cancelled");
  await assert.rejects(
    updateParticipant(meetingId, uid, { status: "confirmed" }),
    /blind_participant_transition_rejected:cancelled->confirmed/
  );
});

test("participant: unknown status fails closed without normalization", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "chat_open", [uid]);
  await db
    .collection("blindMeetings")
    .doc(meetingId)
    .collection("participants")
    .doc(uid)
    .set({ userId: uid, serverStatus: "garbage_state" });

  await assert.rejects(
    updateParticipant(meetingId, uid, { status: "cancelled" }),
    /blind_participant_status_unknown/
  );
  assert.equal(await participantStatus(meetingId, uid), "garbage_state");
});

test("participant: same-status retry is idempotent and merges extras", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "awaiting_acceptance", [uid]);
  await seedParticipant(meetingId, uid, "accepted");

  await updateParticipant(meetingId, uid, {
    status: "accepted",
    extra: { retryMarker: true },
  });
  const snap = await db
    .collection("blindMeetings")
    .doc(meetingId)
    .collection("participants")
    .doc(uid)
    .get();
  assert.equal(snap.data()?.serverStatus, "accepted");
  assert.equal(snap.data()?.retryMarker, true);
});

test("participant: archived meeting freezes all transitions; cancelled meeting only settles", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "archived", [uid]);
  await seedParticipant(meetingId, uid, "confirmed");
  await assert.rejects(
    updateParticipant(meetingId, uid, { status: "attended" }),
    /blind_meeting_archived_participant_frozen/
  );

  const cancelledMeetingId = uniqueId("m");
  await seedMeeting(cancelledMeetingId, "cancelled", [uid]);
  await seedParticipant(cancelledMeetingId, uid, "confirmed");
  await assert.rejects(
    updateParticipant(cancelledMeetingId, uid, { status: "attended" }),
    /blind_meeting_cancelled_participant_transition_rejected/
  );
  // 취소 정산 계열 전이는 허용된다.
  await updateParticipant(cancelledMeetingId, uid, { status: "cancelled" });
  assert.equal(
    await participantStatus(cancelledMeetingId, uid),
    "cancelled"
  );
});

// -----------------------------------------------------------------------------
// setApplication choke point
// -----------------------------------------------------------------------------

test("application: initial create allows applied only", async () => {
  const uid = uniqueId("u");
  await assert.rejects(
    setApplication(uid, { status: "confirmed" }),
    /blind_application_missing_for_transition:confirmed/
  );
  await setApplication(uid, { status: "applied", open: true });
  assert.equal((await applicationStatus(uid))?.serverStatus, "applied");
});

test("application: reopen and re-apply edges work, forward skips are rejected", async () => {
  const uid = uniqueId("u");
  await seedApplication(uid, "invited", { meetingId: "m1" });

  // 초대 거절 재오픈: invited → applied
  await setApplication(uid, { status: "applied", open: true, meetingId: null });
  assert.equal((await applicationStatus(uid))?.serverStatus, "applied");

  // applied → completed 직행은 불가
  await assert.rejects(
    setApplication(uid, { status: "completed" }),
    /blind_application_transition_rejected:applied->completed/
  );

  // 완료 후 재신청: completed → applied
  await seedApplication(uid, "completed");
  await setApplication(uid, { status: "applied", open: true });
  assert.equal((await applicationStatus(uid))?.serverStatus, "applied");
});

test("application: unknown status fails closed", async () => {
  const uid = uniqueId("u");
  await db.collection("blindMeetingApplications").doc(uid).set({
    userId: uid,
    serverStatus: "totally_bogus",
  });
  await assert.rejects(
    setApplication(uid, { status: "cancelled" }),
    /blind_application_status_unknown/
  );
});

test("application: cancelOpenApplication still gates matched applications", async () => {
  const uid = uniqueId("u");
  await seedApplication(uid, "confirmed", { meetingId: "m_live", open: false });
  await assert.rejects(
    cancelOpenApplication(uid),
    new RegExp(CANCEL_ALREADY_MATCHED_CODE)
  );

  const freeUid = uniqueId("u");
  await seedApplication(freeUid, "applied", { open: true, meetingId: null });
  const result = await cancelOpenApplication(freeUid);
  assert.equal(result.outcome, "cancelled");
  assert.equal((await applicationStatus(freeUid))?.serverStatus, "cancelled");
});

// -----------------------------------------------------------------------------
// 신청 취소 + 하트 환불 (정확히 1회, 같은 트랜잭션)
// -----------------------------------------------------------------------------

async function heartBalance(uid: string): Promise<number> {
  const snap = await db.collection("users").doc(uid).get();
  return Number(snap.data()?.heartBalance ?? 0);
}

async function refundLedgerCount(uid: string): Promise<number> {
  const snap = await db
    .collection("heartTransactions")
    .where("uid", "==", uid)
    .where("type", "==", "heart_refund")
    .get();
  return snap.size;
}

/** DNA 시작 결제가 끝난 열린 신청을 심는다 (잔액 = 100 - 30). */
async function seedChargedOpenApplication(
  uid: string,
  patch: Record<string, unknown> = {}
): Promise<void> {
  await db.collection("users").doc(uid).set(
    { heartBalance: 100 - BLIND_MEETING_HEART_COST, isStudentVerified: true },
    { merge: true }
  );
  await db
    .collection("heartTransactions")
    .doc(blindMeetingHeartSpendId(uid, 1))
    .set({
      uid,
      feature: "blind_meeting",
      resourceId: uid,
      amount: BLIND_MEETING_HEART_COST,
      heartBalanceAfter: 100 - BLIND_MEETING_HEART_COST,
      createdAt: new Date(),
    });
  await seedApplication(uid, "applied", {
    open: true,
    meetingId: null,
    heartCost: BLIND_MEETING_HEART_COST,
    heartChargeCount: 1,
    requestedDateKeys: ["2026-09-01"],
    ...patch,
  });
}

test("cancel before match refunds the charged hearts exactly once", async () => {
  const uid = uniqueId("u_refund");
  await seedChargedOpenApplication(uid);

  const result = await cancelOpenApplication(uid);
  assert.equal(result.outcome, "cancelled");
  assert.equal(result.heartRefunded, BLIND_MEETING_HEART_COST);
  assert.equal(result.heartBalance, 100);
  assert.equal(await heartBalance(uid), 100, "balance restored to original");
  assert.equal(await refundLedgerCount(uid), 1);
  const refund = await db
    .collection("heartTransactions")
    .doc(blindMeetingHeartRefundId(uid, 1))
    .get();
  assert.equal(refund.exists, true);
  assert.equal(refund.data()?.refundOfTransactionId, blindMeetingHeartSpendId(uid, 1));

  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "cancelled");
  assert.equal(app?.stage, "cancelled");
  assert.equal(app?.open, false);
  assert.equal(app?.meetingId, null);
  assert.equal(app?.heartRefundedAmount, BLIND_MEETING_HEART_COST);
  // 재사용 DNA 필드/날짜는 신청서에 그대로 남는다 (덮어쓰기 없음).
  assert.deepEqual(app?.requestedDateKeys, ["2026-09-01"]);
});

test("double cancel (retry) never refunds twice", async () => {
  const uid = uniqueId("u_double");
  await seedChargedOpenApplication(uid);

  const first = await cancelOpenApplication(uid);
  const second = await cancelOpenApplication(uid);
  const third = await cancelOpenApplication(uid);
  assert.equal(first.outcome, "cancelled");
  assert.equal(second.outcome, "already_cancelled");
  assert.equal(third.outcome, "already_cancelled");
  assert.equal(second.heartRefunded, 0);
  assert.equal(await heartBalance(uid), 100, "original balance, not +cost");
  assert.equal(await refundLedgerCount(uid), 1);
});

test("concurrent cancel calls settle into exactly one refund", async () => {
  const uid = uniqueId("u_concurrent");
  await seedChargedOpenApplication(uid);

  const outcomes = await Promise.allSettled([
    cancelOpenApplication(uid),
    cancelOpenApplication(uid),
    cancelOpenApplication(uid),
  ]);
  let refundedTotal = 0;
  for (const outcome of outcomes) {
    if (outcome.status === "fulfilled") refundedTotal += outcome.value.heartRefunded;
  }
  assert.equal(refundedTotal, BLIND_MEETING_HEART_COST);
  assert.equal(await heartBalance(uid), 100);
  assert.equal(await refundLedgerCount(uid), 1);
});

test("cancel on a matched application is refused deterministically and refunds nothing", async () => {
  const uid = uniqueId("u_matched");
  await seedChargedOpenApplication(uid, {
    open: false,
    meetingId: "m_matched",
    status: PARTICIPANT_STATUS_TO_APP.confirmed,
    serverStatus: "confirmed",
    stage: "matched",
  });
  await assert.rejects(cancelOpenApplication(uid), (error: unknown) => {
    const err = error as { message: string; details?: { code?: string; meetingId?: string } };
    assert.match(err.message, new RegExp(CANCEL_ALREADY_MATCHED_CODE));
    assert.equal(err.details?.code, CANCEL_ALREADY_MATCHED_CODE);
    assert.equal(err.details?.meetingId, "m_matched");
    return true;
  });
  assert.equal(await heartBalance(uid), 100 - BLIND_MEETING_HEART_COST);
  assert.equal(await refundLedgerCount(uid), 0);
  assert.equal((await applicationStatus(uid))?.serverStatus, "confirmed");
});

test("cancel without an original spend ledger fails closed (no refund)", async () => {
  const uid = uniqueId("u_nospend");
  await db.collection("users").doc(uid).set({ heartBalance: 10 }, { merge: true });
  await seedApplication(uid, "applied", {
    open: true,
    meetingId: null,
    heartCost: BLIND_MEETING_HEART_COST,
    heartChargeCount: 1,
  });
  const result = await cancelOpenApplication(uid);
  assert.equal(result.outcome, "cancelled");
  assert.equal(result.heartRefunded, 0);
  assert.equal(await heartBalance(uid), 10);
  assert.equal(await refundLedgerCount(uid), 0);
});

test("cancelled application can re-apply and the next cancel refunds the new charge only", async () => {
  const uid = uniqueId("u_reapply");
  await seedChargedOpenApplication(uid);
  await cancelOpenApplication(uid);
  assert.equal(await heartBalance(uid), 100);

  // 재신청 (새 차감: 신청 경로가 chargeCount 2 로 다시 차감한다)
  await createPaidBlindMeetingApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.open, true);
  assert.equal(app?.heartChargeCount, 2);
  assert.equal(await heartBalance(uid), 100 - BLIND_MEETING_HEART_COST);

  const again = await cancelOpenApplication(uid);
  assert.equal(again.heartRefunded, BLIND_MEETING_HEART_COST);
  assert.equal(await heartBalance(uid), 100);
  assert.equal(await refundLedgerCount(uid), 2, "one refund per charge");
});

test("party cancel refunds every member exactly once and is idempotent", async () => {
  const leader = uniqueId("u_party_lead");
  const friend = uniqueId("u_party_friend");
  await seedChargedOpenApplication(leader, { open: false, stage: "waitingForPartyMembers" });
  await seedChargedOpenApplication(friend, { open: false, stage: "waitingForPartyMembers" });
  const partyId = uniqueId("party");
  await db.collection("blindMeetingParties").doc(partyId).set({
    partyId,
    leaderUserId: leader,
    acceptedUserIds: [leader, friend],
    pendingInviteeIds: [],
    pendingInviteIds: [],
    canonicalGender: "male",
    status: "locked",
    rosterVersion: 1,
    completedApplicationUserIds: [],
    meetingId: null,
  });
  for (const uid of [leader, friend]) {
    await db.collection("blindMeetingPartyMemberships").doc(uid).set({
      partyId,
      active: true,
    });
  }

  const summary = await cancelBlindMeetingParty(leader, partyId);
  assert.deepEqual(
    summary.map((s) => [s.userId, s.applicationCancelled, s.heartRefunded]),
    [[leader, true, BLIND_MEETING_HEART_COST], [friend, true, BLIND_MEETING_HEART_COST]]
  );
  for (const uid of [leader, friend]) {
    assert.equal(await heartBalance(uid), 100);
    assert.equal(await refundLedgerCount(uid), 1);
    assert.equal((await applicationStatus(uid))?.serverStatus, "cancelled");
  }
  // 두 번째 호출: 파티가 이미 cancelled 라 active 가 아님 → no-op, 환불 없음
  const again = await cancelBlindMeetingParty(leader, partyId);
  assert.deepEqual(again, []);
  for (const uid of [leader, friend]) {
    assert.equal(await heartBalance(uid), 100);
    assert.equal(await refundLedgerCount(uid), 1);
  }
});

// -----------------------------------------------------------------------------
// submitNewApplication — 재신청 business invariant
//
// FSM 전이(invited→applied 등)는 초대 거절 재오픈용으로 합법이지만,
// active invitation/meeting 에 귀속된 신청을 신규 submit 이 applied 로
// 덮어쓰면 안 된다. 이 guard 는 신청서와 연결 미팅을 같은 트랜잭션에서
// 읽어 판단한다.
// -----------------------------------------------------------------------------

function submitParams(uid: string) {
  return {
    userId: uid,
    dnaPayload: { userId: uid, schemaVersion: 1 },
    requestedDateKeys: ["2026-09-01"],
    prefersAlcoholFree: false,
    waitlistOptIn: true,
  };
}

// 프로덕션 신규 신청 entrypoint 는 하트 차감형
// createPaidBlindMeetingApplication 으로 교체됐다. 재신청 invariant 는 같은
// 경로에서 검증하되, 하트 잔액을 먼저 시드해 결제 가드가 invariant 검증을
// 가리지 않게 한다.
async function submitNewApplication(
  params: ReturnType<typeof submitParams>
): Promise<void> {
  await db
    .collection("users")
    .doc(params.userId)
    .set({ heartBalance: 100000 }, { merge: true });
  await createPaidBlindMeetingApplication(params);
}

async function dnaDoc(userId: string) {
  const snap = await db.collection("blindMeetingDna").doc(userId).get();
  return snap.exists ? snap.data() : null;
}

test("submit guard: no prior application creates applied + dna atomically", async () => {
  const uid = uniqueId("u");
  await submitNewApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.open, true);
  assert.equal(app?.meetingId, null);
  assert.notEqual(await dnaDoc(uid), null);
});

test("submit guard: active invitation rejects new submission untouched", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "awaiting_acceptance", [uid]);
  await seedApplication(uid, "invited", { meetingId, open: false });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_reapplication_blocked_active_meeting/
  );
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "invited");
  assert.equal(app?.meetingId, meetingId);
  // 거부된 submit 이 DNA 를 미리 덮어써서도 안 된다 (원자성).
  assert.equal(await dnaDoc(uid), null);
});

test("submit guard: accepted invitation rejects new submission", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "awaiting_acceptance", [uid]);
  await seedApplication(uid, "accepted", { meetingId, open: false });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_reapplication_blocked_active_meeting/
  );
  assert.equal((await applicationStatus(uid))?.serverStatus, "accepted");
});

test("submit guard: confirmed active meeting rejects new submission", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "chat_open", [uid]);
  await seedApplication(uid, "confirmed", { meetingId, open: false });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_reapplication_blocked_active_meeting/
  );
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "confirmed");
  assert.equal(app?.meetingId, meetingId);
});

test("submit guard: active application with missing meeting fails closed", async () => {
  const uid = uniqueId("u");
  await seedApplication(uid, "invited", {
    meetingId: uniqueId("m_missing"),
    open: false,
  });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_application_meeting_link_missing/
  );
  assert.equal((await applicationStatus(uid))?.serverStatus, "invited");
});

test("submit guard: active application on settled meeting fails closed without repair", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "cancelled", [uid]);
  await seedApplication(uid, "confirmed", { meetingId, open: false });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_application_stale_meeting_link/
  );
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "confirmed");
  assert.equal(app?.meetingId, meetingId);
});

test("submit guard: meeting-bound status without meetingId fails closed", async () => {
  const uid = uniqueId("u");
  await seedApplication(uid, "invited", { meetingId: null, open: false });

  await assert.rejects(
    submitNewApplication(submitParams(uid)),
    /blind_application_active_without_meeting/
  );
  assert.equal((await applicationStatus(uid))?.serverStatus, "invited");
});

test("submit guard: cancelled application may reapply", async () => {
  const uid = uniqueId("u");
  await seedApplication(uid, "cancelled", { meetingId: null, open: false });

  await submitNewApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.open, true);
});

test("submit guard: completed application may reapply even with stale meetingId", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedMeeting(meetingId, "read_only", [uid]);
  // 완료 정리 루프는 meetingId 를 지우지 않는다 — terminal 신청은 그래도 재신청 가능.
  await seedApplication(uid, "completed", { meetingId, open: false });

  await submitNewApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.meetingId, null);
});

test("submit guard: open applied resubmission is idempotent", async () => {
  const uid = uniqueId("u");
  await submitNewApplication(submitParams(uid));
  await submitNewApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.open, true);
});

// -----------------------------------------------------------------------------
// reopenApplicationIfBoundTo — 재오픈 쪽 대칭 guard
// -----------------------------------------------------------------------------

test("reopen guard: bound application reopens to applied", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedApplication(uid, "invited", { meetingId, open: false });

  assert.equal(await reopenApplicationIfBoundTo(uid, meetingId), true);
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.open, true);
  assert.equal(app?.meetingId, null);
});

test("reopen guard: application re-claimed by another meeting is untouched", async () => {
  const otherMeetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedApplication(uid, "invited", { meetingId: otherMeetingId, open: false });

  assert.equal(await reopenApplicationIfBoundTo(uid, uniqueId("m_old")), false);
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "invited");
  assert.equal(app?.meetingId, otherMeetingId);
});

test("reopen guard: terminal application is not resurrected", async () => {
  const meetingId = uniqueId("m");
  const uid = uniqueId("u");
  await seedApplication(uid, "cancelled", { meetingId, open: false });

  assert.equal(await reopenApplicationIfBoundTo(uid, meetingId), false);
  assert.equal((await applicationStatus(uid))?.serverStatus, "cancelled");
});

// -----------------------------------------------------------------------------
// legacy 수락 대기 미팅 정규화 (LEGACY_COMPATIBILITY_ONLY)
//
// 수락 단계는 제거됐다. 과거에 awaiting_acceptance 로 남은 미팅은 좌석이 모두
// 유지돼 있으면 새 계약(매칭 = 확정)대로 서버가 확정하고 채팅방을 연다.
// -----------------------------------------------------------------------------

async function seedInvitedMeeting(): Promise<{
  meetingId: string;
  uids: string[];
}> {
  const meetingId = uniqueId("m");
  const uids = Array.from({ length: 6 }, () => uniqueId("u"));
  await seedMeeting(meetingId, "awaiting_acceptance", uids);
  await seedGenderedUsers(uids);
  for (const uid of uids) {
    await seedParticipant(meetingId, uid, "invited");
    await seedApplication(uid, "invited", { meetingId, open: false });
  }
  return { meetingId, uids };
}

test("legacy awaiting_acceptance with all six seats held → confirmed/chat_open + one room, no user action", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();

  const confirmed = await confirmLegacyAwaitingAcceptanceMeeting(meetingId);
  assert.equal(confirmed, true);

  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "chat_open");
  assert.equal(meetingSnap.data()?.groupChatId, `blind_${meetingId}`);
  assert.ok(meetingSnap.data()?.confirmedAt != null);

  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed");
    const participantSnap = await db
      .collection("blindMeetings")
      .doc(meetingId)
      .collection("participants")
      .doc(uid)
      .get();
    assertNoDepositFields(participantSnap.data());
    const app = await applicationStatus(uid);
    assert.equal(app?.serverStatus, "confirmed");
    assert.equal(app?.stage, "matched");
  }
  assertNoDepositFields(meetingSnap.data());
  await assertNoDepositLedger(meetingId);

  const roomSnap = await db
    .collection("chat_rooms")
    .doc(`blind_${meetingId}`)
    .get();
  assert.deepEqual(roomSnap.data()?.participantIds, uids);

  // 재실행은 idempotent (방 1개, 상태 유지)
  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), true);
  const rooms = await db
    .collection("chat_rooms")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(rooms.size, 1);
});

test("legacy awaiting_acceptance with a vacated seat is never confirmed by the direct path", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await seedParticipant(meetingId, uids[1], "cancelled");

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), false);
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "awaiting_acceptance");
  assert.equal(meetingSnap.data()?.groupChatId, undefined);
  const roomSnap = await db
    .collection("chat_rooms")
    .doc(`blind_${meetingId}`)
    .get();
  assert.equal(roomSnap.exists, false);
});

test("scheduler sweep confirms intact legacy meetings and skips vacated ones", async () => {
  const intact = await seedInvitedMeeting();
  const vacated = await seedInvitedMeeting();
  await seedParticipant(vacated.meetingId, vacated.uids[0], "cancelled");

  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  const byId = new Map(outcomes.map((o) => [o.meetingId, o.outcome]));
  assert.equal(byId.get(intact.meetingId), "confirmed");
  // 빈 좌석 + 대체 진행 없음 → 취소가 아니라 repair 표시 (타이머 없음).
  assert.equal(byId.get(vacated.meetingId), "repair_required");
  assert.equal(
    (await db.collection("blindMeetings").doc(intact.meetingId).get()).data()?.serverStatus,
    "chat_open"
  );
  assert.equal(
    (await db.collection("blindMeetings").doc(vacated.meetingId).get()).data()?.serverStatus,
    "awaiting_acceptance"
  );
});

test("five-person vote: a finalized no_show cannot veto the remaining participants", async () => {
  // participantIds 는 좌석 명부라 노쇼도 남는다. 그것만 확인하면 결원을 만든
  // 당사자가 "거부" 한 표로 남은 다섯 명의 진행 결정을 뒤집고 미팅을 취소시킨다.
  const meetingId = uniqueId("m_veto");
  const seats = [
    uniqueId("u"), uniqueId("u"), uniqueId("u"),
    uniqueId("u"), uniqueId("u"), uniqueId("u"),
  ];
  await seedMeeting(meetingId, "checkin_open", seats);
  for (const uid of seats.slice(0, 5)) {
    await seedParticipant(meetingId, uid, "confirmed");
  }
  const noShowUid = seats[5];
  await seedParticipant(meetingId, noShowUid, "no_show");

  await assert.rejects(
    () => voteFivePersonException({ meetingId, userId: noShowUid, agree: false }),
    (error: unknown) => String((error as Error).message).length > 0
  );

  // 거부표가 저장되지 않았고 미팅도 취소되지 않았다.
  const votes = await db
    .collection("blindMeetings").doc(meetingId)
    .collection("fivePersonVotes").get();
  assert.equal(votes.size, 0, "노쇼의 표는 기록되지 않는다");
  const meeting = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meeting.data()?.serverStatus, "checkin_open", "미팅이 취소되면 안 된다");

  // 정상 참가자는 그대로 투표할 수 있다.
  await voteFivePersonException({ meetingId, userId: seats[0], agree: true });
  const after = await db
    .collection("blindMeetings").doc(meetingId)
    .collection("fivePersonVotes").get();
  assert.equal(after.size, 1, "정상 참가자 투표는 기록된다");
});

// -----------------------------------------------------------------------------
// legacy awaiting_deposits 문서 복구 — 결제 없이 canonical 상태로
// -----------------------------------------------------------------------------

async function seedLegacyDepositMeeting(
  participantStatuses: ParticipantStatus[]
): Promise<{ meetingId: string; uids: string[] }> {
  const meetingId = uniqueId("m_legacy");
  const uids = Array.from({ length: 6 }, () => uniqueId("u"));
  await db.collection("blindMeetings").doc(meetingId).set({
    status: LEGACY_MEETING_STATUS_AWAITING_DEPOSITS_APP,
    serverStatus: LEGACY_MEETING_STATUS_AWAITING_DEPOSITS,
    participantIds: uids,
    teamAUserIds: uids.slice(0, 3),
    teamBUserIds: uids.slice(3, 6),
    commonAvailableDateKeys: ["20260901"],
    matchedDateKey: "20260901",
    isAlcoholFree: false,
    // 과거 문서에 남아 있을 수 있는 결제 필드 — 무시되어야 한다.
    depositsOpenedAt: new Date(),
    depositAmount: 5000,
  });
  await seedGenderedUsers(uids);
  for (const [index, uid] of uids.entries()) {
    await seedParticipant(meetingId, uid, participantStatuses[index], {
      depositStatus: "pending",
      serverDepositStatus: "pending",
    });
    await seedApplication(uid, participantStatuses[index], {
      meetingId,
      open: false,
    });
  }
  return { meetingId, uids };
}

async function assertNoAcceptanceStateEver(meetingId: string): Promise<void> {
  const snap = await db.collection("blindMeetings").doc(meetingId).get();
  const data = snap.data() ?? {};
  assert.notEqual(data.serverStatus, "awaiting_acceptance", "awaiting_acceptance must never be written");
  assert.notEqual(data.status, MEETING_STATUS_TO_APP.awaiting_acceptance);
  assert.equal(data.acceptanceWindowStartedAt, undefined, "no acceptance window");
  assert.equal(data.acceptanceDeadline, undefined);
}

async function assertSingleRoom(meetingId: string, uids: string[]): Promise<void> {
  const rooms = await db
    .collection("chat_rooms")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(rooms.size, 1, "exactly one room per meeting");
  assert.deepEqual([...(rooms.docs[0].data().participantIds as string[])].sort(), [...uids].sort());
}

test("A1: legacy awaiting_deposits with an intact 3M+3F match → confirmed + one room, no user action, no acceptance state", async () => {
  // 과거 상태가 섞여 있어도(invited/accepted/legacy deposit_pending) 수락 수를
  // 세지 않는다. canonical 좌석 6개가 온전하면 매칭 = 확정 계약으로 확정한다.
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "invited", "accepted", "confirmed", "accepted", "accepted",
  ]);
  await db
    .collection("blindMeetings").doc(meetingId)
    .collection("participants").doc(uids[0])
    .set(
      {
        status: LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING_APP,
        serverStatus: LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING,
      },
      { merge: true }
    );

  const outcome = await repairLegacyMeetingStatus(meetingId);
  assert.equal(outcome, "confirmed");

  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "chat_open");
  assert.equal(meetingSnap.data()?.groupChatId, `blind_${meetingId}`);
  assert.equal(meetingSnap.data()?.legacyRepairRequired, undefined);
  await assertNoAcceptanceStateEver(meetingId);
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed");
    assert.equal((await applicationStatus(uid))?.serverStatus, "confirmed");
  }
  await assertSingleRoom(meetingId, uids);
  await assertNoDepositLedger(meetingId);

  // 재실행은 no-op 이고 방도 하나다 (idempotent).
  assert.equal(await repairLegacyMeetingStatus(meetingId), "not_legacy");
  await assertSingleRoom(meetingId, uids);
});

test("A2: legacy awaiting_deposits with 5 seats → repair, not confirmed, not awaiting_acceptance", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  await db.collection("blindMeetings").doc(meetingId).set(
    { participantIds: uids.slice(0, 5), teamBUserIds: uids.slice(3, 5) },
    { merge: true }
  );

  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  assert.equal(meetingSnap.data()?.legacyRepairRequired, true);
  assert.ok((meetingSnap.data()?.legacyRepairReasons as string[]).some((r) => r.startsWith("seat_count")));
  assert.equal(meetingSnap.data()?.groupChatId, undefined);
  await assertNoAcceptanceStateEver(meetingId);
  const rooms = await db.collection("chat_rooms").where("meetingId", "==", meetingId).get();
  assert.equal(rooms.size, 0);
});

test("A3: legacy awaiting_deposits with 4M+2F → repair", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  // 여성 좌석 하나를 남성으로 바꿔 성비를 깨뜨린다.
  await db.collection("users").doc(uids[5]).set(
    { onboarding: { gender: "male" } },
    { merge: true }
  );

  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  assert.equal(meetingSnap.data()?.legacyRepairRequired, true);
  assert.ok((meetingSnap.data()?.legacyRepairReasons as string[]).some((r) => /gender/i.test(r)));
  assert.equal(meetingSnap.data()?.groupChatId, undefined);
  await assertNoAcceptanceStateEver(meetingId);
  for (const uid of uids) {
    assert.notEqual(await participantStatus(meetingId, uid), "confirmed");
  }
});

test("A3b: legacy awaiting_deposits with a duplicate seat uid → repair", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  await db.collection("blindMeetings").doc(meetingId).set(
    { participantIds: [uids[0], uids[0], uids[2], uids[3], uids[4], uids[5]] },
    { merge: true }
  );
  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  await assertNoAcceptanceStateEver(meetingId);
  assert.equal((await db.collection("blindMeetings").doc(meetingId).get()).data()?.groupChatId, undefined);
});

test("A3c: legacy awaiting_deposits with a detached application → repair", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  // 한 좌석의 신청서가 다른 미팅에 재클레임됐다 (linkage 깨짐).
  await db.collection("blindMeetingApplications").doc(uids[1]).set(
    { meetingId: uniqueId("m_other") },
    { merge: true }
  );
  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.ok((meetingSnap.data()?.legacyRepairReasons as string[]).some((r) => r.startsWith("application_detached")));
  await assertNoAcceptanceStateEver(meetingId);
});

test("A3d: legacy awaiting_deposits with a vacated (cancelled) seat → repair, never awaiting_acceptance", async () => {
  const { meetingId } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "cancelled",
  ]);
  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  assert.equal(meetingSnap.data()?.groupChatId, undefined);
  await assertNoAcceptanceStateEver(meetingId);
});

test("legacy awaiting_deposits with a missing participant doc is flagged for repair, not confirmed", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  await db
    .collection("blindMeetings").doc(meetingId)
    .collection("participants").doc(uids[2])
    .delete();

  assert.equal(
    await repairLegacyMeetingStatus(meetingId),
    "repair_required"
  );
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  assert.equal(meetingSnap.data()?.legacyRepairRequired, true);
  assert.equal(meetingSnap.data()?.groupChatId, undefined);
  await assertNoAcceptanceStateEver(meetingId);
  const review = await db
    .collection("blindMeetingOpsReviews")
    .doc(`${meetingId}_meeting_legacy_status_repair`)
    .get();
  assert.equal(review.exists, true);
});

test("A4: repair-marked legacy doc is not mutated again by reruns (single review, no duplicate writes)", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  await db
    .collection("blindMeetings").doc(meetingId)
    .collection("participants").doc(uids[2])
    .delete();
  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  const flaggedAt = (await db.collection("blindMeetings").doc(meetingId).get()).data()?.legacyRepairFlaggedAt;

  // 다음 tick 들: 표시된 문서는 다시 쓰지 않는다 (운영자 수정 대기).
  for (let i = 0; i < 3; i++) {
    assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_pending");
  }
  const after = (await db.collection("blindMeetings").doc(meetingId).get()).data() ?? {};
  assert.deepEqual(after.legacyRepairFlaggedAt, flaggedAt, "flag timestamp untouched");
  assert.equal(after.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  const reviews = await db
    .collection("blindMeetingOpsReviews")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(reviews.size, 1, "exactly one review record");
  await assertNoAcceptanceStateEver(meetingId);
});

test("legacy awaiting_deposits with a post-confirm participant state is flagged for repair", async () => {
  const { meetingId } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "completed",
  ]);
  assert.equal(
    await repairLegacyMeetingStatus(meetingId),
    "repair_required"
  );
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, LEGACY_MEETING_STATUS_AWAITING_DEPOSITS);
  assert.equal(meetingSnap.data()?.legacyRepairRequired, true);
  await assertNoAcceptanceStateEver(meetingId);
});

test("concurrent normalizer runs on one legacy meeting converge to one confirmed meeting and one room", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "accepted",
  ]);
  const outcomes = await Promise.allSettled([
    repairLegacyMeetingStatus(meetingId),
    repairLegacyMeetingStatus(meetingId),
    repairLegacyMeetingStatus(meetingId),
  ]);
  for (const outcome of outcomes) {
    assert.equal(outcome.status, "fulfilled", String((outcome as PromiseRejectedResult).reason));
  }
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "chat_open");
  assert.equal(meetingSnap.data()?.legacyRepairRequired, undefined);
  await assertSingleRoom(meetingId, uids);
  await assertNoAcceptanceStateEver(meetingId);
});

test("canonical meeting is not touched by the legacy normalizer", async () => {
  const { meetingId } = await seedInvitedMeeting();
  assert.equal(await repairLegacyMeetingStatus(meetingId), "not_legacy");
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "awaiting_acceptance");
});

// -----------------------------------------------------------------------------
// 취소 / 노쇼 — 결제·환급 subsystem 없이 terminal 상태로 수렴
// -----------------------------------------------------------------------------

async function seedConfirmedMeetingWithRoom(): Promise<{
  meetingId: string;
  uids: string[];
}> {
  const seeded = await seedInvitedMeeting();
  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(seeded.meetingId), true);
  const meetingSnap = await db.collection("blindMeetings").doc(seeded.meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "chat_open");
  return seeded;
}

test("cancelMeeting settles every seat and reopens applications without a payment subsystem", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithRoom();

  await cancelMeeting(meetingId, "five_person_rejected");

  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "cancelled");
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "cancelled");
    const app = await applicationStatus(uid);
    assert.equal(app?.serverStatus, "applied");
    assert.equal(app?.open, true);
    const participantSnap = await db
      .collection("blindMeetings").doc(meetingId)
      .collection("participants").doc(uid)
      .get();
    assertNoDepositFields(participantSnap.data());
  }
  await assertNoDepositLedger(meetingId);
});

test("no_show settlement revokes chat membership and restricts without any refund dependency", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithRoom();
  await db.collection("blindMeetings").doc(meetingId).set(
    { status: MEETING_STATUS_TO_APP.checkin_open, serverStatus: "checkin_open" },
    { merge: true }
  );
  const noShowUid = uids[4];

  await settleCancellation({
    meetingId,
    userId: noShowUid,
    replacementFound: false,
    emergency: false,
    isNoShowWithoutContact: true,
  });

  assert.equal(await participantStatus(meetingId, noShowUid), "no_show");
  assert.equal((await applicationStatus(noShowUid))?.serverStatus, "no_show");
  const roomSnap = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.equal(
    (roomSnap.data()?.participantIds as string[]).includes(noShowUid),
    false,
    "no_show loses chat membership"
  );
  const restriction = await db
    .collection("blindMeetingRestrictions")
    .doc(noShowUid)
    .get();
  assert.equal(restriction.exists, true, "no_show is restricted");
  const participantSnap = await db
    .collection("blindMeetings").doc(meetingId)
    .collection("participants").doc(noShowUid)
    .get();
  assertNoDepositFields(participantSnap.data());
  assert.equal(participantSnap.data()?.settlementOutcome, "no_show");
  await assertNoDepositLedger(meetingId);
});

test("emergency cancellation settles the seat immediately and leaves an ops review", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithRoom();
  const leaver = uids[1];

  await settleCancellation({
    meetingId,
    userId: leaver,
    replacementFound: false,
    emergency: true,
  });

  assert.equal(await participantStatus(meetingId, leaver), "cancelled");
  assert.equal((await applicationStatus(leaver))?.serverStatus, "cancelled");
  const roomSnap = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.equal((roomSnap.data()?.participantIds as string[]).includes(leaver), false);
  const review = await db
    .collection("blindMeetingOpsReviews")
    .doc(`${meetingId}_${leaver}_emergency_cancellation`)
    .get();
  assert.equal(review.exists, true);
  const restriction = await db.collection("blindMeetingRestrictions").doc(leaver).get();
  assert.equal(restriction.exists, false, "emergency cancellation is not sanctioned");
  await assertNoDepositLedger(meetingId);
});

// -----------------------------------------------------------------------------
// 독립 리뷰 finding 회귀 (2026-09-03)
// -----------------------------------------------------------------------------

test("party cancel skips members already settled after a match (no refund, status untouched)", async () => {
  const leader = uniqueId("u_party_lead2");
  const noShow = uniqueId("u_party_noshow");
  await seedChargedOpenApplication(leader, { open: false, stage: "waitingForPartyMembers" });
  // 매칭 후 노쇼로 정산된 멤버: meetingId 는 null 이지만 terminal 상태다.
  await seedChargedOpenApplication(noShow, {
    open: false,
    status: PARTICIPANT_STATUS_TO_APP.no_show,
    serverStatus: "no_show",
    stage: "matched",
  });
  const partyId = uniqueId("party2");
  await db.collection("blindMeetingParties").doc(partyId).set({
    partyId,
    leaderUserId: leader,
    acceptedUserIds: [leader, noShow],
    pendingInviteeIds: [],
    pendingInviteIds: [],
    canonicalGender: "male",
    status: "locked",
    rosterVersion: 1,
    completedApplicationUserIds: [],
    meetingId: null,
  });
  for (const uid of [leader, noShow]) {
    await db.collection("blindMeetingPartyMemberships").doc(uid).set({ partyId, active: true });
  }

  const summary = await cancelBlindMeetingParty(leader, partyId);
  assert.deepEqual(
    summary.map((s) => [s.userId, s.applicationCancelled, s.heartRefunded]),
    [[leader, true, BLIND_MEETING_HEART_COST], [noShow, false, 0]]
  );
  assert.equal(await heartBalance(noShow), 100 - BLIND_MEETING_HEART_COST, "no refund after match");
  assert.equal(await refundLedgerCount(noShow), 0);
  assert.equal((await applicationStatus(noShow))?.serverStatus, "no_show", "terminal status untouched");
  assert.equal(await heartBalance(leader), 100);
});

test("cancel → DNA start twice charges once (stale dnaApplicationCompleted is cleared)", async () => {
  const uid = uniqueId("u_restart");
  await db.collection("users").doc(uid).set(
    {
      heartBalance: 100 - BLIND_MEETING_HEART_COST,
      isStudentVerified: true,
      onboarding: { lifestyle: { drinking: "sometimes", smoking: "nonSmoker" } },
    },
    { merge: true }
  );
  await db.collection("heartTransactions").doc(blindMeetingHeartSpendId(uid, 1)).set({
    uid,
    feature: "blind_meeting",
    amount: BLIND_MEETING_HEART_COST,
    createdAt: new Date(),
  });
  await seedApplication(uid, "applied", {
    open: true,
    meetingId: null,
    heartCost: BLIND_MEETING_HEART_COST,
    heartChargeCount: 1,
    dnaApplicationCompleted: true,
  });
  const cancelled = await cancelOpenApplication(uid);
  assert.equal(cancelled.heartRefunded, BLIND_MEETING_HEART_COST);
  assert.equal((await applicationStatus(uid))?.dnaApplicationCompleted, false);
  assert.equal(await heartBalance(uid), 100);

  const first = await startPaidBlindMeetingDna(uid);
  assert.equal(first.charged, true);
  assert.equal(first.heartChargeCount, 2);
  assert.equal(await heartBalance(uid), 100 - BLIND_MEETING_HEART_COST);

  // 재진입/재시도: 이어쓰기 초안을 그대로 돌려주고 다시 차감하지 않는다.
  const second = await startPaidBlindMeetingDna(uid);
  assert.equal(second.charged, false);
  assert.equal(second.heartChargeCount, 2);
  assert.equal(await heartBalance(uid), 100 - BLIND_MEETING_HEART_COST, "charged exactly once");
});

test("re-apply clears stale refund/cancel fields on the application", async () => {
  const uid = uniqueId("u_stale");
  await seedChargedOpenApplication(uid);
  await cancelOpenApplication(uid);
  assert.equal((await applicationStatus(uid))?.heartRefundedAmount, BLIND_MEETING_HEART_COST);

  await createPaidBlindMeetingApplication(submitParams(uid));
  const app = await applicationStatus(uid);
  assert.equal(app?.serverStatus, "applied");
  assert.equal(app?.heartRefundedAmount, undefined);
  assert.equal(app?.heartRefundedAt, undefined);
  assert.equal(app?.cancelledAt, undefined);
  assert.equal(app?.dnaApplicationCompleted, true);
});

test("cancelMeeting resets a matched party to ready so its members can be re-matched", async () => {
  const seeded = await seedInvitedMeeting();
  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(seeded.meetingId), true);
  const partyId = uniqueId("party_matched");
  const members = seeded.uids.slice(0, 2);
  await db.collection("blindMeetingParties").doc(partyId).set({
    partyId,
    leaderUserId: members[0],
    acceptedUserIds: members,
    pendingInviteeIds: [],
    pendingInviteIds: [],
    canonicalGender: "male",
    status: "matched",
    meetingId: seeded.meetingId,
    rosterVersion: 1,
    completedApplicationUserIds: members,
  });

  await cancelMeeting(seeded.meetingId, "five_person_rejected");

  const party = (await db.collection("blindMeetingParties").doc(partyId).get()).data();
  assert.equal(party?.status, "ready");
  assert.equal(party?.meetingId, null);
  for (const uid of members) {
    const app = await applicationStatus(uid);
    assert.equal(app?.serverStatus, "applied");
    assert.equal(app?.open, true);
  }
});

// -----------------------------------------------------------------------------
// FINAL RELEASE CLOSURE ② — legacy acceptance timeout 완전 제거
//
// legacy awaiting_acceptance 미팅은 사용자 수락을 다시 기다리지 않는다.
//   온전한 canonical match      → 확정 (응답 창이 아무리 오래 지났어도)
//   대체 충원 진행 중           → 취소하지 않고 replacement FSM 에 맡긴다
//   빈 좌석 + 대체 진행 없음     → legacyRepairRequired 1회 (취소 아님, 타이머 아님)
// -----------------------------------------------------------------------------

const LONG_AGO = new Date(Date.now() - 30 * 24 * 3600 * 1000);

test("closure②: legacy awaiting_acceptance whose old response window expired long ago is confirmed, not cancelled", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await db.collection("blindMeetings").doc(meetingId).set(
    { createdAt: LONG_AGO, acceptanceWindowStartedAt: LONG_AGO },
    { merge: true }
  );

  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  const mine = outcomes.find((o) => o.meetingId === meetingId);
  assert.equal(mine?.outcome, "confirmed");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "chat_open");
  assert.equal(data?.cancelReason, undefined, "never cancelled by a timeout");
  assert.equal(data?.legacyRepairRequired, undefined);
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed");
  }
  // 성별 스냅샷이 확정 시점에 고정된다 (③ 의 복구 근거).
  const genders = data?.participantGenders as Record<string, string>;
  assert.equal(Object.keys(genders ?? {}).length, 6);
  assert.equal(Object.values(genders).filter((g) => g === "male").length, 3);
  assert.equal(Object.values(genders).filter((g) => g === "female").length, 3);
});

test("closure②: legacy awaiting_acceptance with replacement_pending + expired window is NOT cancelled (left to the replacement FSM)", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await seedParticipant(meetingId, uids[2], "replacement_pending");
  await db.collection("blindMeetings").doc(meetingId).set(
    { createdAt: LONG_AGO, acceptanceWindowStartedAt: LONG_AGO },
    { merge: true }
  );

  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  const mine = outcomes.find((o) => o.meetingId === meetingId);
  assert.equal(mine?.outcome, "replacement_in_progress");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "awaiting_acceptance", "status untouched");
  assert.equal(data?.legacyRepairRequired, undefined, "not a repair case");
  assert.equal(data?.acceptanceDeadline, undefined);
  assert.equal(await participantStatus(meetingId, uids[2]), "replacement_pending");
  const reviews = await db
    .collection("blindMeetingOpsReviews")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(reviews.size, 0);
});

test("closure②: legacy awaiting_acceptance with an open replacement offer is left to the replacement FSM", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await seedParticipant(meetingId, uids[4], "cancelled");
  await db.collection("blindMeetingReplacementOffers").doc(`${meetingId}_${uids[4]}_cand`).set({
    meetingId,
    vacantParticipantId: uids[4],
    candidateUid: "cand",
    offerStatus: "offered",
    expiresAt: new Date(Date.now() + 3600 * 1000),
  });

  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(outcomes.find((o) => o.meetingId === meetingId)?.outcome, "replacement_in_progress");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "awaiting_acceptance");
  assert.equal(data?.legacyRepairRequired, undefined);
});

test("closure②: legacy awaiting_acceptance with a vacated seat and no replacement → repair marker once, never cancelled", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await seedParticipant(meetingId, uids[1], "cancelled");
  await db.collection("blindMeetings").doc(meetingId).set(
    { createdAt: LONG_AGO, acceptanceWindowStartedAt: LONG_AGO },
    { merge: true }
  );

  const first = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(first.find((o) => o.meetingId === meetingId)?.outcome, "repair_required");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "awaiting_acceptance", "not cancelled");
  assert.equal(data?.legacyRepairRequired, true);
  assert.ok(Array.isArray(data?.legacyRepairReasons) && data!.legacyRepairReasons.length > 0);
  const reviewId = `${meetingId}_meeting_legacy_status_repair`;
  assert.equal((await db.collection("blindMeetingOpsReviews").doc(reviewId).get()).exists, true);
  const flaggedAt = data?.legacyRepairFlaggedAt;

  // 다음 tick: 같은 문서를 다시 쓰지 않는다 (duplicate side effect 0).
  const second = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(second.find((o) => o.meetingId === meetingId)?.outcome, "repair_pending");
  const again = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.deepEqual(again?.legacyRepairFlaggedAt, flaggedAt, "flag timestamp unchanged");
  assert.equal(again?.serverStatus, "awaiting_acceptance");
  const reviews = await db
    .collection("blindMeetingOpsReviews")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(reviews.size, 1);
  for (const uid of uids) {
    const app = await applicationStatus(uid);
    assert.equal(app?.meetingId, meetingId, "applications are not reopened by a timeout");
  }
});

// -----------------------------------------------------------------------------
// FINAL RELEASE CLOSURE ③ — groupChatRepair 복구 정책
//
// 복구 근거 우선순위: 미팅 participantGenders 스냅샷 → 참가자 문서 gender →
// 현재 users 문서. 근거가 없으면 fail-closed + groupChatRepairRequired 1회,
// 이후 tick 은 같은 오류/write 를 반복하지 않는다.
// -----------------------------------------------------------------------------

/** 매칭 tx 가 만든 것과 같은 모양의 confirmed 미팅 (방 없음, 성별 스냅샷 포함). */
async function seedConfirmedMeetingWithoutRoom(options: {
  withSnapshot: boolean;
}): Promise<{ meetingId: string; uids: string[] }> {
  const meetingId = uniqueId("m_repair");
  const uids = Array.from({ length: 6 }, () => uniqueId("u_repair"));
  await seedMeeting(meetingId, "confirmed", uids);
  await seedGenderedUsers(uids);
  for (const [index, uid] of uids.entries()) {
    await seedParticipant(meetingId, uid, "confirmed", {
      ...(options.withSnapshot ? { gender: index < 3 ? "male" : "female" } : {}),
    });
    await seedApplication(uid, "confirmed", { meetingId, open: false });
  }
  if (options.withSnapshot) {
    const participantGenders: Record<string, string> = {};
    uids.forEach((uid, index) => {
      participantGenders[uid] = index < 3 ? "male" : "female";
    });
    await db.collection("blindMeetings").doc(meetingId).set({ participantGenders }, { merge: true });
  }
  return { meetingId, uids };
}

async function dropCurrentGender(uid: string): Promise<void> {
  await db.collection("users").doc(uid).set(
    { onboarding: { gender: FieldValue.delete() }, gender: FieldValue.delete() },
    { merge: true }
  );
}

test("closure③: repair with match-time gender snapshot succeeds even when a current gender field is missing", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithoutRoom({ withSnapshot: true });
  await dropCurrentGender(uids[0]);

  const outcome = await repairConfirmedMeetingGroupChat(meetingId);
  assert.equal(outcome, "opened");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "chat_open");
  assert.equal(data?.groupChatId, `blind_${meetingId}`);
  assert.equal(data?.groupChatRepairRequired, undefined);
  const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.deepEqual([...(room.data()?.participantIds as string[])].sort(), [...uids].sort());
});

test("closure③: repair falls back to the participant-document gender when the meeting snapshot is absent", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithoutRoom({ withSnapshot: true });
  await db.collection("blindMeetings").doc(meetingId).set({ participantGenders: FieldValue.delete() }, { merge: true });
  await dropCurrentGender(uids[5]);

  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "opened");
  assert.equal((await db.collection("blindMeetings").doc(meetingId).get()).data()?.serverStatus, "chat_open");
});

test("closure③: evidence truly missing → fail closed, repair marker + ops review exactly once, no retry loop", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithoutRoom({ withSnapshot: false });
  await dropCurrentGender(uids[2]);

  const first = await repairConfirmedMeetingGroupChat(meetingId);
  assert.equal(first, "repair_required");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "confirmed", "status untouched (fail-closed)");
  assert.equal(data?.groupChatRepairRequired, true);
  assert.ok(typeof data?.groupChatRepairReason === "string" && data!.groupChatRepairReason.length > 0);
  const flaggedAt = data?.groupChatRepairFlaggedAt;
  const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.equal(room.exists, false, "no room without a canonical 3M+3F evidence");
  const reviewId = `${meetingId}_meeting_group_chat_repair`;
  assert.equal((await db.collection("blindMeetingOpsReviews").doc(reviewId).get()).exists, true);

  // 다음 tick 들: 같은 write/오류를 반복하지 않는다.
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "repair_pending");
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "repair_pending");
  const again = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.deepEqual(again?.groupChatRepairFlaggedAt, flaggedAt);
  const reviews = await db
    .collection("blindMeetingOpsReviews")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(reviews.size, 1, "single review document");
});

test("closure③: repair is idempotent on a healthy meeting (one room, one chat_open, no duplicate notifications)", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithoutRoom({ withSnapshot: true });
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "opened");
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "not_confirmed");
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "not_confirmed");
  const rooms = await db.collection("chat_rooms").where("meetingId", "==", meetingId).get();
  assert.equal(rooms.size, 1);
  // 인앱 알림은 users/{uid}/notifications/{idempotencyKey} 에 저장된다.
  for (const uid of uids) {
    const notifications = await db
      .collection("users")
      .doc(uid)
      .collection("notifications")
      .where("meetingId", "==", meetingId)
      .where("type", "==", "blind_meeting_chat_created")
      .get();
    assert.equal(notifications.size, 1, `exactly one chat_created notification for ${uid}`);
  }
});

test("closure③: repair never rebuilds the roster from a mutable profile — a corrupted current gender does not override the snapshot", async () => {
  const { meetingId, uids } = await seedConfirmedMeetingWithoutRoom({ withSnapshot: true });
  // 현재 프로필이 잘못 바뀌어 4M+2F 처럼 보이더라도 확정 시점 스냅샷이 우선한다.
  await db.collection("users").doc(uids[5]).set({ onboarding: { gender: "male" } }, { merge: true });
  assert.equal(await repairConfirmedMeetingGroupChat(meetingId), "opened");
  const room = await db.collection("chat_rooms").doc(`blind_${meetingId}`).get();
  assert.deepEqual([...(room.data()?.participantIds as string[])].sort(), [...uids].sort());
});

// -----------------------------------------------------------------------------
// 독립 리뷰 finding 회귀 (release review, 2026-09-04)
//
// legacy 경로의 무결성 검사는 신규 매칭 tx 와 같은 강도여야 한다. 약하면
// 손상된 legacy 미팅이 자동 확정돼 6인 방이 열리고, 이후 대체 충원조차
// 좌석 스냅샷 불일치로 조용히 실패한다.
// -----------------------------------------------------------------------------

test("review P2-1: legacy meeting whose teams are not single-gender is flagged, never confirmed", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  // 총원은 3남+3녀 그대로지만 팀이 섞여 있다: teamA=[남,남,여] / teamB=[여,여,남].
  await db.collection("blindMeetings").doc(meetingId).set(
    {
      teamAUserIds: [uids[0], uids[1], uids[3]],
      teamBUserIds: [uids[4], uids[5], uids[2]],
    },
    { merge: true }
  );

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), false);
  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(
    outcomes.find((o) => o.meetingId === meetingId)?.outcome,
    "repair_required"
  );
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "awaiting_acceptance", "not confirmed");
  assert.equal(data?.legacyRepairRequired, true);
  assert.ok(
    (data?.legacyRepairReasons as string[]).includes("team_gender_split"),
    JSON.stringify(data?.legacyRepairReasons)
  );
  assert.equal(
    (await db.collection("chat_rooms").doc(`blind_${meetingId}`).get()).exists,
    false,
    "no room for a corrupted team split"
  );
});

test("review P2-1b: legacy meeting whose team arrays do not cover the roster is flagged", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await db.collection("blindMeetings").doc(meetingId).set(
    { teamBUserIds: [uids[3], uids[4]] },
    { merge: true }
  );

  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(
    outcomes.find((o) => o.meetingId === meetingId)?.outcome,
    "repair_required"
  );
  const reasons = (
    await db.collection("blindMeetings").doc(meetingId).get()
  ).data()?.legacyRepairReasons as string[];
  assert.ok(reasons.includes("team_size:3+2"), JSON.stringify(reasons));
  assert.ok(reasons.includes("team_roster_mismatch"), JSON.stringify(reasons));
});

test("review P2-4: an already-confirmed application no longer aborts the confirm loop midway", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  // 부분 승격된 상태(재시도): 참가자는 invited 인데 신청서는 이미 confirmed.
  // 예전에는 FSM 이 accepted 재기록을 거부해 루프가 상태 전이 뒤에서 멈췄고
  // "confirmed 인데 방 없음" 이 남았다.
  await seedApplication(uids[2], "confirmed", { meetingId, open: false });

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), true);
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "chat_open", "확정이 끝까지 진행된다");
  assert.equal(data?.groupChatId, `blind_${meetingId}`);
  assert.equal(data?.legacyRepairRequired, undefined);
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed");
    assert.equal((await applicationStatus(uid))?.serverStatus, "confirmed");
  }
  const rooms = await db
    .collection("chat_rooms")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(rooms.size, 1);
});

test("review P2-4b: a bound application in a non-promotable status is flagged before any transition", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  // 손상: 신청서가 이 미팅에 묶인 채 terminal 상태다. 승격할 수 없으므로
  // 상태 전이 이전에 걸러야 "confirmed 인데 방 없음" 이 생기지 않는다.
  await seedApplication(uids[2], "no_show", { meetingId, open: false });

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), false);
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "awaiting_acceptance");
  assert.equal(data?.groupChatId, undefined);
  assert.equal(
    (await db.collection("chat_rooms").doc(`blind_${meetingId}`).get()).exists,
    false
  );
  const outcomes = await repairLegacyAwaitingAcceptanceMeetings();
  assert.equal(
    outcomes.find((o) => o.meetingId === meetingId)?.outcome,
    "repair_required"
  );
  const reasons = (
    await db.collection("blindMeetings").doc(meetingId).get()
  ).data()?.legacyRepairReasons as string[];
  assert.ok(
    reasons.some((r) => r.startsWith("application_status:")),
    JSON.stringify(reasons)
  );
});

test("review P2-3: legacy awaiting_deposits with a replacement in progress defers instead of flagging", async () => {
  const { meetingId, uids } = await seedLegacyDepositMeeting([
    "accepted", "accepted", "accepted", "accepted", "accepted", "cancelled",
  ]);
  await db.collection("blindMeetingReplacementOffers").doc(`${meetingId}_${uids[5]}_cand`).set({
    meetingId,
    vacantParticipantId: uids[5],
    candidateUid: "cand_dep",
    offerStatus: "offered",
    expiresAt: new Date(Date.now() + 3600 * 1000),
  });

  assert.equal(await repairLegacyMeetingStatus(meetingId), "replacement_in_progress");
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.legacyRepairRequired, undefined, "not flagged while replacing");
  assert.equal(
    (await db.collection("blindMeetingOpsReviews").doc(`${meetingId}_meeting_legacy_status_repair`).get()).exists,
    false
  );
  // 대체 제안이 사라지면 그때 repair 로 넘어간다 (두 legacy 경로가 같은 판단).
  await db.collection("blindMeetingReplacementOffers").doc(`${meetingId}_${uids[5]}_cand`).set(
    { offerStatus: "expired" },
    { merge: true }
  );
  assert.equal(await repairLegacyMeetingStatus(meetingId), "repair_required");
  assert.equal(
    (await db.collection("blindMeetings").doc(meetingId).get()).data()?.legacyRepairRequired,
    true
  );
});

test("recheck P2-1: a participant ahead of its application still confirms the whole roster", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  // 반대 방향 skew: 참가자는 accepted 인데 신청서는 아직 invited.
  // 예전 배포의 acceptInvitation 이 참가자와 신청서를 별도 await 로 승격했기
  // 때문에 실제로 존재하는 조합이다. 신청서를 참가자 기준으로 승격하면
  // invited → confirmed 라는 불법 전이가 되어 루프가 전이 뒤에서 멈췄다.
  await seedParticipant(meetingId, uids[3], "accepted");
  await seedApplication(uids[3], "invited", { meetingId, open: false });

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), true);
  const data = (await db.collection("blindMeetings").doc(meetingId).get()).data();
  assert.equal(data?.serverStatus, "chat_open");
  assert.equal(data?.groupChatId, `blind_${meetingId}`);
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed", uid);
    assert.equal((await applicationStatus(uid))?.serverStatus, "confirmed", uid);
  }
  const rooms = await db
    .collection("chat_rooms")
    .where("meetingId", "==", meetingId)
    .get();
  assert.equal(rooms.size, 1);
});

test("recheck P2-1b: every participant/application skew combination confirms the whole roster", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  const combos: [ParticipantStatus, ParticipantStatus][] = [
    ["invited", "invited"],
    ["invited", "accepted"],
    ["invited", "confirmed"],
    ["accepted", "invited"],
    ["accepted", "confirmed"],
    ["confirmed", "invited"],
  ];
  for (const [index, [participant, application]] of combos.entries()) {
    await seedParticipant(meetingId, uids[index], participant);
    await seedApplication(uids[index], application, { meetingId, open: false });
  }

  assert.equal(await confirmLegacyAwaitingAcceptanceMeeting(meetingId), true);
  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed", uid);
    assert.equal((await applicationStatus(uid))?.serverStatus, "confirmed", uid);
  }
  assert.equal(
    (await db.collection("blindMeetings").doc(meetingId).get()).data()?.serverStatus,
    "chat_open"
  );
});
