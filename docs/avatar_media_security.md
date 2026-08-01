# Avatar Media Security

Seolleyeon treats original user photos as private recommendation and generation
inputs, never as profile display assets. Public screens must resolve only an
approved avatar URL or render a placeholder. This reduces photo exposure, but it
is not a complete anonymity guarantee: accounts, approvals, operational logs, and
abuse workflows can still link activity to a user when policy or safety requires
it.

## Bucket Separation

- Private source photos: `gs://seolleyeon-private-source-photos/users/{uid}/source/{photoId}.jpg`
  - Backend service accounts only.
  - No public read, no client read/write, no Firebase download URL in Firestore,
    and no signed URL stored or logged.
  - Used only by CLIP embedding and avatar generation workers.
  - Do not apply normal avatar-generation TTL deletion to this bucket.

- Avatar temp candidates: `gs://seolleyeon-avatar-temp/users/{uid}/jobs/{jobId}/candidates/{candidateId}.png`
  - Backend and worker service accounts only.
  - Owner preview is served through a backend API or a short-lived signed URL
    generated at request time only.
  - Signed preview URLs must not be persisted in Firestore, recommendation docs,
    logs, analytics, or push payloads.
  - Default lifecycle deletion is 3 days. Explicit rejected-candidate cleanup may
    delete sooner.

- Approved avatars: `gs://seolleyeon-approved-avatars/users/{uid}/avatar/{avatarId}.png`
  - Display-safe profile asset.
  - Access model: public-readable approved-avatar bucket or CDN path, backend
    writes only. This is the only avatar bucket intended for public display.
  - Direct app display should use `APPROVED_AVATAR_PUBLIC_BASE_URL` in
    production. Firebase Storage token URLs are compatibility-only and must be
    limited to approved avatar objects, never source photos or temp candidates.
  - Clients must not upload or overwrite approved avatars.

## IAM And Service Accounts

- `avatar-upload-api@...`: may write private source photos and update
  `userPrivateMedia/{uid}` after user authentication and consent checks.
- `clip-worker@...`: may read private source photos and write
  `clipEmbeddings/{uid}`. It must not write public `users/{uid}` image fields.
- `avatar-worker@...`: may read private source photos and write avatar temp
  candidates plus backend-only job state.
- `avatar-approval-api@...`: may read temp candidates, copy approved assets to
  the approved bucket, update public avatar fields, and delete rejected temp
  assets.
- Flutter clients: no read/write access to private source photos, avatar temp
  candidates, `userPrivateMedia`, `clipEmbeddings`, `avatarJobs`, or
  `avatarCandidates`.

Production IAM should bind these permissions per bucket and collection instead
of granting broad project storage/admin roles. Prefer Workload Identity or
runtime-attached service accounts over static keys.

## Queue Auth Model

Upload APIs enqueue avatar and CLIP work through Cloud Tasks or Pub/Sub using a
backend service account. Cloud Tasks mode targets `/tasks/avatar-generation` and
`/tasks/clip-embedding`. Worker endpoints must require Cloud Run IAM/OIDC
authentication from the queue service account in production and should verify
the expected audience, issuer, project, and task/topic name. Queue payloads may
contain IDs and private GCS paths, but must not include signed URLs or raw image
bytes.

## Firestore Contract

Public `users/{uid}` documents may contain `profileImageMode`,
`avatar.approvedAvatarUrl`, `avatar.approvedAvatarStoragePath`, and
`onboarding.avatarUrls`.

These display fields are backend-owned. Flutter clients may read them for
display, but must not create or modify `avatar.approvedAvatarUrl`,
`avatar.approvedAvatarStoragePath`, `onboarding.avatarUrls`, or legacy
`onboarding.photoUrls`.

Public `users/{uid}` documents must never contain original source photo URLs,
signed URLs, private GCS URIs, private bucket names, CLIP vectors, face QA
embeddings, or long-lived avatar candidate preview URLs.

Production public display uses the public-readable approved avatar access model:
only objects in `seolleyeon-approved-avatars` may be directly displayed. Firebase
Storage download tokens, when used for local or compatibility paths, are allowed
only for approved avatar display objects. They must never be created for private
source photos or temp candidates.

`onboarding.photoUrls` is deprecated. For MVP compatibility it may contain
`[approvedAvatarUrl]` only, never source photos.

Backend-only collections:

- `userPrivateMedia/{uid}` stores `sourcePhotos.gcsUri`, consent, retention, and
  CLIP source metadata.
- `clipEmbeddings/{uid}` stores raw vectors and source photo IDs.
- `avatarJobs/{jobId}` and `avatarCandidates/{candidateId}` store worker state
  and temporary candidate references.

## Lifecycle And Retention

Apply `docs/gcs_lifecycle_avatar_temp.json` to `seolleyeon-avatar-temp` for the
default 3-day TTL:

```sh
gcloud storage buckets update gs://seolleyeon-avatar-temp --lifecycle-file=docs/gcs_lifecycle_avatar_temp.json
```

Do not apply this lifecycle config to `seolleyeon-private-source-photos` or
`seolleyeon-approved-avatars`. Source photos are retained according to consent,
account state, abuse/legal hold policy, and account deletion workflows. Approved
avatars remain until replaced, deleted, consent is withdrawn for display, or the
account is deleted.

## Consent And Account Deletion

On consent withdrawal:

- Mark active `sourcePhotos` as `deleted` or `blocked`.
- Delete private source objects when retention is no longer consented or legally
  required.
- Delete CLIP embeddings and set `userPrivateMedia.clip.embeddingStatus =
  "deleted"`.
- Delete temp candidates, QA face embeddings, and temporary signed URLs.
- Keep approved avatars only if the user still consents to profile display.

On account deletion:

- Delete private source photos, temp candidates, approved avatars, CLIP
  embeddings, avatar jobs/candidates, QA embeddings, and public display fields.
- Remove queued tasks where supported, or make workers no-op when the account is
  already deleted.
- Keep only the minimal records required by legal, fraud, or safety obligations.

Face-recognition QA embeddings are temporary QA artifacts and must never be
stored long-term.

Operational cleanup is implemented in `scripts/avatar_media_cleanup.py`. It
defaults to dry-run, deletes only avatar-temp candidates during TTL cleanup, and
deletes private source photos plus CLIP embeddings only for explicit consent
withdrawal, account deletion, admin deletion, or retention-policy actions.
