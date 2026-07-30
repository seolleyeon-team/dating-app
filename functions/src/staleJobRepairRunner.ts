/**
 * Dry-run repair runner. Does not mutate Firestore.
 * Intended for scheduled/operator invocation behind an explicit feature flag.
 */

import {
  planStaleRepairs,
  type RepairPlan,
  type StaleDomain,
  type StaleJobSnapshot,
} from "./staleJobRepair";

export type RepairRunnerInput = {
  nowMs: number;
  jobs: StaleJobSnapshot[];
  /** When false, runner refuses to produce apply instructions. */
  allowApply: boolean;
};

export type RepairRunnerResult = {
  dryRun: true;
  scanned: number;
  stale: number;
  plans: RepairPlan[];
  applyBlocked: boolean;
  excludedDomains: StaleDomain[];
};

/** Domains never auto-applied even if allowApply somehow flips true. */
export const NEVER_AUTO_APPLY: ReadonlySet<StaleDomain> = new Set([
  "deposit_pending",
  "refund_pending",
  "season_meeting_pending",
]);

export function runStaleJobRepairDryRun(
  input: RepairRunnerInput
): RepairRunnerResult {
  const plans = planStaleRepairs(input.jobs, input.nowMs);
  const stale = plans.filter((p) => p.stale).length;
  return {
    dryRun: true,
    scanned: input.jobs.length,
    stale,
    plans,
    // Hard safety: this runner never applies. Operators must use a separate
    // approved apply path that is not implemented here on purpose.
    applyBlocked: true,
    excludedDomains: [...NEVER_AUTO_APPLY],
  };
}

export function summarizeRepairPlans(plans: RepairPlan[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const plan of plans) {
    const key = `${plan.domain}:${plan.action}`;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}
