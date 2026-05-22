# PR7 Live Staging Checklist

## Worker/GPU

Status: PR7-B implemented, staging validation pending live GPU environment.

Preflight:

- Confirm Cloud Run IAM or shared-secret auth is configured before invoking
  task endpoints.
- Confirm `GET /readyz` returns `status=ok`, the expected `authMode`, and
  `batchDrainEnabled=true` only when drain mode is intended.
- Set `AVATAR_BATCHING_ENABLED=true`, `AVATAR_BATCH_MODE=drain`, and
  `AVATAR_BATCH_CONCURRENCY_PER_GPU=1` for drain workers.
- Keep `AVATAR_BATCH_MAX_JOBS`, `AVATAR_BATCH_MAX_SECONDS`,
  `AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS`, and
  `AVATAR_BATCH_SOFT_STOP_BEFORE_DEADLINE_SECONDS` bounded for staging.
- Do not enable `AVATAR_WORKER_DRY_RUN` outside local/dev/test.

Smoke commands:

```sh
python scripts/avatar_worker_staging_smoke.py --dry_run --output_report_json tmp/avatar_worker_staging_dry_run.json
python scripts/avatar_worker_staging_smoke.py --real_gpu --worker_url https://AVATAR_WORKER --id_token_from_gcloud --audience https://AVATAR_WORKER --output_report_json tmp/avatar_worker_staging_real_gpu.json
```

Pass criteria:

- `/readyz` reports the expected auth posture and no private source refs.
- Dry-run smoke completes locally with a redacted report.
- Real GPU smoke completes against staging without returning source refs.
- Drain mode processes jobs sequentially and exits before the deadline safety
  window.
- Model cache metrics show a single process cache rather than per-job reloads.

## PR7-F Staging Canary

Status: implemented, dry-run safe by default.

Canary command:

```sh
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --dry_run --output_report_json tmp\avatar_staging_canary_pr7f.json
```

Live canary command:

```sh
.\.venv\Scripts\python.exe scripts\avatar_staging_canary.py --live --worker_url https://AVATAR_WORKER --id_token_from_gcloud --audience https://AVATAR_WORKER --output_report_json tmp\avatar_staging_canary_live_pr7f.json
```

Exact gates:

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

Rollback flags:

- `AVATAR_DISABLE_NEW_GENERATION=true`
- `AVATAR_COST_KILL_SWITCH_ENABLED=true`
- `AVATAR_GPU_WORKER_ENABLED=false`
- `AVATAR_FORCE_SINGLE_JOB_MODE=true`
