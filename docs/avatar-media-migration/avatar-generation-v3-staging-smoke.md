# Avatar Generation V3 Staging Smoke

Status: safe staging commands for AV3-G. Commands default to dry-run or
readiness/warmup checks and avoid heavy model calls unless explicitly marked as
real GPU.

## Preconditions

- Work from the repository root.
- Use a Python environment with worker dependencies installed for local dry-run
  smoke, or run the checks inside the worker image.
- `Pillow` is required even for local smoke because the fixture generator imports
  `PIL`.
- Do not export tokens into shell history. Use `gcloud auth` and Secret Manager
  bindings instead.
- Confirm the Cloud Run service was deployed with `--no-allow-unauthenticated`.
- Keep `AVATAR_GPU_WORKER_ENABLED=false` until the full gate passes.

Optional PowerShell setup for report paths:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
```

## 1. Local Dry-Run Worker Smoke

This path uses fake Firestore/GCS clients, deterministic fixture PNGs, and no
model download:

```powershell
python scripts/avatar_worker_smoke_test.py `
  --dry_run `
  --job_id avatar_smoke_job `
  --uid avatar_smoke_user `
  --source_gcs_uri gs://seolleyeon-final-private-source-photos/users/avatar_smoke_user/source/smoke_source_001.jpg `
  --candidate_count 4 `
  --output_report_json tmp/avatar_worker_smoke_report.json
```

Expected result:

- Report status is `ok`.
- `mode` is `dry_run`.
- `sourceRef` is redacted.
- No real GPU or model call occurs.

## 2. Dependency Import Check

Use the existing smoke report to check whether `torch` and
`diffusers.Flux2KleinPipeline` are importable:

```powershell
python scripts/avatar_worker_smoke_test.py `
  --dry_run `
  --output_report_json tmp/avatar_dependency_report.json
```

Expected result:

- Dry-run still succeeds even if `Flux2KleinPipeline` is unavailable locally.
- The `dependencies` section records availability without downloading model
  weights.

Do not run `--real_gpu` on a laptop or CI host unless that host has the intended
CUDA, diffusers, model access, Firestore, and GCS setup.

## 2A. V3 Trait and Prompt Dry-Run

Run these before a live GPU smoke. They do not send photos to external APIs:

```powershell
python scripts/avatar_trait_extraction_smoke.py `
  --dry_run `
  --report_json out/avatar_trait_smoke.json

python scripts/avatar_flux_param_sweep.py `
  --dry_run `
  --steps 4,6 `
  --guidance 1.0,1.3 `
  --report_json out/avatar_param_sweep.json
```

Expected result:

- Trait smoke returns a validated dry-run trait card.
- Param sweep reports prompt versions and confirms no `negative_prompt` kwarg.

## 3. Build Image

Build with Cloud Build using a non-secret image name:

```powershell
gcloud builds submit `
  --config cloudbuild.avatar-worker.yaml `
  --substitutions _IMAGE=REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/seolleyeon-avatar-worker:TAG
```

Expected result:

- Cloud Build succeeds.
- The image is pushed to Artifact Registry.
- No token or service account key appears in build logs.

## 4. Deploy Locked Worker

Deploy with queue claims disabled first:

```powershell
gcloud run deploy seolleyeon-avatar-worker `
  --image REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/seolleyeon-avatar-worker:TAG `
  --region asia-northeast3 `
  --gpu 1 `
  --gpu-type nvidia-l4 `
  --cpu 8 `
  --memory 32Gi `
  --concurrency 1 `
  --min-instances 0 `
  --max-instances 1 `
  --no-allow-unauthenticated `
  --service-account avatar-worker@PROJECT_ID.iam.gserviceaccount.com `
  --set-env-vars ENVIRONMENT=production,AVATAR_WORKER_MODE=flux,AVATAR_WORKER_AUTH_MODE=cloud_run_iam,AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true,SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos,AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp,MAX_CANDIDATES=4,AVATAR_BATCHING_ENABLED=true,AVATAR_BATCH_MODE=drain,AVATAR_BATCH_CONCURRENCY_PER_GPU=1,AVATAR_GPU_WORKER_ENABLED=false,AVATAR_DISABLE_NEW_GENERATION=true
```

Expected result:

- Service deploys without public unauthenticated access.
- Queue/drain claims are disabled until smoke passes.
- Any Hugging Face token is provided through Secret Manager, not this command.

## 5. Queue Config Gate

Validate local or staging env before queue traffic:

```powershell
python scripts/avatar_queue_config_check.py `
  --env_file path\to\staging-avatar-queue.env `
  --output_report_json tmp/avatar_queue_config_report.json
```

Expected result:

- Report `ok` is `true`.
- `JOB_QUEUE_MODE` is `cloud_tasks` or `pubsub` in production.
- `AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES <= AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS`.
- `AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS` is near the worker timeout, normally
  around `900`.

The env file must not contain secrets. Use it for non-secret names, URLs, retry
bounds, and queue settings only.

## 6. IAM/OIDC Gate

Check that unauthenticated requests are rejected and authenticated requests
succeed. The script redacts bearer tokens:

```powershell
python scripts/avatar_live_iam_check.py `
  --worker_url https://WORKER_URL `
  --use_gcloud_token `
  --audience https://WORKER_URL `
  --output_report_json tmp/avatar_live_iam_report.json
```

Expected result:

- `unauthenticated_healthz_rejected` is `ok`.
- `authenticated_healthz` is `ok`.
- No token or private source ref is printed.

Optional Cloud Tasks dry-run description:

```powershell
python scripts/avatar_live_iam_check.py `
  --worker_url https://WORKER_URL `
  --use_gcloud_token `
  --audience https://WORKER_URL `
  --describe_task_dry_run `
  --queue_name avatar-generation `
  --task_url https://WORKER_URL/tasks/avatar-generation `
  --service_account_email task-invoker@PROJECT_ID.iam.gserviceaccount.com `
  --output_report_json tmp/avatar_live_iam_task_report.json
```

This does not create a real task.

## 7. Worker Readiness and Warmup

Run staging smoke against the live Cloud Run service. By default, real GPU mode
posts to `/warmup`, not `/tasks/avatar-generation`:

```powershell
python scripts/avatar_worker_staging_smoke.py `
  --real_gpu `
  --worker_url https://WORKER_URL `
  --id_token_from_gcloud `
  --audience https://WORKER_URL `
  --warmup_timeout_seconds 900 `
  --output_report_json tmp/avatar_worker_gpu_warmup_report.json
```

Expected result:

- `/readyz` returns auth posture and model cache metrics.
- `/warmup` returns `status=ok`, `mode=flux`, and `warmed=true`.
- If `Flux2KleinPipeline` or model access is missing, the report fails before
  queue traffic is enabled.

Only post a real task payload after Firestore/GCS staging fixtures exist:

```powershell
python scripts/avatar_worker_staging_smoke.py `
  --real_gpu `
  --worker_url https://WORKER_URL `
  --id_token_from_gcloud `
  --audience https://WORKER_URL `
  --post_task_payload `
  --job_id STAGING_JOB_ID `
  --uid STAGING_UID `
  --source_gcs_uri gs://seolleyeon-final-private-source-photos/users/STAGING_UID/source/STAGING_SOURCE.jpg `
  --candidate_count 4 `
  --task_timeout_seconds 900 `
  --output_report_json tmp/avatar_worker_gpu_task_report.json
```

Do not use this task-post command with production user data unless the staging
job, source consent, buckets, and cleanup lifecycle have already been reviewed.

## 8. Backlog and Cost Gates

Check aggregate queue state:

```powershell
python scripts/avatar_queue_status.py `
  --firestore_project PROJECT_ID `
  --fail_stale_over 0 `
  --output_report_json tmp/avatar_queue_status_report.json
```

Check cost assumptions without mutation:

```powershell
python scripts/avatar_cost_report.py `
  --firestore_project PROJECT_ID `
  --date 2026-05-21 `
  --month 2026-05 `
  --dry_run `
  --output_report_json tmp/avatar_cost_report.json
```

Expected result:

- Queue status emits aggregate counts only.
- Cost report emits pricing assumptions and aggregate budget state only.
- No user IDs, private refs, signed URLs, prompts, or tokens appear.

## 9. Enable Controlled Traffic

After all gates pass, enable claims intentionally:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --region asia-northeast3 `
  --update-env-vars AVATAR_GPU_WORKER_ENABLED=true,AVATAR_DISABLE_NEW_GENERATION=false
```

Keep Cloud Tasks/Pub/Sub dispatch concurrency at or below one GPU lane until a
separate capacity test proves a higher value is safe.

If the queue posts explicit payloads to `/tasks/avatar-generation` instead of
calling `/tasks/avatar-generation/drain`, also unpause or retarget the queue in
the queueing layer. The env update above enables drain-mode claims; it is not a
queue-level dispatch switch.

## 10. Rollback and Pause

Pause new claims:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --region asia-northeast3 `
  --update-env-vars AVATAR_GPU_WORKER_ENABLED=false,AVATAR_DISABLE_NEW_GENERATION=true,AVATAR_COST_KILL_SWITCH_ENABLED=true
```

Roll traffic back to a previous revision:

```powershell
gcloud run services update-traffic seolleyeon-avatar-worker `
  --region asia-northeast3 `
  --to-revisions PREVIOUS_REVISION=100
```

Do not delete temp candidate objects during rollback unless the cleanup runbook
calls for it. The normal TTL cleanup path should own temp artifact removal.

## Smoke Pass Criteria

- Local dry-run smoke passes.
- Dependency report records expected torch/diffusers availability.
- Cloud Build image succeeds.
- Cloud Run deploy is private and uses the worker service account.
- Queue config report has no errors.
- IAM report confirms unauthenticated rejection and authenticated success.
- Real GPU warmup succeeds, or a specific dependency/model-access blocker is
  recorded before traffic is enabled.
- Queue status has no stale leases above the launch threshold.
- Cost report is reviewed and kill switches are understood.
- No smoke report contains tokens, signed URLs, raw prompts, or private source
  refs.
