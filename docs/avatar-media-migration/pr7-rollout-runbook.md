# PR7 Rollout Runbook

## Phase 0: Dry-Run

Run:

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_pr7_load_canary.py -q
.\.venv\Scripts\python.exe scripts\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json tmp\avatar_pr7f_load.json
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json tmp\avatar_pr7f_canary.json
```

Required result: both reports have `ok=true`, duplicate claims are `0`, privacy status is `pass`, and no real GPU/GCS use is reported.

## Phase 1: Staging Canary

Deploy staging worker with production-like IAM and staging buckets, keep queue dispatch paused, then run:

```sh
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --live --worker_url https://AVATAR_WORKER --id_token_from_gcloud --audience https://AVATAR_WORKER --output_report_json tmp\avatar_pr7f_canary_live.json
```

Required result: all exact gates pass: `gcs`, `firestore`, `queue`, `oidc`, `gpu`, `tempDocs`, `qa`, `previewApproval`, `cleanup`, and `privacy`.

## Phase 2: Limited Production

- Enable cost guard and kill switch monitoring.
- Enable worker with `AVATAR_BATCH_CONCURRENCY_PER_GPU=1`.
- Start with a bounded queue dispatch rate.
- Watch queue backlog, stale leases, failures, spend, QA rejects, and approval latency.
- Run privacy QA before widening.

## Rollback

Set:

```sh
AVATAR_DISABLE_NEW_GENERATION=true
AVATAR_COST_KILL_SWITCH_ENABLED=true
AVATAR_GPU_WORKER_ENABLED=false
AVATAR_FORCE_SINGLE_JOB_MODE=true
```

Pause queue dispatch and allow in-flight leases to expire or sweep them. Cleanup only temp candidate artifacts and rejected candidates; do not delete private source media during rollback.
