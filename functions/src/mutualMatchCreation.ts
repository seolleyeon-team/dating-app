/**
 * Authoritative mutual-match creation (P1-1).
 *
 * One pair of users has at most one logical match. Both triggers that can
 * form a match — `onInteractionCreated` (interactions like/super_like) and
 * `onRecEventCreated` (recEvents like/swipe_right) — call `ensureMutualMatch`
 * and nothing else creates `matches/*` documents.
 *
 * Everything that decides whether a match may exist is read inside ONE
 * Firestore transaction, before any write:
 *
 *   - the deterministic match document `match_<a>_<b>` (sorted uids),
 *   - every legacy random-id match that already names both users,
 *   - the reverse like (so two simultaneous mutual likes cannot both commit),
 *   - both block directions,
 *   - the direct room `dm_<a>_<b>`.
 *
 * Decisions:
 *   - any block in either direction      → no match, no room, nothing written;
 *   - no reverse like                     → nothing written;
 *   - an existing match that is not active (unmatched / ended) → nothing
 *     written: a closed room is never reopened and rematching is not an
 *     implicit side effect of a repeated like;
 *   - an existing active match            → nothing new is created. If the
 *     caller asked for a chat room and the active match has none yet (the
 *     recEvents path creates room-less matches) and no direct room exists,
 *     the room is attached to that match;
 *   - otherwise the canonical match is created. A pre-existing direct room
 *     (paid direct chat) is linked by `matchId` only — its status,
 *     participants and participant metadata are never overwritten and no
 *     system message is posted into it.
 */
import {
  FieldValue,
  type DocumentReference,
  type DocumentSnapshot,
  type Firestore,
  type Query,
  type Transaction,
} from "firebase-admin/firestore";

import { buildDeterministicMatchId, buildDirectRoomId } from "./matchIdentity";

export type MutualMatchParticipantInfo = Record<
  string,
  { nickname: string; avatarUrl: string | null }
>;

export type MutualMatchReverseLikeSource = "interactions" | "recEvents";

export type EnsureMutualMatchParams = {
  userA: string;
  userB: string;
  matchType: string;
  /** Partition of both users (validated by the caller). */
  dataPartition: "production" | "play_review";
  /**
   * Where the reverse like is looked up. The query runs inside the
   * transaction so a concurrent mutual like is serialised against it.
   */
  reverseLikeSource: MutualMatchReverseLikeSource;
  chatRoom?: {
    participantInfo: MutualMatchParticipantInfo;
    systemMessage: string;
  };
};

export type EnsureMutualMatchOutcome =
  | "blocked"
  | "no_reverse_like"
  | "existing_inactive"
  | "existing_active"
  | "room_attached"
  | "created";

export type EnsureMutualMatchResult = {
  outcome: EnsureMutualMatchOutcome;
  matchId: string | null;
  roomId: string | null;
  /** True only when this call created the match document. */
  created: boolean;
  /** True only when this call created the chat room (and its system message). */
  roomCreated: boolean;
};

const LIKE_ACTIONS = ["like", "super_like"];
const REC_LIKE_EVENT_TYPES = ["like", "swipe_right"];

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function userIdsOf(data: Record<string, unknown> | undefined): string[] {
  const raw = data?.userIds;
  return Array.isArray(raw) ? raw.map(asString).filter((v) => v.length > 0) : [];
}

function reverseLikeQuery(
  db: Firestore,
  source: MutualMatchReverseLikeSource,
  liker: string,
  target: string
): Query {
  if (source === "recEvents") {
    return db
      .collectionGroup("events")
      .where("userId", "==", liker)
      .where("targetUserId", "==", target)
      .where("eventType", "in", REC_LIKE_EVENT_TYPES)
      .limit(1);
  }
  return db
    .collection("interactions")
    .where("fromUserId", "==", liker)
    .where("toUserId", "==", target)
    .where("action", "in", LIKE_ACTIONS)
    .limit(1);
}

/** Both block directions, read inside the transaction. */
export async function readBlockPair(
  db: Firestore,
  tx: Transaction,
  userA: string,
  userB: string
): Promise<{ blocked: boolean }> {
  const [forward, reverse] = await Promise.all([
    tx.get(db.collection("blocks").doc(userA).collection("targets").doc(userB)),
    tx.get(db.collection("blocks").doc(userB).collection("targets").doc(userA)),
  ]);
  return { blocked: forward.exists || reverse.exists };
}

/** Non-transactional variant for notification gating. */
export async function isBlockedEitherWay(
  db: Firestore,
  userA: string,
  userB: string
): Promise<boolean> {
  const [forward, reverse] = await Promise.all([
    db.collection("blocks").doc(userA).collection("targets").doc(userB).get(),
    db.collection("blocks").doc(userB).collection("targets").doc(userA).get(),
  ]);
  return forward.exists || reverse.exists;
}

function createRoomWithSystemMessage(
  tx: Transaction,
  roomRef: DocumentReference,
  params: {
    roomId: string;
    matchId: string;
    userA: string;
    userB: string;
    dataPartition: string;
    participantInfo: MutualMatchParticipantInfo;
    systemMessage: string;
  }
): void {
  const now = FieldValue.serverTimestamp();
  tx.set(roomRef, {
    roomId: params.roomId,
    type: "one_to_one",
    status: "active",
    participantIds: [params.userA, params.userB],
    participantInfo: params.participantInfo,
    matchId: params.matchId,
    createdAt: now,
    updatedAt: now,
    lastMessage: params.systemMessage,
    lastMessageAt: now,
    dataPartition: params.dataPartition,
  });
  // Deterministic id: a retried transaction or a redelivered event can never
  // post the welcome message twice.
  tx.set(roomRef.collection("messages").doc(`system_match_${params.matchId}`), {
    senderId: "system",
    text: params.systemMessage,
    content: params.systemMessage,
    type: "system",
    createdAt: now,
    dataPartition: params.dataPartition,
  });
}

export async function ensureMutualMatch(
  db: Firestore,
  params: EnsureMutualMatchParams
): Promise<EnsureMutualMatchResult> {
  const matchId = buildDeterministicMatchId(params.userA, params.userB);
  const roomId = buildDirectRoomId(params.userA, params.userB);
  const canonicalRef = db.collection("matches").doc(matchId);
  const roomRef = db.collection("chat_rooms").doc(roomId);

  return db.runTransaction(async (tx) => {
    // ---- reads (all before any write) ---------------------------------
    const [canonicalSnap, legacySnap, reverseSnap, blocks, roomSnap] =
      await Promise.all([
        tx.get(canonicalRef),
        tx.get(
          db.collection("matches").where("userIds", "array-contains", params.userA)
        ),
        tx.get(
          reverseLikeQuery(db, params.reverseLikeSource, params.userB, params.userA)
        ),
        readBlockPair(db, tx, params.userA, params.userB),
        tx.get(roomRef),
      ]);

    if (blocks.blocked) {
      return { outcome: "blocked", matchId: null, roomId: null, created: false, roomCreated: false };
    }
    if (reverseSnap.empty) {
      return { outcome: "no_reverse_like", matchId: null, roomId: null, created: false, roomCreated: false };
    }

    // The canonical document wins; otherwise the oldest legacy match that
    // names both users (a second canonical match is never created beside it).
    let existing: DocumentSnapshot | null = canonicalSnap.exists ? canonicalSnap : null;
    if (!existing) {
      const legacy = legacySnap.docs
        .filter((doc) => doc.id !== matchId && userIdsOf(doc.data()).includes(params.userB))
        .sort((a, b) => a.id.localeCompare(b.id));
      existing = legacy[0] ?? null;
    }

    if (existing) {
      const data = (existing.data() ?? {}) as Record<string, unknown>;
      if (asString(data.status) !== "active") {
        return { outcome: "existing_inactive", matchId: existing.id, roomId: asString(data.chatRoomId) || null, created: false, roomCreated: false };
      }
      const existingRoomId = asString(data.chatRoomId);
      if (params.chatRoom && !existingRoomId && !roomSnap.exists) {
        createRoomWithSystemMessage(tx, roomRef, {
          roomId,
          matchId: existing.id,
          userA: params.userA,
          userB: params.userB,
          dataPartition: params.dataPartition,
          participantInfo: params.chatRoom.participantInfo,
          systemMessage: params.chatRoom.systemMessage,
        });
        tx.set(existing.ref, { chatRoomId: roomId, updatedAt: FieldValue.serverTimestamp() }, { merge: true });
        return { outcome: "room_attached", matchId: existing.id, roomId, created: false, roomCreated: true };
      }
      return { outcome: "existing_active", matchId: existing.id, roomId: existingRoomId || null, created: false, roomCreated: false };
    }

    // ---- writes -------------------------------------------------------
    const wantsRoom = params.chatRoom !== undefined;
    tx.create(canonicalRef, {
      userIds: [params.userA, params.userB],
      matchType: params.matchType,
      matchedAt: FieldValue.serverTimestamp(),
      status: "active",
      chatRoomId: wantsRoom ? roomId : null,
      dataPartition: params.dataPartition,
    });

    let roomCreated = false;
    if (params.chatRoom) {
      if (roomSnap.exists) {
        // A direct room already exists (e.g. paid direct chat). Link it but
        // never touch its lifecycle state or participant metadata.
        const roomData = (roomSnap.data() ?? {}) as Record<string, unknown>;
        if (!asString(roomData.matchId)) {
          tx.set(roomRef, { matchId, updatedAt: FieldValue.serverTimestamp() }, { merge: true });
        }
      } else {
        createRoomWithSystemMessage(tx, roomRef, {
          roomId,
          matchId,
          userA: params.userA,
          userB: params.userB,
          dataPartition: params.dataPartition,
          participantInfo: params.chatRoom.participantInfo,
          systemMessage: params.chatRoom.systemMessage,
        });
        roomCreated = true;
      }
    }

    return { outcome: "created", matchId, roomId: wantsRoom ? roomId : null, created: true, roomCreated };
  });
}
