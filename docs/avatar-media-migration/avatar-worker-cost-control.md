# Avatar Worker Cost Control

This note is for `seolleyeon-final` staging and later production rollout. It
does not change privacy rules: source photos stay private, candidate preview is
runtime-only, and approved avatars remain the public display asset.

## Cloud Run baseline

Start conservatively:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --project=seolleyeon-final `
  --region=asia-northeast3 `
  --min-instances=0 `
  --max-instances=1 `
  --concurrency=1 `
  --timeout=900
```

Cloud Tasks dispatch deadline should not exceed the worker request timeout:

```powershell
firebase functions:config:set avatar.queue_dispatch_deadline_seconds=900 --project=seolleyeon-final
```

For `.env.seolleyeon-final` / Cloud Run env:

```text
AVATAR_GPU_WORKER_ENABLED=true
AVATAR_DISABLE_NEW_GENERATION=false
AVATAR_COST_KILL_SWITCH_ENABLED=false
AVATAR_WORKER_MAX_REQUEST_SECONDS=900
AVATAR_WORKER_MAX_JOB_SECONDS=300
AVATAR_WORKER_SOFT_STOP_MARGIN_SECONDS=30
AVATAR_BATCHING_ENABLED=true
AVATAR_BATCH_MODE=drain
AVATAR_BATCH_CONCURRENCY_PER_GPU=1
AVATAR_BATCH_MAX_JOBS=1
AVATAR_BATCH_MAX_SECONDS=900
AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS=15
AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS=900
AVATAR_WORKER_DRY_RUN=false
```

## Pause / resume

Pause new generation:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --project=seolleyeon-final `
  --region=asia-northeast3 `
  --update-env-vars AVATAR_DISABLE_NEW_GENERATION=true,AVATAR_COST_KILL_SWITCH_ENABLED=true
```

Resume:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --project=seolleyeon-final `
  --region=asia-northeast3 `
  --update-env-vars AVATAR_DISABLE_NEW_GENERATION=false,AVATAR_COST_KILL_SWITCH_ENABLED=false
```

## Stuck jobs

Inspect queue/job health:

```powershell
python scripts/avatar_queue_status.py --firestore_project seolleyeon-final --fail_stale_over 0
python scripts/avatar_job_lease_sweeper.py --firestore_project seolleyeon-final --dry_run
```

Apply stale lease recovery only after reviewing the dry-run output:

```powershell
python scripts/avatar_job_lease_sweeper.py --firestore_project seolleyeon-final --apply
```

Direct worker requests now stop when the per-job deadline is too close and mark
the job with `avatar_worker_deadline_exceeded`. Kill-switch pauses mark the job
with `avatar_worker_cost_guard_paused` instead of running indefinitely.
