# Festival bridge current state

Last checked: 2026-05-28

## Guard

- Active gcloud account: `seolleyeon.official@gmail.com`
- Active gcloud project at check time: `seolleyeon-festival`
- Active Firebase project at check time: `seolleyeon-festival`
- ADC status: `ADC_OK`
- Source project `seolleyeon`: not touched

This bridge work intentionally uses explicit `--project` flags because it spans:

- GPU host project: `seolleyeon-final`
- Production data/control project: `seolleyeon-festival`

## seolleyeon-final

### Existing staging worker

- Service: `seolleyeon-avatar-worker`
- Region: `asia-southeast1`
- URL: `https://seolleyeon-avatar-worker-lkafkwznta-as.a.run.app`
- Latest ready revision: `seolleyeon-avatar-worker-00045-p7g`
- Service account: `avatar-worker@seolleyeon-final.iam.gserviceaccount.com`
- GPU: `nvidia-l4`
- Max instances: `1`
- Existing env targets staging buckets:
  - `SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos`
  - `AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp`

Hard rule: this service is not a production target and must not be modified for the festival bridge.

### Bridge worker

- Service: `seolleyeon-avatar-worker-festival`
- Region: `asia-southeast1`
- Cloud Run status URL: `https://seolleyeon-avatar-worker-festival-lkafkwznta-as.a.run.app`
- Functions task target URL: `https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app/tasks/avatar-generation`
- Latest ready revision: `seolleyeon-avatar-worker-festival-00005-f6f`
- Service account: `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com`
- Image: `asia-northeast3-docker.pkg.dev/seolleyeon-final/seolleyeon-repo/seolleyeon-avatar-worker:festival-bridge-20260528-data-project`
- Data project env: `seolleyeon-festival`
- Source/temp/approved buckets env: `seolleyeon-festival-*`
- Unauthenticated `/readyz`: `403`
- Authenticated `/readyz`: `200`

### GPU quota

- Quota: `NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion`
- Region: `asia-southeast1`
- Value: `3`

### Artifact Registry

- Repository: `asia-northeast3/seolleyeon-repo`
- Format: Docker

## seolleyeon-festival

### Buckets

All checked buckets exist in `ASIA-NORTHEAST3`, have Uniform bucket-level access enabled, and public access prevention enforced.

- `seolleyeon-festival-private-source-photos`
- `seolleyeon-festival-avatar-temp`
- `seolleyeon-festival-approved-avatars`
- `seolleyeon-festival-chat-profile-photos`

### Cloud Tasks

- Queue: `avatar-generation`
- Location: `asia-northeast3`
- State: `RUNNING`
- Max concurrent dispatches: `1`
- Max dispatches per second: `1`
- Max attempts: `3`

### Service accounts

- `avatar-worker@seolleyeon-festival.iam.gserviceaccount.com`
- `task-invoker@seolleyeon-festival.iam.gserviceaccount.com`

### Existing deployed functions

Current deployed functions include festival-specific recommendation/chat/taste/reveal functions and the selected avatar/chat media functions:

- `uploadAvatarSourcePhoto`: deployed
- `getAvatarJobCandidates`: deployed
- `approveAvatarCandidate`: deployed
- `getChatRealProfilePhoto`: deployed

## Current blocker/risk

`seolleyeon-festival` does not have Cloud Run L4 GPU quota in `asia-southeast1`, so the normal production worker cannot be deployed there yet.

The bridge is deployed and uses explicit `AVATAR_DATA_PROJECT`/`FIRESTORE_PROJECT=seolleyeon-festival`. Internal smoke reached worker processing and safe `no_previewable_candidates` fallback, but did not produce preview candidates for approval/approved-lock retest.
