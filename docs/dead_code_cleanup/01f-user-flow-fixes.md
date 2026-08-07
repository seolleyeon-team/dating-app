# User-flow fixes

## Cleanup-audit fixes

No new runtime code fix was required during this cleanup audit. The baseline was green and the investigated workflow mismatches were stale labels or intentional historical replacements. No route was removed to hide an error.

## Pre-existing worktree fixes

The current dirty worktree already contains onboarding/auth/eligibility changes from earlier user work, including partial-save protection, onboarding field recovery, strict eligibility checks, and email-link/session handling. Those changes were preserved and were not modified, rebased, committed, or attributed to this cleanup task.

| Area | Current treatment in this audit |
|---|---|
| Onboarding field persistence | Preserved as user WIP; no rewrite performed |
| Email-link/Firebase session | Preserved as user WIP; external browser validation remains deferred |
| Blind-meeting eligibility | Preserved; server fail-closed behavior is protected |
| Safety stamp and meeting flows | Preserved; no route or feature deletion |
| App Check / push / deep links | Preserved; platform validation remains external |

Any future flow defect found while deleting a candidate must follow the required order: reproduce, write a failing test, make the smallest modular fix, run the full gate, and keep the fix separate from deletion.
