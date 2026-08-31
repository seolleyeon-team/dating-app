/**
 * 블라인드 3:3 participant/application FSM — Firestore Emulator 통합 테스트.
 *
 * 실행 (repo root, Java 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-blind-fsm \
 *     "node --test functions/lib/blindMeeting/blindMeetingFsm.emulator-test.js"
 *
 * store choke point(updateParticipant/setApplication)와 orchestrator
 * 진입점(accept/decline)을 실제 Firestore 트랜잭션 위에서 검증한다.
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

initializeApp({ projectId: "demo-blind-fsm" });

import {
  setApplication,
  updateParticipant,
  cancelOpenApplication,
} from "./store";
import { acceptInvitation, declineInvitation } from "./orchestrator";
import {
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
      depositStatus: "notRequired",
      serverDepositStatus: "not_required",
      ...extra,
    });
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
  await assert.rejects(cancelOpenApplication(uid), /이미 매칭된 미팅이 있어요/);

  const freeUid = uniqueId("u");
  await seedApplication(freeUid, "applied", { open: true, meetingId: null });
  await cancelOpenApplication(freeUid);
  assert.equal((await applicationStatus(freeUid))?.serverStatus, "cancelled");
});

// -----------------------------------------------------------------------------
// orchestrator 진입점: accept / decline
// -----------------------------------------------------------------------------

async function seedInvitedMeeting(): Promise<{
  meetingId: string;
  uids: string[];
}> {
  const meetingId = uniqueId("m");
  const uids = Array.from({ length: 6 }, () => uniqueId("u"));
  await seedMeeting(meetingId, "awaiting_acceptance", uids);
  for (const uid of uids) {
    await seedParticipant(meetingId, uid, "invited");
    await seedApplication(uid, "invited", { meetingId, open: false });
  }
  return { meetingId, uids };
}

test("acceptInvitation is idempotent under double call", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await acceptInvitation(meetingId, uids[0]);
  // 재시도 — internal error 없이 accepted 유지
  await acceptInvitation(meetingId, uids[0]);
  assert.equal(await participantStatus(meetingId, uids[0]), "accepted");
  assert.equal((await applicationStatus(uids[0]))?.serverStatus, "accepted");
  // 미팅은 아직 awaiting_acceptance (6명 중 1명만 수락)
  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "awaiting_acceptance");
});

test("all six accept without a deposit and open one group chat", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();

  for (const uid of uids) {
    await acceptInvitation(meetingId, uid);
  }

  const meetingSnap = await db.collection("blindMeetings").doc(meetingId).get();
  assert.equal(meetingSnap.data()?.serverStatus, "chat_open");
  assert.equal(meetingSnap.data()?.groupChatId, `blind_${meetingId}`);

  for (const uid of uids) {
    assert.equal(await participantStatus(meetingId, uid), "confirmed");
    const participantSnap = await db
      .collection("blindMeetings")
      .doc(meetingId)
      .collection("participants")
      .doc(uid)
      .get();
    assert.equal(participantSnap.data()?.serverDepositStatus, "not_required");
  }

  const roomSnap = await db
    .collection("chat_rooms")
    .doc(`blind_${meetingId}`)
    .get();
  assert.deepEqual(roomSnap.data()?.participantIds, uids);
});

test("declineInvitation twice stays terminal and never resurrects the seat", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  await declineInvitation(meetingId, uids[1], "일정 변경");
  assert.equal(await participantStatus(meetingId, uids[1]), "cancelled");
  const reopened = await applicationStatus(uids[1]);
  assert.equal(reopened?.serverStatus, "applied");
  assert.equal(reopened?.open, true);

  // 두 번째 거절 — cancelled(terminal) 유지, replacement_pending 역전이 없음
  await declineInvitation(meetingId, uids[1], "중복 클릭");
  assert.equal(await participantStatus(meetingId, uids[1]), "cancelled");
  // 재오픈된 신청이 유지된다 (settle이 덮어쓰지 않음)
  const after = await applicationStatus(uids[1]);
  assert.equal(after?.serverStatus, "applied");
  assert.equal(after?.open, true);
});

test("accept/decline race settles into one coherent outcome", async () => {
  const { meetingId, uids } = await seedInvitedMeeting();
  const outcomes = await Promise.allSettled([
    acceptInvitation(meetingId, uids[2]),
    declineInvitation(meetingId, uids[2], "race"),
  ]);
  // 어느 쪽도 무작위 internal error로 죽지 않아야 한다
  for (const outcome of outcomes) {
    if (outcome.status === "rejected") {
      const message = String((outcome.reason as Error).message ?? "");
      assert.match(
        message,
        /blind_participant_transition_rejected|수락할 수 있는 단계|거절할 수 있는 단계/,
        `unexpected failure: ${message}`
      );
    }
  }
  const finalStatus = await participantStatus(meetingId, uids[2]);
  assert.ok(
    ["accepted", "cancelled"].includes(String(finalStatus)),
    `incoherent final status: ${finalStatus}`
  );
  const app = await applicationStatus(uids[2]);
  if (finalStatus === "cancelled") {
    assert.equal(app?.serverStatus, "applied", "거절이면 신청이 재오픈된다");
  } else {
    assert.equal(app?.serverStatus, "accepted");
  }
});
