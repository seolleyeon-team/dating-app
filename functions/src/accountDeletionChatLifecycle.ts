/**
 * Account-deletion chat message lifecycle.
 *
 * Policy (configurable, dating-app safe default):
 * - Message bodies retained for dispute / safety evidence during retention window
 * - Author identifiers anonymized immediately
 * - Display name forced to DELETED_USER_DISPLAY_NAME
 * - Attachment / media URL fields cleared immediately
 * - After retention (no legal hold): body redacted and sensitive metadata purged
 */

import { createHash } from "node:crypto";
import {
  FieldValue,
  type Firestore,
  type QueryDocumentSnapshot,
} from "firebase-admin/firestore";

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";

export { DELETED_USER_DISPLAY_NAME };

/** Default retention for deleted-author message bodies (days). */
export const DEFAULT_DELETED_MESSAGE_RETENTION_DAYS = 90;

/** Firestore fields treated as attachment / media pointers. */
export const CHAT_MEDIA_FIELD_KEYS = [
  "imageUrl",
  "photoUrl",
  "mediaUrl",
  "attachmentUrl",
  "attachmentUrls",
  "storagePath",
  "storagePaths",
  "gsPath",
  "downloadUrl",
  "thumbnailUrl",
  "fileUrl",
] as const;

export type ChatMessageAnonymizePlan = {
  roomId: string;
  messageId: string;
  anonymizedSenderId: string;
  clearMedia: boolean;
};

export type ChatMessagePurgePlan = {
  roomId: string;
  messageId: string;
};

export function buildAnonymizedSenderId(uid: string): string {
  const digest = createHash("sha256")
    .update(`seolleyeon:deleted:${uid}`)
    .digest("hex");
  return `deleted_${digest.slice(0, 16)}`;
}

export function buildDeletedMessageAnonymizePatch(params: {
  uid: string;
  retentionDays?: number;
}): Record<string, unknown> {
  const retentionDays =
    params.retentionDays ?? DEFAULT_DELETED_MESSAGE_RETENTION_DAYS;
  const purgeAfterMs = Date.now() + retentionDays * 24 * 60 * 60 * 1000;
  const mediaClears: Record<string, unknown> = {};
  for (const key of CHAT_MEDIA_FIELD_KEYS) {
    mediaClears[key] = FieldValue.delete();
  }
  return {
    authorDeleted: true,
    authorDeletedAt: FieldValue.serverTimestamp(),
    senderId: buildAnonymizedSenderId(params.uid),
    senderDisplayName: DELETED_USER_DISPLAY_NAME,
    displayName: DELETED_USER_DISPLAY_NAME,
    nickname: DELETED_USER_DISPLAY_NAME,
    avatarUrl: null,
    senderAvatarUrl: null,
    purgeAfter: new Date(purgeAfterMs),
    legalHold: false,
    ...mediaClears,
  };
}

export function buildDeletedMessagePurgePatch(): Record<string, unknown> {
  return {
    text: "[삭제된 메시지]",
    content: "[삭제된 메시지]",
    purgedAt: FieldValue.serverTimestamp(),
    purgedReason: "retention_elapsed",
  };
}

export function shouldPurgeDeletedAuthorMessage(doc: {
  authorDeleted?: unknown;
  legalHold?: unknown;
  purgeAfter?: { toDate?: () => Date } | Date | string | null;
  purgedAt?: unknown;
  now?: Date;
}): boolean {
  if (doc.purgedAt) return false;
  if (doc.authorDeleted !== true) return false;
  if (doc.legalHold === true) return false;
  const now = doc.now ?? new Date();
  const raw = doc.purgeAfter;
  let purgeAfter: Date | null = null;
  if (raw instanceof Date) purgeAfter = raw;
  else if (raw && typeof raw === "object" && typeof raw.toDate === "function") {
    purgeAfter = raw.toDate();
  } else if (typeof raw === "string" && raw.trim()) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) purgeAfter = parsed;
  }
  if (!purgeAfter) return false;
  return purgeAfter.getTime() <= now.getTime();
}

export async function anonymizeChatMessagesForDeletedUser(
  firestore: Firestore,
  params: {
    uid: string;
    roomId: string;
    pageSize?: number;
    dryRun?: boolean;
  }
): Promise<{ scanned: number; anonymized: number }> {
  const pageSize = params.pageSize ?? 200;
  let scanned = 0;
  let anonymized = 0;
  let lastDoc: QueryDocumentSnapshot | undefined;

  for (;;) {
    let query = firestore
      .collection("chat_rooms")
      .doc(params.roomId)
      .collection("messages")
      .where("senderId", "==", params.uid)
      .orderBy("__name__")
      .limit(pageSize);
    if (lastDoc) query = query.startAfter(lastDoc);
    const snap = await query.get();
    if (snap.empty) break;
    scanned += snap.size;
    lastDoc = snap.docs[snap.docs.length - 1];

    const targets = snap.docs.filter(
      (doc) => doc.data()?.authorDeleted !== true
    );
    if (targets.length > 0) {
      if (!params.dryRun) {
        const batch = firestore.batch();
        const patch = buildDeletedMessageAnonymizePatch({ uid: params.uid });
        for (const doc of targets) {
          batch.set(doc.ref, patch, { merge: true });
        }
        await batch.commit();
      }
      anonymized += targets.length;
    }
    if (snap.size < pageSize) break;
  }

  return { scanned, anonymized };
}

export async function purgeExpiredDeletedAuthorMessages(
  firestore: Firestore,
  options: { limit?: number; now?: Date; dryRun?: boolean } = {}
): Promise<{ scanned: number; purged: number; skipped: number }> {
  const limit = options.limit ?? 300;
  const now = options.now ?? new Date();
  const snap = await firestore
    .collectionGroup("messages")
    .where("authorDeleted", "==", true)
    .where("legalHold", "==", false)
    .where("purgeAfter", "<=", now)
    .limit(limit)
    .get();

  let purged = 0;
  const candidates = snap.docs.filter((doc) =>
    shouldPurgeDeletedAuthorMessage({
      authorDeleted: doc.data()?.authorDeleted,
      legalHold: doc.data()?.legalHold,
      purgeAfter: doc.data()?.purgeAfter ?? null,
      purgedAt: doc.data()?.purgedAt,
      now,
    })
  );

  if (!options.dryRun) {
    for (let i = 0; i < candidates.length; i += 400) {
      const chunk = candidates.slice(i, i + 400);
      const batch = firestore.batch();
      const patch = buildDeletedMessagePurgePatch();
      for (const doc of chunk) {
        batch.set(doc.ref, patch, { merge: true });
      }
      await batch.commit();
      purged += chunk.length;
    }
  } else {
    purged = candidates.length;
  }

  return {
    scanned: snap.size,
    purged,
    skipped: snap.size - purged,
  };
}
