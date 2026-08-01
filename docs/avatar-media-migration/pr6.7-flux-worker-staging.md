# PR6.7 FLUX Worker Staging Runbook

Status: staging-runnable repair for the Seolleyeon avatar worker.

## Scope

PR6.7 makes the FLUX worker fail fast when real inference dependencies or auth
posture are missing, while preserving local dry-run smoke tests for development.
It does not start PR6.8+ QA/model scoring work.

## Dependency Strategy

Worker dependencies are isolated in `requirements_avatar_worker.txt`. Do not add
FLUX, torch, or diffusers pins to the global recommendation requirements unless a
shared runtime truly needs them.

The production Docker image starts from:

```sh
pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
```

That base image provides the CUDA torch strategy. The requirements file pins the
rest of the worker runtime: diffusers, transformers, accelerate, safetensors,
Pillow, google-cloud-storage, google-cloud-firestore, firebase-admin, Flask, and
gunicorn.

`diffusers` must expose `Flux2KleinPipeline`. If it does not, real FLUX mode
raises immediately instead of silently using dry-run.

## Docker Build

Build from the repository root:

```sh
docker build \
  -f lib/ai_recommend_model/avatar_generation/Dockerfile \
  -t asia-northeast3-docker.pkg.dev/PROJECT/REPO/seolleyeon-avatar-worker:PR6_7_TAG \
  .
```

Push:

```sh
docker push asia-northeast3-docker.pkg.dev/PROJECT/REPO/seolleyeon-avatar-worker:PR6_7_TAG
```

## Cloud Run GPU Deploy Template

Use one L4 GPU, min instances 0, max instances 1, and concurrency 1:

```sh
gcloud run deploy seolleyeon-avatar-worker \
  --image asia-northeast3-docker.pkg.dev/PROJECT/REPO/seolleyeon-avatar-worker:PR6_7_TAG \
  --region asia-northeast3 \
  --gpu 1 \
  --gpu-type nvidia-l4 \
  --cpu 8 \
  --memory 32Gi \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --no-allow-unauthenticated \
  --service-account avatar-worker@PROJECT.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=production,AVATAR_WORKER_MODE=flux,AVATAR_WORKER_AUTH_MODE=cloud_run_iam,AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true,SOURCE_PHOTO_BUCKET=seolleyeon-private-source-photos,AVATAR_TEMP_BUCKET=seolleyeon-avatar-temp,MAX_CANDIDATES=4,AVATAR_CANDIDATE_TTL_HOURS=72,AVATAR_GENERATION_WIDTH=1024,AVATAR_GENERATION_HEIGHT=1024,AVATAR_GENERATION_STEPS=4,AVATAR_GENERATION_GUIDANCE_SCALE=1.0 \
  --set-secrets HF_TOKEN=avatar-worker-hf-token:latest
```

Grant only the Cloud Tasks/Pub/Sub caller service account `roles/run.invoker` on
this service. With `AVATAR_WORKER_AUTH_MODE=cloud_run_iam`, the Flask app
requires `AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true` and the Cloud Run `K_SERVICE`
runtime variable. Unauthenticated traffic should never reach the container.

For non-IAM staging only, use:

```text
AVATAR_WORKER_AUTH_MODE=shared_secret
AVATAR_WORKER_SHARED_SECRET=<Secret Manager value>
```

and send `X-Avatar-Worker-Token`. Do not use shared secrets as the preferred
production boundary when Cloud Run IAM/OIDC is available.

## Required Environment

- `ENVIRONMENT=production`
- `AVATAR_WORKER_MODE=flux`
- `AVATAR_WORKER_AUTH_MODE=cloud_run_iam` or `shared_secret`
- `AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true` when using Cloud Run IAM
- `SOURCE_PHOTO_BUCKET=seolleyeon-private-source-photos`
- `AVATAR_TEMP_BUCKET=seolleyeon-avatar-temp`
- `MAX_CANDIDATES=4`
- `AVATAR_CANDIDATE_TTL_HOURS=72`
- `AVATAR_GENERATION_WIDTH=1024`
- `AVATAR_GENERATION_HEIGHT=1024`
- `AVATAR_GENERATION_STEPS=4`
- `AVATAR_GENERATION_GUIDANCE_SCALE=1.0`
- `HF_TOKEN` from Secret Manager if the model requires gated Hugging Face access

`AVATAR_WORKER_DRY_RUN=true` and `AVATAR_WORKER_MODE=dry_run` are rejected when
`ENVIRONMENT=production`.

## Smoke Tests

Local dry-run smoke:

```sh
python scripts/avatar_worker_smoke_test.py \
  --dry_run \
  --job_id avatar_smoke_job \
  --uid avatar_smoke_user \
  --source_gcs_uri gs://seolleyeon-private-source-photos/users/avatar_smoke_user/source/smoke_source_001.jpg \
  --candidate_count 4 \
  --output_report_json tmp/avatar_worker_smoke_report.json
```

The report redacts private source refs and records dependency detection.

Real GPU staging smoke:

```sh
python scripts/avatar_worker_smoke_test.py \
  --real_gpu \
  --payload_json tmp/avatar_job_payload.json \
  --output_report_json tmp/avatar_worker_real_gpu_report.json
```

The real GPU smoke requires Firestore/GCS credentials, an existing queued
`avatarJobs/{jobId}`, matching `userPrivateMedia/{uid}` source refs and consent,
and a diffusers build with `Flux2KleinPipeline`.

## Rollback

1. Shift Cloud Tasks/Pub/Sub push target back to the previous worker revision or
   pause the avatar generation queue.
2. Run:

```sh
gcloud run services update-traffic seolleyeon-avatar-worker \
  --region asia-northeast3 \
  --to-revisions PREVIOUS_REVISION=100
```

3. Confirm new jobs are no longer entering `running` on the bad revision.
4. Leave existing temp candidates for the cleanup lifecycle job; do not expose
   private source refs or temp refs to public user documents during rollback.
