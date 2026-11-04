/**
 * P1-5 — blind-meeting personal data on account deletion.
 *
 * Before this module an account deletion left behind, keyed by the deleted
 * uid or naming it inside other users' documents:
 *   - blindMeetingDna/{uid} and blindMeetingDnaDrafts/{uid} — the private
 *     preference questionnaire (purely personal, no accounting value);
 *   - blindMeetingApplications/{uid} — requested dates and companion
 *     preferences, still `open` for the replacement search;
 *   - blindMeetings/{meetingId}/publicProfiles/{uid} — nickname, department,
 *     MBTI, interests and one-line intro shown to the other five members;
 *   - blindMeetingParties/{partyId}.memberProfiles.{uid} — nickname, photo and
 *     MBTI shown to the friend party; blindMeetingPartyMemberships/{uid};
 *   - blindMeetingStats/{uid} — per-user counters.
 *
 * Deleted outright: DNA, DNA draft, party membership, stats. Anonymised in
 * place (other members' documents keep their shape): the public profile
 * snapshot and the party member snapshot. The application is closed
 * (open:false, status cancelled, preferences removed) so the replacement
 * search and the matching engine never pick the account again; its meeting
 * link is kept for the meeting lifecycle, which already refuses withdrawn
 * accounts (store.requireVerifiedUser) and handles the vacancy.
 *
 * Kept on purpose: blindMeetingRestrictions/{uid} (safety sanctions),
 * blindMeetingHistory (uid-only re-match avoidance), heartTransactions and
 * meeting_cancel_refund records (financial retention).
 */
import { FieldValue, type Firestore } from "firebase-admin/firestore";

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";

export type AccountDeletionMeetingDocs = {
  hasDna: boolean;
  hasDnaDraft: boolean;
  hasApplication: boolean;
  partyIds: string[];
  hasPartyMembership: boolean;
  hasStats: boolean;
  /** Meetings whose publicProfiles subcollection names this uid. */
  publicProfileMeetingIds: string[];
};

export type AccountDeletionMeetingCounts = {
  blindMeetingDnaDeleted: number;
  blindMeetingApplicationsClosed: number;
  blindMeetingPublicProfilesScrubbed: number;
  blindMeetingPartyMembersScrubbed: number;
  blindMeetingPartyMembershipsDeleted: number;
  blindMeetingStatsDeleted: number;
};

export type MeetingCleanupOperation =
  | { kind: "deleteBlindMeetingDna" }
  | { kind: "deleteBlindMeetingDnaDraft" }
  | { kind: "closeBlindMeetingApplication" }
  | { kind: "scrubBlindMeetingPublicProfile"; meetingId: string }
  | { kind: "scrubBlindMeetingPartyMember"; partyId: string }
  | { kind: "deleteBlindMeetingPartyMembership" }
  | { kind: "deleteBlindMeetingStats" };

export const MEETING_CLEANUP_OPERATION_KINDS: ReadonlySet<string> = new Set([
  "deleteBlindMeetingDna",
  "deleteBlindMeetingDnaDraft",
  "closeBlindMeetingApplication",
  "scrubBlindMeetingPublicProfile",
  "scrubBlindMeetingPartyMember",
  "deleteBlindMeetingPartyMembership",
  "deleteBlindMeetingStats",
]);

function requirePathSegment(value: string, field: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
    throw new Error(`${field} is not a safe path segment.`);
  }
  return normalized;
}

export function emptyMeetingDocs(): AccountDeletionMeetingDocs {
  return {
    hasDna: false,
    hasDnaDraft: false,
    hasApplication: false,
    partyIds: [],
    hasPartyMembership: false,
    hasStats: false,
    publicProfileMeetingIds: [],
  };
}

export function emptyMeetingCounts(): AccountDeletionMeetingCounts {
  return {
    blindMeetingDnaDeleted: 0,
    blindMeetingApplicationsClosed: 0,
    blindMeetingPublicProfilesScrubbed: 0,
    blindMeetingPartyMembersScrubbed: 0,
    blindMeetingPartyMembershipsDeleted: 0,
    blindMeetingStatsDeleted: 0,
  };
}

export function meetingCountsFromDocs(
  docs: AccountDeletionMeetingDocs
): AccountDeletionMeetingCounts {
  return {
    blindMeetingDnaDeleted: (docs.hasDna ? 1 : 0) + (docs.hasDnaDraft ? 1 : 0),
    blindMeetingApplicationsClosed: docs.hasApplication ? 1 : 0,
    blindMeetingPublicProfilesScrubbed: docs.publicProfileMeetingIds.length,
    blindMeetingPartyMembersScrubbed: docs.partyIds.length,
    blindMeetingPartyMembershipsDeleted: docs.hasPartyMembership ? 1 : 0,
    blindMeetingStatsDeleted: docs.hasStats ? 1 : 0,
  };
}

export async function loadAccountDeletionMeetingDocs(
  firestore: Firestore,
  uid: string
): Promise<AccountDeletionMeetingDocs> {
  const safeUid = requirePathSegment(uid, "uid");
  const [dnaSnap, draftSnap, applicationSnap, membershipSnap, statsSnap, partiesSnap, meetingsSnap] =
    await Promise.all([
      firestore.collection("blindMeetingDna").doc(safeUid).get(),
      firestore.collection("blindMeetingDnaDrafts").doc(safeUid).get(),
      firestore.collection("blindMeetingApplications").doc(safeUid).get(),
      firestore.collection("blindMeetingPartyMemberships").doc(safeUid).get(),
      firestore.collection("blindMeetingStats").doc(safeUid).get(),
      firestore
        .collection("blindMeetingParties")
        .where("acceptedUserIds", "array-contains", safeUid)
        .get(),
      firestore
        .collection("blindMeetings")
        .where("participantIds", "array-contains", safeUid)
        .get(),
    ]);

  const publicProfileMeetingIds: string[] = [];
  for (const meeting of meetingsSnap.docs) {
    const profile = await meeting.ref.collection("publicProfiles").doc(safeUid).get();
    if (profile.exists) publicProfileMeetingIds.push(meeting.id);
  }

  return {
    hasDna: dnaSnap.exists,
    hasDnaDraft: draftSnap.exists,
    hasApplication: applicationSnap.exists,
    partyIds: partiesSnap.docs.map((doc) => doc.id),
    hasPartyMembership: membershipSnap.exists,
    hasStats: statsSnap.exists,
    publicProfileMeetingIds,
  };
}

export function planAccountDeletionMeetingOperations(params: {
  uid: string;
  docs: AccountDeletionMeetingDocs;
}): MeetingCleanupOperation[] {
  requirePathSegment(params.uid, "uid");
  const docs = params.docs;
  const operations: MeetingCleanupOperation[] = [];
  if (docs.hasDna) operations.push({ kind: "deleteBlindMeetingDna" });
  if (docs.hasDnaDraft) operations.push({ kind: "deleteBlindMeetingDnaDraft" });
  if (docs.hasApplication) operations.push({ kind: "closeBlindMeetingApplication" });
  for (const meetingId of docs.publicProfileMeetingIds) {
    operations.push({ kind: "scrubBlindMeetingPublicProfile", meetingId });
  }
  for (const partyId of docs.partyIds) {
    operations.push({ kind: "scrubBlindMeetingPartyMember", partyId });
  }
  if (docs.hasPartyMembership) operations.push({ kind: "deleteBlindMeetingPartyMembership" });
  if (docs.hasStats) operations.push({ kind: "deleteBlindMeetingStats" });
  return operations;
}

export async function applyMeetingCleanupOperation(
  firestore: Firestore,
  uid: string,
  operation: MeetingCleanupOperation
): Promise<void> {
  const safeUid = requirePathSegment(uid, "uid");
  const now = FieldValue.serverTimestamp();
  switch (operation.kind) {
    case "deleteBlindMeetingDna":
      await firestore.collection("blindMeetingDna").doc(safeUid).delete();
      return;
    case "deleteBlindMeetingDnaDraft":
      await firestore.collection("blindMeetingDnaDrafts").doc(safeUid).delete();
      return;
    case "closeBlindMeetingApplication":
      await firestore.collection("blindMeetingApplications").doc(safeUid).set(
        {
          open: false,
          status: "cancelled",
          serverStatus: "cancelled",
          requestedDateKeys: [],
          prefersAlcoholFree: FieldValue.delete(),
          waitlistOptIn: FieldValue.delete(),
          accountDeleted: true,
          accountDeletedAt: now,
          updatedAt: now,
        },
        { merge: true }
      );
      return;
    case "scrubBlindMeetingPublicProfile":
      await firestore
        .collection("blindMeetings")
        .doc(requirePathSegment(operation.meetingId, "meetingId"))
        .collection("publicProfiles")
        .doc(safeUid)
        .set(
          {
            nickname: DELETED_USER_DISPLAY_NAME,
            department: null,
            mbti: null,
            topInterestIds: [],
            oneLineIntro: null,
            accountDeleted: true,
            updatedAt: now,
          },
          { merge: true }
        );
      return;
    case "scrubBlindMeetingPartyMember":
      // Nested-map merge: keys are field NAMES under set({merge:true}); the
      // dotted-path form would create a literal top-level key (see the
      // participantInfo defect this finding started from).
      await firestore
        .collection("blindMeetingParties")
        .doc(requirePathSegment(operation.partyId, "partyId"))
        .set(
          {
            memberProfiles: {
              [safeUid]: {
                nickname: DELETED_USER_DISPLAY_NAME,
                profileImageUrl: "",
                mbti: "",
                accountDeleted: true,
              },
            },
            updatedAt: now,
          },
          { merge: true }
        );
      return;
    case "deleteBlindMeetingPartyMembership":
      await firestore.collection("blindMeetingPartyMemberships").doc(safeUid).delete();
      return;
    case "deleteBlindMeetingStats":
      await firestore.collection("blindMeetingStats").doc(safeUid).delete();
      return;
  }
}
