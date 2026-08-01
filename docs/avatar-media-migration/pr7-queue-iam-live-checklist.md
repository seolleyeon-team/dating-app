# PR7-C Queue IAM Live Checklist

This checklist covers the Seolleyeon avatar queue retry/OIDC/IAM live controls
owned by PR7-C. It does not change the upload publisher or PR7-A lease writes.

## Queue Names

Cloud Tasks production queue names:

- Avatar generation: `projects/PROJECT_ID/locations/asia-northeast3/queues/avatar-generation`
- CLIP embedding: `projects/PROJECT_ID/locations/asia-northeast3/queues/clip-embedding`

Publisher env:

- `ENVIRONMENT=production`
- `JOB_QUEUE_MODE=cloud_tasks`
- `GCP_PROJECT=PROJECT_ID`
- `GCP_LOCATION=asia-northeast3`
- `AVATAR_GENERATION_QUEUE_NAME=avatar-generation`
- `CLIP_EMBEDDING_QUEUE_NAME=clip-embedding`
- `AVATAR_GENERATION_TASK_URL=https://AVATAR_WORKER/tasks/avatar-generation`
- `CLIP_EMBEDDING_TASK_URL=https://CLIP_WORKER/tasks/clip-embedding`

Pub/Sub fallback names:

- `AVATAR_GENERATION_TOPIC=avatar-generation`
- `CLIP_EMBEDDING_TOPIC=clip-embedding`
- `PUBSUB_DEAD_LETTER_TOPIC=avatar-worker-dlq`

## Retry And Dead-Letter Controls

Recommended production queue controls:

- `AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND=1`
- `AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES=1`
- `AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS=1`
- `AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS=900`
- `AVATAR_QUEUE_MAX_ATTEMPTS=3`
- `AVATAR_QUEUE_MIN_BACKOFF_SECONDS=30`
- `AVATAR_QUEUE_MAX_BACKOFF_SECONDS=600`
- `AVATAR_QUEUE_MAX_DOUBLINGS=4`
- `AVATAR_QUEUE_DEAD_LETTER_TOPIC=avatar-worker-dlq`

Run the config gate before enabling production traffic:

```sh
python scripts/avatar_queue_config_check.py
```

The check fails production if Cloud Tasks/Pub/Sub is not explicitly configured,
if OIDC caller identity is missing, or if queue concurrency exceeds GPU worker
capacity. Warnings should be resolved before launch unless the production owner
documents an exception.

## OIDC And IAM

Cloud Tasks must mint an OIDC token with:

- `TASK_INVOKER_SERVICE_ACCOUNT=task-invoker@PROJECT_ID.iam.gserviceaccount.com`
- `TASK_OIDC_AUDIENCE=https://AVATAR_WORKER` when Cloud Run expects a custom audience

Grant only the task invoker service account Cloud Run invocation rights:

```sh
gcloud run services add-iam-policy-binding seolleyeon-avatar-worker \
  --region asia-northeast3 \
  --member serviceAccount:task-invoker@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker
```

Use the same `roles/run.invoker` binding for the CLIP worker when Pub/Sub or
Cloud Tasks calls it. Do not use `--allow-unauthenticated` for production worker
services.

Live IAM probe:

```sh
python scripts/avatar_live_iam_check.py \
  --worker_url https://AVATAR_WORKER \
  --use_gcloud_token \
  --audience https://AVATAR_WORKER \
  --describe_task_dry_run \
  --queue_name projects/PROJECT_ID/locations/asia-northeast3/queues/avatar-generation \
  --task_url https://AVATAR_WORKER/tasks/avatar-generation \
  --service_account_email task-invoker@PROJECT_ID.iam.gserviceaccount.com
```

Expected result:

- Unauthenticated `/healthz` returns `401` or `403`.
- Authenticated `/healthz` returns `2xx`.
- The dry-run task description does not print tokens, source photo refs, or
  idempotency keys.

## Backlog Thresholds

Run backlog status:

```sh
python scripts/avatar_queue_status.py \
  --firestore_project PROJECT_ID \
  --firestore_database '(default)' \
  --fail_stale_over 0 \
  --fail_retryable_over 10 \
  --fail_queued_over 25 \
  --fail_p95_age_seconds_over 1800
```

Suggested alert thresholds:

- `stale > 0`: page the queue owner after PR7-A lease fields are live.
- `retryable > 10`: pause new queue fanout and inspect worker errors.
- `queued > 25`: slow uploads or scale worker capacity deliberately.
- `p95 queue age > 1800 seconds`: treat as degraded backlog.

The status script reads generic `avatarJobs` fields and only marks stale jobs
when `processing.leaseExpiresAt` exists and has expired. It reports aggregate
counts and estimates only; it does not print private source refs.
