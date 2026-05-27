# Avatar Generation V3 Environment

Status: safe env documentation for Cloud Run, dependency, and operator script
configuration. No secrets are stored here.

## Production Minimum

Set these before allowing queue traffic to the GPU worker:

```text
ENVIRONMENT=production
AVATAR_WORKER_MODE=flux
AVATAR_WORKER_AUTH_MODE=cloud_run_iam
AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true
SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos
AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp
MAX_CANDIDATES=4
AVATAR_BATCHING_ENABLED=true
AVATAR_BATCH_MODE=drain
AVATAR_BATCH_CONCURRENCY_PER_GPU=1
AVATAR_GPU_WORKER_ENABLED=false
```

Keep `AVATAR_GPU_WORKER_ENABLED=false` until build, deploy, dependency,
IAM/OIDC, warmup, queue, and cost gates pass.

## Worker Runtime Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `ENVIRONMENT` | empty, treated as local/dev for mode resolution | `production` | Enables production dry-run rejection. |
| `PORT` | `8080` in Dockerfile | Cloud Run provided or `8080` | HTTP port for Flask service. |
| `AVATAR_WORKER_MODE` | `flux` when production, otherwise `dry_run`; Dockerfile sets `flux` | `flux` | Must be `dry_run` or `flux`. |
| `AVATAR_WORKER_DRY_RUN` | unset | unset or `false` | `true` is rejected in production and outside local/dev/test. |
| `MODEL_ID` | `black-forest-labs/FLUX.2-klein-4B` in Dockerfile | same | Payload validation currently accepts the code constant model id. |
| `SOURCE_PHOTO_BUCKET` | `seolleyeon-final-private-source-photos` | staging/prod private source bucket | Worker rejects source refs outside this bucket. |
| `AVATAR_TEMP_BUCKET` | `seolleyeon-final-avatar-temp` | staging/prod private temp bucket | Candidate PNGs are written here before approval. |
| `APPROVED_AVATAR_BUCKET` | `seolleyeon-approved-avatars` | approved avatar bucket | Used by storage/cleanup helpers. |
| `MAX_CANDIDATES` | `4` | `4` | Worker clamps above default max. |
| `AVATAR_CANDIDATE_TTL_HOURS` | `72` | `72` or shorter staging TTL | Temp candidate lifecycle. |
| `AVATAR_GENERATION_WIDTH` | `1024` | `1024` | Passed to FLUX call. |
| `AVATAR_GENERATION_HEIGHT` | `1024` | `1024` | Passed to FLUX call. |
| `AVATAR_GENERATION_STEPS` | `4` | `4` initially | Increase only after cost/latency review. |
| `AVATAR_GENERATION_GUIDANCE_SCALE` | `1.0` | `1.0` initially | Passed to FLUX call. |
| `AVATAR_FLUX_NUM_INFERENCE_STEPS` | `4` | `4` initially | V3 preferred FLUX steps env; falls back to legacy generation steps. |
| `AVATAR_FLUX_GUIDANCE_SCALE` | `1.0` | `1.0` initially | V3 preferred FLUX guidance env; falls back to legacy guidance. |
| `AVATAR_REFERENCE_PRIVACY_PREPROCESS` | enabled unless explicitly false | enabled | Downsamples/blurs reference before image-conditioned generation. |
| `AVATAR_REFERENCE_PREPROCESS_MODE` | `region_aware_v1` conceptually | `region_aware_v1` | V3 region-aware preprocessing mode. |
| `AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE` | `32` | `64` | Face region abstraction size; staging uses 64px to avoid glasses-like eye smearing while still avoiding original-resolution reference input. |
| `AVATAR_REFERENCE_FACE_BLUR_RADIUS` | `4.0` | `2.0` | Face-region blur; staging uses a lighter blur so no-glasses eyes are not collapsed into frame-like dark bands. |
| `AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE` | `96` | `96` | Non-face/style region abstraction size. |
| `AVATAR_REFERENCE_NONFACE_BLUR_RADIUS` | `1.5` | `1.5` | Softer blur for hair/clothing/style region. |
| `AVATAR_WORKER_ID` | `avatar-worker-{pid}` | service/revision-specific value optional | Used for drain lease owner. |
| `AVATAR_WORKER_DEADLINE_SECONDS` | unset | align with queue timeout, for example `900` | Used to stop drain before timeout. |
| `CLOUD_RUN_TASK_TIMEOUT_SECONDS` | unset | optional fallback to queue timeout | Used when worker deadline is unset. |

## V3 Analysis, Trait, and Adaptive Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `AVATAR_FACE_DETECTOR_ENABLED` | enabled in `flux`, disabled in local `dry_run` unless set | `true` | Runs source face/safety analysis before generation. |
| `AVATAR_FACE_DETECTOR_PROVIDER` | `mediapipe` conceptually | `mediapipe` | Current implementation uses the default detector builder. |
| `AVATAR_FACE_DETECTOR_MIN_CONFIDENCE` | `0.6` | `0.6` then tune | Alias for MediaPipe minimum confidence. |
| `AVATAR_MEDIAPIPE_ENABLED` | `true` | `true` | Enables MediaPipe provider discovery. When disabled with fail-closed, source analysis rejects instead of silently weakening. |
| `AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH` | unset | baked local `.task` path when Face Landmarker is enabled | The worker must not download this asset per request. If absent, it falls back to public `mp.solutions.face_detection` when allowed. |
| `AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES` | `true` | `true` after model smoke | Blendshapes are used transiently for broad expression binning only; raw arrays are not stored. |
| `AVATAR_MEDIAPIPE_NUM_FACES` | `2` | `2` | Allows single/multi-face source classification. |
| `AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE` | `0.6` | `0.6` then tune | Face Landmarker / MediaPipe detector confidence. |
| `AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE` | `0.6` | `0.6` then tune | Face Landmarker presence threshold. |
| `AVATAR_MEDIAPIPE_FAIL_CLOSED_IN_PRODUCTION` | `true` | `true` | Production should not quietly fall through to weak detection if MediaPipe is unavailable. |
| `AVATAR_FACE_MIN_RELATIVE_SIZE` | `0.08` | tune after fixture calibration | Rejects tiny faces. |
| `AVATAR_REJECT_MULTI_FACE` | true conceptually | `true` | Multi-face sources are hard rejected by source analysis. |
| `AVATAR_REJECT_NO_FACE` | true conceptually | `true` | No-face sources are hard rejected by source analysis. |
| `AVATAR_TRAIT_EXTRACTION_ENABLED` | enabled in `flux`, disabled in local `dry_run` unless set | `true` | Runs Florence-2 trait extraction. |
| `AVATAR_TRAIT_MODEL_ID` | `microsoft/Florence-2-large-ft` | same unless staged alternative is tested | Local model path/cache must be present. |
| `AVATAR_TRAIT_MAX_IMAGE_EDGE` | `768` | `768` | Resizes source before trait extraction. |
| `AVATAR_TRAIT_LOCAL_FILES_ONLY` | `true` | `false` in staging when the model is not pre-cached | Keeps production deploys deterministic when pre-baked caches are used; staging may download the public Florence model. |
| `AVATAR_TRAIT_ATTENTION_IMPLEMENTATION` | `eager` | `eager` | Avoids SDPA compatibility errors in Florence-2 remote code. |
| `AVATAR_TRAIT_FLORENCE_TASK_PROMPT` | `MORE_DETAILED_CAPTION` | same | Florence task prompt token; the adapter wraps it as `<MORE_DETAILED_CAPTION>` before calling the model. |
| `AVATAR_TRAIT_DRY_RUN` | `true` in dry-run, false otherwise | `false` | Local-only smoke path. |
| `AVATAR_TRAIT_REQUIRE_VALIDATED` | `true` | `true` | Requires deterministic validator pass. |
| `AVATAR_TRAIT_QWEN_FALLBACK_ENABLED` | `false` | `false` | Optional, disabled by default. |
| `AVATAR_TRAIT_USE_PRIVACY_REFERENCE` | `false` | `false` | Trait extraction runs on a resized local source image so small facial accessories such as glasses are not blurred away; FLUX still receives only the privacy-processed reference. |
| `AVATAR_CANDIDATE_TRAIT_QA_ENABLED` | enabled in `flux`, disabled in local `dry_run` unless set | `true` | Re-runs safe categorical trait extraction on generated candidates only when source eyewear is known, so QA can reject invented or omitted glasses. |
| `AVATAR_SAM_ENABLED` | `false` | `false` initially | Optional mask refinement only. |
| `AVATAR_SAM_MODEL_ID` | `facebook/sam-vit-base` conceptually | optional | Use only with lazy loading and memory review. |
| `AVATAR_SAM_LOAD_ON_DEMAND` | `true` conceptually | `true` | Do not load SAM at worker startup. |
| `AVATAR_INITIAL_CANDIDATE_COUNT` | `4` | `4` | Initial generation count. |
| `AVATAR_EXTRA_CANDIDATE_COUNT` | `4` | `4` | Extra generation when safe candidates are too low. |
| `AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA` | `2` | `2` | Extra generation threshold. |
| `AVATAR_MAX_TOTAL_CANDIDATES` | `8` | `8` | Max generated candidates per job. |
| `AVATAR_PREVIEW_COUNT` | `4` | `4` | Final preview selection target. |
| `AVATAR_MIN_PREVIEW_CANDIDATES` | `1` | `1` | Minimum safe/soft candidate count required for `preview_ready`. |
| `AVATAR_PREVIEW_REQUIRE_FOUR` | `false` | `false` until QA calibration proves four safe candidates are consistently available | When true, jobs do not become `preview_ready` with fewer than `AVATAR_PREVIEW_COUNT` selected candidates. Privacy/safety is stricter than showing exactly four. |
| `AVATAR_PREVIEW_FILL_WITH_SOFT_PASS` | `true` | `true` after QA review | Uses low-risk soft pass to fill preview. |
| `AVATAR_PREVIEW_FILL_HARD_REJECT` | `false` | `false` | Must remain false. |
| `AVATAR_QA_PHASH_NEAR_DUPLICATE_REJECT_THRESHOLD` | `0.985` | calibrate with fixtures | Strict near-duplicate guard for deterministic image similarity. |
| `AVATAR_QA_PHASH_REVIEW_THRESHOLD` | `0.92` | calibrate with fixtures | Moderate perceptual similarity only adds review/debug evidence; it is not a face identity hard reject. |
| `AVATAR_QA_ALLOW_PHASH_HARD_REJECT_ONLY_NEAR_DUPLICATE` | `true` | `true` | Prevents broad crop/color similarity from becoming `too_identifiable`. |
| `AVATAR_QA_REQUIRE_RELIABLE_FACE_SIM_FOR_TOO_IDENTIFIABLE` | `true` | `true` | Requires reliable face similarity or near-duplicate evidence before hard rejecting as too identifiable. |
| `AVATAR_RERANK_PROVIDER` | `deterministic_qa_tier` | `deterministic_qa_tier` until CLIP/DINO calibration is approved | Current production path uses deterministic QA tiers plus optional score hooks. Do not label a deployment as CLIP/DINO rerank unless the model hook is explicitly enabled and verified. |
| `AVATAR_CLIP_MODEL_ID` | `openai/clip-vit-large-patch14` | same unless benchmarked | Reserved CLIP rerank model id for deployments that enable and verify the hook. |
| `AVATAR_DINO_MODEL_ID` | `facebook/dinov2-base` | same unless benchmarked | Reserved DINOv2 rerank model id for deployments that enable and verify the hook. |

## Auth Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `AVATAR_WORKER_AUTH_MODE` | unset | `cloud_run_iam` | Production requests fail unless auth mode is configured. |
| `AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED` | false | `true` | Required by app when auth mode is `cloud_run_iam`. |
| `K_SERVICE` | Cloud Run provided | Cloud Run provided | App checks this in Cloud Run IAM mode. |
| `AVATAR_WORKER_REQUIRE_SHARED_SECRET` | false | false | Legacy/local fallback guard. |
| `AVATAR_WORKER_SHARED_SECRET` | unset | Secret Manager only for non-IAM staging | Never commit or print this value. |
| `ALLOW_INSECURE_WORKER_LOCAL` | false | false | Allows unauthenticated local requests only in local/dev/test. |
| `AVATAR_WORKER_ALLOW_INSECURE_LOCAL` | false | false | Same local-only purpose. |

Production should use Cloud Run IAM plus OIDC. Shared-secret mode is acceptable
for isolated non-IAM staging, but it should not replace Cloud Run IAM in
production.

## Batch and Lease Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `AVATAR_BATCHING_ENABLED` | `true` in lease config | `true` for drain mode | Required for `/tasks/avatar-generation/drain`. |
| `AVATAR_BATCH_MODE` | `drain` | `drain` | Drain endpoint requires this exact value. |
| `AVATAR_BATCH_MAX_JOBS` | `5` | match GPU capacity, normally `1` to `5` | Alias fallback: `AVATAR_JOB_BATCH_SIZE`, `AVATAR_CLAIM_BATCH_SIZE`. |
| `AVATAR_BATCH_MAX_SECONDS` | `1200` | less than Cloud Run timeout | Hard stop for one drain run. |
| `AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS` | `30` | `30` | Empty-queue idle stop. |
| `AVATAR_BATCH_POLL_INTERVAL_SECONDS` | `2` | `2` | Poll sleep between empty claims. |
| `AVATAR_BATCH_LEASE_SECONDS` | `1800` | at least expected job duration | Alias fallback: `AVATAR_JOB_LEASE_SECONDS`, `AVATAR_LEASE_SECONDS`. |
| `AVATAR_JOB_HEARTBEAT_SECONDS` | `60` | `60` | Alias fallback: `AVATAR_HEARTBEAT_SECONDS`. |
| `AVATAR_BATCH_MAX_ATTEMPTS` | `2` | `2` or `3` | Alias fallback: `AVATAR_JOB_MAX_ATTEMPTS`, `AVATAR_MAX_ATTEMPTS`. |
| `AVATAR_BATCH_REQUIRE_APPROVED_SOURCE_CONSENT` | `true` | `true` | Requires private media consent before claim. |
| `AVATAR_BATCH_CONCURRENCY_PER_GPU` | `1` | `1` | Worker rejects drain when not `1`. |
| `AVATAR_BATCH_CANDIDATES_PER_USER` | `4` | `4` | Used by claim/cost assumptions. |
| `AVATAR_BATCH_SOFT_STOP_BEFORE_DEADLINE_SECONDS` | `60` | `60` or higher | Alias fallback: `AVATAR_JOB_DEADLINE_SAFETY_SECONDS`, `AVATAR_DEADLINE_SAFETY_SECONDS`. |
| `AVATAR_ALLOW_STALE_LEASE_RECOVERY` | `true` | `true` | Allows expired running jobs to be reclaimed under max attempts. |
| `AVATAR_FORCE_SINGLE_JOB_MODE` | `false` | `false` unless incident mitigation | Forces conservative single-job behavior. |
| `AVATAR_JOB_MAX_SCAN` | `250` | `250` | Alias fallback: `AVATAR_CLAIM_MAX_SCAN`. |

## Kill Switch and Cost Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `AVATAR_GPU_WORKER_ENABLED` | `true` | `false` before launch, `true` after gates pass | Stops drain-mode lease claims when false. |
| `AVATAR_DISABLE_NEW_GENERATION` | `false` | `false` after launch | Stops drain-mode lease claims when true. |
| `AVATAR_COST_KILL_SWITCH_ENABLED` | `false` | `false` after cost gates pass | Stops drain-mode lease claims when true. |
| `AVATAR_COST_ENFORCE_BUDGET` | `false` | `true` after budget policy is approved | Turns spend alerts into hard guards. |
| `CLOUD_RUN_L4_GPU_USD_PER_SECOND` | `0.0001867` | confirm current regional price | Cost estimate only. |
| `CLOUD_RUN_CPU_USD_PER_VCPU_SECOND` | `0.000018` | confirm current regional price | Cost estimate only. |
| `CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND` | `0.000002` | confirm current regional price | Cost estimate only. |
| `CLOUD_RUN_GPU_ZONAL_REDUNDANCY` | `false` | match Cloud Run setting | Doubles GPU portion when true. |
| `CLOUD_RUN_VCPU` | `4` | match deployed CPU | Cost estimate input; deploy template may use `8`. |
| `CLOUD_RUN_MEMORY_GIB` | `16` | match deployed memory | Cost estimate input; deploy template may use `32`. |
| `CLOUD_RUN_PRICING_VERSION` | `cloud_run_l4_2026_05` | explicit rollout pricing label | Stored in cost docs. |
| `AVATAR_COST_ALERT_DAILY_USD` | `10` | approved daily alert | Advisory unless budget enforcement is on. |
| `AVATAR_COST_ALERT_MONTHLY_USD` | `200` | approved monthly alert | Advisory unless budget enforcement is on. |
| `AVATAR_COST_HARD_DAILY_GENERATION_LIMIT` | `500` | approved daily hard limit | Stops claims through guard. |
| `AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT` | `10000` | approved monthly hard limit | Stops claims through guard. |

Cost defaults are planning assumptions. Confirm Cloud Run GPU, CPU, memory,
zonal redundancy, logging, storage, Firestore, and Artifact Registry pricing
before production budget approval.

If queue traffic posts explicit payloads to `/tasks/avatar-generation`, also
pause or retarget that queue during rollout. These kill switches guard
lease-claim paths; they are not a substitute for queue-level pause controls in a
direct-push topology.

## Queue Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `JOB_QUEUE_MODE` | `dry_run` in config checker | `cloud_tasks` or `pubsub` | Production dry-run queue mode is an error. |
| `CLOUD_TASKS_PROJECT` | unset | project id | Required for Cloud Tasks and Pub/Sub checks. |
| `GCP_LOCATION` | guidance default `asia-northeast3` | `asia-northeast3` | Queue/service region. |
| `AVATAR_GENERATION_QUEUE_NAME` | guidance default `avatar-generation` | explicit queue name | Cloud Tasks mode. |
| `AVATAR_GENERATION_TASK_URL` | unset | worker task URL | Must be absolute HTTPS in production. |
| `CLIP_EMBEDDING_QUEUE_ENABLED` | `true` in checker | explicit true/false | Controls required CLIP queue env. |
| `CLIP_EMBEDDING_QUEUE_NAME` | guidance default `clip-embedding` | explicit queue name when enabled | Cloud Tasks mode. |
| `CLIP_EMBEDDING_TASK_URL` | unset | CLIP worker URL when enabled | Must be absolute HTTPS in production. |
| `TASK_INVOKER_SERVICE_ACCOUNT` | unset | Cloud Tasks OIDC service account | Needs `roles/run.invoker` on worker service. |
| `TASK_OIDC_AUDIENCE` | unset | worker URL when custom audience is required | Checker warns when omitted in production. |
| `PUBSUB_PUSH_SERVICE_ACCOUNT` | unset | Pub/Sub OIDC service account | Required for Pub/Sub production if task invoker is absent. |
| `PUBSUB_DEAD_LETTER_TOPIC` | unset | explicit dead-letter topic | Pub/Sub poison-message isolation. |
| `AVATAR_QUEUE_DEAD_LETTER_TOPIC` | unset | explicit dead-letter/quarantine doc | Checker warns in Cloud Tasks mode. |
| `AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND` | unset | `1` | Must be explicit; max checker bound is `5`. |
| `AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES` | unset | `1` | Keep <= GPU max concurrent jobs. |
| `AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS` | unset | `1` | Bounded GPU fanout. |
| `AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS` | unset | around `900` | Checker warns below `600`. |
| `AVATAR_QUEUE_MAX_ATTEMPTS` | unset | `3` or lower | Higher values multiply GPU cost. |
| `AVATAR_QUEUE_MIN_BACKOFF_SECONDS` | unset | explicit, for example `30` | Must be <= max backoff. |
| `AVATAR_QUEUE_MAX_BACKOFF_SECONDS` | unset | explicit, for example `600` | Retry bound. |
| `AVATAR_QUEUE_MAX_DOUBLINGS` | unset | explicit, for example `5` | Retry backoff shape. |
| `AVATAR_QUEUE_BATCH_SIZE` | `4` in queue status estimate | match batch plan | Estimate only. |
| `AVATAR_QUEUE_GPU_SECONDS_PER_CANDIDATE` | `30.0` | measured staging value | Estimate only. |
| `AVATAR_QUEUE_GPU_COST_PER_SECOND_USD` | `0.0` | approved cost estimate value | Estimate only. |
| `AVATAR_DEFAULT_CANDIDATE_COUNT` | `4` | `4` | Queue status estimate fallback. |

## QA Env

| Name | Default | Production recommendation | Notes |
| --- | --- | --- | --- |
| `AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD` | `0.65` | keep explicit after calibration | High score rejects. |
| `AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD` | `0.50` | keep explicit after calibration | Medium score requires review. |
| `AVATAR_QA_CHILDLIKE_REJECT_THRESHOLD` | `0.70` | keep explicit after calibration | High score rejects. |
| `AVATAR_QA_CHILDLIKE_REVIEW_THRESHOLD` | `0.45` | keep explicit after calibration | Medium score requires review. |
| `AVATAR_QA_BEAUTIFICATION_REJECT_THRESHOLD` | `0.75` | keep explicit after calibration | High score rejects. |
| `AVATAR_QA_BEAUTIFICATION_REVIEW_THRESHOLD` | `0.50` | keep explicit after calibration | Medium score requires review. |
| `AVATAR_QA_ALLOW_DEV_BYPASS` | `false` | `false` | Ignored in production. |
| `AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW` | `false` | `false` in production | Staging smoke aid only. The code ignores it in production and it should be absent from production deploy env. |
| `AVATAR_OBSERVABILITY_HASH_SALT` | `avatar-observability-v1` | Secret Manager or env managed outside repo | Do not commit if treated as secret. |

## Model Cache and Hugging Face Env

These values are optional and must not be committed with secrets:

| Name | Default | Recommendation | Notes |
| --- | --- | --- | --- |
| `HF_TOKEN` | unset | Secret Manager binding only if gated access is required | Never print or commit. |
| `HF_HOME` | Hugging Face default | writable model cache path | Helps Cloud Run cache behavior inside container filesystem. |
| `TRANSFORMERS_CACHE` | library default | writable model cache path if used | Optional compatibility setting. |
| `HF_HUB_CACHE` | library default | writable model cache path if used | Optional cache location. |

## No-Secrets Rule

Do not commit:

- Hugging Face tokens.
- `AVATAR_WORKER_SHARED_SECRET`.
- ID tokens or bearer tokens.
- Service account JSON keys.
- Signed URLs or private source refs in operator reports.
- `.env` files that contain real project secrets.

Use Secret Manager and IAM bindings for secrets. Operator scripts should write
only redacted JSON reports.
