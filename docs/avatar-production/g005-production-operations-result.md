# G005 Production Operations Readiness Result

Date: 2026-07-27

## Decision

- Repository operations implementation: `PASS`
- `seolleyeon-final` internal staging operations: `PASS_WITH_WATCH_ITEMS`
- `PRODUCTION_OPERATIONS_READY=false`
- Public rollout: not authorized and not executed
- Source project `seolleyeon`: not mutated

This retry repaired the staging inventory, rollback, and observability tooling,
reconciled the missing staging monitoring resources, and collected current
sanitized queue and cost evidence. It does not authorize production rollout.

## Staging Evidence

- Worker revision: `seolleyeon-avatar-worker-00047-9qx` in
  `asia-southeast1`, with max instances 1, concurrency 1, and 1800 second
  timeout.
- Release inventory: complete and `ok=true`; eight selected Functions, one
  worker, one queue, and three media buckets were present. Cloud Run private
  invocation and absence of public IAM principals on all three buckets were
  verified from live IAM policies. The only warning is the still-temporary
  festival bridge.
- Live preflight: `ok=true`; no blocker. The optional CLIP worker remained an
  avatar-only warning.
- Observability apply: 29/29 successful after fixing the actual gcloud/API
  contracts: 14 log metrics, 14 alert policies, and one dashboard.
- Observability verify: 29/29 `in_sync`, mutation count zero.
- Rollback verify: passed with zero mutations. Queue pause, kill-switch update,
  and revision routing were skipped in verify mode; lease and cleanup checks
  were explicit dry-runs; private-source aggregate was unchanged.
- Authenticated worker `/readyz`: 200. Unauthenticated `/readyz`: 403.

## Repairs

- Corrected the final worker region in release and rollback configuration to
  `asia-southeast1`.
- Aligned the queue manifest with deployed retry backoff, 30 to 600 seconds.
- Parsed snake_case Storage CLI security fields and treated absent bucket
  retention locks as intentional. Bucket-level retention is not added because
  consent withdrawal and account deletion must remain executable.
- Treated omitted Cloud Run minScale as the platform default zero.
- Updated rollback dry-run commands to current CLIs, reused the active Python
  interpreter, parsed summarized storage bytes, and rejected empty aggregate
  evidence.
- Added an explicit `--dry_run` cleanup flag mutually exclusive with `--apply`.
- Fixed Monitoring resource discovery by display name and updates by actual
  resource name.
- Switched log metrics to config-file creation with valid `EXTRACT(...)` label
  extractors, corrected count thresholds for GT-only policy comparisons, added
  non-overlapping dashboard coordinates, and normalized only documented API
  response defaults.
- Added apply exit-code gating, fail-closed temp-file cleanup, redacted temp
  paths, and safe field-only drift reporting.
- Preserved existing Monitoring notification channels during policy updates;
  invalid remote channel references now stop mutation instead of being cleared.
- Changed rollback env mutation to `--update-env-vars` and removed task-target /
  Cloud Functions fallback. Only explicit prior Cloud Run revision routing remains.
- Added an allowed-project guard and exact project-specific confirmation token
  for the legacy negative-prompt retry mutator.

## Queue And Cost Watch Items

- Active queue: queued 0, running 0, stale 0.
- Legacy retryable jobs: 9. Their p95 age was about 5.34 million seconds.
- Strict queue thresholds correctly raised `retryable` and
  `p95_age_seconds` alerts. No legacy job was retried, deleted, or mutated.
- Historical cost evidence: 26 jobs, 25 approvals, total estimated USD 1.506491,
  and USD 0.06026 per approved avatar.
- `totalWorkerSeconds`: p50 81.997, p95 530.454. The p95 remains above the
  240-second canary target and requires calibration/timeout analysis, not an
  automatic timeout change.

## Remaining Blockers

1. App Check debug token exchange/admin listing still returns 403, so the fresh
   exact-consent cohort could not perform live callable uploads. No bypass was
   used.
2. Nine legacy retryable staging jobs need an explicitly authorized terminalize
   or retry decision after lineage review.
3. Alert policies are installed without an invented notification channel. An
   owner-approved channel must be bound before production operations.
4. Worker p95 latency remains above target.
5. The festival bridge remains temporary and is not a production migration
   completion signal.

No production resource, public traffic, private media object, or user document
was changed by this G005 operations retry.