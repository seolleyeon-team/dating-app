/**
 * sendChatText — the only way a client puts free text into a chat room.
 *
 * P1-2: every decision that authorises the send is made INSIDE the message
 * transaction, on the room document as it is at commit time:
 *
 *   - the caller is an active account (resolveUser) in the room's partition;
 *   - the caller is a current participant (`participantIds`, server-owned);
 *   - the room is in a sendable lifecycle state: `status` absent or "active"
 *     and `writable` absent or true. closed (unmatch / account deletion),
 *     read_only and archived (blind meeting lifecycle) rooms refuse;
 *   - no block exists in either direction between the two members of a
 *     two-person room — whatever `type` / `roomType` the document carries,
 *     so a client-mutated discriminator cannot bypass the check;
 *   - `clientMessageId` (optional, sender-scoped) makes the write idempotent:
 *     a timeout followed by a retry addresses the same message document and
 *     returns the existing id instead of creating a second message. Two
 *     distinct sends with identical text and different ids are two messages.
 */
import { createHash } from "node:crypto";

import { FieldValue, type Firestore, type Transaction } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";

import { assertSafeMemberText } from "./contentSafety";
import { dataPartitionOf } from "./playReviewAccess";

type AppUser = { userId: string; data?: Record<string, unknown> };
type ResolveUser = (request: CallableRequest<unknown>) => Promise<AppUser>;

export const CHAT_TEXT_MAX_LENGTH = 1000;
export const CLIENT_MESSAGE_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

/** Room lifecycle states in which a participant may still send. */
export const SENDABLE_ROOM_STATUSES: ReadonlySet<string> = new Set(["active"]);

export type SendDenial = {
  code: "not-found" | "permission-denied" | "failed-precondition";
  message: string;
};

function requestData(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function parseRoomId(value: unknown): string {
  const id = typeof value === "string" ? value.trim() : "";
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(id)) {
    throw new HttpsError("invalid-argument", "roomId is invalid.");
  }
  return id;
}

/** Optional sender-scoped idempotency key; absent means "always a new message". */
export function parseClientMessageId(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const id = typeof value === "string" ? value.trim() : "";
  if (!CLIENT_MESSAGE_ID_PATTERN.test(id)) {
    throw new HttpsError("invalid-argument", "clientMessageId is invalid.");
  }
  return id;
}

/** Deterministic message document id for (room, sender, clientMessageId). */
export function buildClientMessageDocId(roomId: string, senderId: string, clientMessageId: string): string {
  return "c_" + createHash("sha256").update(`${roomId}\u0000${senderId}\u0000${clientMessageId}`).digest("hex").slice(0, 40);
}

export function participantIdsOf(room: Record<string, unknown> | undefined): string[] {
  const raw = room?.participantIds;
  return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === "string" && v.length > 0) : [];
}

/** Whether the room's lifecycle state still accepts messages (pure). */
export function isRoomSendable(room: Record<string, unknown>): boolean {
  const status = typeof room.status === "string" ? room.status : "active";
  if (!SENDABLE_ROOM_STATUSES.has(status)) return false;
  if (room.writable === false) return false;
  return true;
}

/**
 * Pure authorisation decision over a room snapshot (pre-read values only).
 * `blocked` is the block state the caller read inside the same transaction.
 */
export function evaluateSendAuthorization(params: {
  room: Record<string, unknown> | undefined;
  roomExists: boolean;
  user: AppUser;
  blocked: boolean;
}): SendDenial | null {
  if (!params.roomExists || !params.room) {
    return { code: "not-found", message: "채팅방을 찾을 수 없어요." };
  }
  const room = params.room;
  const participants = participantIdsOf(room);
  if (!participants.includes(params.user.userId)) {
    return { code: "permission-denied", message: "채팅방에 입장할 수 없어요." };
  }
  const userPartition = dataPartitionOf(params.user.data ?? {});
  const roomPartition = dataPartitionOf(room);
  if (userPartition === "invalid" || roomPartition === "invalid" || userPartition !== roomPartition) {
    return { code: "permission-denied", message: "채팅방에 입장할 수 없어요." };
  }
  if (!isRoomSendable(room)) {
    return { code: "failed-precondition", message: "종료된 채팅방에는 메시지를 보낼 수 없어요." };
  }
  if (params.blocked) {
    return { code: "permission-denied", message: "차단된 사용자와는 메시지를 보낼 수 없어요." };
  }
  return null;
}

/** The peer of a two-person room, or null for group rooms. */
export function peerOf(room: Record<string, unknown>, userId: string): string | null {
  const participants = participantIdsOf(room);
  if (participants.length !== 2 || !participants.includes(userId)) return null;
  return participants.find((candidate) => candidate !== userId) ?? null;
}

async function readBlockedInTransaction(
  firestore: Firestore,
  tx: Transaction,
  userId: string,
  peerId: string | null
): Promise<boolean> {
  if (!peerId) return false;
  const [forward, reverse] = await Promise.all([
    tx.get(firestore.collection("blocks").doc(userId).collection("targets").doc(peerId)),
    tx.get(firestore.collection("blocks").doc(peerId).collection("targets").doc(userId)),
  ]);
  return forward.exists || reverse.exists;
}

export type SendChatTextResult = { messageId: string; deduplicated: boolean };

/** Transactional core, shared by the callable and the emulator tests. */
export async function sendChatTextCore(
  firestore: Firestore,
  user: AppUser,
  input: { roomId: string; text: string; clientMessageId: string | null }
): Promise<SendChatTextResult> {
  const roomRef = firestore.collection("chat_rooms").doc(input.roomId);
  const messageRef = input.clientMessageId
    ? roomRef.collection("messages").doc(buildClientMessageDocId(input.roomId, user.userId, input.clientMessageId))
    : roomRef.collection("messages").doc();

  return firestore.runTransaction(async (transaction) => {
    // ---- reads ----------------------------------------------------------
    const [roomSnap, existingMessage] = await Promise.all([
      transaction.get(roomRef),
      input.clientMessageId ? transaction.get(messageRef) : Promise.resolve(null),
    ]);
    const room = (roomSnap.data() ?? {}) as Record<string, unknown>;
    const blocked = roomSnap.exists
      ? await readBlockedInTransaction(firestore, transaction, user.userId, peerOf(room, user.userId))
      : false;

    // ---- decide ---------------------------------------------------------
    const denial = evaluateSendAuthorization({ room, roomExists: roomSnap.exists, user, blocked });
    if (denial) throw new HttpsError(denial.code, denial.message);

    if (existingMessage?.exists) {
      // Same sender, same clientMessageId: the earlier attempt committed.
      if (existingMessage.get("senderId") !== user.userId) {
        throw new HttpsError("already-exists", "메시지를 보낼 수 없어요.");
      }
      return { messageId: messageRef.id, deduplicated: true };
    }

    // ---- writes ---------------------------------------------------------
    const now = FieldValue.serverTimestamp();
    transaction.set(messageRef, {
      senderId: user.userId,
      text: input.text,
      type: "text",
      ...(input.clientMessageId ? { clientMessageId: input.clientMessageId } : {}),
      createdAt: now,
      updatedAt: now,
    });
    transaction.set(roomRef, {
      lastMessage: input.text, lastMessageAt: now, photoBlurUnlocked: true,
      photoBlurUnlockedAt: now, photoBlurUnlockedBy: user.userId, updatedAt: now,
    }, { merge: true });
    return { messageId: messageRef.id, deduplicated: false };
  });
}

export function createSendChatTextFunction(firestore: Firestore, resolveUser: ResolveUser) {
  return onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
    const user = await resolveUser(request);
    const input = requestData(request.data);
    const roomId = parseRoomId(input.roomId);
    const clientMessageId = parseClientMessageId(input.clientMessageId);
    const text = assertSafeMemberText(input.text, "text", CHAT_TEXT_MAX_LENGTH);
    return sendChatTextCore(firestore, user, { roomId, text, clientMessageId });
  });
}
