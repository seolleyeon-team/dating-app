# PR7-D Avatar Cost Model

Status: implemented.

## Pricing Inputs

`avatar_generation.cost.AvatarCostConfig.from_env()` reads:

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

Default values are configurable PR7 planning assumptions, not a billing
contract:

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

The default formula includes only Cloud Run L4 GPU, vCPU, and memory runtime.
It excludes storage, network egress, Artifact Registry, build minutes, logging,
monitoring, Firestore, and GCS operation costs unless those are added in a
future pricing version.

## Formula

For a job or a shared batch runtime:

```text
gpu_usd = duration_seconds * CLOUD_RUN_L4_GPU_USD_PER_SECOND * gpu_multiplier
cpu_usd = duration_seconds * CLOUD_RUN_VCPU * CLOUD_RUN_CPU_USD_PER_VCPU_SECOND
memory_usd = duration_seconds * CLOUD_RUN_MEMORY_GIB * CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND
total_usd = gpu_usd + cpu_usd + memory_usd
```

`gpu_multiplier` is `2` when `CLOUD_RUN_GPU_ZONAL_REDUNDANCY=true`, otherwise
`1`. Reports include the component breakdown and pricing version.

## Persisted Estimate Payloads

PR7-D does not edit `worker.py` or `worker_service.py`. Instead it exposes
small helpers for PR7-B or a coordinator to persist cost estimates when a job
or batch completes:

- `build_job_cost_document(duration_seconds=...)` returns
  `costEstimateUsd` and `costEstimate`.
- `build_batch_cost_document(jobs, duration_seconds=...)` returns
  `batchCostEstimateUsd` and `batchCostEstimate`.

Both helper payloads include `durationSeconds`, `pricingVersion`, and the GPU,
CPU, and memory cost breakdown. Callers may pass `estimated_at` to record the
timestamp used for the estimate.

## Aggregation

`aggregate_avatar_job_costs()` counts generated jobs with statuses
`preview_ready`, `approved`, `needs_review`, and `failed`. It prefers persisted
`costEstimateUsd`, `generationCostUsd`, or `costUsd` fields, then falls back to
runtime metadata such as `processing.durationSeconds` or
`processing.startedAt`/`completedAt`.

Daily and monthly windows are UTC and can be overridden in
`scripts/avatar_cost_report.py` with `--date YYYY-MM-DD` and `--month YYYY-MM`.
The report emits aggregate counts and costs only; it does not emit user IDs,
job IDs, private source refs, signed URLs, prompts, or image paths.

## Guards

New claim attempts are blocked before mutating a job when any of these gates
fail:

- `AVATAR_GPU_WORKER_ENABLED=false`
- `AVATAR_DISABLE_NEW_GENERATION=true`
- `AVATAR_COST_KILL_SWITCH_ENABLED=true`
- `AVATAR_COST_HARD_DAILY_GENERATION_LIMIT` reached
- `AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT` reached
- budget alert reached while `AVATAR_COST_ENFORCE_BUDGET=true`

Quota limits are hard generation-count limits. Budget alerts are advisory
unless `AVATAR_COST_ENFORCE_BUDGET=true`, at which point daily or monthly
budget breaches stop new claims.

## Operator Report

Dry-run fixture example:

```sh
python scripts/avatar_cost_report.py \
  --fixture_json tmp/avatar_jobs_fixture.json \
  --date 2026-05-14 \
  --month 2026-05 \
  --dry_run \
  --output_report_json tmp/avatar_cost_report.json
```

Live report:

```sh
python scripts/avatar_cost_report.py \
  --firestore_project PROJECT_ID \
  --firestore_database "(default)" \
  --date 2026-05-14 \
  --month 2026-05 \
  --dry_run
```

The scenario block estimates the launch assumption of 1000 users with 4 avatar
candidates each. With the default configurable assumptions and 120 seconds per
user, the scenario cost is nonzero and reports as `34.884` USD.
