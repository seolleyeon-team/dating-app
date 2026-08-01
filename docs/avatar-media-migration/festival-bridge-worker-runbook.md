# Festival bridge worker runbook

Last updated: 2026-05-28

## Why this bridge exists

`seolleyeon-festival` does not yet have Cloud Run NVIDIA L4 GPU quota in `asia-southeast1`. `seolleyeon-final` has L4 no-zonal quota, so a temporary bridge worker is deployed in `seolleyeon-final` while all production avatar data remains in `seolleyeon-festival`.

This bridge is temporary. It must be retired after `seolleyeon-festival` receives its own Cloud Run L4 quota.

## Project boundary

| Boundary | Project |
|---|---|
| GPU host project | `seolleyeon-final` |
| Production data project | `seolleyeon-festival` |
| Cloud Tasks queue project | `seolleyeon-festival` |
| Functions project | `seolleyeon-festival` |

Existing staging worker:

- `seolleyeon-final / asia-southeast1 / seolleyeon-avatar-worker`
- Not used by production.
- Not modified for the bridge path.

Bridge worker:

- `seolleyeon-final / asia-southeast1 / seolleyeon-avatar-worker-festival`
- Cloud Run status URL: `https://seolleyeon-avatar-worker-festival-lkafkwznta-as.a.run.app`
- Functions task target URL: `https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app/tasks/avatar-generation`
- Revision: `seolleyeon-avatar-worker-festival-00005-f6f`
- Image: `asia-northeast3-docker.pkg.dev/seolleyeon-final/seolleyeon-repo/seolleyeon-avatar-worker:festival-bridge-20260528-data-project`
- Digest: `sha256:07c8b736a3d18f7b345660f42732007f6b2272375dc23d4a42aaf5810535836f`
- Runtime SA: `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com`

## Runtime env

The bridge worker is configured with:

```text
ENVIRONMENT=production_bridge
AVATAR_DATA_PROJECT=seolleyeon-festival
FIRESTORE_PROJECT=seolleyeon-festival
GCP_PROJECT=seolleyeon-festival
SOURCE_PHOTO_BUCKET=seolleyeon-festival-private-source-photos
AVATAR_TEMP_BUCKET=seolleyeon-festival-avatar-temp
APPROVED_AVATAR_BUCKET=seolleyeon-festival-approved-avatars
AVATAR_WORKER_AUTH_MODE=cloud_run_iam
AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true
AVATAR_WORKER_DRY_RUN=false
AVATAR_REFERENCE_PRIVACY_PREPROCESS=true
AVATAR_PREVIEW_FILL_HARD_REJECT=false
AVATAR_CANDIDATE_TRAIT_QA_ENABLED=true
AVATAR_COST_ENFORCE_BUDGET=true
AVATAR_COST_KILL_SWITCH_ENABLED=false
AVATAR_TRAIT_LOCAL_FILES_ONLY=false
AVATAR_WORKER_DEADLINE_SECONDS=1800
AVATAR_WORKER_MAX_REQUEST_SECONDS=1800
AVATAR_WORKER_MAX_JOB_SECONDS=1500
```

The worker code fails closed in `production_bridge` if the data project is not `seolleyeon-festival` or if any avatar/source/temp bucket points to `seolleyeon-final-*`.

## Functions env

`functions/.env.seolleyeon-festival` points `seolleyeon-festival` Functions to:

```text
AVATAR_GENERATION_TASK_URL=https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app/tasks/avatar-generation
TASK_OIDC_AUDIENCE=https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app
TASK_INVOKER_SERVICE_ACCOUNT=task-invoker@seolleyeon-festival.iam.gserviceaccount.com
CLIP_EMBEDDING_QUEUE_ENABLED=false
AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS=1800
```

Deployed selected functions:

- `uploadAvatarSourcePhoto`
- `getAvatarJobCandidates`
- `approveAvatarCandidate`
- `getChatRealProfilePhoto`

## IAM summary

See `docs/avatar-media-migration/festival-bridge-iam-table.md`.

Key active bridge permissions:

- Bridge SA has `roles/datastore.user` on project `seolleyeon-festival`.
- Bridge SA has `roles/storage.objectViewer` on `gs://seolleyeon-festival-private-source-photos`.
- Bridge SA has `roles/storage.objectAdmin` on `gs://seolleyeon-festival-avatar-temp`.
- `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` has `roles/run.invoker` on the bridge service.

## Verification completed

- Unauthenticated bridge `/readyz`: 403.
- Authenticated bridge `/readyz`: 200.
- Ready response includes `dataProject=seolleyeon-festival`.
- Cloud Tasks OIDC preflight to `/readyz`: 200 after IAM propagation.
- Functions build/test passed.
- Selected functions deployed to `seolleyeon-festival`.
- Firestore/Storage rules deployed to `seolleyeon-festival`.
- Privacy QA passed.

## Internal smoke gate

Run with internal `seolleyeon-festival` test UIDs and synthetic StyleGAN test fixtures only.

Smoke result:

- Upload callable: passed with safe response and queued avatar job.
- Cloud Tasks to bridge worker: passed.
- Worker data boundary: Firestore/job state in `seolleyeon-festival`, logs in bridge service under `seolleyeon-final`.
- Worker completion: passed to safe terminal fallback for synthetic fixtures.
- Latest terminal result: `no_previewable_candidates / qa_requires_review`.
- Preview API / approval / approved-lock retest: not run because no previewable candidate was returned.

Operational interpretation: the bridge path is verified through worker processing and safe QA fallback. This satisfies the bridge smoke gate because the worker reached an expected safe terminal state. It is not a preview/approval smoke yet. Do not switch Flutter/Festival config or call the system production-ready until a previewable internal fixture passes approval and lock retest.

## Rollback

Pause queue:

```powershell
gcloud tasks queues pause avatar-generation `
  --project=seolleyeon-festival `
  --location=asia-northeast3
```

Set kill switches before redeploying selected functions:

```text
AVATAR_DISABLE_NEW_GENERATION=true
AVATAR_COST_KILL_SWITCH_ENABLED=true
```

Disable bridge by removing invoker:

```powershell
gcloud run services remove-iam-policy-binding seolleyeon-avatar-worker-festival `
  --project=seolleyeon-final `
  --region=asia-southeast1 `
  --member=serviceAccount:task-invoker@seolleyeon-festival.iam.gserviceaccount.com `
  --role=roles/run.invoker
```

Do not delete source photos as rollback.

## Monitoring

- Cloud Run logs: `seolleyeon-final`, service `seolleyeon-avatar-worker-festival`
- Firestore jobs: `seolleyeon-festival`, collections `avatarJobs`, `avatarCandidates`, `userPrivateMedia`
- Cloud Tasks: `seolleyeon-festival / asia-northeast3 / avatar-generation`
- Cost controls: `max-instances=1`, `min-instances=0`, `concurrency=1`

## Exit plan

When `seolleyeon-festival` L4 quota is approved:

1. Deploy the same worker image or a newer verified image into `seolleyeon-festival`.
2. Update `AVATAR_GENERATION_TASK_URL` to the festival-hosted worker URL.
3. Run production internal smoke.
4. Remove cross-project `run.invoker`.
5. Remove bridge SA permissions on `seolleyeon-festival`.
6. Delete or disable `seolleyeon-avatar-worker-festival`.
