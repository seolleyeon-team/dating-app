> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# PR5 FLUX.2-klein Avatar Worker

PR5 adds a Python Cloud Run worker path for processing `avatar_generation`
payloads. The worker defaults to dry-run fixture mode for local tests and only
loads the real FLUX pipeline when `AVATAR_WORKER_MODE=flux`.

## Endpoint

HTTP service:

```text
POST /tasks/avatar-generation
```

Implementation:

```text
lib/ai_recommend_model/avatar_generation/worker.py
lib/ai_recommend_model/avatar_generation/worker_service.py
```

Payload:

```json
{
  "jobId": "avatar_job_...",
  "uid": "user_123",
  "sourcePhotoIds": ["src_001"],
  "sourcePhotoRefs": [
    "gs://seolleyeon-private-source-photos/users/user_123/source/src_001.jpg"
  ],
  "candidateCount": 4,
  "modelId": "black-forest-labs/FLUX.2-klein-4B",
  "jobType": "avatar_generation",
  "schemaVersion": "avatar_job_v1",
  "idempotencyKey": "user_123:src_001:avatar_generation_v1"
}
```

Pub/Sub push wrappers with `message.data` base64 JSON are also accepted by the
payload decoder.

## Worker Flow

1. Validate `schemaVersion == avatar_job_v1` and `jobType == avatar_generation`.
2. Require `sourcePhotoRefs` to use `gs://` or `gcs://`.
3. Require the source bucket to match `SOURCE_PHOTO_BUCKET`, default
   `seolleyeon-private-source-photos`.
4. Load `avatarJobs/{jobId}` and verify `uid`.
5. Load `userPrivateMedia/{uid}` and verify avatar generation consent plus
   `profileDisplayOriginalPhoto == false`.
6. Read the private source image from GCS using the worker service account.
7. Update the job to `running`, generate 4 candidates, then update to
   `qa_pending`.
8. Store candidate PNGs in:
   `gs://seolleyeon-avatar-temp/users/{uid}/jobs/{jobId}/candidates/{candidateId}.png`
9. Write `avatarCandidates/{candidateId}` with `qa_pending` status.
10. Call `avatar_generation.qa.run_avatar_candidate_qa`.
11. Set candidate status to `preview_ready`, `needs_review`, or `rejected`.
12. Set job status to `preview_ready` if at least one candidate is previewable,
    `needs_review` if all candidates require review, or `failed` if all are
    rejected.

The worker never creates signed source-photo URLs, never uses HTTP source
photos for real users, and never calls external image APIs.

## Model Loading

`Flux2KleinImageGenerator` lazily imports:

```python
from diffusers import Flux2KleinPipeline
```

The real model path is used only when:

```text
AVATAR_WORKER_MODE=flux
```

Dry-run mode:

```text
AVATAR_WORKER_MODE=dry_run
```

Dry-run creates deterministic fixture PNGs with PIL. This exercises storage,
Firestore, path generation, status transitions, and QA integration without GPU
inference or model downloads.

## Prompt Policy

The prompt builder requires a privacy-preserving adult 3D avatar with
medium-level resemblance, broad non-identifying cues only, no exact biometric
copy, no unique marks, ordinary adult university-student tone, no beautification,
no idol/model/influencer look, no childlike/chibi/babyface look, same visible
crop, and no logo/text/watermark.

## Environment

- `AVATAR_WORKER_MODE=dry_run|flux`, default `dry_run`
- `MODEL_ID=black-forest-labs/FLUX.2-klein-4B`
- `SOURCE_PHOTO_BUCKET=seolleyeon-private-source-photos`
- `AVATAR_TEMP_BUCKET=seolleyeon-avatar-temp`
- `GCP_PROJECT`
- `FIRESTORE_DATABASE`
- `MAX_CANDIDATES=4`
- `AVATAR_CANDIDATE_TTL_HOURS=72`
- `AVATAR_GENERATION_WIDTH=1024`
- `AVATAR_GENERATION_HEIGHT=1024`
- `AVATAR_GENERATION_STEPS=4`
- `AVATAR_GENERATION_GUIDANCE_SCALE=1.0`
- `AVATAR_WORKER_REQUIRE_SHARED_SECRET=false`
- `AVATAR_WORKER_SHARED_SECRET`, optional local fallback guard
- `HF_HOME` or `TRANSFORMERS_CACHE`, optional model cache

Production Cloud Run should enforce IAM invoker on the worker service. The
optional shared-secret header is only a fallback for local or non-IAM deployment.

## Local Fixture Mode

With real Firestore/GCS credentials:

```sh
python -m avatar_generation.worker \
  --payload_json /path/to/avatar_job_payload.json \
  --mode dry_run \
  --firestore_project seolleyeon
```

For unit tests, fake Firestore/GCS clients are used and no network or GPU work
runs.

## Container

Dockerfile:

```text
lib/ai_recommend_model/avatar_generation/Dockerfile
```

Build from `lib/ai_recommend_model`:

```sh
docker build -f avatar_generation/Dockerfile -t seolleyeon-avatar-worker .
```

Cloud Run GPU starting point:

```sh
gcloud run deploy seolleyeon-avatar-worker \
  --image REGION-docker.pkg.dev/PROJECT/REPO/seolleyeon-avatar-worker:TAG \
  --region asia-northeast3 \
  --gpu 1 \
  --gpu-type nvidia-l4 \
  --cpu 8 \
  --memory 32Gi \
  --concurrency 1 \
  --max-instances 1 \
  --no-allow-unauthenticated
```

Use Secret Manager or environment variables for Hugging Face tokens if the model
requires gated access. Do not commit tokens or service account keys.

## PR6 Dependency

PR5 calls the QA interface but does not implement real ML QA. The default QA
stub is conservative: unknown QA state is not previewable. PR6 replaces this
with real/best-effort adult, privacy, brand, watermark, crop, and beautification
checks.
