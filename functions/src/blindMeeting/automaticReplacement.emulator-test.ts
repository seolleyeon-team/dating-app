/**
 * 3:3 블라인드 미팅 — 대타(자동 대체) 탐색 회귀 테스트 (Firestore Emulator).
 *
 * `processBlindMeetingReplacementSearches` 는 2026-09-09 부터 두 예약 작업
 * (blindMeetingLifecycleTick 5분, blindMeetingMatchingTick 10분) 에서 동시에
 * 돌고 있지만 테스트가 하나도 없었다. 실제 진입점만 사용해 다음을 고정한다.
 *
 *  A. 나가기 → 빈자리 → (후보 없음) → 후보 등장 → 탐색이 같은 성별 후보로
 *     채운다: 미팅/팀/채팅방 참가자 교체, 신청서 close, 투표 라운드 재시작,
 *     시스템 메시지(나감·초대)에 readBy 없음.
 *  B. 두 tick 이 동시에 탐색을 돌려도 같은 빈자리를 두 번 채우지 않는다.
 *  C. 탐색 기한이 지나면 미팅 취소·방 보관·남은 참가자 하트 30 환불 —
 *     재실행·동시 실행에도 환불은 1회 (heartTransactions 문서 id 로 멱등).
 *  D. 탐색 중인 미팅이 있으면 matching tick 은 새 3:3 을 만들지 않고, 탐색이
 *     끝나면 다시 만든다 (먼저 신청한 후보가 새 방으로 빠지지 않게).
 *  E. 성별·날짜가 맞지 않는 후보로는 채우지 않는다.
 *  E–G. (NEW-19) 다른 경로로 취소된 미팅의 탐색 정리, fill/기한 취소 race, 환불 대상 tx 내 확정.
 *  H. (NEW-19) 이미 시작·종료된 미팅의 탐색은 채우지도 취소하지도 않고 닫는다.
 *
 * 실행 (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p02-lib
 *   firebase emulators:exec --only firestore --project demo-blind-replacement \
 *     "node --test functions/.p02-lib/blindMeeting/automaticReplacement.emulator-test.js"
 */
import assert from "node:assert/strict";
import { before, beforeEach, test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { Timestamp, getFirestore, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-blind-replacement" });

import {
  cancelReplacementFailedMeeting,
  fillBlindMeetingVacancies,
  leaveBlindMeeting,
  processBlindMeetingReplacementSearches,
} from "./automaticReplacement";
import { cancelMeeting, runMatchingForDate } from "./orchestrator";
import { blindMeetingMatchingTick } from "./scheduled";

let db: Firestore;
before(() => {
  db = getFirestore();
});

type Gender = "male" | "female";
type Seed = { userId: string; gender: Gender };

function dateKeyInWindow(offsetDays: number): string {
  const base = new Date(Date.now() + offsetDays * 24 * 3600 * 1000);
  return `${base.getUTCFullYear()}-${String(base.getUTCMonth() + 1).padStart(2, "0")}-${String(base.getUTCDate()).padStart(2, "0")}`;
}

let runSeq = 0;
const tagOf = () => `rp${++runSeq}_${Date.now().toString(36)}`;

async function seedApplicant(seed: Seed, dateKeys: string[], appliedAt = new Date()): Promise<void> {
  await db.collection("users").doc(seed.userId).set({
    isStudentVerified: true,
    isWithdrawn: false,
    loginDisabled: false,
    nickname: seed.userId,
    heartBalance: 0,
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
    availableDateKeys: dateKeys,
  });
  await db.collection("blindMeetingApplications").doc(seed.userId).set({
    userId: seed.userId,
    open: true,
    status: "applied",
    serverStatus: "applied",
    stage: "searchingCandidates",
    requestedDateKeys: dateKeys,
    meetingId: null,
    appliedAt,
  });
}

/** Tests share one emulator database: close every other open application and search first. */
async function isolate(): Promise<void> {
  const open = await db.collection("blindMeetingApplications").where("open", "==", true).get();
  const searching = await db.collection("blindMeetings").where("replacementSearchActive", "==", true).get();
  const batch = db.batch();
  open.docs.forEach((d) => batch.set(d.ref, { open: false, status: "cancelled", serverStatus: "cancelled" }, { merge: true }));
  searching.docs.forEach((d) => batch.set(d.ref, { replacementSearchActive: false }, { merge: true }));
  await batch.commit();
}

async function matchMeeting(dateKey: string): Promise<{ meetingId: string; males: string[]; females: string[] }> {
  const tag = tagOf();
  const males = [1, 2, 3].map((i) => `${tag}_m${i}`);
  const females = [1, 2, 3].map((i) => `${tag}_f${i}`);
  for (const uid of males) await seedApplicant({ userId: uid, gender: "male" }, [dateKey]);
  for (const uid of females) await seedApplicant({ userId: uid, gender: "female" }, [dateKey]);
  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1, "exactly one meeting is created");
  const meeting = (await db.collection("blindMeetings").doc(created[0]).get()).data() ?? {};
  assert.equal(meeting.serverStatus, "chat_open");
  return { meetingId: created[0], males, females };
}

const meetingData = async (id: string) => (await db.collection("blindMeetings").doc(id).get()).data() ?? {};
const participantData = async (id: string, uid: string) =>
  (await db.collection("blindMeetings").doc(id).collection("participants").doc(uid).get()).data() ?? {};
const roomOf = async (id: string) => db.collection("chat_rooms").doc(`blind_${id}`);

async function systemMessages(meetingId: string): Promise<Array<Record<string, unknown>>> {
  const msgs = await (await roomOf(meetingId)).collection("messages").get();
  return msgs.docs.map((d) => d.data()).filter((m) => m.senderId === "system");
}

beforeEach(async () => {
  await isolate();
});

test("A: leave → vacancy kept open → a same-gender candidate appears → the search fills it", async () => {
  const dateKey = dateKeyInWindow(4);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[0];
  const roundBefore = Number((await meetingData(meetingId)).scheduleVoteRound ?? 0);

  await leaveBlindMeeting({ meetingId, userId: leaver });
  let meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, true, "search opened");
  assert.ok(meeting.replacementSearchDeadlineAt instanceof Timestamp, "deadline set");
  assert.equal((await participantData(meetingId, leaver)).serverStatus, "cancelled");
  let room = (await (await roomOf(meetingId)).get()).data() ?? {};
  assert.equal((room.participantIds as string[]).includes(leaver), false, "leaver removed from the room");
  const leaveMsg = (await systemMessages(meetingId)).find((m) => String(m.text).includes("나갔습니다"));
  assert.ok(leaveMsg, "leave system message");
  assert.equal("readBy" in leaveMsg!, false, "no legacy readBy on the leave message");

  // A female candidate on the right date and a male on a wrong date must not be picked.
  const tag = tagOf();
  await seedApplicant({ userId: `${tag}_wrong_gender`, gender: "female" }, [dateKey], new Date(Date.now() - 60_000));
  await seedApplicant({ userId: `${tag}_wrong_date`, gender: "male" }, [dateKeyInWindow(9)], new Date(Date.now() - 50_000));
  await processBlindMeetingReplacementSearches();
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true, "E: no incompatible candidate fills the seat");

  const replacement = `${tag}_male_ok`;
  await seedApplicant({ userId: replacement, gender: "male" }, [dateKey]);
  await processBlindMeetingReplacementSearches();

  meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, false, "search closed once filled");
  const ids = meeting.participantIds as string[];
  assert.equal(ids.length, 6);
  assert.equal(new Set(ids).size, 6);
  assert.ok(ids.includes(replacement) && !ids.includes(leaver), "leaver replaced in participantIds");
  const teams = [...(meeting.teamAUserIds as string[]), ...(meeting.teamBUserIds as string[])];
  assert.ok(teams.includes(replacement) && !teams.includes(leaver), "leaver replaced in the team");
  assert.equal(Number(meeting.scheduleVoteRound ?? 0), roundBefore + 1, "schedule vote restarts for the new roster");
  const newcomer = await participantData(meetingId, replacement);
  assert.equal(newcomer.serverStatus, "confirmed");
  assert.equal(newcomer.isReplacement, true);
  assert.equal((await participantData(meetingId, leaver)).replacementUserId, replacement);
  const app = (await db.collection("blindMeetingApplications").doc(replacement).get()).data() ?? {};
  assert.deepEqual([app.open, app.serverStatus, app.meetingId], [false, "confirmed", meetingId]);
  room = (await (await roomOf(meetingId)).get()).data() ?? {};
  assert.ok((room.participantIds as string[]).includes(replacement), "newcomer joins the room");
  assert.deepEqual(
    [...(room.participantIds as string[])].sort(),
    [...ids].sort(),
    "room members equal the meeting roster"
  );
  const invite = (await systemMessages(meetingId)).find((m) => String(m.text).includes("초대되었어요"));
  assert.ok(invite, "invite system message");
  assert.equal("readBy" in invite!, false, "no legacy readBy on the invite message");
  // Untouched candidates stay in the queue.
  for (const uid of [`${tag}_wrong_gender`, `${tag}_wrong_date`]) {
    assert.equal((await db.collection("blindMeetingApplications").doc(uid).get()).data()?.open, true, uid);
  }
  void females;
});

test("B: both ticks running the search concurrently fill a vacancy exactly once", async () => {
  const dateKey = dateKeyInWindow(5);
  const { meetingId, females } = await matchMeeting(dateKey);
  const leaver = females[1];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const tag = tagOf();
  await seedApplicant({ userId: `${tag}_f_a`, gender: "female" }, [dateKey], new Date(Date.now() - 2_000));
  await seedApplicant({ userId: `${tag}_f_b`, gender: "female" }, [dateKey], new Date(Date.now() - 1_000));

  await Promise.all([
    processBlindMeetingReplacementSearches(),
    processBlindMeetingReplacementSearches(),
    fillBlindMeetingVacancies(meetingId),
  ]);

  const meeting = await meetingData(meetingId);
  const ids = meeting.participantIds as string[];
  assert.equal(ids.length, 6);
  assert.equal(new Set(ids).size, 6, "no duplicate participant");
  const joined = [`${tag}_f_a`, `${tag}_f_b`].filter((uid) => ids.includes(uid));
  assert.deepEqual(joined, [`${tag}_f_a`], "FIFO: the earliest applicant takes the single seat, exactly once");
  assert.equal(meeting.replacementSearchActive, false);
  assert.equal((await db.collection("blindMeetingApplications").doc(`${tag}_f_b`).get()).data()?.open, true, "the other candidate stays queued");
  const invites = (await systemMessages(meetingId)).filter((m) => String(m.text).includes("초대되었어요"));
  assert.equal(invites.length, 1, "exactly one invite message");
  const room = (await (await roomOf(meetingId)).get()).data() ?? {};
  assert.equal(new Set(room.participantIds as string[]).size, 6);
});

test("C: deadline passed → meeting cancelled, room archived, remaining members refunded 30 hearts exactly once", async () => {
  const dateKey = dateKeyInWindow(6);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[2];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  await db.collection("blindMeetings").doc(meetingId).set(
    { replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) },
    { merge: true }
  );
  const remaining = [...males, ...females].filter((uid) => uid !== leaver);

  // Both ticks fire at once, then once more later.
  await Promise.all([processBlindMeetingReplacementSearches(), processBlindMeetingReplacementSearches()]);
  await processBlindMeetingReplacementSearches();

  const meeting = await meetingData(meetingId);
  assert.equal(meeting.serverStatus, "cancelled");
  assert.equal(meeting.replacementSearchActive, false);
  const room = (await (await roomOf(meetingId)).get()).data() ?? {};
  assert.deepEqual([room.status, room.writable, room.participantIds], ["archived", false, []]);
  for (const uid of remaining) {
    const user = (await db.collection("users").doc(uid).get()).data() ?? {};
    assert.equal(user.heartBalance, 30, `${uid}: refunded exactly once`);
    const refunds = await db.collection("heartTransactions")
      .where("uid", "==", uid).where("resourceId", "==", meetingId).get();
    assert.equal(refunds.size, 1, `${uid}: one refund record`);
    assert.equal(refunds.docs[0].data().type, "meeting_cancel_refund");
    assert.equal((await participantData(meetingId, uid)).serverStatus, "cancelled");
    const app = (await db.collection("blindMeetingApplications").doc(uid).get()).data() ?? {};
    assert.deepEqual([app.open, app.serverStatus, app.meetingId], [false, "cancelled", null]);
  }
  const leaverUser = (await db.collection("users").doc(leaver).get()).data() ?? {};
  assert.equal(leaverUser.heartBalance, 0, "the member who left is not refunded");
});

test("D: matching tick defers new 3:3s while a replacement search is open, and resumes after it closes", async () => {
  const meetingDate = dateKeyInWindow(7);
  const { meetingId, males } = await matchMeeting(meetingDate);
  await leaveBlindMeeting({ meetingId, userId: males[1] });
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true);

  // A full new pool on another date only (cannot fill the vacancy: no common date).
  const otherDate = dateKeyInWindow(10);
  const tag = tagOf();
  const pool = [
    ...[1, 2, 3].map((i) => ({ userId: `${tag}_m${i}`, gender: "male" as const })),
    ...[1, 2, 3].map((i) => ({ userId: `${tag}_f${i}`, gender: "female" as const })),
  ];
  for (const seed of pool) await seedApplicant(seed, [otherDate]);

  const run = () => (blindMeetingMatchingTick as unknown as { run: (e: unknown) => Promise<unknown> }).run({ scheduleTime: new Date().toISOString() });
  await run();
  let newMeetings = await db.collection("blindMeetings").where("participantIds", "array-contains", pool[0].userId).get();
  assert.equal(newMeetings.size, 0, "no new meeting while a search is open");
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true, "vacancy still open (no compatible candidate)");

  // The search ends (deadline) → the next tick cancels it and then matches the waiting pool.
  await db.collection("blindMeetings").doc(meetingId).set(
    { replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) },
    { merge: true }
  );
  await run();
  assert.equal((await meetingData(meetingId)).serverStatus, "cancelled");
  newMeetings = await db.collection("blindMeetings").where("participantIds", "array-contains", pool[0].userId).get();
  assert.equal(newMeetings.size, 1, "the waiting pool is matched once the search is over");
});

// ---------------------------------------------------------------------------
// Liveness and race regressions (2026-10-27 final verification)
// ---------------------------------------------------------------------------

const runMatchingTick = () =>
  (blindMeetingMatchingTick as unknown as { run: (e: unknown) => Promise<unknown> }).run({ scheduleTime: new Date().toISOString() });

async function seedWaitingPool(dateKey: string): Promise<string[]> {
  const tag = tagOf();
  const pool = [
    ...[1, 2, 3].map((i) => ({ userId: `${tag}_m${i}`, gender: "male" as const })),
    ...[1, 2, 3].map((i) => ({ userId: `${tag}_f${i}`, gender: "female" as const })),
  ];
  for (const seed of pool) await seedApplicant(seed, [dateKey]);
  return pool.map((p) => p.userId);
}

async function meetingsOf(uid: string) {
  return db.collection("blindMeetings").where("participantIds", "array-contains", uid).get();
}

test("E: a meeting cancelled through another path while its search is open must not pause ordinary matching forever", async () => {
  const { meetingId, males } = await matchMeeting(dateKeyInWindow(4));
  await leaveBlindMeeting({ meetingId, userId: males[0] });
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true);

  // e.g. lifecycle `finalizeExpiredScheduleVotes` → cancelMeeting("schedule_window_expired"),
  // or the ops rematch path. Neither knows about the replacement search.
  await cancelMeeting(meetingId, "schedule_window_expired");
  assert.equal((await meetingData(meetingId)).serverStatus, "cancelled");

  const pool = await seedWaitingPool(dateKeyInWindow(11));
  await runMatchingTick();
  assert.equal((await meetingData(meetingId)).replacementSearchActive, false, "a cancelled meeting's search is closed");
  assert.equal((await meetingsOf(pool[0])).size, 1, "ordinary matching resumes instead of deferring forever");

  // Even after the deadline the stale search must not stay open either.
  await db.collection("blindMeetings").doc(meetingId).set({ replacementSearchActive: true, replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) }, { merge: true });
  await processBlindMeetingReplacementSearches();
  assert.equal((await meetingData(meetingId)).replacementSearchActive, false, "deadline path also clears a stale flag");
});

test("F: a fill that commits before the deadline cancel runs must not end in a cancelled meeting with a confirmed newcomer", async () => {
  const dateKey = dateKeyInWindow(5);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[1];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const replacement = `${tagOf()}_m_late`;
  await seedApplicant({ userId: replacement, gender: "male" }, [dateKey]);
  // The deadline passes while a tick's search snapshot still lists the meeting...
  await db.collection("blindMeetings").doc(meetingId).set({ replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) }, { merge: true });
  // ...and another path (a second leave, or the other tick before the deadline) fills the seat first.
  assert.equal(await fillBlindMeetingVacancies(meetingId), 1);
  assert.equal((await meetingData(meetingId)).replacementSearchActive, false);
  // Now the stale cancel from the first snapshot runs.
  await cancelReplacementFailedMeeting(meetingId);

  const meeting = await meetingData(meetingId);
  assert.notEqual(meeting.serverStatus, "cancelled", "a filled meeting is not cancelled by a stale deadline");
  assert.ok((meeting.participantIds as string[]).includes(replacement));
  assert.equal((await participantData(meetingId, replacement)).serverStatus, "confirmed");
  const room = (await (await roomOf(meetingId)).get()).data() ?? {};
  assert.notEqual(room.status, "archived");
  for (const uid of [...males, ...females].filter((u) => u !== leaver)) {
    assert.equal((await db.collection("users").doc(uid).get()).data()?.heartBalance, 0, `${uid}: no refund for a meeting that goes ahead`);
  }
});

test("G: the deadline cancel refunds exactly the members confirmed at commit time (read inside the transaction)", async () => {
  const { meetingId, males, females } = await matchMeeting(dateKeyInWindow(6));
  const first = males[0];
  await leaveBlindMeeting({ meetingId, userId: first });
  await db.collection("blindMeetings").doc(meetingId).set({ replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) }, { merge: true });
  // A second member leaves right before the cancel commits.
  const second = females[0];
  await leaveBlindMeeting({ meetingId, userId: second });
  await cancelReplacementFailedMeeting(meetingId);
  const expectedRefunded = [...males, ...females].filter((u) => u !== first && u !== second);
  for (const uid of expectedRefunded) {
    assert.equal((await db.collection("users").doc(uid).get()).data()?.heartBalance, 30, uid);
  }
  for (const uid of [first, second]) {
    assert.equal((await db.collection("users").doc(uid).get()).data()?.heartBalance, 0, `${uid}: left, not refunded`);
  }
  assert.equal((await meetingData(meetingId)).serverStatus, "cancelled");
});

test("H: a search still open when the meeting has already started or finished neither fills nor cancels it — it is closed", async () => {
  // leaveBlindMeeting only requires a confirmed participant, so a member can
  // leave on the day (checkin_open / in_progress) and the lifecycle tick keeps
  // moving the meeting forward while the search is open.
  const cases: Array<{ status: string; deadlinePassed: boolean; day: number }> = [
    { status: "in_progress", deadlinePassed: false, day: 9 },
    { status: "completed", deadlinePassed: true, day: 10 },
  ];
  for (const c of cases) {
    await isolate();
    const dateKey = dateKeyInWindow(c.day);
    const { meetingId, males, females } = await matchMeeting(dateKey);
    const leaver = males[0];
    await leaveBlindMeeting({ meetingId, userId: leaver });
    const newcomer = `${tagOf()}_m_new`;
    await seedApplicant({ userId: newcomer, gender: "male" }, [dateKey]);
    await db.collection("blindMeetings").doc(meetingId).set({
      serverStatus: c.status,
      status: c.status,
      replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() + (c.deadlinePassed ? -1_000 : 3_600_000)),
    }, { merge: true });

    await processBlindMeetingReplacementSearches();

    const meeting = await meetingData(meetingId);
    assert.equal(meeting.serverStatus, c.status, `${c.status}: the meeting is not cancelled`);
    assert.equal(meeting.replacementSearchActive, false, `${c.status}: the search is closed`);
    assert.ok(!(meeting.participantIds as string[]).includes(newcomer), `${c.status}: nobody joins a meeting that already started`);
    const app = (await db.collection("blindMeetingApplications").doc(newcomer).get()).data() ?? {};
    assert.equal(app.open, true, `${c.status}: the newcomer stays in the pool`);
    const room = (await (await roomOf(meetingId)).get()).data() ?? {};
    assert.notEqual(room.status, "archived", `${c.status}: the room is not archived by the search`);
    for (const uid of [...males, ...females].filter((u) => u !== leaver)) {
      assert.equal((await db.collection("users").doc(uid).get()).data()?.heartBalance, 0, `${c.status}/${uid}: no refund`);
    }
  }
});
