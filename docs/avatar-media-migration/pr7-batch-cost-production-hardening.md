# PR7 Batch Cost Production Hardening

## PR7-A Lease, Batching, Stale Recovery

Status: implemented.

Canonical lease schema:

- Lease state is written under `avatarJobs.processing.*`.
- Canonical fields are `leaseOwner`, `leaseToken`, `leaseExpiresAt`,
  `leaseHeartbeatAt`, `attempt`, `batchId`, `startedAt`, `lastErrorCode`, and
  `lastErrorMessage`.
- Legacy flat lease fields are read for compatibility but new writes use the
  nested `processing` map.

Claim rules:

- Claimable jobs are `queued`, stale `running` jobs with expired
  `processing.leaseExpiresAt` and `processing.attempt < max_attempts`, or
  retryable `failed` jobs below max attempts.
- `preview_ready`, `approved`, and `cancelled` jobs are never claimed.
- Missing refs, non-GCS refs, public HTTPS refs, wrong buckets, signed/query
  refs, and unsafe paths fail closed with redacted `processing.lastError*`
  values.
- If `userPrivateMedia/{uid}` exists, consent and active private source-photo
  membership are enforced before claim.

PR7 env names:

- `AVATAR_BATCHING_ENABLED`
- `AVATAR_BATCH_MODE`
- `AVATAR_BATCH_MAX_JOBS`
- `AVATAR_BATCH_MAX_SECONDS`
- `AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS`
- `AVATAR_BATCH_POLL_INTERVAL_SECONDS`
- `AVATAR_BATCH_LEASE_SECONDS`
- `AVATAR_BATCH_MAX_ATTEMPTS`
- `AVATAR_BATCH_REQUIRE_APPROVED_SOURCE_CONSENT`
- `AVATAR_BATCH_CONCURRENCY_PER_GPU`
- `AVATAR_BATCH_CANDIDATES_PER_USER`
- `AVATAR_BATCH_SOFT_STOP_BEFORE_DEADLINE_SECONDS`
- `AVATAR_ALLOW_STALE_LEASE_RECOVERY`
- `AVATAR_FORCE_SINGLE_JOB_MODE`

Kill switches:

- `AVATAR_GPU_WORKER_ENABLED=false` stops claims.
- `AVATAR_DISABLE_NEW_GENERATION=true` stops claims.
- `AVATAR_COST_KILL_SWITCH_ENABLED=true` stops claims.

Sweeper behavior:

- Dry-run is the default.
- Expired `running` leases below max attempts are requeued and nested lease
  owner/token fields are cleared.
- Expired `running` leases at max attempts are marked non-retryable `failed`.
- Reports include aggregate counts only and do not emit private source refs.

## PR7-C Queue Retry/OIDC/IAM Live Controls

PR7-C adds three operator scripts:

- `scripts/avatar_queue_status.py`: aggregate `avatarJobs` backlog health,
  stale lease detection when `processing.leaseExpiresAt` is present, and GPU
  batch/cost estimates from env defaults.
- `scripts/avatar_queue_config_check.py`: fail-fast validation for production
  Cloud Tasks/Pub/Sub env, OIDC caller identity, retry guidance, and bounded GPU
  fanout.
- `scripts/avatar_live_iam_check.py`: live unauthenticated/authenticated
  `/healthz` IAM probe plus sanitized Cloud Tasks dry-run description.

Production should prefer Cloud Tasks with:

- `avatar-generation`
- `clip-embedding`
- `TASK_INVOKER_SERVICE_ACCOUNT=task-invoker@PROJECT_ID.iam.gserviceaccount.com`
- `roles/run.invoker` on both worker Cloud Run services
- max dispatch/concurrency capped to the GPU worker capacity, normally `1`

Cost controls:

- Keep `AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES <= AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS`.
- Keep `AVATAR_QUEUE_MAX_ATTEMPTS=3` unless an incident review approves more.
- Use `AVATAR_QUEUE_BATCH_SIZE`, `AVATAR_QUEUE_GPU_SECONDS_PER_CANDIDATE`, and
  `AVATAR_QUEUE_GPU_COST_PER_SECOND_USD` to make backlog cost estimates explicit.
- Treat stale leases and retryable jobs as cost-risk backlog, not just latency.

Privacy controls:

- Live IAM output redacts tokens, source refs, idempotency keys, and signed URL
  query material.
- Backlog status reports aggregate counts only.
- Task creation in `avatar_live_iam_check.py` is description-only; it does not
  create a real task or print request bodies.

Launch gate:

```sh
python scripts/avatar_queue_config_check.py
python scripts/avatar_live_iam_check.py --worker_url https://AVATAR_WORKER --use_gcloud_token
python scripts/avatar_queue_status.py --firestore_project PROJECT_ID --fail_stale_over 0
```

Do not broaden the queue publisher or PR7-A lease implementation in this lane.

## PR7-B GPU Worker Batch/Drain Mode

Status: implemented.

Worker behavior:

- `/tasks/avatar-generation` accepts `avatar_job_v1` and canonical
  `avatar_batch_job_v1` payloads with `jobType=avatar_generation_batch`,
  `batchId`, `jobIds`, `maxJobs`, and `deadlineSeconds`. Legacy `jobs` arrays
  remain accepted for tests/dev compatibility. Batch payloads are processed
  sequentially on one GPU lane.
- `/tasks/avatar-generation/drain` claims work through the PR7-A
  `claim_avatar_job_batch` interface when `AVATAR_BATCHING_ENABLED=true` and
  `AVATAR_BATCH_MODE=drain`.
- Drain mode enforces `AVATAR_BATCH_CONCURRENCY_PER_GPU=1`, stops before the
  configured deadline safety window, and exits after max batch or idle windows.
- Batch `jobIds` and claimed lease payloads are loaded/enriched internally from
  `avatarJobs` for private source refs; returned results and reports do not
  include source refs.
- `dry_run` is allowed only in local/dev/test environments. Production defaults
  to `flux` and rejects dry-run mode.
- The FLUX generator is cached as a process singleton. Metrics expose cache
  hits, misses, load calls, and cache size.
- Per-job metric hooks are emitted for started, completed, and failed job
  events without logging source refs.
- Each completed worker job records `avatarJobs.cost` with `candidateCount`,
  `totalWorkerSeconds`, `estimatedUsd`, `pricingVersion`, and
  `secondsByStage`. The worker also writes PR7-D helper-compatible
  `costEstimateUsd`, `costEstimate`, and `durationSeconds`.
- Explicit batch and drain results include aggregate `metrics.cost` with
  `jobCount`, `candidateCount`, `totalWorkerSeconds`, `estimatedUsd`,
  `pricingVersion`, and batching savings fields.

Worker endpoints:

- `GET /healthz`: liveness.
- `GET /readyz`: readiness/auth posture and batch-drain/model-cache metrics.
- `POST /warmup`: optional authenticated model warmup.
- `POST /tasks/avatar-generation`: single or explicit batch payload.
- `POST /tasks/avatar-generation/drain`: lease-backed drain loop.

Staging smoke:

```sh
python scripts/avatar_worker_staging_smoke.py --dry_run --output_report_json tmp/avatar_worker_smoke.json
python scripts/avatar_worker_staging_smoke.py --real_gpu --worker_url https://AVATAR_WORKER --id_token_from_gcloud --audience https://AVATAR_WORKER --output_report_json tmp/avatar_worker_gpu_smoke.json
```

Privacy notes:

- Smoke reports redact private GCS paths.
- Batch/drain results include job ids and aggregate candidate counts only.
- Batch result metadata may include `batchId`, but never source refs.
- Cost metrics are duration/pricing aggregates only and do not contain source
  refs or source object paths.
- No external image API integrations are used by the worker lane.

## PR7-D Cost Estimation, Quotas, Budget Guard, Kill Switch

Status: implemented.

PR7-D adds:

- `lib/ai_recommend_model/avatar_generation/cost.py` for Cloud Run GPU, CPU,
  and memory pricing, job/batch cost estimates, aggregate daily/monthly actuals,
  quota checks, and budget alerts.
- `scripts/avatar_cost_report.py` for dry-run or live aggregate reporting with
  `--date`, `--month`, and the default 1000 users x 4 candidates launch
  scenario.
- Lease-claim integration in `job_lease.py` so kill switch, quota, and enforced
  budget failures return no claim before mutating `avatarJobs`.
- `build_job_cost_document()` and `build_batch_cost_document()` helpers so
  PR7-B or a coordinator can persist per-job/per-batch estimate fields without
  this lane editing `worker.py`.

Required env names:

- `CLOUD_RUN_L4_GPU_USD_PER_SECOND`
- `CLOUD_RUN_CPU_USD_PER_VCPU_SECOND`
- `CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND`
- `CLOUD_RUN_GPU_ZONAL_REDUNDANCY`
- `CLOUD_RUN_VCPU`
- `CLOUD_RUN_MEMORY_GIB`
- `CLOUD_RUN_PRICING_VERSION`
- `AVATAR_COST_ALERT_DAILY_USD`
- `AVATAR_COST_ALERT_MONTHLY_USD`
- `AVATAR_COST_HARD_DAILY_GENERATION_LIMIT`
- `AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT`
- `AVATAR_COST_KILL_SWITCH_ENABLED`
- `AVATAR_COST_ENFORCE_BUDGET`
- `AVATAR_GPU_WORKER_ENABLED`
- `AVATAR_DISABLE_NEW_GENERATION`

Default values are configurable PR7 planning assumptions:

- `CLOUD_RUN_L4_GPU_USD_PER_SECOND=0.0001867`
- `CLOUD_RUN_CPU_USD_PER_VCPU_SECOND=0.000018`
- `CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND=0.000002`
- `CLOUD_RUN_VCPU=4`
- `CLOUD_RUN_MEMORY_GIB=16`
- `CLOUD_RUN_PRICING_VERSION=cloud_run_l4_2026_05`
- `AVATAR_COST_ALERT_DAILY_USD=10`
- `AVATAR_COST_ALERT_MONTHLY_USD=200`
- `AVATAR_COST_HARD_DAILY_GENERATION_LIMIT=500`
- `AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT=10000`

The default estimate includes Cloud Run GPU, vCPU, and memory runtime only. It
excludes storage, network egress, Artifact Registry, build minutes, logging,
monitoring, Firestore, and GCS operation costs unless a future pricing version
adds them.

Formula:

```text
total_usd =
  duration_seconds * CLOUD_RUN_L4_GPU_USD_PER_SECOND * gpu_multiplier
  + duration_seconds * CLOUD_RUN_VCPU * CLOUD_RUN_CPU_USD_PER_VCPU_SECOND
  + duration_seconds * CLOUD_RUN_MEMORY_GIB * CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND
```

`gpu_multiplier` is `2` when `CLOUD_RUN_GPU_ZONAL_REDUNDANCY=true`, otherwise
`1`.

Guard behavior:

- `AVATAR_COST_KILL_SWITCH_ENABLED=true` stops new claims immediately.
- Hard daily/monthly generation limits stop claims when reached.
- Daily/monthly spend alerts are advisory by default.
- `AVATAR_COST_ENFORCE_BUDGET=true` turns spend alerts into hard claim guards.
- Guard failures do not mutate queued jobs.

Launch gate:

```sh
python scripts/avatar_cost_report.py --firestore_project PROJECT_ID --date 2026-05-14 --month 2026-05 --dry_run
python scripts/avatar_queue_status.py --firestore_project PROJECT_ID --fail_stale_over 0
```

Privacy controls:

- Cost reports emit aggregate counts/costs only.
- Reports do not emit user IDs, job IDs, private source refs, signed URLs,
  prompts, source paths, or candidate paths.

## PR7-E Observability, Alerts, Dashboard, Runbooks

Status: implemented as a reusable module and operator docs. Runtime worker
integration can consume the module later without changing `worker.py` in this
lane.

Code:

- `lib/ai_recommend_model/avatar_generation/observability.py` defines the
  canonical structured event schema `avatar_observability_event_v1`.
- It also defines `avatar_metric_payload_v1` for log-based metric extraction.
- `build_avatar_event()` emits redacted event dictionaries with `uidHash`
  instead of raw `uid`.
- `build_avatar_metric_payload()` emits redacted metric payload dictionaries
  with low-cardinality labels and redacted resource data.
- `redact_observability_payload()` recursively redacts forbidden keys and
  sensitive GCS/signed URL values.

Forbidden observability fields:

- signed URLs and download URLs
- private source refs and source paths
- candidate refs and candidate paths
- raw embeddings and source embeddings
- prompts and negative prompts
- idempotency keys

Canonical event names:

- `avatar_upload_enqueued`
- `avatar_job_claimed`
- `avatar_batch_started`
- `avatar_model_load_started`
- `avatar_model_load_completed`
- `avatar_job_generation_started`
- `avatar_candidates_generated`
- `avatar_candidate_qa_pass`
- `avatar_candidate_qa_reject`
- `avatar_job_preview_ready`
- `avatar_job_failed`
- `avatar_job_retry_scheduled`
- `avatar_stale_lease_recovered`
- `avatar_batch_completed`
- `avatar_batch_deadline_stop`
- `avatar_cost_guard_paused`
- `avatar_cleanup_completed`
- `avatar_live_gpu_smoke_started`
- `avatar_live_gpu_smoke_completed`
- `avatar_live_iam_check_completed`

Legacy dot-style event names remain accepted by the module for compatibility,
but dashboards, alerts, and runbooks should use the snake_case names above.

Dashboard and alerts:

- Dashboard metrics are listed in
  `docs/avatar-media-migration/pr7-observability-runbook.md`.
- Log-based metrics cover starts, completions, failures, retries, skipped jobs,
  batch/drain completion, stale lease detection/recovery, privacy QA failures,
  IAM failures, GPU smoke failures, cost guard blocks, durations, and cost
  estimates.
- Initial alerts cover failure rate, no completions with backlog, stale leases,
  retry storms, privacy QA hard failures, IAM/GPU smoke failures, daily cost
  threshold, cost guard blocks, and drain starvation.

Runbooks:

- Stuck jobs
- Stale lease recovery
- Pause and resume
- Retry
- Drain
- Canary
- Cost
- GPU smoke
- IAM
- Privacy QA

Validation:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_observability.py -q
```

## PR7-F Load, Canary, Production Readiness

Status: implemented.

PR7-F adds:

- `scripts/avatar_pipeline_load_test.py` for CI-safe dry-run load drills using emulator/fake Firestore by default.
- `scripts/avatar_staging_canary.py` for dry-run and live staging canary gate reports.
- `tests/test_avatar_pr7_load_canary.py` covering duplicate prevention, stale lease requeue, cost timing, privacy QA marker, and canary dry-run reports.
- Production readiness and rollout docs for flags, gates, rollback, and handoff.

Load test safety defaults:

- `--dry_run`
- `--no_real_gcs`
- `--no_real_gpu`
- `--firestore_emulator`
- `--report_json`

Load report coverage:

- 1000-user scenario marker.
- 10-job CI mode default.
- Prompt CLI fields: `--num_users`, `--jobs_per_user`, `--candidate_count`, `--batch_size`, and `--simulate_worker`.
- Batch size, number of batches, average batch size, cost estimate, GPU seconds, total simulated worker seconds, and claim-loop timing.
- Estimated cost per user and cost per approved avatar when simulated worker completion is enabled.
- Stale leases simulated/recovered plus failures/retries.
- Duplicate claim prevention.
- Privacy leakage check result with `pr7f_privacy_qa_pass` marker and no private/temp/source/signed markers in the final report.

Canary exact gates:

- `gcs`
- `firestore`
- `queue`
- `oidc`
- `gpu`
- `tempDocs`
- `qa`
- `previewApproval`
- `cleanup`
- `privacy`

Launch gate:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_pr7_load_canary.py -q
.\.venv\Scripts\python.exe scripts\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json tmp\avatar_pr7f_load.json
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json tmp\avatar_pr7f_canary.json
```

Rollback flags:

- `AVATAR_DISABLE_NEW_GENERATION=true`
- `AVATAR_COST_KILL_SWITCH_ENABLED=true`
- `AVATAR_GPU_WORKER_ENABLED=false`
- `AVATAR_FORCE_SINGLE_JOB_MODE=true`
