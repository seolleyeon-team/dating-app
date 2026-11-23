/**
 * Purge expired, mailbox-unproven emailLinkTokens.
 * Safe criterion: expiresAt < now AND no emailVerifiedUid.
 */

import { FieldPath, Timestamp, type Firestore } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";
import { onSchedule } from "firebase-functions/v2/scheduler";

import { SCHEDULER_CHECKPOINT_COLLECTION } from "./goodbyeAutoCompleteSweep";

export const EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID = "purgeExpiredEmailLinkTokens";

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

export type EmailLinkTokenPurgeResult = {
  scanned: number;
  deleted: number;
  skipped: number;
  pages: number;
  /** true when the run reached the end of the collection. */
  exhausted: boolean;
};

const DEFAULT_PAGE_SIZE = 500;
const DEFAULT_TIME_BUDGET_MS = 240_000;
const DEFAULT_MAX_DOCS = 200_000;

/**
 * AUD-25: this used to read `limit(500)` with no ordering and no cursor, i.e.
 * the same first 500 document ids every night. Tokens that are kept on purpose
 * (mailbox-proven ones are never purged, unexpired ones not yet) fill that
 * window over time, and from then on no expired token behind it was ever
 * deleted.
 *
 * Now the whole collection is walked in document-id pages until it ends or
 * the time/work budget is spent. An interrupted run stores the last id it
 * handled and the next run continues from there, so a collection larger than
 * one run's budget is still covered across runs. Paging by document id needs
 * no index and does not depend on the type `expiresAt` was stored with.
 */
export async function purgeExpiredEmailLinkTokens(
  firestore: Firestore,
  options: {
    /** Page size (documents read per query). */
    limit?: number;
    now?: Date;
    timeBudgetMs?: number;
    maxDocs?: number;
    nowMs?: () => number;
  } = {}
): Promise<EmailLinkTokenPurgeResult> {
  const pageSize = Math.max(1, options.limit ?? DEFAULT_PAGE_SIZE);
  const now = options.now ?? new Date();
  const nowMs = options.nowMs ?? (() => Date.now());
  const timeBudgetMs = options.timeBudgetMs ?? DEFAULT_TIME_BUDGET_MS;
  const maxDocs = Math.max(1, options.maxDocs ?? DEFAULT_MAX_DOCS);
  const startedAt = nowMs();
  const tokens = firestore.collection("emailLinkTokens");
  const checkpointRef = firestore
    .collection(SCHEDULER_CHECKPOINT_COLLECTION)
    .doc(EMAIL_LINK_TOKEN_PURGE_CHECKPOINT_ID);

  const storedCursor = (await checkpointRef.get()).get("cursor");
  let cursor: string | null =
    typeof storedCursor === "string" && storedCursor.length > 0 ? storedCursor : null;

  const result: EmailLinkTokenPurgeResult = {
    scanned: 0,
    deleted: 0,
    skipped: 0,
    pages: 0,
    exhausted: false,
  };

  for (;;) {
    let query = tokens.orderBy(FieldPath.documentId()).limit(pageSize);
    if (cursor) query = query.startAfter(cursor);
    const snap = await query.get();
    if (snap.empty) {
      result.exhausted = true;
      break;
    }
    result.pages += 1;
    result.scanned += snap.size;

    const candidates = selectEmailLinkTokenIdsToPurge(
      snap.docs.map((doc) => ({
        id: doc.id,
        expiresAt: doc.data()?.expiresAt ?? null,
        emailVerifiedUid: doc.data()?.emailVerifiedUid,
      })),
      now
    );
    // Firestore batch max 500.
    for (let i = 0; i < candidates.length; i += 400) {
      const chunk = candidates.slice(i, i + 400);
      const batch = firestore.batch();
      for (const id of chunk) {
        batch.delete(tokens.doc(id));
      }
      await batch.commit();
      result.deleted += chunk.length;
    }

    cursor = snap.docs[snap.docs.length - 1].id;
    if (snap.size < pageSize) {
      result.exhausted = true;
      break;
    }
    if (result.scanned >= maxDocs || nowMs() - startedAt >= timeBudgetMs) break;
  }

  result.skipped = result.scanned - result.deleted;
  // A finished pass starts over next time; an interrupted one resumes.
  await checkpointRef.set(
    { cursor: result.exhausted ? null : cursor, updatedAt: Timestamp.now() },
    { merge: true }
  );
  return result;
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
      timeoutSeconds: 300,
    },
    async () => {
      const result = await purgeExpiredEmailLinkTokens(firestore, { limit: 500 });
      logger.info("purgeExpiredEmailLinkTokens completed", result);
    }
  );
}
