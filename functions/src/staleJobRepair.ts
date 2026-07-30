/**
 * Dry-run / plan-only stale job repair helpers.
 *
 * Blind-meeting states are intentionally unsupported here.
 * This module never mutates Firestore by itself — callers must apply plans.
 */

export type StaleDomain =
  | "avatar_pending"
  | "recommendation_running"
  | "notification_scheduled"
  | "account_deletion_running"
  | "season_meeting_pending"
  | "deposit_pending"
  | "refund_pending"
  | "replacement_pending"
  | "safety_stamp_incomplete";

export type StaleJobSnapshot = {
  domain: StaleDomain;
  id: string;
  status: string;
  updatedAtMs: number;
  retryCount?: number;
  ownerUid?: string;
};

export type RepairAction =
  | "noop"
  | "retry"
  | "dead_letter"
  | "operator_review"
  | "expire";

export type RepairPlan = {
  domain: StaleDomain;
  id: string;
  action: RepairAction;
  reason: string;
  stale: boolean;
  retryCount: number;
  maxRetries: number;
  maxAgeMs: number;
  dryRun: true;
};

/** Normal maximum age before a domain is considered stale. */
export const STALE_MAX_AGE_MS: Record<StaleDomain, number> = {
  avatar_pending: 30 * 60 * 1000,
  recommendation_running: 2 * 60 * 60 * 1000,
  notification_scheduled: 24 * 60 * 60 * 1000,
  account_deletion_running: 60 * 60 * 1000,
  season_meeting_pending: 6 * 60 * 60 * 1000,
  deposit_pending: 30 * 60 * 1000,
  refund_pending: 60 * 60 * 1000,
  replacement_pending: 30 * 60 * 1000,
  safety_stamp_incomplete: 24 * 60 * 60 * 1000,
};

export const STALE_MAX_RETRIES: Record<StaleDomain, number> = {
  avatar_pending: 3,
  recommendation_running: 2,
  notification_scheduled: 5,
  account_deletion_running: 5,
  season_meeting_pending: 2,
  deposit_pending: 5,
  refund_pending: 8,
  replacement_pending: 3,
  safety_stamp_incomplete: 2,
};

const ACTIVE_STATUSES: Record<StaleDomain, ReadonlySet<string>> = {
  avatar_pending: new Set(["queued", "pending", "running", "generating"]),
  recommendation_running: new Set(["running", "pending"]),
  notification_scheduled: new Set(["scheduled", "pending"]),
  account_deletion_running: new Set(["running", "pending", "partial"]),
  season_meeting_pending: new Set(["pending", "awaiting_confirm"]),
  deposit_pending: new Set(["pending", "processing"]),
  refund_pending: new Set(["pending", "processing", "retrying"]),
  replacement_pending: new Set(["pending", "open"]),
  safety_stamp_incomplete: new Set(["incomplete", "awaiting"]),
};

export function isActiveStatus(domain: StaleDomain, status: string): boolean {
  return ACTIVE_STATUSES[domain].has(String(status || "").trim().toLowerCase());
}

export function planStaleRepair(
  job: StaleJobSnapshot,
  nowMs: number
): RepairPlan {
  const maxAgeMs = STALE_MAX_AGE_MS[job.domain];
  const maxRetries = STALE_MAX_RETRIES[job.domain];
  const retryCount = Math.max(0, Math.floor(job.retryCount ?? 0));
  const ageMs = Math.max(0, nowMs - job.updatedAtMs);
  const active = isActiveStatus(job.domain, job.status);
  const stale = active && ageMs > maxAgeMs;

  if (!active) {
    return {
      domain: job.domain,
      id: job.id,
      action: "noop",
      reason: "not_active",
      stale: false,
      retryCount,
      maxRetries,
      maxAgeMs,
      dryRun: true,
    };
  }

  if (!stale) {
    return {
      domain: job.domain,
      id: job.id,
      action: "noop",
      reason: "within_sla",
      stale: false,
      retryCount,
      maxRetries,
      maxAgeMs,
      dryRun: true,
    };
  }

  if (retryCount >= maxRetries) {
    return {
      domain: job.domain,
      id: job.id,
      action: "dead_letter",
      reason: "retry_budget_exhausted",
      stale: true,
      retryCount,
      maxRetries,
      maxAgeMs,
      dryRun: true,
    };
  }

  // High-risk money / meeting domains escalate to operators after first stale hit.
  if (
    job.domain === "deposit_pending" ||
    job.domain === "refund_pending" ||
    job.domain === "season_meeting_pending"
  ) {
    return {
      domain: job.domain,
      id: job.id,
      action: "operator_review",
      reason: "high_risk_stale",
      stale: true,
      retryCount,
      maxRetries,
      maxAgeMs,
      dryRun: true,
    };
  }

  if (job.domain === "safety_stamp_incomplete") {
    return {
      domain: job.domain,
      id: job.id,
      action: "expire",
      reason: "safety_window_elapsed",
      stale: true,
      retryCount,
      maxRetries,
      maxAgeMs,
      dryRun: true,
    };
  }

  return {
    domain: job.domain,
    id: job.id,
    action: "retry",
    reason: "stale_active",
    stale: true,
    retryCount,
    maxRetries,
    maxAgeMs,
    dryRun: true,
  };
}

export function planStaleRepairs(
  jobs: StaleJobSnapshot[],
  nowMs: number
): RepairPlan[] {
  return jobs.map((job) => planStaleRepair(job, nowMs));
}
