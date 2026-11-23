/**
 * AUD-08 — account deletion and the 3:3 blind-meeting seat (Firestore Emulator).
 *
 * Before the fix the deletion cleanup only closed the member's application:
 * the participant document stayed `confirmed`, so the replacement search never
 * saw a vacancy, the roster kept a deleted account as an attendee, and once the
 * DNA and users documents were gone every later replacement search for that
 * meeting gave up (the roster could not be hydrated).
 *
 * The tests drive the real handlers in the production order
 * (executeAvatarCleanup: load → plan → lock the account → social operations →
 * meeting operations → delete the users document) and the real replacement
 * lifecycle (leaveBlindMeeting / fillBlindMeetingVacancies /
 * processBlindMeetingReplacementSearches / runMatchingForDate).
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p02-lib
 *   firebase emulators:exec --only firestore --project demo-blind-deletion \
 *     "node --test functions/.p02-lib/blindMeeting/accountDeletionSeat.emulator-test.js"
 */
import assert from "node:assert/strict";
import { before, beforeEach, test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { Timestamp, getFirestore, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-blind-deletion" });

import {
  MEETING_CLEANUP_OPERATION_KINDS,
  applyMeetingCleanupOperation,
} from "../accountDeletionMeetingCleanup";
import { applySocialCleanupOperation } from "../accountDeletionSocialCleanup";
import {
  loadAccountDeletionDocs,
  planAccountDeletionPiiOperations,
  type CleanupOperation,
} from "../avatarCleanup";
import {
  fillBlindMeetingVacancies,
  leaveBlindMeeting,
  processBlindMeetingReplacementSearches,
} from "./automaticReplacement";
import { runMatchingForDate } from "./orchestrator";

let db: Firestore;
before(() => {
  db = getFirestore();
});

type Gender = "male" | "female";

function dateKeyInWindow(offsetDays: number): string {
  const base = new Date(Date.now() + offsetDays * 24 * 3600 * 1000);
  return `${base.getUTCFullYear()}-${String(base.getUTCMonth() + 1).padStart(2, "0")}-${String(base.getUTCDate()).padStart(2, "0")}`;
}

let runSeq = 0;
const tagOf = () => `ad${++runSeq}_${Date.now().toString(36)}`;

async function seedApplicant(userId: string, gender: Gender, dateKeys: string[], appliedAt = new Date()): Promise<void> {
  await db.collection("users").doc(userId).set({
    isStudentVerified: true, adultVerified: true, realNameVerified: true,
    isWithdrawn: false,
    loginDisabled: false,
    nickname: userId,
    heartBalance: 0,
    onboarding: {
      gender,
      campusLifeZones: ["sinchon"],
      lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
    },
  });
  await db.collection("blindMeetingDna").doc(userId).set({
    userId,
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
  await db.collection("blindMeetingApplications").doc(userId).set({
    userId,
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
  for (const uid of males) await seedApplicant(uid, "male", [dateKey]);
  for (const uid of females) await seedApplicant(uid, "female", [dateKey]);
  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1, "exactly one meeting is created");
  assert.equal((await meetingData(created[0])).serverStatus, "chat_open");
  return { meetingId: created[0], males, females };
}

const meetingData = async (id: string) => (await db.collection("blindMeetings").doc(id).get()).data() ?? {};
const participantData = async (id: string, uid: string) =>
  (await db.collection("blindMeetings").doc(id).collection("participants").doc(uid).get()).data() ?? {};
const applicationData = async (uid: string) =>
  (await db.collection("blindMeetingApplications").doc(uid).get()).data() ?? {};
const roomData = async (id: string) => (await db.collection("chat_rooms").doc(`blind_${id}`).get()).data() ?? {};
const heartBalanceOf = async (uid: string) => (await db.collection("users").doc(uid).get()).data()?.heartBalance;

async function systemMessages(meetingId: string, containing: string): Promise<number> {
  const msgs = await db.collection("chat_rooms").doc(`blind_${meetingId}`).collection("messages").get();
  return msgs.docs.filter((d) => d.data().senderId === "system" && String(d.data().text).includes(containing)).length;
}

async function heartTransactionsOf(uid: string): Promise<Array<Record<string, unknown>>> {
  const snap = await db.collection("heartTransactions").where("uid", "==", uid).get();
  return snap.docs.map((d) => d.data());
}

const SOCIAL_KINDS = new Set(["closeChatRoom", "detachGroupChatMember", "anonymizeChatMessages"]);

/**
 * The blind-meeting and chat part of the account-deletion executor, in its
 * real order. `afterLoad` runs between the document load and the first
 * operation — where a matcher or a replacement fill can still commit against
 * the account in production.
 */
async function deleteAccount(uid: string, afterLoad?: () => Promise<void>): Promise<CleanupOperation[]> {
  const docs = await loadAccountDeletionDocs(db, uid);
  const operations = planAccountDeletionPiiOperations({ uid, docs });
  if (afterLoad) await afterLoad();
  // lockAccountForDeletion (only when the users document still exists).
  const userRef = db.collection("users").doc(uid);
  if ((await userRef.get()).exists) {
    await userRef.set({ status: "deleting", isWithdrawn: true, loginDisabled: true, profileVisible: false }, { merge: true });
  }
  for (const operation of operations) {
    if (SOCIAL_KINDS.has(operation.kind)) {
      await applySocialCleanupOperation(db, uid, operation as never);
    } else if (MEETING_CLEANUP_OPERATION_KINDS.has(operation.kind)) {
      await applyMeetingCleanupOperation(db, uid, operation as never);
    }
  }
  // deletePublicUser
  await userRef.delete();
  return operations;
}

/** The seat is vacated the way leaveBlindMeeting vacates it, and nobody else is touched. */
async function assertSeatReleased(meetingId: string, deleted: string, others: string[]): Promise<void> {
  const seat = await participantData(meetingId, deleted);
  assert.equal(seat.serverStatus, "cancelled", "the deleted member's seat is no longer confirmed");
  assert.equal(seat.status, "cancelled");
  const room = await roomData(meetingId);
  assert.equal((room.participantIds as string[]).includes(deleted), false, "the deleted member left the group room");
  const app = await applicationData(deleted);
  assert.deepEqual([app.open, app.serverStatus, app.meetingId], [false, "cancelled", null], "application closed and unbound");
  assert.equal(app.accountDeleted, true);
  for (const uid of others) {
    assert.equal((await participantData(meetingId, uid)).serverStatus, "confirmed", `${uid}: seat untouched`);
    const otherApp = await applicationData(uid);
    assert.deepEqual([otherApp.open, otherApp.serverStatus, otherApp.meetingId], [false, "confirmed", meetingId], `${uid}: application untouched`);
    assert.ok((room.participantIds as string[]).includes(uid), `${uid}: still in the room`);
    assert.equal((await db.collection("blindMeetingDna").doc(uid).get()).exists, true, `${uid}: DNA untouched`);
  }
}

beforeEach(async () => {
  await isolate();
});

test("delete before matching: the application is closed, the account is never matched, nobody is refunded or charged", async () => {
  const dateKey = dateKeyInWindow(4);
  const tag = tagOf();
  const males = [1, 2, 3].map((i) => `${tag}_m${i}`);
  const females = [1, 2, 3].map((i) => `${tag}_f${i}`);
  for (const uid of males) await seedApplicant(uid, "male", [dateKey]);
  for (const uid of females) await seedApplicant(uid, "female", [dateKey]);
  const deleted = males[0];

  await deleteAccount(deleted);

  const app = await applicationData(deleted);
  assert.deepEqual([app.open, app.serverStatus, app.requestedDateKeys], [false, "cancelled", []]);
  assert.equal((await db.collection("blindMeetingDna").doc(deleted).get()).exists, false);
  assert.deepEqual(await runMatchingForDate(dateKey), [], "five applicants do not make a meeting");
  for (const uid of [...males.slice(1), ...females]) {
    assert.equal((await applicationData(uid)).open, true, `${uid}: still waiting`);
  }
  // A new applicant completes the pool; the deleted account is not in the meeting.
  await seedApplicant(`${tag}_m4`, "male", [dateKey]);
  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1);
  const ids = (await meetingData(created[0])).participantIds as string[];
  assert.equal(ids.includes(deleted), false);
  assert.equal(new Set(ids).size, 6);
  assert.deepEqual(await heartTransactionsOf(deleted), [], "no heart ledger entry for the deleted account");
  assert.equal((await db.collection("users").doc(deleted).get()).exists, false);
});

test("delete after matching: the seat is released like a leave, the search opens, and a same-gender applicant fills it", async () => {
  const dateKey = dateKeyInWindow(5);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const deleted = females[1];
  const others = [...males, ...females].filter((uid) => uid !== deleted);

  await deleteAccount(deleted);

  await assertSeatReleased(meetingId, deleted, others);
  const seat = await participantData(meetingId, deleted);
  assert.equal(seat.replacementSearchActive, true, "the seat waits for a replacement");
  let meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, true, "the replacement search is open");
  assert.ok(meeting.replacementSearchDeadlineAt instanceof Timestamp);
  assert.ok((meeting.replacementSearchDeadlineAt as Timestamp).toMillis() > Date.now(), "a fresh search window");
  assert.notEqual(meeting.serverStatus, "cancelled");
  assert.equal(await systemMessages(meetingId, "나갔습니다"), 1, "one leave notice");
  // No heart moves: the vacating member is not refunded (leave contract), nobody is charged.
  for (const uid of others) {
    assert.equal(await heartBalanceOf(uid), 0, `${uid}: balance untouched`);
    assert.deepEqual(await heartTransactionsOf(uid), []);
  }
  assert.deepEqual(await heartTransactionsOf(deleted), []);

  // The deleted account has no DNA or users document any more; the search must still fill the seat.
  const tag = tagOf();
  await seedApplicant(`${tag}_wrong_gender`, "male", [dateKey], new Date(Date.now() - 60_000));
  await processBlindMeetingReplacementSearches();
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true, "a man does not take a woman's seat");
  const replacement = `${tag}_f_ok`;
  await seedApplicant(replacement, "female", [dateKey]);
  await processBlindMeetingReplacementSearches();

  meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, false, "search closed once filled");
  const ids = meeting.participantIds as string[];
  assert.equal(new Set(ids).size, 6);
  assert.ok(ids.includes(replacement) && !ids.includes(deleted), "the deleted member is replaced in the roster");
  const teams = [...(meeting.teamAUserIds as string[]), ...(meeting.teamBUserIds as string[])];
  assert.ok(teams.includes(replacement) && !teams.includes(deleted));
  assert.equal((await participantData(meetingId, replacement)).serverStatus, "confirmed");
  assert.deepEqual([...((await roomData(meetingId)).participantIds as string[])].sort(), [...ids].sort());
  assert.equal((await db.collection("users").doc(deleted).get()).exists, false, "the deleted users document is not recreated");
  assert.equal((await db.collection("blindMeetingDna").doc(deleted).get()).exists, false);
});

test("delete before the meeting starts (schedule confirmed): seat released; when nobody is found the meeting is cancelled and only the remaining members are refunded, once", async () => {
  const dateKey = dateKeyInWindow(6);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const startAt = Timestamp.fromMillis(Date.now() + 3 * 24 * 3600 * 1000);
  await db.collection("blindMeetings").doc(meetingId).set({
    status: "scheduleConfirmed",
    serverStatus: "schedule_confirmed",
    slotId: `${dateKey}#evening`,
    confirmedDateKey: dateKey,
    scheduledStartAt: startAt,
  }, { merge: true });
  const deleted = males[2];
  const others = [...males, ...females].filter((uid) => uid !== deleted);

  await deleteAccount(deleted);
  await assertSeatReleased(meetingId, deleted, others);
  assert.equal((await meetingData(meetingId)).serverStatus, "schedule_confirmed", "the meeting itself is not cancelled by the deletion");

  // Nobody applies; the search window ends.
  await db.collection("blindMeetings").doc(meetingId).set({ replacementSearchDeadlineAt: Timestamp.fromMillis(Date.now() - 1_000) }, { merge: true });
  await Promise.all([processBlindMeetingReplacementSearches(), processBlindMeetingReplacementSearches()]);
  await processBlindMeetingReplacementSearches();
  // The cleanup may run again after the settlement (retry of the deletion request).
  await deleteAccount(deleted);

  const meeting = await meetingData(meetingId);
  assert.equal(meeting.serverStatus, "cancelled");
  assert.equal(meeting.replacementSearchActive, false);
  for (const uid of others) {
    assert.equal(await heartBalanceOf(uid), 30, `${uid}: refunded exactly once`);
    const ledger = await heartTransactionsOf(uid);
    assert.equal(ledger.length, 1, `${uid}: one ledger entry`);
    assert.deepEqual([ledger[0].type, ledger[0].amount, ledger[0].resourceId], ["meeting_cancel_refund", 30, meetingId]);
  }
  assert.deepEqual(await heartTransactionsOf(deleted), [], "the deleted account is not refunded");
  assert.equal((await db.collection("users").doc(deleted).get()).exists, false, "no users document is recreated for the deleted account");
  assert.equal((await participantData(meetingId, deleted)).serverStatus, "cancelled");
});

test("delete while a replacement search is active: the second seat joins the open search (same deadline) and both seats are filled", async () => {
  const dateKey = dateKeyInWindow(7);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[0];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const deadlineBefore = (await meetingData(meetingId)).replacementSearchDeadlineAt as Timestamp;
  assert.ok(deadlineBefore instanceof Timestamp);
  const deleted = females[0];
  const others = [...males, ...females].filter((uid) => uid !== deleted && uid !== leaver);

  await deleteAccount(deleted);

  await assertSeatReleased(meetingId, deleted, others);
  let meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, true);
  assert.equal((meeting.replacementSearchDeadlineAt as Timestamp).toMillis(), deadlineBefore.toMillis(), "one window for the open search");
  assert.equal((await participantData(meetingId, leaver)).replacementSearchActive, true, "the earlier vacancy is still open");

  // One applicant per vacated seat; the deleted member's seat has no candidate snapshot to compare against.
  const tag = tagOf();
  await seedApplicant(`${tag}_f_new`, "female", [dateKey], new Date(Date.now() - 2_000));
  await processBlindMeetingReplacementSearches();
  meeting = await meetingData(meetingId);
  assert.ok((meeting.participantIds as string[]).includes(`${tag}_f_new`), "the woman takes the deleted member's seat");
  assert.equal((meeting.participantIds as string[]).includes(deleted), false);
  assert.equal(meeting.replacementSearchActive, true, "the man's seat is still open");
  await seedApplicant(`${tag}_m_new`, "male", [dateKey]);
  await processBlindMeetingReplacementSearches();

  meeting = await meetingData(meetingId);
  const ids = meeting.participantIds as string[];
  assert.equal(meeting.replacementSearchActive, false);
  assert.equal(new Set(ids).size, 6);
  assert.deepEqual(
    [...ids].sort(),
    [...others, `${tag}_f_new`, `${tag}_m_new`].sort(),
    "both vacated seats are filled, everyone else kept their seat"
  );
  const teamA = meeting.teamAUserIds as string[];
  const teamB = meeting.teamBUserIds as string[];
  const teamOf = (uid: string) => (teamA.includes(uid) ? "A" : teamB.includes(uid) ? "B" : "none");
  assert.equal(teamOf(`${tag}_f_new`), teamOf(females[1]), "the woman joins the women's team");
  assert.equal(teamOf(`${tag}_m_new`), teamOf(males[1]), "the man joins the men's team");
});

test("a member who left and then deleted the account: the open seat stays fillable and the deletion changes nothing else", async () => {
  const dateKey = dateKeyInWindow(8);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[1];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const before = await meetingData(meetingId);

  await deleteAccount(leaver);

  const after = await meetingData(meetingId);
  assert.equal(after.replacementSearchActive, true);
  assert.equal((after.replacementSearchDeadlineAt as Timestamp).toMillis(), (before.replacementSearchDeadlineAt as Timestamp).toMillis());
  assert.equal(await systemMessages(meetingId, "나갔습니다"), 1, "no second leave notice");
  const replacement = `${tagOf()}_m_ok`;
  await seedApplicant(replacement, "male", [dateKey]);
  await processBlindMeetingReplacementSearches();
  const meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, false, "the seat of an account that no longer exists is still filled");
  assert.ok((meeting.participantIds as string[]).includes(replacement));
  assert.equal((meeting.participantIds as string[]).includes(leaver), false);
  void females;
});

test("deletion racing a replacement confirmation: a fill that commits after the deletion loaded its documents still ends with the seat released", async () => {
  const dateKey = dateKeyInWindow(9);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = males[0];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const candidate = `${tagOf()}_m_cand`;
  await seedApplicant(candidate, "male", [dateKey]);

  // The deletion has loaded its documents (no meeting yet); the fill confirms the candidate; the cleanup then runs.
  await deleteAccount(candidate, async () => {
    assert.equal(await fillBlindMeetingVacancies(meetingId), 1);
    assert.equal((await participantData(meetingId, candidate)).serverStatus, "confirmed");
  });

  const others = [...males, ...females].filter((uid) => uid !== leaver);
  await assertSeatReleased(meetingId, candidate, others);
  const meeting = await meetingData(meetingId);
  assert.equal(meeting.replacementSearchActive, true, "the seat is open again");
  assert.equal((await participantData(meetingId, candidate)).replacementSearchActive, true);
});

test("deletion racing the matcher: a match that commits after the deletion loaded its documents still ends with the seat released", async () => {
  const dateKey = dateKeyInWindow(10);
  const tag = tagOf();
  const males = [1, 2, 3].map((i) => `${tag}_m${i}`);
  const females = [1, 2, 3].map((i) => `${tag}_f${i}`);
  for (const uid of males) await seedApplicant(uid, "male", [dateKey]);
  for (const uid of females) await seedApplicant(uid, "female", [dateKey]);
  const deleted = females[2];
  let meetingId = "";

  await deleteAccount(deleted, async () => {
    const created = await runMatchingForDate(dateKey);
    assert.equal(created.length, 1);
    meetingId = created[0];
  });

  await assertSeatReleased(meetingId, deleted, [...males, ...females].filter((uid) => uid !== deleted));
  assert.equal((await meetingData(meetingId)).replacementSearchActive, true);
});

test("concurrent deletion and replacement confirmation never leave a deleted account in a confirmed seat", async () => {
  const dateKey = dateKeyInWindow(11);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const leaver = females[0];
  await leaveBlindMeeting({ meetingId, userId: leaver });
  const candidate = `${tagOf()}_f_cand`;
  await seedApplicant(candidate, "female", [dateKey]);

  await Promise.all([
    fillBlindMeetingVacancies(meetingId),
    processBlindMeetingReplacementSearches(),
    deleteAccount(candidate),
  ]);

  const meeting = await meetingData(meetingId);
  const ids = meeting.participantIds as string[];
  assert.equal(new Set(ids).size, 6, "no duplicate seat");
  const seat = await participantData(meetingId, candidate);
  assert.notEqual(seat.serverStatus, "confirmed", "a deleted account never keeps a confirmed seat");
  const app = await applicationData(candidate);
  assert.equal(app.open, false, "the deleted account's application is closed");
  assert.equal(app.serverStatus, "cancelled");
  const room = await roomData(meetingId);
  assert.equal((room.participantIds as string[]).includes(candidate), false, "the deleted account is not in the room");
  if (ids.includes(candidate)) {
    // The fill won the race: the seat was confirmed and then released again.
    assert.equal(seat.serverStatus, "cancelled");
    assert.equal(seat.replacementSearchActive, true);
  } else {
    // The deletion won the race: the candidate never joined.
    assert.equal(ids.includes(leaver), true);
  }
  assert.equal(meeting.replacementSearchActive, true, "a seat is still open either way");
  for (const uid of [...males, ...females].filter((u) => u !== leaver)) {
    assert.equal((await participantData(meetingId, uid)).serverStatus, "confirmed", `${uid}: seat untouched`);
    assert.equal(await heartBalanceOf(uid), 0, `${uid}: no heart movement`);
  }
});

test("deletion executed twice is a no-op the second time: one leave notice, same deadline, no heart movement", async () => {
  const dateKey = dateKeyInWindow(12);
  const { meetingId, males, females } = await matchMeeting(dateKey);
  const deleted = males[1];
  const others = [...males, ...females].filter((uid) => uid !== deleted);

  await deleteAccount(deleted);
  const first = await meetingData(meetingId);
  const firstSeat = await participantData(meetingId, deleted);
  const secondRunOperations = await deleteAccount(deleted);
  await Promise.all([deleteAccount(deleted), deleteAccount(deleted)]);

  await assertSeatReleased(meetingId, deleted, others);
  const second = await meetingData(meetingId);
  assert.equal((second.replacementSearchDeadlineAt as Timestamp).toMillis(), (first.replacementSearchDeadlineAt as Timestamp).toMillis(), "the search window is not restarted");
  assert.equal(second.replacementSearchActive, true);
  assert.deepEqual(second.participantIds, first.participantIds);
  assert.equal(((await participantData(meetingId, deleted)).leftAt as Timestamp).toMillis(), (firstSeat.leftAt as Timestamp).toMillis(), "the seat is not rewritten");
  assert.equal(await systemMessages(meetingId, "나갔습니다"), 1, "exactly one leave notice");
  assert.equal(secondRunOperations.some((op) => op.kind === "deleteBlindMeetingDna"), false, "nothing left to delete on the second run");
  for (const uid of [...others, deleted]) {
    assert.deepEqual(await heartTransactionsOf(uid), [], `${uid}: no heart ledger entry`);
  }
  for (const uid of others) assert.equal(await heartBalanceOf(uid), 0);
});
