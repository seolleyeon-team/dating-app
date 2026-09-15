import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import { assertSafeMemberText } from "./contentSafety";

type AppUser = { userId: string; data?: Record<string, unknown> };
type ResolveUser = (request: CallableRequest<unknown>) => Promise<AppUser>;

function requestData(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function roomId(value: unknown): string {
  const id = typeof value === "string" ? value.trim() : "";
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(id)) {
    throw new HttpsError("invalid-argument", "roomId is invalid.");
  }
  return id;
}

export function createSendChatTextFunction(firestore: Firestore, resolveUser: ResolveUser) {
  return onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
    const user = await resolveUser(request);
    const input = requestData(request.data);
    const id = roomId(input.roomId);
    const text = assertSafeMemberText(input.text, "text", 1000);
    const roomRef = firestore.collection("chat_rooms").doc(id);
    const room = await roomRef.get();
    if (!room.exists) throw new HttpsError("not-found", "채팅방을 찾을 수 없어요.");
    const participants = Array.isArray(room.get("participantIds"))
      ? room.get("participantIds").filter((value: unknown): value is string => typeof value === "string")
      : [];
    if (!participants.includes(user.userId)) {
      throw new HttpsError("permission-denied", "채팅방에 입장할 수 없어요.");
    }
    if (room.get("type") === "one_to_one" && participants.length === 2) {
      const peerId = participants.find((candidate: string) => candidate !== user.userId);
      if (!peerId) throw new HttpsError("permission-denied", "채팅 상대를 확인할 수 없어요.");
      const [forward, reverse] = await Promise.all([
        firestore.collection("blocks").doc(user.userId).collection("targets").doc(peerId).get(),
        firestore.collection("blocks").doc(peerId).collection("targets").doc(user.userId).get(),
      ]);
      if (forward.exists || reverse.exists) {
        throw new HttpsError("permission-denied", "차단된 사용자와는 메시지를 보낼 수 없어요.");
      }
    }
    const messageRef = roomRef.collection("messages").doc();
    const now = FieldValue.serverTimestamp();
    await firestore.runTransaction(async (transaction) => {
      transaction.set(messageRef, {
        senderId: user.userId, text, type: "text", readBy: [user.userId],
        createdAt: now, updatedAt: now,
      });
      transaction.set(roomRef, {
        lastMessage: text, lastMessageAt: now, photoBlurUnlocked: true,
        photoBlurUnlockedAt: now, photoBlurUnlockedBy: user.userId, updatedAt: now,
      }, { merge: true });
    });
    return { messageId: messageRef.id };
  });
}
