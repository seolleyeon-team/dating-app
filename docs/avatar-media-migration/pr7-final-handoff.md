# PR7 Final Handoff

## Coordinator Final Status

Status: `PASS_STAGING_READY`.

PR7 is code/test/dry-run ready for staging rollout, but it is not
`PASS_PRODUCTION_READY`. Live GCP/GPU verification is still required for:

- Cloud Tasks or Pub/Sub dispatch into the deployed worker.
- Cloud Run IAM/OIDC service-to-service invocation.
- Real staging GCS source/temp/approved bucket read/write permissions.
- Cloud Run GPU FLUX.2-klein inference with a safe staging fixture image.
- Cloud Scheduler or lifecycle cleanup verification.
- Firestore transaction/race smoke under live staging credentials.
- QA v1 threshold calibration with a Seolleyeon staging sample set.

Latest coordinator validation:

```sh
.venv\Scripts\python.exe -m compileall -q lib\ai_recommend_model scripts tests
.venv\Scripts\python.exe -m pytest -q tests
.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning
bash scripts/check_avatar_media_privacy.sh
npm --prefix functions run build
npm --prefix functions test
flutter test test\profile_display_image_resolver_test.dart
.venv\Scripts\python.exe scripts\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json out\avatar_load_report_verify.json
.venv\Scripts\python.exe scripts\avatar_cost_report.py --dry_run
.venv\Scripts\python.exe scripts\avatar_queue_status.py --dry_run
.venv\Scripts\python.exe scripts\avatar_job_lease_sweeper.py --dry_run
.venv\Scripts\python.exe scripts\avatar_worker_staging_smoke.py --dry_run --output_report_json out\avatar_worker_smoke.json
.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json out\avatar_staging_canary_verify.json
```

All commands above passed in the local Codex environment. Live staging commands
were not run because this environment does not provide deployed GCP services,
Cloud Run GPU access, staging IAM, real buckets, or Cloud Scheduler.

## PR7-A

Implemented:

- Firestore lease helpers in `avatar_generation/job_lease.py` using canonical
  nested `avatarJobs.processing.*` fields.
- Batch claim orchestration in `avatar_generation/batching.py`.
- Stale lease recovery script in `scripts/avatar_job_lease_sweeper.py`.
- Cost guard integration before job claim mutation.
- Consent and private source bucket validation before claims.
- No claim for `preview_ready`, `approved`, or `cancelled` jobs.
- `--dry_run` sweeper mode that can run without Firestore credentials for
  local PR gates.

Validation:

```sh
.venv\Scripts\python.exe -m pytest tests\test_avatar_job_lease.py -q
.venv\Scripts\python.exe scripts\avatar_job_lease_sweeper.py --dry_run
```

## PR7-C

Implemented:

- Backlog status script in `scripts/avatar_queue_status.py`.
- Queue configuration gate in `scripts/avatar_queue_config_check.py`.
- Live IAM/OIDC probe in `scripts/avatar_live_iam_check.py`.
- Queue/IAM live checklist in
  `docs/avatar-media-migration/pr7-queue-iam-live-checklist.md`.
- `--dry_run` queue status mode that can run without Firestore credentials for
  local PR gates.

Validation:

```sh
.venv\Scripts\python.exe -m pytest tests\test_avatar_queue_ops.py -q
.venv\Scripts\python.exe scripts\avatar_queue_status.py --dry_run
```

## PR7-G

Final privacy regression status: pass in local/dry-run mode.

Key findings:

- No Dart/Flutter client references to `seolleyeon-private-source-photos`,
  `seolleyeon-avatar-temp`, `userPrivateMedia`, `clipEmbeddings`,
  `sourcePhotoRefs`, `sourcePhotoGcsUri`, or `gcsUri`.
- Backend `getSignedUrl` usage remains limited to runtime owner preview URL
  generation in `functions/src/avatarApproval.ts`; signed URLs are not stored in
  Firestore.
- `scripts/qa_media_privacy.py --dry_run --fail_on_warning` passed.
- PR7 report JSON emits aggregate status/cost only, not source refs, signed
  URLs, prompts, or user ids.

Blocked by environment:

- Real GPU smoke, real Cloud Tasks dispatch, real IAM/OIDC invocation, real GCS
  bucket permission checks, real Cloud Scheduler cleanup, and staging canary
  are `BLOCKED_BY_ENV` until run in the staging GCP project.

## PR7-B

Implemented:

- GPU worker accepts `avatar_job_v1` and canonical `avatar_batch_job_v1`
  payloads with `jobType=avatar_generation_batch`, `batchId`, `jobIds`,
  `maxJobs`, and `deadlineSeconds`.
- Batch `jobIds` mode loads `avatarJobs/{jobId}` internally and reconstructs
  private source refs only inside the worker.
- Lease-backed drain mode consumes PR7-A `claim_avatar_job_batch` and canonical
  `avatarJobs.processing.*` lease fields.
- Processing remains sequential with concurrency `1`.
- Deadline-aware drain stop is wired through `ClaimDeadline`.
- `/readyz` and authenticated optional `/warmup` endpoints are available.
- FLUX generator singleton/cache metrics are exposed.
- Per-job metric hooks are available for started/completed/failed events.
- Worker jobs persist `avatarJobs.cost` plus PR7-D helper-compatible
  `costEstimateUsd`, `costEstimate`, and `durationSeconds`.
- Explicit batch and drain responses include aggregate cost metrics generated
  through `build_batch_cost_document()`.
- Staging smoke script supports `--dry_run`, `--real_gpu`, `--worker_url`,
  `--audience`, `--id_token_from_gcloud`, and `--output_report_json`.

Validation:

```sh
.venv\Scripts\python.exe -m pytest tests/test_avatar_generation_worker.py -q
```

Privacy:

- Worker responses and smoke reports do not return source refs.
- Source refs are used only internally for generation and consent validation.
- Cost documents and metrics contain durations, pricing, candidate counts, and
  estimates only; no source refs are emitted.
- Dry-run mode is blocked outside local/dev/test and production rejects it.
- No external image APIs are used by this lane.

Blocked by environment:

- Real GPU staging smoke requires a deployed worker URL, IAM audience, and
  FLUX-capable GPU image.

## PR7-D

Implemented:

- Default cost assumptions now match the PR7 prompt:
  L4 GPU `0.0001867`, vCPU `0.000018`, memory GiB `0.000002`,
  4 vCPU, 16 GiB, pricing version `cloud_run_l4_2026_05`,
  daily alert `10`, monthly alert `200`, daily hard limit `500`, and monthly
  hard limit `10000`.
- `scripts/avatar_cost_report.py --dry_run` can run without Firestore inputs
  and emits the nonzero 1000 users x 4 candidates scenario estimate.
- `build_job_cost_document()` and `build_batch_cost_document()` expose
  persistable fields for PR7-B/coordinator worker integration without editing
  `worker.py` or `worker_service.py`.
- Cost docs and report pricing metadata label defaults as configurable
  assumptions and list storage, network egress, and Artifact Registry as
  excluded cost categories.

Validation:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_cost.py tests\test_avatar_job_lease.py -q
.\.venv\Scripts\python.exe scripts\avatar_cost_report.py --dry_run
```

Privacy:

- Report output remains aggregate-only.
- No user IDs, job IDs, source refs, signed URLs, prompts, source paths, or
  candidate paths are emitted by the cost report.

Risks:

- Defaults are planning assumptions and must be reviewed against current Cloud
  Run pricing before hard budget enforcement.
- The guard still scans `avatarJobs`; large production volume may need an
  indexed rollup document.

## PR7-E

Implemented:

- Added reusable observability helpers in
  `lib/ai_recommend_model/avatar_generation/observability.py`.
- Defined `avatar_observability_event_v1` structured events and
  `avatar_metric_payload_v1` metric payloads for log-based Cloud Monitoring
  metrics.
- Added the exact canonical PR7 snake_case avatar event names:
  `avatar_upload_enqueued`, `avatar_job_claimed`, `avatar_batch_started`,
  `avatar_model_load_started`, `avatar_model_load_completed`,
  `avatar_job_generation_started`, `avatar_candidates_generated`,
  `avatar_candidate_qa_pass`, `avatar_candidate_qa_reject`,
  `avatar_job_preview_ready`, `avatar_job_failed`,
  `avatar_job_retry_scheduled`, `avatar_stale_lease_recovered`,
  `avatar_batch_completed`, `avatar_batch_deadline_stop`,
  `avatar_cost_guard_paused`, `avatar_cleanup_completed`,
  `avatar_live_gpu_smoke_started`, `avatar_live_gpu_smoke_completed`, and
  `avatar_live_iam_check_completed`.
- Kept dot-style event names as legacy aliases only; dashboards and runbooks use
  the canonical snake_case names.
- Added recursive redaction for signed URLs, download URLs, private source
  refs, source paths, candidate refs, candidate paths, raw embeddings, prompts,
  and idempotency keys.
- Event/resource payloads use `uidHash` instead of raw `uid`.
- Added `docs/avatar-media-migration/pr7-observability-runbook.md` with
  log-based metric guidance, dashboard metric list, alert thresholds, and
  runbooks for stuck jobs, stale lease recovery, pause/resume, retry, drain,
  canary, cost, GPU smoke, IAM, and privacy QA.
- Documented PR7-E in
  `docs/avatar-media-migration/pr7-batch-cost-production-hardening.md`.

Validation:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_observability.py -q
```

Privacy:

- No source refs, signed URLs, raw embeddings, prompts, idempotency keys, or
  candidate refs are allowed in observability event attributes or metric
  labels/resources.
- Log-based metric labels are intentionally low-cardinality and should not use
  job id or user hash.

Risks:

- Runtime worker/service integration is intentionally left for the consuming
  lane; this PR7-E lane did not edit `worker.py`.
- Dashboard and alert resources still need to be created in the target cloud
  project from the documented log-based metric definitions.

## PR7-F

Implemented:

- CI-safe avatar pipeline load test script with `dry_run`, `no_real_gcs`, `no_real_gpu`, `firestore_emulator`, and JSON report support.
- Default load simulation documents the 1000-user launch scenario and 10-job CI mode.
- Regression tests cover 100 duplicate-prevention claims, stale crash lease requeue, cost timing, privacy QA marker, and canary dry-run report gates.
- Staging canary script supports dry-run and live modes with exact gates for `gcs`, `firestore`, `queue`, `oidc`, `gpu`, `tempDocs`, `qa`, `previewApproval`, `cleanup`, and `privacy`.
- Production readiness checklist and rollout runbook document feature flags, rollback, privacy gates, and promotion blockers.

Validation:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_pr7_load_canary.py -q
.\.venv\Scripts\python.exe scripts\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json tmp\avatar_pr7f_load.json
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json tmp\avatar_pr7f_canary.json
```

Privacy:

- Reports emit aggregate readiness and cost status only.
- No private source refs, signed URLs, user IDs, prompts, source paths, or candidate paths are emitted by PR7-F reports.
- Privacy QA marker is `pr7f_privacy_qa_pass`.

Handoff JSON:

```json
{
  "owner": "PR7-F",
  "status": "implemented",
  "assets": [
    "scripts/avatar_pipeline_load_test.py",
    "scripts/avatar_staging_canary.py",
    "tests/test_avatar_pr7_load_canary.py",
    "docs/avatar-media-migration/pr7-live-staging-checklist.md",
    "docs/avatar-media-migration/pr7-production-readiness-checklist.md",
    "docs/avatar-media-migration/pr7-rollout-runbook.md",
    "docs/avatar-media-migration/pr7-batch-cost-production-hardening.md",
    "docs/avatar-media-migration/pr7-final-handoff.md"
  ],
  "verification": {
    "pytest": ".\\.venv\\Scripts\\python.exe -m pytest tests\\test_avatar_pr7_load_canary.py -q",
    "loadDryRun": ".\\.venv\\Scripts\\python.exe scripts\\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json tmp\\avatar_pr7f_load.json",
    "canaryDryRun": ".\\.venv\\Scripts\\python.exe scripts\\avatar_staging_canary.py --dry_run --output_report_json tmp\\avatar_pr7f_canary.json"
  },
  "rollbackFlags": {
    "AVATAR_DISABLE_NEW_GENERATION": true,
    "AVATAR_COST_KILL_SWITCH_ENABLED": true,
    "AVATAR_GPU_WORKER_ENABLED": false,
    "AVATAR_FORCE_SINGLE_JOB_MODE": true
  },
  "privacy": {
    "status": "pass",
    "qaMarker": "pr7f_privacy_qa_pass",
    "sourceRefsEmitted": false,
    "signedUrlsEmitted": false,
    "userIdsEmitted": false
  }
}
```
