# PR7-E Observability Runbook

## Structured Events

All avatar worker observability logs should emit JSON using
`avatar_observability_event_v1` from
`lib/ai_recommend_model/avatar_generation/observability.py`.

Required fields:

- `schemaVersion=avatar_observability_event_v1`
- `service=avatar-generation`
- `eventName`
- `severity`
- `timestamp`
- `attributes`

Canonical PR7 event names:

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

Forbidden log fields are always redacted: signed URLs, raw embeddings, prompts,
source refs, source paths, candidate refs, idempotency keys, and download URLs.
Use `uidHash`, never raw `uid`, in logs and metric resource labels.

## Log-Based Metrics

Create Cloud Logging log-based metrics using JSON filters on
`jsonPayload.schemaVersion="avatar_observability_event_v1"` or
`jsonPayload.schemaVersion="avatar_metric_payload_v1"`.

Recommended metric payloads:

- `avatar_generation_started_count`: count `avatar_job_generation_started`
- `avatar_generation_completed_count`: count `avatar_job_preview_ready`
- `avatar_generation_failed_count`: count `avatar_job_failed`
- `avatar_generation_retry_count`: count `avatar_job_retry_scheduled`
- `avatar_batch_completed_count`: count `avatar_batch_completed`
- `avatar_batch_deadline_stop_count`: count `avatar_batch_deadline_stop`
- `avatar_stale_lease_recovered_count`: count `avatar_stale_lease_recovered`
- `avatar_privacy_qa_failed_count`: count `avatar_candidate_qa_reject`
- `avatar_cost_guard_blocked_count`: count `avatar_cost_guard_paused`
- `avatar_gpu_smoke_failed_count`: count `avatar_live_gpu_smoke_completed` with
  `status!="pass"`
- `avatar_iam_check_failed_count`: count `avatar_live_iam_check_completed` with
  `status!="pass"`
- `avatar_generation_duration_seconds`: distribution from metric payload
  `value`
- `avatar_batch_duration_seconds`: distribution from metric payload `value`
- `avatar_cost_estimate_usd`: distribution from metric payload `value`

Keep labels low-cardinality: `status`, `eventName`, `modelId`, `batchMode`,
`environment`, `reason`, and `severity`. Do not label on job id or user hash.

## Dashboard Metrics

Production dashboard tiles:

- Queue backlog by status: queued, running, retryable failed, stale running
- Claim rate and claim failures
- Generation starts, completions, failures, retries, skips
- Success rate and failure rate over 5m/30m/24h
- P50/P95/P99 generation duration seconds
- Batch size, batch duration, drain processed count
- Stale lease detected and recovered counts
- Model cache hits, misses, load calls, and cache size
- Cost estimate USD per job, per batch, daily total, monthly total
- Budget guard allowed vs blocked decisions
- Privacy QA pass/fail/review counts
- IAM live check pass/fail
- GPU smoke pass/fail
- Log volume and error log rate for `avatar-generation`

## Alerts

Suggested initial alerts:

- Failure rate: `avatar_generation_failed_count / started_count > 5%` for 10m.
- No completions: queued backlog > 0 and completed count == 0 for 15m.
- Stuck jobs: running jobs with expired `processing.leaseExpiresAt` > 0 for 10m.
- Retry storm: retry count > 20 in 15m or retry rate > completion rate.
- Privacy QA: any privacy QA hard fail in production.
- IAM: any live IAM check failure in production.
- GPU smoke: any GPU smoke failure after deploy or canary.
- Cost: daily estimate >= `AVATAR_COST_ALERT_DAILY_USD`.
- Cost hard stop: any `avatar_cost_guard_paused`.
- Drain starvation: drain completes with `processedCount=0` while queue backlog
  remains > 0 for 10m.

## Stuck Jobs

1. Check `scripts/avatar_queue_status.py --firestore_project PROJECT_ID`.
2. Confirm whether jobs are `running` with expired
   `avatarJobs.processing.leaseExpiresAt`.
3. Check worker logs for `avatar_job_generation_started`,
   `avatar_job_failed`, and stale running jobs in queue status output.
4. If failures are active, pause first with `AVATAR_GPU_WORKER_ENABLED=false`.
5. Continue with stale lease recovery only after confirming no live worker still
   owns the lease.

## Stale Lease Recovery

1. Run the sweeper in dry-run mode:

   ```sh
   python scripts/avatar_job_lease_sweeper.py --firestore_project PROJECT_ID --dry_run
   ```

2. Confirm the report only contains aggregate counts and no source refs.
3. Apply recovery:

   ```sh
   python scripts/avatar_job_lease_sweeper.py --firestore_project PROJECT_ID --apply
   ```

4. Watch `avatar_stale_lease_recovered`, retry count, and failure rate for 15m.

## Pause

Set one of the production kill switches:

- `AVATAR_GPU_WORKER_ENABLED=false` for worker-level pause.
- `AVATAR_DISABLE_NEW_GENERATION=true` for product-level generation pause.
- `AVATAR_COST_KILL_SWITCH_ENABLED=true` for budget emergency pause.

Confirm `avatar_cost_guard_paused` or the deployment pause marker is logged and
claim rate drops to zero.

## Resume

1. Confirm cost, IAM, privacy, and queue alerts are clear.
2. Restore the paused env var to its approved value.
3. Deploy or restart the worker as required by the hosting environment.
4. Confirm claim rate and `avatar_job_preview_ready` completions recover.

## Retry

Retry only retryable `failed` jobs below max attempts. Prefer existing PR7-A
claim logic rather than direct document edits. Monitor `avatar_job_retry_scheduled`,
`processing.attempt`, and cost guard alerts during retry waves.

## Drain

Use drain mode for controlled backlog processing:

```sh
curl -X POST https://AVATAR_WORKER/tasks/avatar-generation/drain
```

Watch `avatar_batch_started`, `avatar_batch_completed`,
`avatar_batch_deadline_stop`, processed count, batch duration, and batch cost
estimate. Stop drain if failure rate exceeds the alert threshold or privacy QA
failures appear.

## Canary

1. Enable a tiny batch, normally one job and one candidate.
2. Run IAM live check and GPU smoke first.
3. Submit the canary job.
4. Require `avatar_live_gpu_smoke_completed`, `avatar_job_preview_ready`,
   privacy QA pass, and candidate upload success before widening traffic.

## Cost

Before production batches:

```sh
python scripts/avatar_cost_report.py --firestore_project PROJECT_ID --dry_run
python scripts/avatar_queue_status.py --firestore_project PROJECT_ID --fail_stale_over 0
```

Watch daily/monthly estimates, hard generation limits, budget guard decisions,
and batch savings. If cost guard blocks claims, keep generation paused until the
budget owner approves new limits.

## GPU Smoke

Run staging smoke after deploy and before canary:

```sh
python scripts/avatar_worker_staging_smoke.py --real_gpu --worker_url https://AVATAR_WORKER --id_token_from_gcloud --audience https://AVATAR_WORKER --output_report_json tmp/avatar_worker_gpu_smoke.json
```

The report must not include source refs, signed URLs, prompts, or embeddings.
Log `avatar_live_gpu_smoke_completed` with `status=pass` only after image
generation, upload, and privacy QA complete.

## IAM

Run:

```sh
python scripts/avatar_live_iam_check.py --worker_url https://AVATAR_WORKER --use_gcloud_token
```

Unauthenticated access should fail, authenticated access should pass, and Cloud
Tasks OIDC audience/service account should match the deployment. Log
`avatar_live_iam_check_completed` without request bodies or tokens.

## Privacy QA

Privacy QA must verify:

- No signed URLs, source refs, raw embeddings, prompts, or idempotency keys in
  logs, reports, metrics, or smoke outputs.
- Source photos remain private GCS refs used only inside the worker.
- Candidate refs are not emitted in observability payloads.
- Logs use `uidHash`, not raw `uid`.
- Log-based metric labels stay low-cardinality and non-sensitive.
