/**
 * Releasing a confirmed blind-meeting seat — the one transaction shape behind
 * both ways a member can vacate it:
 *
 *   - leaveBlindMeeting (the member leaves the group room), and
 *   - the account-deletion cleanup (AUD-08: before this the deletion only
 *     closed the application, so the seat stayed `confirmed`; the replacement
 *     search never saw a vacancy and the lifecycle kept treating a deleted
 *     account as an attendee).
 *
 * The state transition is identical in both: the participant becomes
 * `cancelled` with `replacementSearchActive`, the meeting opens (or joins) its
 * replacement search, and the member leaves the group room. No heart is
 * refunded to the member who vacates the seat (the leave contract); the
 * remaining members are refunded only if the search later times out
 * (cancelReplacementFailedMeeting).
 *
 * Kept free of the store/orchestrator imports so the account-deletion module
 * can use it with the Firestore handle it was given.
 */
import {
  FieldValue,
  Timestamp,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";

import {
  BLIND_MEETING_COLLECTIONS,
  PARTICIPANT_STATUS_TO_APP,
  asStrArray,
} from "./types";

export type SeatReleaseMode = "leave" | "account_deletion";

export type SeatReleaseRefusal =
  /** The meeting or the participant document does not exist. */
  | "not_found"
  /** The user is not listed in the meeting roster. */
  | "not_participant"
  /** The seat is not `confirmed` (already vacated, attended, settled, ...). */
  | "not_confirmed"
  /** The meeting has no group room (leave only; a deletion still releases). */
  | "no_room";

export type SeatReleasePlan =
  | { refusal: SeatReleaseRefusal }
  | { refusal: null; write: () => void };

/**
 * Reads everything the release needs inside `tx` and returns either the
 * reason it does not apply or a `write` that queues the writes. Every read
 * happens here, so a caller may run it after its own reads and before any
 * write of the same transaction.
 *
 * `mode: "leave"` also closes the member's application, exactly as the
 * callable always did. `mode: "account_deletion"` leaves the application to
 * the caller (which closes it in the same transaction) and does not create
 * documents for a group room that no longer exists.
 */
export async function planSeatRelease(
  tx: Transaction,
  firestore: Firestore,
  params: {
    meetingId: string;
    userId: string;
    replacementSearchWindowMs: number;
    mode: SeatReleaseMode;
  }
): Promise<SeatReleasePlan> {
  const meetingRef = firestore
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(params.meetingId);
  const participantRef = meetingRef
    .collection(BLIND_MEETING_COLLECTIONS.participants)
    .doc(params.userId);
  const [meetingSnap, participantSnap] = await Promise.all([
    tx.get(meetingRef),
    tx.get(participantRef),
  ]);
  if (!meetingSnap.exists || !participantSnap.exists) {
    return { refusal: "not_found" };
  }
  const meeting = meetingSnap.data() ?? {};
  if (!asStrArray(meeting.participantIds).includes(params.userId)) {
    return { refusal: "not_participant" };
  }
  const status = String(participantSnap.data()?.serverStatus ?? "");
  if (status !== "confirmed") return { refusal: "not_confirmed" };

  const roomId = String(meeting.groupChatId ?? "");
  if (!roomId && params.mode === "leave") return { refusal: "no_room" };
  const roomRef = roomId ? firestore.collection("chat_rooms").doc(roomId) : null;
  const roomSnap = roomRef ? await tx.get(roomRef) : null;
  const writeRoom =
    roomRef != null &&
    roomSnap != null &&
    (params.mode === "leave" || roomSnap.exists);
  const room = roomSnap?.data() ?? {};
  const memberIds = asStrArray(room.participantIds).filter(
    (uid) => uid !== params.userId
  );
  const info = { ...((room.participantInfo as Record<string, unknown>) ?? {}) };
  const nickname = (info[params.userId] as Record<string, unknown> | undefined)
    ?.nickname;
  const leaveMessage = `${typeof nickname === "string" && nickname.trim().length > 0 ? nickname.trim() : "참가자 한 분"}님이 나갔습니다. 설레연이 곧 대타를 구해서 초대할게요.`;
  delete info[params.userId];

  // A search that is still open keeps its deadline: every seat opened during
  // it shares the one window. A deadline left behind by an earlier, already
  // closed search (the fill clears only the flag) is not a deadline for this
  // one — reusing it cancelled the meeting on the next tick without searching.
  const openDeadline =
    meeting.replacementSearchActive === true &&
    meeting.replacementSearchDeadlineAt instanceof Timestamp
      ? meeting.replacementSearchDeadlineAt
      : null;
  const deadline =
    openDeadline ??
    Timestamp.fromMillis(Date.now() + params.replacementSearchWindowMs);

  const write = (): void => {
    tx.set(
      participantRef,
      {
        status: PARTICIPANT_STATUS_TO_APP.cancelled,
        serverStatus: "cancelled",
        leftByUser: true,
        replacementSearchActive: true,
        leftAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
        ...(params.mode === "account_deletion" ? { accountDeleted: true } : {}),
      },
      { merge: true }
    );
    tx.set(
      meetingRef,
      {
        replacementSearchActive: true,
        replacementSearchDeadlineAt: deadline,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    if (writeRoom && roomRef != null) {
      tx.set(
        roomRef,
        {
          participantIds: memberIds,
          participantInfo: info,
          lastMessage: leaveMessage,
          lastMessageAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      tx.create(roomRef.collection("messages").doc(), {
        senderId: "system",
        type: "system",
        text: leaveMessage,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });
    }
    if (params.mode === "leave") {
      tx.set(
        firestore
          .collection(BLIND_MEETING_COLLECTIONS.applications)
          .doc(params.userId),
        {
          status: PARTICIPANT_STATUS_TO_APP.cancelled,
          serverStatus: "cancelled",
          stage: "cancelled",
          open: false,
          meetingId: null,
          leftMeetingAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    }
  };
  return { refusal: null, write };
}
