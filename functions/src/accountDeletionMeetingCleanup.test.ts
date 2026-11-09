import assert from "node:assert/strict";
import test from "node:test";

import { type Firestore } from "firebase-admin/firestore";

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";
import {
  applyMeetingCleanupOperation,
  emptyMeetingDocs,
  meetingCountsFromDocs,
  planAccountDeletionMeetingOperations,
} from "./accountDeletionMeetingCleanup";
import { FakeFirestore, type Db } from "./testing/fakeFirestore";

function fakeDb(): { db: Db; firestore: Firestore } {
  const db: Db = new Map();
  return { db, firestore: new FakeFirestore(db) as unknown as Firestore };
}

test("P1-5 meeting plan: one operation per personal record, nothing for an account without blind-meeting data", () => {
  assert.deepEqual(planAccountDeletionMeetingOperations({ uid: "u1", docs: emptyMeetingDocs() }), []);
  const ops = planAccountDeletionMeetingOperations({
    uid: "u1",
    docs: {
      hasDna: true, hasDnaDraft: true, hasApplication: true,
      partyIds: ["party_a"], hasPartyMembership: true, hasStats: true,
      publicProfileMeetingIds: ["m1", "m2"],
    },
  });
  assert.deepEqual(ops.map((op) => op.kind), [
    "deleteBlindMeetingDna", "deleteBlindMeetingDnaDraft", "closeBlindMeetingApplication",
    "scrubBlindMeetingPublicProfile", "scrubBlindMeetingPublicProfile",
    "scrubBlindMeetingPartyMember", "deleteBlindMeetingPartyMembership", "deleteBlindMeetingStats",
  ]);
  assert.deepEqual(meetingCountsFromDocs({
    hasDna: true, hasDnaDraft: false, hasApplication: true,
    partyIds: ["party_a"], hasPartyMembership: true, hasStats: false,
    publicProfileMeetingIds: ["m1", "m2"],
  }), {
    blindMeetingDnaDeleted: 1, blindMeetingApplicationsClosed: 1, blindMeetingPublicProfilesScrubbed: 2,
    blindMeetingPartyMembersScrubbed: 1, blindMeetingPartyMembershipsDeleted: 1, blindMeetingStatsDeleted: 0,
  });
  assert.throws(() => planAccountDeletionMeetingOperations({ uid: "../x", docs: emptyMeetingDocs() }));
});

test("P1-5 meeting apply: DNA, draft, membership and stats are deleted; the application is closed and stripped of preferences", async () => {
  const { db, firestore } = fakeDb();
  db.set("blindMeetingDna/u1", { answers: { q1: "a" } });
  db.set("blindMeetingDnaDrafts/u1", { answers: { q1: "a" } });
  db.set("blindMeetingPartyMemberships/u1", { partyId: "party_a", active: true });
  db.set("blindMeetingStats/u1", { completedMeetings: 2 });
  db.set("blindMeetingApplications/u1", {
    userId: "u1", status: "applied", open: true, requestedDateKeys: ["2026-11-10"],
    prefersAlcoholFree: true, waitlistOptIn: false, meetingId: null, partyId: "party_a",
  });
  for (const kind of ["deleteBlindMeetingDna", "deleteBlindMeetingDnaDraft", "deleteBlindMeetingPartyMembership", "deleteBlindMeetingStats", "closeBlindMeetingApplication"] as const) {
    await applyMeetingCleanupOperation(firestore, "u1", { kind });
  }
  assert.equal(db.has("blindMeetingDna/u1"), false);
  assert.equal(db.has("blindMeetingDnaDrafts/u1"), false);
  assert.equal(db.has("blindMeetingPartyMemberships/u1"), false);
  assert.equal(db.has("blindMeetingStats/u1"), false);
  const app = db.get("blindMeetingApplications/u1") ?? {};
  assert.equal(app.open, false);
  assert.equal(app.status, "cancelled");
  assert.deepEqual(app.requestedDateKeys, []);
  assert.equal("prefersAlcoholFree" in app, false);
  assert.equal("waitlistOptIn" in app, false);
  assert.equal(app.accountDeleted, true);
  assert.equal(app.partyId, "party_a", "lifecycle links are kept");
});

test("P1-5 meeting apply: public profile and party member snapshots are anonymised in place; other members untouched", async () => {
  const { db, firestore } = fakeDb();
  db.set("blindMeetings/m1/publicProfiles/u1", {
    userId: "u1", nickname: "진짜이름", department: "컴퓨터과학", mbti: "ENFP",
    topInterestIds: ["i1", "i2"], oneLineIntro: "안녕", avatarSeed: 7, schoolVerified: true,
  });
  db.set("blindMeetingParties/party_a", {
    acceptedUserIds: ["u1", "u2"],
    memberProfiles: {
      u1: { userId: "u1", nickname: "진짜이름", profileImageUrl: "https://x/a.jpg", mbti: "ENFP" },
      u2: { userId: "u2", nickname: "친구", profileImageUrl: "https://x/b.jpg", mbti: "ISTJ" },
    },
  });
  await applyMeetingCleanupOperation(firestore, "u1", { kind: "scrubBlindMeetingPublicProfile", meetingId: "m1" });
  await applyMeetingCleanupOperation(firestore, "u1", { kind: "scrubBlindMeetingPartyMember", partyId: "party_a" });

  const profile = db.get("blindMeetings/m1/publicProfiles/u1") ?? {};
  assert.equal(profile.nickname, DELETED_USER_DISPLAY_NAME);
  assert.equal(profile.department, null);
  assert.equal(profile.mbti, null);
  assert.deepEqual(profile.topInterestIds, []);
  assert.equal(profile.oneLineIntro, null);
  assert.equal(profile.avatarSeed, 7, "non-identifying fields keep the document shape");

  const party = db.get("blindMeetingParties/party_a") ?? {};
  const members = party.memberProfiles as Record<string, Record<string, unknown>>;
  assert.equal(members.u1.nickname, DELETED_USER_DISPLAY_NAME);
  assert.equal(members.u1.profileImageUrl, "");
  assert.equal(members.u2.nickname, "친구", "the other member's snapshot is untouched");
  assert.equal(members.u2.profileImageUrl, "https://x/b.jpg");
  assert.equal(Object.keys(party).some((k) => k.includes(".")), false, "no literal dotted key");
});
