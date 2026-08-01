# Festival bridge worker design

## Purpose

This is a temporary bridge so festival production avatar generation can use `seolleyeon-final` Cloud Run L4 GPU quota while keeping all production data in `seolleyeon-festival`.

The existing `seolleyeon-final` staging worker service must not be used as a production endpoint.

## Design table

| Item | Value |
|---|---|
| Cloud Run host project | `seolleyeon-final` |
| Production data/control project | `seolleyeon-festival` |
| Bridge service name | `seolleyeon-avatar-worker-festival` |
| Existing staging service untouched | `seolleyeon-avatar-worker` |
| Bridge image used | `asia-northeast3-docker.pkg.dev/seolleyeon-final/seolleyeon-repo/seolleyeon-avatar-worker:festival-bridge-20260528-data-project` |
| Runtime service account | `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com` |
| Firestore/data project | `seolleyeon-festival` |
| Source bucket | `seolleyeon-festival-private-source-photos` |
| Temp bucket | `seolleyeon-festival-avatar-temp` |
| Approved avatar bucket | `seolleyeon-festival-approved-avatars` |
| Invoker | `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` |
| Queue | `seolleyeon-festival / asia-northeast3 / avatar-generation` |
| Worker status URL | `https://seolleyeon-avatar-worker-festival-lkafkwznta-as.a.run.app` |
| Functions task target URL | `https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app/tasks/avatar-generation` |
| Functions env | `seolleyeon-festival` Functions point `AVATAR_GENERATION_TASK_URL` to bridge worker URL |

## Required bridge env

The bridge worker must fail closed unless these values are present:

```text
ENVIRONMENT=production_bridge
AVATAR_DATA_PROJECT=seolleyeon-festival
FIRESTORE_PROJECT=seolleyeon-festival
GCP_PROJECT=seolleyeon-festival
SOURCE_PHOTO_BUCKET=seolleyeon-festival-private-source-photos
AVATAR_TEMP_BUCKET=seolleyeon-festival-avatar-temp
APPROVED_AVATAR_BUCKET=seolleyeon-festival-approved-avatars
```

The bridge worker must not use:

```text
seolleyeon-final-private-source-photos
seolleyeon-final-avatar-temp
seolleyeon-final-approved-avatars
```

## Risk review

| Risk | Mitigation |
|---|---|
| Existing staging worker accidentally used | Deploy a separate service named `seolleyeon-avatar-worker-festival`; never point production Functions at `seolleyeon-avatar-worker` |
| Worker writes to `seolleyeon-final` Firestore | Require explicit `AVATAR_DATA_PROJECT`/`FIRESTORE_PROJECT` support before deploy |
| Worker writes to `seolleyeon-final` buckets | Bridge startup must reject any `seolleyeon-final-*` avatar/source/temp bucket |
| Cross-project IAM too broad | Use bridge service account with `roles/datastore.user` on `seolleyeon-festival` and bucket-level storage roles only |
| Cloud Tasks cannot invoke bridge | Grant `roles/run.invoker` on bridge service to `task-invoker@seolleyeon-festival.iam.gserviceaccount.com` and verify IAM before Functions deploy |
| Image pull blocked | Prefer cross-project Artifact Registry Reader for the `seolleyeon-final` Cloud Run service agent; copy image only if needed |
| Signed URL/private ref leakage | Keep existing privacy QA and grep checks; no source refs or signed URLs may be returned to clients |
| Cost/quota overrun | Keep `min-instances=0`, `max-instances=1`, `concurrency=1` |

## Deployment notes

- The bridge uses a rebuilt image in `seolleyeon-final` because it needed explicit bridge data-project support.
- The existing staging worker `seolleyeon-avatar-worker` was not used and was not modified.
- Worker env includes `AVATAR_TRAIT_LOCAL_FILES_ONLY=false` and extended worker deadlines to match the live GPU generation path.
- `seolleyeon-festival` Functions use `CLIP_EMBEDDING_QUEUE_ENABLED=false` for this temporary bridge because no festival CLIP task target is deployed for this smoke path.

## Rollback

- Pause `seolleyeon-festival / asia-northeast3 / avatar-generation` queue.
- Set or deploy kill switches:
  - `AVATAR_DISABLE_NEW_GENERATION=true`
  - `AVATAR_COST_KILL_SWITCH_ENABLED=true`
- Remove or update `AVATAR_GENERATION_TASK_URL` from `seolleyeon-festival` Functions.
- Keep source photos private; do not delete user source photos as rollback.

## Exit plan

When `seolleyeon-festival` Cloud Run L4 quota is approved:

1. Deploy the same worker image into `seolleyeon-festival`.
2. Update `AVATAR_GENERATION_TASK_URL` to the festival-hosted worker.
3. Run internal production smoke.
4. Retire `seolleyeon-avatar-worker-festival`.
5. Remove cross-project IAM bindings.
