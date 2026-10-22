/**
 * P0-2 (2026-10 production audit): server-authoritative chat unread state.
 *
 * Before this module the only unread signal was the per-message `readBy`
 * array: every badge evaluation read every message of every room, marking a
 * room read rewrote every unread message (one batch, >500 fails) and the daily
 * digest scanned users × rooms × messages. All of that scaled with total
 * message history.
 *
 * Model (room document, `chat_rooms/{roomId}`):
 *
 *   unreadCounts:      { <uid>: number }   server-only increments, one per
 *                                          accountable message per recipient;
 *                                          a participant may reset ONLY its own
 *                                          key to 0 (firestore.rules)
 *   lastReadAt:        { <uid>: Timestamp } participant-written, own key only
 *   unreadModelVersion: 1                  present once the room carries
 *                                          server-maintained counts (set by the
 *                                          first accounted message or by the
 *                                          backfill); absent = legacy room
 *   unreadBackfilledAt: Timestamp          set once the backfill finished the
 *                                          room (idempotency / resume marker)
 *
 * Invariant (strict correctness, per room and participant `u`):
 *
 *   unreadCounts[u] == |{ m : m.senderId != u
 *                           && m.commitTime > lastReadAt[u] }|
 *
 * where `lastReadAt[u]` is the server time of `u`'s last mark-read and a
 * missing `lastReadAt[u]` means "every message counts". The client resets the
 * counter to 0 and stamps `lastReadAt` in ONE write; the trigger increments
 * only for recipients whose `lastReadAt` is older than the message's commit
 * time (`DocumentSnapshot.createTime`, which a client cannot forge). A
 * trigger delivered AFTER the recipient already marked the room read (the
 * message was on screen when they did) therefore leaves the counter at 0 —
 * no phantom unread — in every interleaving, because both writes go through
 * Firestore's serialisable transactions on the room document.
 *
 * Message document: `unreadAccountedAt` marks that this message's increments
 * were applied. The Firestore trigger is delivered at least once; the marker
 * is read and written inside the same transaction as the increments, so a
 * redelivery (or the backfill visiting the same message) can never count a
 * message twice.
 *
 * Semantics preserved from the pre-existing client (`chat_service.dart`):
 * every message a user did not send counts as unread for them — system and
 * promise messages included — until they open the room. Old clients keep
 * computing their badge from `readBy`, which the server still writes.
 */
import {
  FieldPath,
  FieldValue,
  Timestamp,
  type DocumentReference,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";

export const UNREAD_MODEL_VERSION = 1;
export const SYSTEM_SENDER_ID = "system";
/** Firestore transaction/batch limit is 500 operations; keep headroom. */
export const BACKFILL_MESSAGE_CHUNK = 400;

type Doc = Record<string, unknown>;

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isRecord(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A Firestore field path segment: uids are safe, but never build dotted strings. */
function unreadCountPath(uid: string): FieldPath {
  return new FieldPath("unreadCounts", uid);
}

// -----------------------------------------------------------------------------
// Pure decisions (unit-tested without Firestore)
// -----------------------------------------------------------------------------

/**
 * Who sees this message as unread: every participant except its sender.
 * System messages (`senderId: "system"`) count for every participant, exactly
 * as the client has always treated them (sender != me and readBy lacks me).
 */
export function unreadRecipientsFor(params: {
  senderId: unknown;
  participantIds: unknown;
}): string[] {
  const senderId = asNonEmptyString(params.senderId);
  if (!senderId) return [];
  const raw = Array.isArray(params.participantIds) ? params.participantIds : [];
  const seen = new Set<string>();
  const recipients: string[] = [];
  for (const entry of raw) {
    const uid = asNonEmptyString(entry);
    if (!uid || uid === senderId || seen.has(uid)) continue;
    seen.add(uid);
    recipients.push(uid);
  }
  return recipients;
}

function asTimestamp(value: unknown): Timestamp | null {
  return value instanceof Timestamp ? value : null;
}

/** `a >= b` on Firestore timestamps (nanosecond precision, no float rounding). */
export function timestampAtOrAfter(a: Timestamp, b: Timestamp): boolean {
  return a.seconds > b.seconds || (a.seconds === b.seconds && a.nanoseconds >= b.nanoseconds);
}

/**
 * Read high-water mark: which recipients still have to be incremented for a
 * message committed at `messageCommittedAt`. A recipient whose `lastReadAt`
 * is at or after the commit time marked the room read while this message was
 * already there, so it is already covered by their reset to 0 (a delayed or
 * redelivered trigger must not resurrect it). No usable timestamp on either
 * side fails toward counting the message, never toward hiding it.
 */
export function recipientsToIncrement(params: {
  senderId: unknown;
  participantIds: unknown;
  lastReadAt: unknown;
  messageCommittedAt: Timestamp | null;
}): { increment: string[]; alreadyRead: string[] } {
  const increment: string[] = [];
  const alreadyRead: string[] = [];
  const lastReadAt = isRecord(params.lastReadAt) ? params.lastReadAt : {};
  for (const uid of unreadRecipientsFor(params)) {
    const readAt = asTimestamp(lastReadAt[uid]);
    if (readAt && params.messageCommittedAt && timestampAtOrAfter(readAt, params.messageCommittedAt)) {
      alreadyRead.push(uid);
    } else {
      increment.push(uid);
    }
  }
  return { increment, alreadyRead };
}

/** Unread count a room document carries for one participant (0 when absent). */
export function unreadCountFor(roomData: Doc | undefined, uid: string): number {
  const counts = roomData?.unreadCounts;
  if (!isRecord(counts)) return 0;
  const value = counts[uid];
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : 0;
}

/** True once the room carries server-maintained counts. */
export function roomHasUnreadModel(roomData: Doc | undefined): boolean {
  return roomData?.unreadModelVersion === UNREAD_MODEL_VERSION;
}

/**
 * The legacy per-message rule the backfill reproduces: a message is unread
 * for `uid` when `uid` did not send it and `readBy` does not contain `uid`.
 */
export function legacyMessageIsUnreadFor(message: Doc, uid: string): boolean {
  const senderId = asNonEmptyString(message.senderId);
  if (!senderId || senderId === uid) return false;
  const readBy = Array.isArray(message.readBy) ? message.readBy : [];
  return !readBy.some((entry) => entry === uid);
}

/**
 * Digest row for one room: participants whose counter is positive, plus the
 * 1:1 peer's nickname for the preview line (groups get no name).
 */
export function digestContributionsForRoom(
  roomData: Doc
): Array<{ uid: string; unreadCount: number; previewSenderName: string | null }> {
  if (roomData.status !== "active") return [];
  if (roomData.dataPartition === "play_review") return [];
  const participantIds = Array.isArray(roomData.participantIds)
    ? roomData.participantIds.filter(
        (v): v is string => typeof v === "string" && v.length > 0
      )
    : [];
  const participantInfo = isRecord(roomData.participantInfo)
    ? roomData.participantInfo
    : {};
  const rows: Array<{
    uid: string;
    unreadCount: number;
    previewSenderName: string | null;
  }> = [];
  for (const uid of participantIds) {
    const unreadCount = unreadCountFor(roomData, uid);
    if (unreadCount <= 0) continue;
    let previewSenderName: string | null = null;
    if (participantIds.length === 2) {
      const peer = participantIds.find((p) => p !== uid);
      const info = peer ? participantInfo[peer] : undefined;
      previewSenderName = isRecord(info)
        ? asNonEmptyString(info.nickname)
        : null;
    }
    rows.push({ uid, unreadCount, previewSenderName });
  }
  return rows;
}

// -----------------------------------------------------------------------------
// Message accounting (trigger path) — the ONE authority for increments
// -----------------------------------------------------------------------------

export type AccountingResult = {
  applied: boolean;
  reason: "applied" | "already_accounted" | "message_missing" | "room_missing" | "no_recipients";
  /** Recipients whose counter was incremented. */
  recipients: string[];
  /** Recipients skipped because they marked the room read after this message was committed. */
  alreadyRead: string[];
};

/**
 * Applies this message's unread increments exactly once. Reads the message
 * and the room, decides, and writes the room increments together with the
 * message marker in ONE transaction, so an at-least-once trigger delivery or
 * a backfill visiting the same message cannot double-count.
 */
export async function accountMessageUnread(
  db: Firestore,
  params: { roomId: string; messageId: string }
): Promise<AccountingResult> {
  const roomRef = db.collection("chat_rooms").doc(params.roomId);
  const messageRef = roomRef.collection("messages").doc(params.messageId);
  return db.runTransaction(async (tx) => {
    const [messageSnap, roomSnap] = await Promise.all([
      tx.get(messageRef),
      tx.get(roomRef),
    ]);
    if (!messageSnap.exists) {
      return { applied: false, reason: "message_missing", recipients: [], alreadyRead: [] };
    }
    const message = (messageSnap.data() ?? {}) as Doc;
    if (message.unreadAccountedAt != null) {
      return { applied: false, reason: "already_accounted", recipients: [], alreadyRead: [] };
    }
    if (!roomSnap.exists) {
      // Orphaned message: mark it so nothing retries forever.
      tx.update(messageRef, { unreadAccountedAt: FieldValue.serverTimestamp() });
      return { applied: false, reason: "room_missing", recipients: [], alreadyRead: [] };
    }
    const room = (roomSnap.data() ?? {}) as Doc;
    const { increment, alreadyRead } = recipientsToIncrement({
      senderId: message.senderId,
      participantIds: room.participantIds,
      lastReadAt: room.lastReadAt,
      messageCommittedAt: messageCommitTime(messageSnap, message),
    });
    applyIncrements(tx, roomRef, increment);
    tx.update(messageRef, { unreadAccountedAt: FieldValue.serverTimestamp() });
    return {
      applied: increment.length > 0,
      reason: increment.length > 0 ? "applied" : "no_recipients",
      recipients: increment,
      alreadyRead,
    };
  });
}

/**
 * When the message was committed: the document's server-assigned create time
 * (unforgeable), falling back to its `createdAt` field only if the snapshot
 * carries no create time; null means "unknown" (every recipient counts).
 */
export function messageCommitTime(
  snap: { createTime?: Timestamp },
  message: Doc
): Timestamp | null {
  return snap.createTime ?? asTimestamp(message.createdAt);
}

function applyIncrements(
  tx: Transaction,
  roomRef: DocumentReference,
  recipients: string[],
  amounts?: Record<string, number>
): void {
  // Varargs form of update(): FieldPath keys never pass through dotted-string
  // parsing, and a nested object would REPLACE the whole unreadCounts map.
  const args: unknown[] = ["unreadModelVersion", UNREAD_MODEL_VERSION];
  for (const uid of recipients) {
    const amount = amounts ? amounts[uid] ?? 0 : 1;
    if (amount <= 0) continue;
    args.push(unreadCountPath(uid), FieldValue.increment(amount));
  }
  if (args.length === 2) return;
  (tx.update as unknown as (ref: DocumentReference, ...rest: unknown[]) => Transaction)(
    roomRef,
    ...args
  );
}

// -----------------------------------------------------------------------------
// Daily digest — O(active rooms), never reads a message document
// -----------------------------------------------------------------------------

export type DigestTarget = {
  unreadCount: number;
  previewSenderName: string | null;
  newestLastMessageAtMs: number;
};

export async function collectDailyUnreadDigest(
  db: Firestore,
  options: { pageSize?: number } = {}
): Promise<{ targets: Map<string, DigestTarget>; roomsScanned: number }> {
  const pageSize = options.pageSize ?? 300;
  const targets = new Map<string, DigestTarget>();
  let roomsScanned = 0;
  let cursor: FirebaseFirestore.QueryDocumentSnapshot | null = null;
  for (;;) {
    let query = db
      .collection("chat_rooms")
      .where("status", "==", "active")
      .orderBy(FieldPath.documentId())
      .limit(pageSize);
    if (cursor) query = query.startAfter(cursor);
    const page = await query.get();
    if (page.empty) break;
    for (const doc of page.docs) {
      roomsScanned += 1;
      const room = (doc.data() ?? {}) as Doc;
      const lastMessageAtMs =
        room.lastMessageAt instanceof Timestamp ? room.lastMessageAt.toMillis() : 0;
      for (const row of digestContributionsForRoom(room)) {
        const existing = targets.get(row.uid);
        if (!existing) {
          targets.set(row.uid, {
            unreadCount: row.unreadCount,
            previewSenderName: row.previewSenderName,
            newestLastMessageAtMs: lastMessageAtMs,
          });
          continue;
        }
        existing.unreadCount += row.unreadCount;
        if (lastMessageAtMs > existing.newestLastMessageAtMs) {
          existing.newestLastMessageAtMs = lastMessageAtMs;
          existing.previewSenderName = row.previewSenderName;
        }
      }
    }
    cursor = page.docs[page.docs.length - 1];
    if (page.size < pageSize) break;
  }
  return { targets, roomsScanned };
}

/** Deterministic per-user, per-day id: a retried run cannot notify twice. */
export function chatDigestNotificationId(digestDate: string): string {
  return `chat_digest_${digestDate}`;
}

// -----------------------------------------------------------------------------
// Backfill — legacy rooms get counts derived from readBy, exactly once
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
 * BACKFILL_MESSAGE_CHUNK messages per transaction. Messages the trigger
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
  const chunkSize = Math.min(options.chunkSize ?? BACKFILL_MESSAGE_CHUNK, BACKFILL_MESSAGE_CHUNK);
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
      if (recipients.length > 0) applyIncrements(tx, roomRef, recipients, increments);
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
// Post-backfill integrity check (read-only)
// -----------------------------------------------------------------------------

export type RoomIntegrityIssue = {
  roomId: string;
  issue:
    | "negative_count"
    | "count_for_non_participant"
    | "missing_model_version"
    | "non_integer_count";
  detail: string;
};

export function checkRoomUnreadIntegrity(roomId: string, roomData: Doc): RoomIntegrityIssue[] {
  const issues: RoomIntegrityIssue[] = [];
  const counts = isRecord(roomData.unreadCounts) ? roomData.unreadCounts : null;
  const participants = new Set(
    Array.isArray(roomData.participantIds)
      ? roomData.participantIds.filter((v): v is string => typeof v === "string")
      : []
  );
  if (counts) {
    for (const [uid, value] of Object.entries(counts)) {
      if (typeof value !== "number" || !Number.isInteger(value)) {
        issues.push({ roomId, issue: "non_integer_count", detail: uid });
      } else if (value < 0) {
        issues.push({ roomId, issue: "negative_count", detail: `${uid}=${value}` });
      }
      // A former participant (account deletion removes members from blind
      // rooms) may keep a stale key; only a positive count for a stranger is
      // an integrity issue.
      if (!participants.has(uid) && typeof value === "number" && value > 0) {
        issues.push({ roomId, issue: "count_for_non_participant", detail: uid });
      }
    }
    if (!roomHasUnreadModel(roomData)) {
      issues.push({ roomId, issue: "missing_model_version", detail: "" });
    }
  }
  return issues;
}

// -----------------------------------------------------------------------------
// Reconciliation — checks the invariant against the messages (offline tool)
// -----------------------------------------------------------------------------

export type RoomUnreadMismatch = {
  roomId: string;
  uid: string;
  actual: number;
  expected: number;
  kind: "over_count" | "under_count";
  /** `lastReadAt`: strict invariant; `readBy`: legacy rule (user never marked read on a new client). */
  basis: "lastReadAt" | "readBy";
  /** The `lastReadAt` the expectation was computed against (repair re-checks it). */
  lastReadAt: Timestamp | null;
  /** Counted messages that carry no accounting marker (their trigger is late or lost). */
  pendingMessageIds: string[];
};

export type RoomUnreadVerification = {
  roomId: string;
  mismatches: RoomUnreadMismatch[];
  /** Participants whose expectation could not be computed within `maxMessages`. */
  unverifiable: string[];
  messagesRead: number;
};

/**
 * Messages newer than `lastReadAt` minus this margin are fetched by their
 * `createdAt` field (the indexed proxy for the commit time — every writer
 * stamps it with the server time); the decision itself uses `createTime`.
 */
const RECONCILE_QUERY_MARGIN_MS = 5 * 60 * 1000;
export const RECONCILE_DEFAULT_GRACE_MS = 5 * 60 * 1000;
export const RECONCILE_DEFAULT_MAX_MESSAGES = 2000;

/**
 * Recomputes every participant's expected counter from the messages and
 * compares it with the room document. Read-only.
 *
 * - `basis: lastReadAt` — expected = messages (sender != uid) whose commit
 *   time is after `lastReadAt[uid]` (the invariant above).
 * - `basis: readBy` — the participant never marked the room read on a new
 *   client; expected = legacy rule (sender != uid and uid not in `readBy`).
 *   This also folds reads performed by OLD clients (which only write
 *   `readBy`) into the counter.
 *
 * A message committed within `graceMs` may still be in the trigger queue, so
 * an `under_count` is reported only when it already holds for the settled
 * messages (older than the grace window). An `over_count` is always definite.
 */
export async function verifyRoomUnreadCounts(
  db: Firestore,
  roomId: string,
  options: { graceMs?: number; maxMessages?: number; now?: Timestamp } = {}
): Promise<RoomUnreadVerification> {
  const graceMs = options.graceMs ?? RECONCILE_DEFAULT_GRACE_MS;
  const maxMessages = options.maxMessages ?? RECONCILE_DEFAULT_MAX_MESSAGES;
  const now = options.now ?? Timestamp.now();
  const settledBefore = Timestamp.fromMillis(now.toMillis() - graceMs);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const result: RoomUnreadVerification = { roomId, mismatches: [], unverifiable: [], messagesRead: 0 };
  const roomSnap = await roomRef.get();
  if (!roomSnap.exists) return result;
  const room = (roomSnap.data() ?? {}) as Doc;
  const participantIds = Array.isArray(room.participantIds)
    ? room.participantIds.filter((v): v is string => typeof v === "string" && v.length > 0)
    : [];
  const lastReadAtMap = isRecord(room.lastReadAt) ? room.lastReadAt : {};

  let legacyMessages: FirebaseFirestore.QueryDocumentSnapshot[] | null | undefined;
  const loadLegacyMessages = async () => {
    if (legacyMessages !== undefined) return legacyMessages;
    const page = await roomRef.collection("messages").orderBy("createdAt").limit(maxMessages + 1).get();
    result.messagesRead += page.size;
    legacyMessages = page.size > maxMessages ? null : page.docs;
    return legacyMessages;
  };

  for (const uid of participantIds) {
    const actual = unreadCountFor(room, uid);
    const readAt = asTimestamp(lastReadAtMap[uid]);
    let docs: FirebaseFirestore.QueryDocumentSnapshot[] | null;
    if (readAt) {
      const page = await roomRef
        .collection("messages")
        .where("createdAt", ">", Timestamp.fromMillis(readAt.toMillis() - RECONCILE_QUERY_MARGIN_MS))
        .orderBy("createdAt")
        .limit(maxMessages + 1)
        .get();
      result.messagesRead += page.size;
      docs = page.size > maxMessages ? null : page.docs;
    } else {
      docs = await loadLegacyMessages();
    }
    if (docs === null) {
      result.unverifiable.push(uid);
      continue;
    }
    let expected = 0;
    let expectedSettled = 0;
    const pendingMessageIds: string[] = [];
    for (const doc of docs) {
      const message = (doc.data() ?? {}) as Doc;
      const committedAt = messageCommitTime(doc, message);
      let counts: boolean;
      if (readAt) {
        counts =
          asNonEmptyString(message.senderId) !== null &&
          message.senderId !== uid &&
          (committedAt === null || !timestampAtOrAfter(readAt, committedAt));
      } else {
        counts = legacyMessageIsUnreadFor(message, uid);
      }
      if (!counts) continue;
      expected += 1;
      if (committedAt === null || !timestampAtOrAfter(committedAt, settledBefore)) expectedSettled += 1;
      if (message.unreadAccountedAt == null) pendingMessageIds.push(doc.id);
    }
    const basis = readAt ? "lastReadAt" : "readBy";
    if (actual > expected) {
      result.mismatches.push({ roomId, uid, actual, expected, kind: "over_count", basis, lastReadAt: readAt, pendingMessageIds });
    } else if (actual < expectedSettled) {
      result.mismatches.push({ roomId, uid, actual, expected, kind: "under_count", basis, lastReadAt: readAt, pendingMessageIds });
    }
  }
  return result;
}

export type RoomReconcileResult = RoomUnreadVerification & {
  /** Mismatches fixed (all of a room's mismatches are fixed together or not at all). */
  repaired: number;
  /** "changed": the room moved since verification (re-run); "too_many_pending": over the transaction budget. */
  skipped: "changed" | "too_many_pending" | null;
};

/**
 * Repairs the mismatches `verifyRoomUnreadCounts` reported, in ONE
 * transaction per room: it re-reads the room and every counted message that
 * had no accounting marker, aborts (skips the room, nothing written) if any
 * participant's `lastReadAt` or any marker changed since verification —
 * a mark-read or a late trigger landed and the expectation is stale — and
 * otherwise applies each delta and marks those messages accounted, so the
 * trigger that may still deliver for them cannot count them again. Dry run
 * performs the same verification and no writes.
 */
export async function reconcileRoomUnread(
  db: Firestore,
  roomId: string,
  options: { dryRun: boolean; graceMs?: number; maxMessages?: number; now?: Timestamp }
): Promise<RoomReconcileResult> {
  const verification = await verifyRoomUnreadCounts(db, roomId, options);
  const result: RoomReconcileResult = { ...verification, repaired: 0, skipped: null };
  if (options.dryRun || verification.mismatches.length === 0) return result;
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const pendingIds = new Set<string>();
  for (const m of verification.mismatches) for (const id of m.pendingMessageIds) pendingIds.add(id);
  if (pendingIds.size > BACKFILL_MESSAGE_CHUNK) {
    result.skipped = "too_many_pending";
    return result;
  }
  const outcome = await db.runTransaction(async (tx) => {
    const snap = await tx.get(roomRef);
    if (!snap.exists) return "changed" as const;
    const room = (snap.data() ?? {}) as Doc;
    const lastReadAtMap = isRecord(room.lastReadAt) ? room.lastReadAt : {};
    for (const m of verification.mismatches) {
      const current = asTimestamp(lastReadAtMap[m.uid]);
      const unchanged =
        (current === null && m.lastReadAt === null) ||
        (current !== null && m.lastReadAt !== null && current.isEqual(m.lastReadAt));
      if (!unchanged) return "changed" as const;
      if (unreadCountFor(room, m.uid) !== m.actual) return "changed" as const;
    }
    const pendingRefs = [...pendingIds].map((id) => roomRef.collection("messages").doc(id));
    const pendingSnaps = await Promise.all(pendingRefs.map((ref) => tx.get(ref)));
    for (const p of pendingSnaps) {
      if (!p.exists || (p.data() ?? {}).unreadAccountedAt != null) return "changed" as const;
    }
    const args: unknown[] = ["unreadModelVersion", UNREAD_MODEL_VERSION];
    for (const m of verification.mismatches) {
      const delta = m.expected - m.actual;
      if (delta !== 0) args.push(unreadCountPath(m.uid), FieldValue.increment(delta));
    }
    (tx.update as unknown as (ref: DocumentReference, ...rest: unknown[]) => Transaction)(roomRef, ...args);
    for (const ref of pendingRefs) {
      tx.update(ref, { unreadAccountedAt: FieldValue.serverTimestamp(), unreadReconciled: true });
    }
    return "repaired" as const;
  });
  if (outcome === "repaired") result.repaired = verification.mismatches.length;
  else result.skipped = outcome;
  return result;
}
