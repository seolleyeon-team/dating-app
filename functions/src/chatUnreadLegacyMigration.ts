/**
 * P0-2 — ONE-TIME legacy migration (version 1): per-message `readBy` receipts
 * → room-level unread model. This is the only module allowed to read the
 * retired `readBy` field (enforced by chatUnreadLegacyGuard.test.ts). It is
 * never imported by a deployed function; the CLI (chatUnreadBackfillCli.ts)
 * runs it by hand with --dry-run first.
 *
 *  1. backfillRoomUnread / runChatUnreadBackfill — derive `unreadCounts` for
 *     rooms created before the model existed (completed in production on
 *     2026-10-16: 23 rooms).
 *  2. initializeReadBoundaries / runReadBoundaryInitialization — give
 *     participants whose counter was derived from receipts an explicit
 *     `lastReadAt` boundary, so that "missing boundary = everything unread"
 *     holds for every room afterwards. Only a CONTIGUOUS receipt history
 *     (every read message older than every unread one) is representable by
 *     one timestamp; anything else is reported, never guessed.
 */
import {
  FieldPath,
  FieldValue,
  Timestamp,
  type DocumentReference,
  type Firestore,
} from "firebase-admin/firestore";

import {
  TRANSACTION_MESSAGE_BUDGET,
  UNREAD_MODEL_VERSION,
  applyUnreadIncrements,
  messageCommitTime,
  unreadCountFor,
} from "./chatUnread";

export const LEGACY_MIGRATION_VERSION = 1;
export const LEGACY_MESSAGE_CHUNK = TRANSACTION_MESSAGE_BUDGET;

type Doc = Record<string, unknown>;

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isRecord(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The retired per-message rule: a message was unread for `uid` when `uid`
 * did not send it and `readBy` did not contain `uid`.
 */
export function legacyMessageIsUnreadFor(message: Doc, uid: string): boolean {
  const senderId = asNonEmptyString(message.senderId);
  if (!senderId || senderId === uid) return false;
  const readBy = Array.isArray(message.readBy) ? message.readBy : [];
  return !readBy.some((entry) => entry === uid);
}

// -----------------------------------------------------------------------------
// Step 1 — backfill: legacy rooms get counts derived from readBy, exactly once
// -----------------------------------------------------------------------------

export type RoomBackfillResult = {
  roomId: string;
  skipped: "already_backfilled" | "missing" | null;
  messagesInspected: number;
  messagesCounted: number;
  counts: Record<string, number>;
  chunks: number;
  writes: number;
};

/**
 * Derives `unreadCounts` for one room from `readBy` (the legacy rule) and
 * marks every inspected message `unreadAccountedAt`, in chunks of at most
 * TRANSACTION_MESSAGE_BUDGET messages per transaction. Messages the trigger
 * already accounted (created after the new Functions were deployed) are
 * skipped, so counts never double. Re-running on a finished room is a no-op
 * (`unreadBackfilledAt`), and an interrupted room resumes from the first
 * unmarked message. Reads happen inside the transaction, so a message that
 * arrives mid-backfill serialises against it instead of being lost.
 */
export async function backfillRoomUnread(
  db: Firestore,
  roomId: string,
  options: { dryRun: boolean; chunkSize?: number; force?: boolean }
): Promise<RoomBackfillResult> {
  const chunkSize = Math.min(options.chunkSize ?? TRANSACTION_MESSAGE_BUDGET, TRANSACTION_MESSAGE_BUDGET);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const result: RoomBackfillResult = {
    roomId,
    skipped: null,
    messagesInspected: 0,
    messagesCounted: 0,
    counts: {},
    chunks: 0,
    writes: 0,
  };
  const roomSnap = await roomRef.get();
  if (!roomSnap.exists) {
    result.skipped = "missing";
    return result;
  }
  const roomData = (roomSnap.data() ?? {}) as Doc;
  if (roomData.unreadBackfilledAt != null && !options.force) {
    result.skipped = "already_backfilled";
    return result;
  }
  const participantIds = Array.isArray(roomData.participantIds)
    ? roomData.participantIds.filter(
        (v): v is string => typeof v === "string" && v.length > 0
      )
    : [];

  let cursor: FirebaseFirestore.QueryDocumentSnapshot | null = null;
  for (;;) {
    const chunk = await db.runTransaction(async (tx) => {
      let query = roomRef
        .collection("messages")
        .orderBy("createdAt")
        .orderBy(FieldPath.documentId())
        .limit(chunkSize);
      if (cursor) query = query.startAfter(cursor);
      const page = await tx.get(query);
      const increments: Record<string, number> = {};
      let counted = 0;
      let inspected = 0;
      const toMark: DocumentReference[] = [];
      for (const doc of page.docs) {
        inspected += 1;
        const message = (doc.data() ?? {}) as Doc;
        if (message.unreadAccountedAt != null) continue;
        let countedThis = false;
        for (const uid of participantIds) {
          if (legacyMessageIsUnreadFor(message, uid)) {
            increments[uid] = (increments[uid] ?? 0) + 1;
            countedThis = true;
          }
        }
        if (countedThis) counted += 1;
        toMark.push(doc.ref);
      }
      const last = page.docs.length > 0 ? page.docs[page.docs.length - 1] : null;
      const done = page.size < chunkSize;
      if (options.dryRun) {
        return { increments, counted, inspected, last, done, writes: 0 };
      }
      const recipients = Object.keys(increments);
      if (recipients.length > 0) applyUnreadIncrements(tx, roomRef, recipients, increments);
      for (const ref of toMark) {
        tx.update(ref, { unreadAccountedAt: FieldValue.serverTimestamp(), unreadBackfilled: true });
      }
      if (done) {
        tx.set(
          roomRef,
          {
            unreadModelVersion: UNREAD_MODEL_VERSION,
            unreadBackfilledAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }
      return {
        increments,
        counted,
        inspected,
        last,
        done,
        writes: toMark.length + (recipients.length > 0 ? 1 : 0) + (done ? 1 : 0),
      };
    });
    result.chunks += 1;
    result.messagesInspected += chunk.inspected;
    result.messagesCounted += chunk.counted;
    result.writes += chunk.writes;
    for (const [uid, n] of Object.entries(chunk.increments)) {
      result.counts[uid] = (result.counts[uid] ?? 0) + n;
    }
    if (chunk.done || !chunk.last) break;
    cursor = chunk.last;
  }
  return result;
}

export type BackfillRunSummary = {
  dryRun: boolean;
  roomsVisited: number;
  roomsBackfilled: number;
  roomsSkippedAlready: number;
  messagesInspected: number;
  messagesCounted: number;
  writes: number;
  lastRoomId: string | null;
  completed: boolean;
};

/**
 * Pages through chat_rooms by document id (never loads them all), persists a
 * checkpoint after every room when `checkpointId` is given, and stops after
 * `limitRooms` rooms so an operator can run it in bounded slices.
 */
export async function runChatUnreadBackfill(
  db: Firestore,
  options: {
    dryRun: boolean;
    limitRooms?: number;
    pageSize?: number;
    checkpointId?: string;
    startAfterRoomId?: string;
    log?: (line: string) => void;
  }
): Promise<BackfillRunSummary> {
  const log = options.log ?? (() => undefined);
  const pageSize = options.pageSize ?? 50;
  const checkpointRef = options.checkpointId
    ? db.collection("chatUnreadBackfillRuns").doc(options.checkpointId)
    : null;
  let startAfter: string | null = options.startAfterRoomId ?? null;
  if (checkpointRef && !startAfter) {
    const cp = await checkpointRef.get();
    const stored = cp.exists ? (cp.data() as Doc).lastRoomId : null;
    if (typeof stored === "string" && stored.length > 0) startAfter = stored;
  }
  const summary: BackfillRunSummary = {
    dryRun: options.dryRun,
    roomsVisited: 0,
    roomsBackfilled: 0,
    roomsSkippedAlready: 0,
    messagesInspected: 0,
    messagesCounted: 0,
    writes: 0,
    lastRoomId: startAfter,
    completed: false,
  };
  const limitRooms = options.limitRooms ?? Number.POSITIVE_INFINITY;
  outer: for (;;) {
    let query = db.collection("chat_rooms").orderBy(FieldPath.documentId()).limit(pageSize);
    if (summary.lastRoomId) query = query.startAfter(summary.lastRoomId);
    const page = await query.get();
    if (page.empty) {
      summary.completed = true;
      break;
    }
    for (const doc of page.docs) {
      if (summary.roomsVisited >= limitRooms) break outer;
      const result = await backfillRoomUnread(db, doc.id, { dryRun: options.dryRun });
      summary.roomsVisited += 1;
      summary.lastRoomId = doc.id;
      if (result.skipped === "already_backfilled") summary.roomsSkippedAlready += 1;
      else if (!result.skipped) summary.roomsBackfilled += 1;
      summary.messagesInspected += result.messagesInspected;
      summary.messagesCounted += result.messagesCounted;
      summary.writes += result.writes;
      log(
        `${options.dryRun ? "[dry-run] " : ""}room ${doc.id}: ${result.skipped ?? "backfilled"} inspected=${result.messagesInspected} counted=${result.messagesCounted} counts=${JSON.stringify(result.counts)} chunks=${result.chunks}`
      );
      if (checkpointRef && !options.dryRun) {
        await checkpointRef.set(
          { lastRoomId: doc.id, updatedAt: FieldValue.serverTimestamp() },
          { merge: true }
        );
      }
    }
    if (page.size < pageSize) {
      summary.completed = true;
      break;
    }
  }
  return summary;
}

// -----------------------------------------------------------------------------
// Step 2 — explicit read boundaries for receipt-derived counters
// -----------------------------------------------------------------------------

export type ReadBoundaryAnomaly = {
  uid: string;
  kind: "non_contiguous" | "counter_mismatch" | "changed";
  detail: string;
};

export type RoomReadBoundaryResult = {
  roomId: string;
  /** Participants that received an explicit boundary (or would, in dry run). */
  initialized: Array<{ uid: string; boundaryMs: number; counter: number }>;
  /** Participants whose missing boundary already matches their counter. */
  consistent: string[];
  /** Participants that already carry a boundary. */
  alreadyBounded: string[];
  anomalies: ReadBoundaryAnomaly[];
  /** Rooms with more messages than `maxMessages` cannot be decided here. */
  unverifiable: string[];
  writes: number;
};

/**
 * For every participant without `lastReadAt` whose counter is NOT "every
 * message I did not send": reconstruct the receipt history; if it is a
 * contiguous suffix and its unread count equals the counter, set
 * `lastReadAt[uid]` to the commit time of the newest READ message (so exactly
 * the counted messages are newer than the boundary). Writes happen in one
 * transaction per room that re-checks the room first; a room that moved is
 * reported as `changed` and left alone.
 */
export async function initializeReadBoundaries(
  db: Firestore,
  roomId: string,
  options: { dryRun: boolean; maxMessages?: number }
): Promise<RoomReadBoundaryResult> {
  const maxMessages = options.maxMessages ?? 2000;
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const result: RoomReadBoundaryResult = {
    roomId, initialized: [], consistent: [], alreadyBounded: [], anomalies: [], unverifiable: [], writes: 0,
  };
  const roomSnap = await roomRef.get();
  if (!roomSnap.exists) return result;
  const room = (roomSnap.data() ?? {}) as Doc;
  const participantIds = Array.isArray(room.participantIds)
    ? room.participantIds.filter((v): v is string => typeof v === "string" && v.length > 0)
    : [];
  const lastReadAt = isRecord(room.lastReadAt) ? room.lastReadAt : {};
  const page = await roomRef.collection("messages").orderBy("createdAt").limit(maxMessages + 1).get();
  if (page.size > maxMessages) {
    result.unverifiable.push(...participantIds.filter((uid) => !(lastReadAt[uid] instanceof Timestamp)));
    return result;
  }
  const planned: Array<{ uid: string; boundary: Timestamp; counter: number }> = [];
  for (const uid of participantIds) {
    if (lastReadAt[uid] instanceof Timestamp) {
      result.alreadyBounded.push(uid);
      continue;
    }
    const counter = unreadCountFor(room, uid);
    const others = page.docs.filter((d) => {
      const sender = asNonEmptyString((d.data() ?? {}).senderId);
      return sender !== null && sender !== uid;
    });
    if (counter === others.length) {
      result.consistent.push(uid);
      continue;
    }
    const flags = others.map((d) => (legacyMessageIsUnreadFor((d.data() ?? {}) as Doc, uid) ? "U" : "R"));
    const firstUnread = flags.indexOf("U");
    const contiguous = firstUnread === -1 || flags.slice(firstUnread).every((f) => f === "U");
    const legacyUnread = flags.filter((f) => f === "U").length;
    if (!contiguous) {
      result.anomalies.push({ uid, kind: "non_contiguous", detail: flags.join("") });
      continue;
    }
    if (legacyUnread !== counter) {
      result.anomalies.push({ uid, kind: "counter_mismatch", detail: `counter=${counter} receipts=${legacyUnread}` });
      continue;
    }
    const newestRead = others[(firstUnread === -1 ? others.length : firstUnread) - 1];
    const boundary = newestRead ? messageCommitTime(newestRead, (newestRead.data() ?? {}) as Doc) : null;
    if (!boundary) {
      result.anomalies.push({ uid, kind: "counter_mismatch", detail: "no commit time on the newest read message" });
      continue;
    }
    planned.push({ uid, boundary, counter });
    result.initialized.push({ uid, boundaryMs: boundary.toMillis(), counter });
  }
  if (options.dryRun || planned.length === 0) return result;

  const outcome = await db.runTransaction(async (tx) => {
    const snap = await tx.get(roomRef);
    if (!snap.exists) return "changed" as const;
    const current = (snap.data() ?? {}) as Doc;
    const currentRead = isRecord(current.lastReadAt) ? current.lastReadAt : {};
    for (const p of planned) {
      if (currentRead[p.uid] instanceof Timestamp) return "changed" as const;
      if (unreadCountFor(current, p.uid) !== p.counter) return "changed" as const;
    }
    const args: unknown[] = [
      "unreadModelVersion", UNREAD_MODEL_VERSION,
      "legacyReadBoundaryMigratedAt", FieldValue.serverTimestamp(),
      "legacyReadBoundaryMigrationVersion", LEGACY_MIGRATION_VERSION,
    ];
    for (const p of planned) args.push(new FieldPath("lastReadAt", p.uid), p.boundary);
    (tx.update as unknown as (ref: DocumentReference, ...rest: unknown[]) => unknown)(roomRef, ...args);
    return "written" as const;
  });
  if (outcome === "written") {
    result.writes = 1;
  } else {
    result.anomalies.push(...planned.map((p) => ({ uid: p.uid, kind: "changed" as const, detail: "room moved between read and write" })));
    result.initialized = [];
  }
  return result;
}

export type ReadBoundaryRunSummary = {
  dryRun: boolean;
  roomsVisited: number;
  participantsInitialized: number;
  participantsConsistent: number;
  participantsAlreadyBounded: number;
  anomalies: number;
  unverifiable: number;
  writes: number;
  lastRoomId: string | null;
  completed: boolean;
};

export async function runReadBoundaryInitialization(
  db: Firestore,
  options: {
    dryRun: boolean;
    limitRooms?: number;
    pageSize?: number;
    checkpointId?: string;
    startAfterRoomId?: string;
    log?: (line: string) => void;
  }
): Promise<ReadBoundaryRunSummary> {
  const log = options.log ?? (() => undefined);
  const pageSize = options.pageSize ?? 50;
  const checkpointRef = options.checkpointId
    ? db.collection("chatUnreadBackfillRuns").doc(options.checkpointId)
    : null;
  let startAfter: string | null = options.startAfterRoomId ?? null;
  if (checkpointRef && !startAfter) {
    const cp = await checkpointRef.get();
    const stored = cp.exists ? (cp.data() as Doc).lastRoomId : null;
    if (typeof stored === "string" && stored.length > 0) startAfter = stored;
  }
  const summary: ReadBoundaryRunSummary = {
    dryRun: options.dryRun, roomsVisited: 0, participantsInitialized: 0, participantsConsistent: 0,
    participantsAlreadyBounded: 0, anomalies: 0, unverifiable: 0, writes: 0, lastRoomId: startAfter, completed: false,
  };
  const limitRooms = options.limitRooms ?? Number.POSITIVE_INFINITY;
  outer: for (;;) {
    let query = db.collection("chat_rooms").orderBy(FieldPath.documentId()).limit(pageSize);
    if (summary.lastRoomId) query = query.startAfter(summary.lastRoomId);
    const page = await query.get();
    if (page.empty) {
      summary.completed = true;
      break;
    }
    for (const doc of page.docs) {
      if (summary.roomsVisited >= limitRooms) break outer;
      const r = await initializeReadBoundaries(db, doc.id, { dryRun: options.dryRun });
      summary.roomsVisited += 1;
      summary.lastRoomId = doc.id;
      summary.participantsInitialized += r.initialized.length;
      summary.participantsConsistent += r.consistent.length;
      summary.participantsAlreadyBounded += r.alreadyBounded.length;
      summary.anomalies += r.anomalies.length;
      summary.unverifiable += r.unverifiable.length;
      summary.writes += r.writes;
      if (r.initialized.length || r.anomalies.length || r.unverifiable.length) {
        log(
          `${options.dryRun ? "[dry-run] " : ""}room ${doc.id}: init=${r.initialized.map((i) => `${i.uid}@${i.boundaryMs}(count ${i.counter})`).join(",") || "-"} ` +
            `anomalies=${r.anomalies.map((a) => `${a.uid}:${a.kind}`).join(",") || "-"} unverifiable=${r.unverifiable.length} writes=${r.writes}`
        );
      }
      if (checkpointRef && !options.dryRun) {
        await checkpointRef.set({ lastRoomId: doc.id, mode: "init-boundaries", updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      }
    }
    if (page.size < pageSize) {
      summary.completed = true;
      break;
    }
  }
  return summary;
}
