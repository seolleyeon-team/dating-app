/**
 * P1-5 — account deletion personal-data cleanup on the real engines.
 *
 * Firestore: set({merge:true}) with a dotted key writes a LITERAL top-level
 * field — the previous cleanup left `participantInfo.<uid>` beside the real
 * nested nickname/avatar (verified on the base source, see the audit doc).
 * The fixed operation replaces exactly the deleted member's nested entry and
 * preserves the other participants' entries; a group room keeps its state.
 * Storage: the onboarding source photographs are listed from the uid's
 * prefix only and deleted with generation match.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore,storage --project demo-p15-deletion \
 *     "node --test functions/.p1-lib/accountDeletion.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
const PROJECT = process.env.GCLOUD_PROJECT ?? "demo-p15-deletion";
const BUCKET = `${PROJECT}.appspot.com`;
process.env.ONBOARDING_PHOTO_BUCKET = BUCKET;
initializeApp({ projectId: PROJECT, storageBucket: BUCKET });

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";
import { applyMeetingCleanupOperation } from "./accountDeletionMeetingCleanup";
import { applySocialCleanupOperation, loadAccountDeletionSocialDocs } from "./accountDeletionSocialCleanup";
import {
  deleteStorageObjectWithGenerationMatch,
  loadAccountDeletionDocs,
  listOnboardingPhotoObjects,
  planAccountDeletionPiiOperations,
  type OnboardingPhotoBucketLike,
} from "./avatarCleanup";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

test("closeChatRoom replaces only the deleted member's nested participantInfo entry (no literal dotted key)", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await db.collection("chat_rooms").doc(room).set({
    type: "one_to_one", status: "active", participantIds: [a, b],
    participantInfo: { [a]: { nickname: "앨리스", avatarUrl: "https://x/a.png" }, [b]: { nickname: "밥", avatarUrl: "https://x/b.png" } },
  });
  await applySocialCleanupOperation(db, a, { kind: "closeChatRoom", id: room });
  const data = (await db.collection("chat_rooms").doc(room).get()).data() ?? {};
  assert.equal(data.status, "closed");
  assert.equal(Object.keys(data).some((k) => k.startsWith("participantInfo.")), false, "no literal dotted key");
  const info = data.participantInfo as Record<string, Record<string, unknown>>;
  assert.equal(info[a].nickname, DELETED_USER_DISPLAY_NAME);
  assert.equal(info[a].avatarUrl, null);
  assert.equal(info[b].nickname, "밥");
  assert.equal(info[b].avatarUrl, "https://x/b.png");
  assert.deepEqual(data.accountDeletedUserIds, [a]);
  // Idempotent on retry.
  await applySocialCleanupOperation(db, a, { kind: "closeChatRoom", id: room });
  assert.deepEqual((await db.collection("chat_rooms").doc(room).get()).data()?.accountDeletedUserIds, [a]);
});

test("a 3:3 room is detached, not closed: status/writable/participantIds untouched, member scrubbed", async () => {
  const members = [fresh("m"), fresh("m"), fresh("m"), fresh("m"), fresh("m"), fresh("m")];
  const room = fresh("group");
  await db.collection("chat_rooms").doc(room).set({
    type: "group", roomType: "blind_meeting_group", status: "active", writable: true, participantIds: members,
    participantInfo: Object.fromEntries(members.map((m, i) => [m, { nickname: `멤버${i}`, avatarUrl: "" }])),
    unreadCounts: Object.fromEntries(members.map((m) => [m, 1])),
  });
  const docs = await loadAccountDeletionSocialDocs(db, members[0]);
  assert.deepEqual(docs.groupChatRoomIds, [room]);
  assert.deepEqual(docs.chatRoomIds, []);
  await applySocialCleanupOperation(db, members[0], { kind: "detachGroupChatMember", id: room });
  const data = (await db.collection("chat_rooms").doc(room).get()).data() ?? {};
  assert.equal(data.status, "active");
  assert.equal(data.writable, true);
  assert.deepEqual(data.participantIds, members);
  const info = data.participantInfo as Record<string, Record<string, unknown>>;
  assert.equal(info[members[0]].nickname, DELETED_USER_DISPLAY_NAME);
  for (let i = 1; i < 6; i += 1) assert.equal(info[members[i]].nickname, `멤버${i}`);
  assert.deepEqual(data.accountDeletedUserIds, [members[0]]);
  assert.equal((data.unreadCounts as Record<string, number>)[members[1]], 1, "the P0-2 unread model is untouched");
});

test("blind-meeting personal data: DNA/draft/membership/stats deleted, application closed, snapshots anonymised in place", async () => {
  const u = fresh("u"), other = fresh("o"), meeting = fresh("meet"), party = fresh("party");
  await Promise.all([
    db.collection("blindMeetingDna").doc(u).set({ answers: { q1: "x" } }),
    db.collection("blindMeetingDnaDrafts").doc(u).set({ answers: { q1: "x" } }),
    db.collection("blindMeetingApplications").doc(u).set({ userId: u, status: "applied", open: true, requestedDateKeys: ["2026-11-20"], prefersAlcoholFree: true, waitlistOptIn: true, meetingId: null, partyId: party, appliedAt: Timestamp.now() }),
    db.collection("blindMeetingPartyMemberships").doc(u).set({ partyId: party, active: true }),
    db.collection("blindMeetingStats").doc(u).set({ completedMeetings: 1 }),
    db.collection("blindMeetingParties").doc(party).set({ acceptedUserIds: [u, other], memberProfiles: { [u]: { nickname: "진짜", profileImageUrl: "https://x/u.jpg", mbti: "ENFP" }, [other]: { nickname: "친구", profileImageUrl: "https://x/o.jpg", mbti: "ISTJ" } } }),
    db.collection("blindMeetings").doc(meeting).set({ participantIds: [u, other], serverStatus: "chat_open" }),
    db.collection("blindMeetings").doc(meeting).collection("publicProfiles").doc(u).set({ userId: u, nickname: "진짜", department: "CS", mbti: "ENFP", topInterestIds: ["a"], oneLineIntro: "hi", avatarSeed: 3 }),
    db.collection("blindMeetings").doc(meeting).collection("publicProfiles").doc(other).set({ userId: other, nickname: "친구", department: "EE" }),
  ]);

  const docs = await loadAccountDeletionDocs(db, u);
  assert.deepEqual(docs.meeting, { hasDna: true, hasDnaDraft: true, hasApplication: true, partyIds: [party], hasPartyMembership: true, hasStats: true, publicProfileMeetingIds: [meeting] });
  for (const op of planAccountDeletionPiiOperations({ uid: u, docs })) {
    if (op.kind.startsWith("deleteBlindMeeting") || op.kind.startsWith("scrubBlindMeeting") || op.kind === "closeBlindMeetingApplication") {
      await applyMeetingCleanupOperation(db, u, op as never);
    }
  }
  assert.equal((await db.collection("blindMeetingDna").doc(u).get()).exists, false);
  assert.equal((await db.collection("blindMeetingDnaDrafts").doc(u).get()).exists, false);
  assert.equal((await db.collection("blindMeetingPartyMemberships").doc(u).get()).exists, false);
  assert.equal((await db.collection("blindMeetingStats").doc(u).get()).exists, false);
  const app = (await db.collection("blindMeetingApplications").doc(u).get()).data() ?? {};
  assert.equal(app.open, false);
  assert.equal(app.status, "cancelled");
  assert.equal("prefersAlcoholFree" in app, false);
  const profile = (await db.collection("blindMeetings").doc(meeting).collection("publicProfiles").doc(u).get()).data() ?? {};
  assert.equal(profile.nickname, DELETED_USER_DISPLAY_NAME);
  assert.equal(profile.department, null);
  assert.deepEqual(profile.topInterestIds, []);
  const otherProfile = (await db.collection("blindMeetings").doc(meeting).collection("publicProfiles").doc(other).get()).data() ?? {};
  assert.equal(otherProfile.nickname, "친구");
  const partyData = (await db.collection("blindMeetingParties").doc(party).get()).data() ?? {};
  const memberProfiles = partyData.memberProfiles as Record<string, Record<string, unknown>>;
  assert.equal(memberProfiles[u].nickname, DELETED_USER_DISPLAY_NAME);
  assert.equal(memberProfiles[other].nickname, "친구");
  assert.equal(Object.keys(partyData).some((k) => k.includes(".")), false);
});

test("onboarding photographs: only the uid's objects are listed and deleted; another user's object survives", async () => {
  const u = fresh("u"), v = fresh("v");
  const bucket = getStorage().bucket();
  const paths = [`users/${u}/onboarding/photos/1_0_a.jpg`, `users/${u}/onboarding/photos/2_1_b.jpg`, `users/${v}/onboarding/photos/1_0_c.jpg`];
  for (const path of paths) {
    await bucket.file(path).save(Buffer.from([0xff, 0xd8, 0xff, 0xd9]), { resumable: false, metadata: { contentType: "image/jpeg" } });
  }
  const refs = await listOnboardingPhotoObjects(bucket as unknown as OnboardingPhotoBucketLike, u);
  assert.deepEqual(refs.map((r) => r.path).sort(), paths.slice(0, 2).sort());
  const docs = await loadAccountDeletionDocs(db, u, {
    listOnboardingPhotoObjects: (uid) => listOnboardingPhotoObjects(bucket as unknown as OnboardingPhotoBucketLike, uid),
  });
  const deletes = planAccountDeletionPiiOperations({ uid: u, docs }).filter((op) => op.kind === "deleteStorage");
  assert.equal(deletes.length, 2);
  for (const op of deletes) {
    const ref = (op as { ref: { bucket: string; path: string } }).ref;
    assert.equal(ref.bucket, BUCKET);
    assert.equal(await deleteStorageObjectWithGenerationMatch(getStorage().bucket(ref.bucket).file(ref.path)), "deleted");
  }
  for (const path of paths.slice(0, 2)) assert.equal((await bucket.file(path).exists())[0], false);
  assert.equal((await bucket.file(paths[2]).exists())[0], true, "another user's photograph is never touched");
  // Re-running on an already-cleaned account is a no-op.
  assert.deepEqual(await listOnboardingPhotoObjects(bucket as unknown as OnboardingPhotoBucketLike, u), []);
});
