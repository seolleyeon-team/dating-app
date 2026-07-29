/**
 * Decide whether an emailLinkToken doc is safe to purge.
 * Only expired tokens without mailbox proof may be deleted.
 */
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
