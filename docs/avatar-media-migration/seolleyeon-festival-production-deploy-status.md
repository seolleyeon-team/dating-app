# seolleyeon-festival production avatar deploy status

Last checked: 2026-05-27

## Status

- Overall status: `BLOCKED_BY_CLOUD_RUN_GPU_QUOTA`
- Production-ready: false
- Public rollout: false
- Source project touched: false
- Worker deployed: false
- Functions deployed for avatar pipeline: false
- Firestore/Storage rules deployed in this run: false
- Flutter/Festival production config switched: false
- Internal production smoke: not run

## Project Guard

- gcloud account: `seolleyeon.official@gmail.com`
- gcloud project: `seolleyeon-festival`
- Firebase active project: `seolleyeon-festival`
- ADC check: `ADC_OK`
- Project number: `597362454449`

## Prepared Resources

- Artifact Registry repo: `asia-northeast3/seolleyeon-repo`
- Worker image:
  `asia-northeast3-docker.pkg.dev/seolleyeon-festival/seolleyeon-repo/seolleyeon-avatar-worker:prod-20260527-source-lock`
- Worker image digest:
  `sha256:8f4151b9b9c60baec69e17d62e211e9558ac66bc8c3ab418a07811752c30019c`

Buckets:

- `seolleyeon-festival-private-source-photos`
- `seolleyeon-festival-avatar-temp`
- `seolleyeon-festival-approved-avatars`
- `seolleyeon-festival-chat-profile-photos`

Bucket posture:

- Location: `ASIA-NORTHEAST3`
- Uniform bucket-level access: enabled
- Public access prevention: enforced
- No `allUsers` / `allAuthenticatedUsers` bindings observed in checked bucket IAM policies

Service accounts:

- `avatar-worker@seolleyeon-festival.iam.gserviceaccount.com`
- `task-invoker@seolleyeon-festival.iam.gserviceaccount.com`
- Functions runtime SA: `597362454449-compute@developer.gserviceaccount.com`

Cloud Tasks:

- Queue: `avatar-generation`
- Location: `asia-northeast3`
- State: `RUNNING`
- Max concurrent dispatches: `1`
- Max dispatches per second: `1`
- Max attempts: `3`

Existing production functions are festival-specific. The avatar pipeline functions remain intentionally undeployed until the worker URL exists and Cloud Tasks OIDC is verified.

## Current Hard Gate

Cloud Run GPU worker deployment is blocked by L4 GPU quota in `asia-southeast1`.

Attempted worker deploy:

```powershell
gcloud run deploy seolleyeon-avatar-worker `
  --project=seolleyeon-festival `
  --region=asia-southeast1 `
  --image=asia-northeast3-docker.pkg.dev/seolleyeon-festival/seolleyeon-repo/seolleyeon-avatar-worker:prod-20260527-source-lock `
  --service-account=avatar-worker@seolleyeon-festival.iam.gserviceaccount.com `
  --gpu=1 `
  --gpu-type=nvidia-l4 `
  --no-gpu-zonal-redundancy `
  --cpu=8 `
  --memory=32Gi `
  --no-cpu-throttling `
  --min-instances=0 `
  --max-instances=1 `
  --concurrency=1 `
  --timeout=1800 `
  --no-allow-unauthenticated
```

Observed blocker:

```text
ERROR: (gcloud.run.deploy) spec.template.metadata.annotations[autoscaling.knative.dev/maxScale]:
You do not have quota for using GPUs without zonal redundancy.
To request quota: g.co/cloudrun/gpu-quota
```

Cloud Quotas API shows the relevant quota IDs:

- `NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion`
- `NvidiaL4GpuAllocPerProjectRegion`

The preferred quota request is:

- Project: `seolleyeon-festival`
- Region: `asia-southeast1`
- GPU: NVIDIA L4
- Zonal redundancy: without zonal redundancy
- Requested value: `1`

Suggested justification:

```text
We need 1 NVIDIA L4 GPU quota for a Cloud Run service in asia-southeast1 for a privacy-preserving avatar generation worker. The service processes one avatar generation job at a time through Cloud Tasks. Initial configuration: max instances 1, min instances 0, concurrency 1, zonal redundancy disabled, no public unauthenticated access. Source photos are private and not exposed to clients.
```

## Do Not Continue Until

1. Cloud Run L4 GPU quota without zonal redundancy is approved for `asia-southeast1`.
2. `seolleyeon-avatar-worker` deploy succeeds.
3. Worker URL is captured.
4. Authenticated `/readyz` returns 200 and unauthenticated `/readyz` returns 403.
5. `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` has `roles/run.invoker` on the worker.
6. Cloud Tasks OIDC target path is verified.

Only after those gates pass may the selected avatar Functions be deployed.
