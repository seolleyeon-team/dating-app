# PR7 Production Readiness Checklist

## Required Assets

- `scripts/avatar_pipeline_load_test.py` dry-run report.
- `scripts/avatar_staging_canary.py` dry-run and staging-live reports.
- Cost report from `scripts/avatar_cost_report.py`.
- Queue backlog report from `scripts/avatar_queue_status.py`.
- Privacy QA report from `scripts/qa_media_privacy.py`.

## Hard Gates

- Load test dry-run passes with `dryRun=true`, `no_real_gcs=true`, `no_real_gpu=true`, and `firestoreEmulator=true`.
- CI mode uses 10 jobs by default; regression coverage includes 100 duplicate-prevention claims.
- 1000-user launch scenario is present in the load/cost reports.
- Stale running leases requeue below max attempts.
- Duplicate claims are `0`.
- Cost report includes jobs per user, candidate count, batch size, number of batches, average batch size, total simulated worker seconds, estimated cost per user, cost per approved avatar where applicable, estimated USD, and timing.
- Load report includes stale leases simulated/recovered plus failures/retries.
- Canary gates all pass: `gcs`, `firestore`, `queue`, `oidc`, `gpu`, `tempDocs`, `qa`, `previewApproval`, `cleanup`, and `privacy`.
- Privacy status is `pass` and reports emit no private source refs, signed URLs, user IDs, prompts, source paths, or candidate paths.

## Feature Flags

Production enablement:

- `AVATAR_GPU_WORKER_ENABLED=true`
- `AVATAR_BATCHING_ENABLED=true`
- `AVATAR_BATCH_MODE=drain`
- `AVATAR_BATCH_CONCURRENCY_PER_GPU=1`
- `AVATAR_COST_ENFORCE_BUDGET=true`

Rollback:

- `AVATAR_DISABLE_NEW_GENERATION=true`
- `AVATAR_COST_KILL_SWITCH_ENABLED=true`
- `AVATAR_GPU_WORKER_ENABLED=false`
- `AVATAR_FORCE_SINGLE_JOB_MODE=true`

## Verification Commands

```sh
.\.venv\Scripts\python.exe -m pytest tests\test_avatar_pr7_load_canary.py -q
.\.venv\Scripts\python.exe scripts\avatar_pipeline_load_test.py --dry_run --num_users 10 --jobs_per_user 1 --candidate_count 4 --simulate_worker --no_real_gcs --no_real_gpu --report_json tmp\avatar_pr7f_load.json
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json tmp\avatar_pr7f_canary.json
```

Do not promote if any command returns nonzero or any report has `ok=false`.
