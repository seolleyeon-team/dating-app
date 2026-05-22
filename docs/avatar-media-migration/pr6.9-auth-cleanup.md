# PR6.9 Worker Auth And Scheduled Cleanup

This repair makes production worker invocation and avatar-media cleanup explicit
before any PR7 batch or cost hardening work starts.

## Cloud Tasks OIDC

Production Cloud Tasks mode must set:

- `ENVIRONMENT=production`
- `JOB_QUEUE_MODE=cloud_tasks`
- `TASK_INVOKER_SERVICE_ACCOUNT=task-invoker@PROJECT_ID.iam.gserviceaccount.com`
- `TASK_OIDC_AUDIENCE=https://avatar-worker-url` when the Cloud Run service
  expects a custom audience
- `AVATAR_GENERATION_TASK_URL=https://avatar-worker-url/tasks/avatar-generation`
- `CLIP_EMBEDDING_TASK_URL=https://clip-worker-url/tasks/clip-embedding`

The upload function fails fast in Cloud Tasks mode if
`TASK_INVOKER_SERVICE_ACCOUNT` is missing. Local unauthenticated worker calls are
allowed only with `ENVIRONMENT=local` and `ALLOW_INSECURE_WORKER_LOCAL=true`.

Recommended Cloud Run binding:

```sh
gcloud run services add-iam-policy-binding seolleyeon-avatar-worker \
  --region asia-northeast3 \
  --member serviceAccount:task-invoker@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker
```

Do not deploy the avatar worker with unauthenticated invoker in production.

## Avatar Worker Runtime Auth

For the worker service:

- `ENVIRONMENT=production`
- `AVATAR_WORKER_AUTH_MODE=cloud_run_iam`
- `AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true`

Local bypass is explicit only:

```sh
ENVIRONMENT=local ALLOW_INSECURE_WORKER_LOCAL=true \
python -m avatar_generation.worker_service
```

## CLIP Worker Runtime Auth

The CLIP embedding worker must fail closed before reading private source-photo
refs. Production accepts only one of these postures:

- `ENVIRONMENT=production`
- `CLIP_WORKER_AUTH_MODE=cloud_run_iam`
- `CLIP_WORKER_CLOUD_RUN_IAM_ENFORCED=true`
- `K_SERVICE` present in the Cloud Run runtime

or:

- `ENVIRONMENT=production`
- `CLIP_WORKER_AUTH_MODE=shared_secret` or
  `CLIP_WORKER_REQUIRE_SHARED_SECRET=true`
- `CLIP_TASK_SHARED_SECRET` configured
- request header `X-Seolleyeon-Task-Secret` exactly matches the configured
  secret

Non-production unauthenticated CLIP calls are allowed only for explicit local
work:

```sh
ENVIRONMENT=local ALLOW_INSECURE_WORKER_LOCAL=true \
python lib/ai_recommend_model/clip_job_service.py
```

`CLIP_WORKER_ALLOW_INSECURE_LOCAL=true` is also accepted for CLIP-only local
fixtures. Do not set either insecure-local flag in production.

## Scheduled TTL Cleanup

Deploy `scripts/avatar_ttl_cleanup.py` as a scheduled job or wrap it in Cloud
Run/Cloud Scheduler with OIDC. It deletes only temp avatar candidate objects in
`seolleyeon-avatar-temp` and marks candidate docs expired. It never deletes
private source photos or approved avatars during TTL cleanup.

Dry-run:

```sh
python scripts/avatar_ttl_cleanup.py \
  --firestore_project PROJECT_ID \
  --firestore_database '(default)' \
  --max_delete_per_run 500 \
  --output_report_json tmp/avatar_ttl_cleanup_report.json
```

Apply:

```sh
python scripts/avatar_ttl_cleanup.py \
  --firestore_project PROJECT_ID \
  --firestore_database '(default)' \
  --max_delete_per_run 500 \
  --apply
```

Suggested Cloud Scheduler cadence: hourly or every 6 hours. Keep
`MAX_DELETE_PER_RUN` conservative until staging confirms delete volume.

## Consent Withdrawal And Account Deletion

`cleanup_user_media(uid, reason)` supports:

- `consent_withdrawal`
- `account_deletion`
- `admin_delete`
- `retention_policy`

It deletes private source photos, temp candidates, approved avatar objects when
the avatar consent/display state is removed, and `clipEmbeddings/{uid}`. It also
cancels avatar jobs and writes `avatarMediaCleanupAudit` with counts and a
hashed uid only. The audit document must not contain GCS paths, signed URLs, raw
vectors, or original image bytes.

Normal avatar generation completion is not a valid cleanup reason and must not
delete source photos.

## Rollback

If scheduled cleanup causes unexpected candidate deletion:

1. Disable the scheduler.
2. Re-run the script without `--apply` to inspect planned deletes.
3. Restore candidate docs or temp objects from backups if needed.
4. Leave source-photo cleanup disabled unless the request is a consent,
   account, admin, or retention deletion.
