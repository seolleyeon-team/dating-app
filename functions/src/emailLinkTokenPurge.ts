/**
 * Purge expired, mailbox-unproven emailLinkTokens.
 * Safe criterion: expiresAt < now AND no emailVerifiedUid.
 */

import { type Firestore } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";
import { onSchedule } from "firebase-functions/v2/scheduler";

export function shouldPurgeEmailLinkToken(doc: {
  expiresAt?: { toDate?: () => Date } | Date | string | null;
  emailVerifiedUid?: unknown;
  now?: Date;
}): boolean {
  if (doc.emailVerifiedUid) return false;
  const now = doc.now ?? new Date();
  const raw = doc.expiresAt;
  let expires: Date | null = null;
  if (raw instanceof Date) expires = raw;
  else if (raw && typeof raw === "object" && typeof raw.toDate === "function") {
    expires = raw.toDate();
  } else if (typeof raw === "string" && raw.trim()) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) expires = parsed;
  }
  if (!expires) return false;
  return expires.getTime() < now.getTime();
}

export function selectEmailLinkTokenIdsToPurge(
  docs: Array<{
    id: string;
    expiresAt?: { toDate?: () => Date } | Date | string | null;
    emailVerifiedUid?: unknown;
  }>,
  now = new Date()
): string[] {
  return docs
    .filter((doc) =>
      shouldPurgeEmailLinkToken({
        expiresAt: doc.expiresAt,
        emailVerifiedUid: doc.emailVerifiedUid,
        now,
      })
    )
    .map((doc) => doc.id);
}

export async function purgeExpiredEmailLinkTokens(
  firestore: Firestore,
  options: { limit?: number; now?: Date } = {}
): Promise<{ scanned: number; deleted: number; skipped: number }> {
  const limit = options.limit ?? 500;
  const now = options.now ?? new Date();
  const snap = await firestore.collection("emailLinkTokens").limit(limit).get();
  const candidates = selectEmailLinkTokenIdsToPurge(
    snap.docs.map((doc) => ({
      id: doc.id,
      expiresAt: doc.data()?.expiresAt ?? null,
      emailVerifiedUid: doc.data()?.emailVerifiedUid,
    })),
    now
  );

  let deleted = 0;
  // Firestore batch max 500.
  for (let i = 0; i < candidates.length; i += 400) {
    const chunk = candidates.slice(i, i + 400);
    const batch = firestore.batch();
    for (const id of chunk) {
      batch.delete(firestore.collection("emailLinkTokens").doc(id));
    }
    await batch.commit();
    deleted += chunk.length;
  }

  return {
    scanned: snap.size,
    deleted,
    skipped: snap.size - deleted,
  };
}

export function createPurgeExpiredEmailLinkTokensSchedule(firestore: Firestore) {
  return onSchedule(
    {
      schedule: "15 4 * * *",
      timeZone: "Asia/Seoul",
      region: "asia-northeast3",
      cpu: "gcf_gen1",
      concurrency: 1,
      maxInstances: 1,
    },
    async () => {
      const result = await purgeExpiredEmailLinkTokens(firestore, { limit: 500 });
      logger.info("purgeExpiredEmailLinkTokens completed", result);
    }
  );
}
