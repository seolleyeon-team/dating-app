> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# Festival bridge final report

Last updated: 2026-05-28

## Status

- Overall status: `PASS_INTERNAL_BRIDGE_SMOKE`
- Production-ready: false
- Public rollout: false
- Flutter/Festival config switched: false

## Boundary

- GPU host project: `seolleyeon-final`
- Data/control project: `seolleyeon-festival`
- Existing staging worker touched: false
- Source project `seolleyeon` touched: false

## Worker

- Service: `seolleyeon-avatar-worker-festival`
- Region: `asia-southeast1`
- Latest ready revision: `seolleyeon-avatar-worker-festival-00005-f6f`
- Runtime service account: `avatar-worker-festival-bridge@seolleyeon-final.iam.gserviceaccount.com`
- Image: `asia-northeast3-docker.pkg.dev/seolleyeon-final/seolleyeon-repo/seolleyeon-avatar-worker:festival-bridge-20260528-data-project`
- Firestore/data env: `seolleyeon-festival`
- Buckets env: `seolleyeon-festival-private-source-photos`, `seolleyeon-festival-avatar-temp`, `seolleyeon-festival-approved-avatars`
- `/readyz`: unauthenticated `403`, authenticated `200`

## Functions

Selected functions deployed to `seolleyeon-festival`:

- `uploadAvatarSourcePhoto`
- `getAvatarJobCandidates`
- `approveAvatarCandidate`
- `getChatRealProfilePhoto`

Functions task target:

- `AVATAR_GENERATION_TASK_URL=https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app/tasks/avatar-generation`
- `TASK_OIDC_AUDIENCE=https://seolleyeon-avatar-worker-festival-810450765203.asia-southeast1.run.app`

Temporary bridge note:

- `CLIP_EMBEDDING_QUEUE_ENABLED=false` because no festival CLIP task target is deployed for this bridge smoke path.

## Smoke

Internal smoke used fresh `seolleyeon-festival` test UIDs and synthetic StyleGAN test fixtures.

Latest smoke evidence:

- Upload callable returned `200`.
- Callable response safety check passed.
- Cloud Task was enqueued to the bridge worker target.
- Worker processed the job from `queued` to `running` to `qa_pending`.
- Worker wrote job state and candidates to `seolleyeon-festival`.
- Worker terminal state was safe fallback: `no_previewable_candidates / qa_requires_review`.
- Candidate docs had no hard reject; candidates were `needs_review` because production bridge QA model signals were unavailable/uncertain.
- Approval and approved-lock retest were not applicable because no previewable candidate was returned.
- Source lineage report showed one current source/job and no current-contract mismatch.

## Privacy

- `qa_media_privacy.py --dry_run --fail_on_warning`: pass.
- Private refs and signed URL greps were classified as backend/test/doc only.
- Flutter/Festival client code was not changed to reference private buckets or private collections.
- No service account keys were committed.
- Temporary Token Creator grant used for internal smoke token generation was removed.

## Verification

- `npm --prefix functions run build`: pass.
- `npm --prefix functions test`: pass.
- `python -m compileall -q lib/ai_recommend_model/avatar_generation scripts tests`: pass.
- `.venv\Scripts\python.exe -m pytest -q tests`: pass, 341 passed / 6 skipped.
- `.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning`: pass.

## Remaining work

- Run a separate previewable-fixture approval smoke before any user-facing rollout or Flutter/Festival config switch.
- Keep `seolleyeon-festival` Cloud Run L4 quota request active.
- After quota approval, deploy the worker directly in `seolleyeon-festival`, update the task URL, rerun smoke, and retire the bridge.
