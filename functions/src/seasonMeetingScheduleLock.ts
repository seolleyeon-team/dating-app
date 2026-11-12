/**
 * P1-13 — the server-observed schedule of a 3:3 season meeting.
 *
 * A season meeting's time is the confirmed promise in its chat room
 * (`chat_rooms/season_<matchId>/promises/{promiseId}.dateTime`). Participants
 * write that value and either party may edit it while it stays confirmed, so
 * it is not evidence by itself. This trigger records, server-side, WHEN the
 * server first saw each confirmed time:
 *
 *   eventThreeVsThreeMatches/{matchId}/serverState/schedule
 *     { promiseId, meetupStartAtMs, observedAt (server time), version }
 *
 * The observation time only ever comes from the server clock. Re-confirming the
 * same time (or safety-stamp writes) keeps the original observation; a changed
 * time is a new observation; a cancelled / rejected / re-requested promise
 * releases the lock. Reads the CURRENT promise and room state in a
 * transaction, so out-of-order or repeated events converge (retry-safe).
 * Clients cannot read or write serverState (default-deny rules).
 */
import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";

import {
  SEASON_MATCHES,
  SEASON_SCHEDULE_LOCK_DOC,
  SEASON_SERVER_STATE,
  timestampMs,
} from "./seasonMeetingAuthority";
import { SEASON_MEETING_EVENT_TYPE } from "./seasonMeetingChat";

const SEASON_ROOM_PREFIX = "season_";
const SAFE_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SCHEDULED = new Set(["confirmed", "in_progress", "completed"]);

export type ScheduleLockOutcome =
  | "not_season_room"
  | "not_linked"
  | "not_active_promise"
  | "observed"
  | "unchanged"
  | "released"
  | "noop";

export async function reconcileSeasonScheduleLock(
  db: Firestore,
  roomId: string,
  promiseId: string,
): Promise<ScheduleLockOutcome> {
  if (!roomId.startsWith(SEASON_ROOM_PREFIX)) return "not_season_room";
  const matchId = roomId.slice(SEASON_ROOM_PREFIX.length);
  if (!SAFE_ID.test(matchId) || !SAFE_ID.test(promiseId)) return "not_linked";
  const matchRef = db.collection(SEASON_MATCHES).doc(matchId);
  const lockRef = matchRef.collection(SEASON_SERVER_STATE).doc(SEASON_SCHEDULE_LOCK_DOC);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const promiseRef = roomRef.collection("promises").doc(promiseId);

  return db.runTransaction(async (tx) => {
    const [match, room, promise, lock] = await Promise.all([
      tx.get(matchRef), tx.get(roomRef), tx.get(promiseRef), tx.get(lockRef),
    ]);
    if (!match.exists || !room.exists) return "not_linked";
    if (match.get("eventType") !== SEASON_MEETING_EVENT_TYPE || match.get("chatRoomId") !== roomId) {
      return "not_linked";
    }
    const lockData = lock.exists ? (lock.data() ?? {}) : null;
    const status = String(promise.exists ? promise.get("status") ?? "" : "").toLowerCase();
    const startMs = promise.exists ? timestampMs(promise.get("dateTime")) : null;
    if (promise.exists && SCHEDULED.has(status) && startMs != null) {
      const active = room.get("activePromise") as { promiseId?: unknown } | undefined;
      if (active && typeof active === "object" && active.promiseId !== promiseId) {
        return "not_active_promise";
      }
      if (lockData && lockData.promiseId === promiseId && lockData.meetupStartAtMs === startMs) {
        return "unchanged";
      }
      tx.set(lockRef, {
        promiseId,
        meetupStartAtMs: startMs,
        observedAt: FieldValue.serverTimestamp(),
        version: (typeof lockData?.version === "number" ? lockData.version : 0) + 1,
      });
      return "observed";
    }
    if (lockData && lockData.promiseId === promiseId) {
      tx.delete(lockRef);
      return "released";
    }
    return "noop";
  });
}

export function createSeasonScheduleLockTrigger(db: Firestore) {
  return onDocumentWritten(
    {
      document: "chat_rooms/{roomId}/promises/{promiseId}",
      // A lost event would leave the meeting without a server-observed
      // schedule (no-show / cancel then fail closed); the reconcile is
      // idempotent and reads current state, so a retry is always safe.
      retry: true,
    },
    async (event) => {
      const { roomId, promiseId } = event.params;
      if (!roomId.startsWith(SEASON_ROOM_PREFIX)) return;
      const outcome = await reconcileSeasonScheduleLock(db, roomId, promiseId);
      if (outcome !== "unchanged" && outcome !== "noop") {
        logger.info("season schedule lock reconciled", { outcome });
      }
    },
  );
}
