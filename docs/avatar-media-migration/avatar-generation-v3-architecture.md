> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# Avatar Generation V3 Architecture

Status: V3 worker integration notes. This file documents the Cloud Run worker
path, the new source-analysis / trait-card / region-preprocess stages, and the
recommended production posture.

## Scope

Avatar Generation V3 is the Cloud Run GPU worker lane for private-source-photo
to avatar-candidate generation. The lane keeps real source photos private,
writes temporary candidates to a private GCS bucket, and exposes only approved
or preview-safe avatar output through later lifecycle steps.

In-scope runtime components:

- `lib/ai_recommend_model/avatar_generation/worker_service.py`: Flask app
  factory served by gunicorn in the Cloud Run image.
- `lib/ai_recommend_model/avatar_generation/worker.py`: payload validation,
  source image loading, FLUX or fixture generation, QA handoff, Firestore/GCS
  writes, model cache, warmup, batch, and drain execution.
- `lib/ai_recommend_model/avatar_generation/job_lease.py`: drain-mode lease
  claiming, stale lease recovery, kill switches, and cost guard hooks.
- `lib/ai_recommend_model/avatar_generation/cost.py`: Cloud Run GPU, vCPU, and
  memory cost estimates and budget guard config.
- `scripts/avatar_worker_smoke_test.py`: local dry-run and optional local real
  GPU smoke.
- `scripts/avatar_worker_staging_smoke.py`: staging worker `/readyz`,
  `/warmup`, and optional task-post smoke.
- `scripts/avatar_queue_config_check.py`, `scripts/avatar_live_iam_check.py`,
  `scripts/avatar_queue_status.py`, and `scripts/avatar_cost_report.py`:
  production gate checks that do not print source refs or tokens.

Out of scope:

- Secret creation, token output, service account key material, or committed
  `.env` files.

## Request Flow

```text
Client or backend enqueue
  -> avatarJobs/{jobId} queued with private gs:// source refs
  -> Cloud Tasks/Pub/Sub invokes Cloud Run worker with OIDC
  -> worker_service.py enforces configured auth posture
  -> worker.py validates payload, user consent, source bucket, and job state
  -> worker loads source image from private GCS using service account identity
  -> source face/safety analysis rejects no-face or multi-face sources
  -> Florence-2 trait extraction creates a validated private trait card
  -> region-aware reference preprocessing abstracts face details more strongly
  -> dry_run fixture generation or FLUX.2-klein GPU generation
  -> adaptive generation adds 4 more candidates when safe candidates are too low
  -> candidate PNGs written to AVATAR_TEMP_BUCKET
  -> avatarCandidates docs written with QA and rerank status
  -> avatarJobs/{jobId} moves to preview_ready only when the configured
     preview count is satisfied, otherwise needs_review or failed
```

The worker accepts `avatar_job_v1` single-job payloads and
`avatar_batch_job_v1` explicit batch payloads. Drain mode claims queued work
itself from Firestore when `AVATAR_BATCHING_ENABLED=true` and
`AVATAR_BATCH_MODE=drain`.

## Production Startup Safety

Production startup should fail closed before any real traffic is routed:

- Set `ENVIRONMENT=production`.
- Set `AVATAR_WORKER_MODE=flux`.
- Do not set `AVATAR_WORKER_DRY_RUN=true` in production. The worker rejects
  production dry-run mode.
- Prefer `AVATAR_WORKER_AUTH_MODE=cloud_run_iam`.
- Set `AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true` when using Cloud Run IAM.
- Deploy Cloud Run with `--no-allow-unauthenticated`.
- Grant `roles/run.invoker` only to the Cloud Tasks or Pub/Sub push service
  account that invokes the worker.
- Keep `AVATAR_BATCH_CONCURRENCY_PER_GPU=1` for GPU batch/drain mode.
- Set `AVATAR_GPU_WORKER_ENABLED=false`,
  `AVATAR_DISABLE_NEW_GENERATION=true`, or
  `AVATAR_COST_KILL_SWITCH_ENABLED=true` to stop new claims during rollout or
  incident response.
- If Cloud Tasks or Pub/Sub pushes explicit payloads directly to
  `/tasks/avatar-generation`, pause or retarget the queue during rollout. The
  worker kill switches stop lease claims in drain mode; they do not replace
  queue-level pause controls for direct task delivery.

`worker_service.py` also checks `K_SERVICE` when
`AVATAR_WORKER_AUTH_MODE=cloud_run_iam`; this confirms the app is running in
Cloud Run context. Non-IAM staging may use `shared_secret`, but that mode should
not be the preferred production boundary.

## Dependency Boundary

The GPU worker has an isolated runtime dependency file:

```text
requirements_avatar_worker.txt
```

Current dependency posture:

- The Docker image starts from `pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime`.
- `torch==2.8.0` is pinned in the worker requirements.
- `diffusers` is pinned to a GitHub archive commit that exposes
  `Flux2KleinPipeline`.
- Worker-only packages include `transformers`, `accelerate`,
  `huggingface-hub`, `safetensors`, `Pillow`, `google-cloud-storage`,
  `google-cloud-firestore`, `firebase-admin`, `Flask`, and `gunicorn`.

Recommendation: keep FLUX, torch, and diffusers out of global recommendation
requirements unless another runtime truly needs them. This avoids forcing GPU
model dependencies into unrelated Cloud Run jobs, local Flutter tooling, or
CI-safe Python lanes.

## Lazy-Load Strategy

Real model loading is intentionally deferred:

- Importing `worker_service.py` creates the Flask app but does not download the model.
- Dry-run mode never imports or loads `Flux2KleinPipeline`.
- `Flux2KleinImageGenerator._load_pipeline()` imports `torch` and
  `Flux2KleinPipeline` only when a real FLUX generation or `/warmup` runs.
- `get_flux2_klein_generator()` caches one generator per model id in process.
- Florence-2 trait extraction is lazy-loaded and can be dry-run for local
  smoke tests.
- SAM is not loaded by default; region preprocessing uses source-analysis boxes
  unless an explicit SAM path is configured.
- `/readyz` reports model cache metrics without forcing a model load.
- `/warmup` may be used after deploy to load the model under authenticated
  operator control before queue traffic is enabled.

This keeps container startup safer for Cloud Run scale-from-zero and makes
dependency failures visible through explicit staging smoke instead of hidden
inside unrelated health checks.

## Cloud Run Deployment Proposal

Build with Cloud Build:

```sh
gcloud builds submit \
  --config cloudbuild.avatar-worker.yaml \
  --substitutions _IMAGE=REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/seolleyeon-avatar-worker:TAG
```

Deploy a single-L4 worker:

```sh
gcloud run deploy seolleyeon-avatar-worker \
  --image REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/seolleyeon-avatar-worker:TAG \
  --region asia-northeast3 \
  --gpu 1 \
  --gpu-type nvidia-l4 \
  --cpu 8 \
  --memory 32Gi \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --no-allow-unauthenticated \
  --service-account avatar-worker@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=production,AVATAR_WORKER_MODE=flux,AVATAR_WORKER_AUTH_MODE=cloud_run_iam,AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true,SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos,AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp,MAX_CANDIDATES=4,AVATAR_BATCHING_ENABLED=true,AVATAR_BATCH_MODE=drain,AVATAR_BATCH_CONCURRENCY_PER_GPU=1,AVATAR_GPU_WORKER_ENABLED=false
```

The Dockerfile serves this app through gunicorn with one worker, one thread,
and a long task timeout to match the single-GPU, concurrency-1 posture.

Enable worker traffic only after staging smoke passes. Do not put Hugging Face
tokens, service account keys, or shared secrets in the command line. Use Secret
Manager bindings for any gated model token required by the image.

## Scripts Integration

Use existing safe scripts first:

- `scripts/avatar_worker_smoke_test.py --dry_run`: local fixture path, no model
  download and no real GPU call.
- `scripts/avatar_worker_staging_smoke.py --dry_run`: local process smoke or
  authenticated worker smoke depending on `--worker_url`.
- `scripts/avatar_worker_staging_smoke.py --real_gpu --worker_url ...`: defaults
  to `/warmup`, not task posting, so it does not require a real Firestore job
  unless `--post_task_payload` is explicitly set.
- `scripts/avatar_queue_config_check.py`: validates queue env and retry bounds.
- `scripts/avatar_live_iam_check.py`: checks unauthenticated rejection and
  authenticated access while redacting tokens and private refs.
- `scripts/avatar_queue_status.py`: aggregate backlog and stale lease report.
- `scripts/avatar_cost_report.py --dry_run`: cost assumptions and budget guard
  report without mutation.

Optional future helper scripts should default to dry-run, avoid model calls by
default, and redact source refs, tokens, prompts, and candidate object paths.

Current local script execution requires worker dependencies such as `Pillow`.
If `ModuleNotFoundError: No module named 'PIL'` appears, run the smoke inside
the worker image or install the isolated worker requirements in a throwaway
Python environment.

## Follow-Ups

- Consider adding a small dependency import smoke that verifies
  `Flux2KleinPipeline` is importable without loading model weights.
- Run the dry-run trait extraction and parameter sweep scripts before any live
  GPU smoke.
