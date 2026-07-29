import {
  FieldValue,
  type Firestore,
} from "firebase-admin/firestore";

import {
  buildDeterministicMatchId,
  buildDirectRoomId,
} from "./matchIdentity";

export type MutualMatchParticipantInfo = Record<
  string,
  { nickname: string; avatarUrl: string | null }
>;

export type EnsureMutualMatchParams = {
  userA: string;
  userB: string;
  matchType: string;
  chatRoom?: {
    participantInfo: MutualMatchParticipantInfo;
    systemMessage: string;
  };
};

export type EnsureMutualMatchResult = {
  matchId: string;
  roomId: string | null;
  created: boolean;
};

export async function ensureMutualMatch(
  db: Firestore,
  params: EnsureMutualMatchParams
): Promise<EnsureMutualMatchResult> {
  const matchId = buildDeterministicMatchId(params.userA, params.userB);
  const roomId = params.chatRoom
    ? buildDirectRoomId(params.userA, params.userB)
    : null;

  const matchRef = db.collection("matches").doc(matchId);
  const roomRef = roomId ? db.collection("chat_rooms").doc(roomId) : null;

  return db.runTransaction(async (tx) => {
    const existingMatch = await tx.get(matchRef);
    const existingRoom =
      roomRef && params.chatRoom ? await tx.get(roomRef) : null;

    if (existingMatch.exists) {
      return { matchId, roomId, created: false };
    }

    tx.create(matchRef, {
      userIds: [params.userA, params.userB],
      matchType: params.matchType,
      matchedAt: FieldValue.serverTimestamp(),
      status: "active",
      chatRoomId: roomId,
    });

    if (roomRef && params.chatRoom) {
      if (existingRoom?.exists) {
        tx.set(roomRef, { matchId }, { merge: true });
      } else {
        tx.set(roomRef, {
          roomId,
          type: "one_to_one",
          status: "active",
          participantIds: [params.userA, params.userB],
          participantInfo: params.chatRoom.participantInfo,
          matchId,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
          lastMessage: params.chatRoom.systemMessage,
          lastMessageAt: FieldValue.serverTimestamp(),
        });

        const msgRef = roomRef.collection("messages").doc();
        tx.set(msgRef, {
          senderId: "system",
          text: params.chatRoom.systemMessage,
          content: params.chatRoom.systemMessage,
          type: "system",
          createdAt: FieldValue.serverTimestamp(),
          readBy: [],
        });
      }
    }

    return { matchId, roomId, created: true };
  });
}
