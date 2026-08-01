# Festival bridge IAM table

Last updated: 2026-05-28

## Principals

| Principal | Project | Purpose |
|---|---|---|
| `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` | `seolleyeon-final` | Cloud Run runtime identity for the temporary festival bridge worker |
| `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` | `seolleyeon-festival` | Cloud Tasks OIDC identity used to invoke the bridge worker |
| `service-810450765203@serverless-robot-prod.iam.gserviceaccount.com` | `seolleyeon-final` | Cloud Run service agent that pulls the worker image |

## Applied IAM

| Principal | Resource | Role | Reason | Applied |
|---|---|---|---|---|
| `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` | project `seolleyeon-festival` | `roles/datastore.user` | Read/write `avatarJobs`, `avatarCandidates`, `userPrivateMedia`, and cost/job metadata in the production data project | yes |
| `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` | `gs://seolleyeon-festival-private-source-photos` | `roles/storage.objectViewer` | Read cleaned private source photos for authorized avatar jobs | yes |
| `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` | `gs://seolleyeon-festival-avatar-temp` | `roles/storage.objectAdmin` | Write/read/delete temporary avatar candidates and QA artifacts as required by the worker | yes |
| `service-810450765203@serverless-robot-prod.iam.gserviceaccount.com` | `seolleyeon-festival/asia-northeast3/seolleyeon-repo` | `roles/artifactregistry.reader` | Allow Cloud Run in `seolleyeon-final` to pull the production worker image if needed | yes |
| `seolleyeon.official@gmail.com` | `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` | `roles/iam.serviceAccountUser` | Allow deployment using the bridge runtime service account | yes |
| `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` | Cloud Run service `seolleyeon-avatar-worker-festival` in `seolleyeon-final` | `roles/run.invoker` | Allow festival Cloud Tasks to invoke the bridge worker through OIDC | yes |
| `service-597362454449@gcp-sa-cloudtasks.iam.gserviceaccount.com` | `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` | `roles/iam.serviceAccountUser` | Allow Cloud Tasks service agent to mint OIDC tokens for the task invoker service account | already present |

## Not granted

- No project Owner/Editor was granted to the bridge service account.
- No project-level Storage Admin was granted to the bridge service account.
- No approved-avatar bucket role was granted to the bridge service account. Approval Functions should handle approved avatar publication unless worker code proves otherwise.
- Existing staging worker service account remains unchanged for this bridge path.
- Temporary `roles/iam.serviceAccountTokenCreator` granted to `seolleyeon.official@gmail.com` on the Firebase Admin SDK service account for internal smoke token generation was removed after smoke.

## Pending IAM

No IAM blocker remains for the bridge path. Keep the cross-project grants temporary and remove them after the worker migrates into `seolleyeon-festival`.

## Rollback IAM

Remove bridge IAM when the normal `seolleyeon-festival` worker is deployed:

```powershell
gcloud projects remove-iam-policy-binding seolleyeon-festival `
  --member=serviceAccount:avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com `
  --role=roles/datastore.user

gcloud storage buckets remove-iam-policy-binding gs://seolleyeon-festival-private-source-photos `
  --member=serviceAccount:avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com `
  --role=roles/storage.objectViewer

gcloud storage buckets remove-iam-policy-binding gs://seolleyeon-festival-avatar-temp `
  --member=serviceAccount:avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com `
  --role=roles/storage.objectAdmin
```
