> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# PR1 Backend Private Upload Endpoint

PR1 adds the first production upload boundary for source photos. The Flutter
client no longer uploads original profile photos directly to Firebase Storage.
It calls a Firebase callable function, and the backend stores only a cleaned
private source image.

## Callable

Function name:

```text
uploadAvatarSourcePhoto
```

Request payload:

```json
{
  "imageBase64": "base64 image bytes",
  "contentType": "image/jpeg | image/png | image/webp",
  "fileName": "optional original filename",
  "slotIndex": 0,
  "uid": "optional authenticated app uid"
}
```

Auth:

- Firebase Auth is required through callable `request.auth`.
- The function resolves the app user from the authenticated Firebase session.
- If `uid` is supplied, it must match the resolved app user ID.
- Student verification is enforced by the existing app-user resolver.

Response payload:

```json
{
  "jobId": "avatar_job_...",
  "avatarStatus": "queued",
  "message": "avatar_generation_queued",
  "duplicate": false
}
```

The response intentionally does not include source photo URLs, signed URLs, GCS
paths, download tokens, source photo IDs, or public display URLs.

## Backend Processing

The function:

1. Validates content type and decoded size.
2. Uses `sharp` to rotate, flatten, normalize to JPEG, and strip metadata.
3. Computes the SHA-256 digest of cleaned bytes.
4. Dedupes by active `sourcePhotos[].sha256` for the same user.
5. Stores non-duplicate cleaned bytes at:

```text
gs://seolleyeon-private-source-photos/users/{uid}/source/{photoId}.jpg
```

6. Writes `userPrivateMedia/{uid}` with active source-photo metadata and consent.
7. Sets `users/{uid}.profileImageMode = "avatar"` and `avatar.status = "queued"`.
8. Deletes public legacy `users/{uid}.onboarding.photoUrls` and top-level
   `photoUrls`.
9. Creates or updates `avatarJobs/{jobId}` in `queued` status.
10. Enqueues avatar generation and CLIP embedding jobs, or records dry-run queue
    behavior in local/dev mode.

## Queue Modes

Environment variables:

- `JOB_QUEUE_MODE=dry_run|cloud_tasks|pubsub`
- `SOURCE_PHOTO_BUCKET`
- `MAX_SOURCE_PHOTO_BYTES`
- `MAX_SOURCE_PHOTO_PIXELS`
- `AVATAR_GENERATION_QUEUE_NAME`
- `CLIP_EMBEDDING_QUEUE_NAME`
- `AVATAR_GENERATION_TASK_URL` for Cloud Tasks, usually ending in
  `/tasks/avatar-generation`
- `CLIP_EMBEDDING_TASK_URL` for Cloud Tasks, usually ending in
  `/tasks/clip-embedding`
- `AVATAR_GENERATION_TOPIC`
- `CLIP_EMBEDDING_TOPIC`
- `GCP_PROJECT`
- `GCP_LOCATION`

`dry_run` is the safe local default. It logs redacted job payloads only.

`cloud_tasks` creates HTTP Cloud Tasks. Queue names may be short queue IDs or
full `projects/{project}/locations/{region}/queues/{queue}` names. Task target
URLs must point to the Cloud Run/worker endpoints above and should use OIDC via
`TASK_INVOKER_SERVICE_ACCOUNT`.

`pubsub` publishes JSON payloads to the configured topics.

Queue payloads include private GCS refs for backend workers, but logs redact
those refs and no signed URLs are generated.

## Flutter Flow

Changed upload screens:

- Onboarding photo upload
- Profile edit photo upload

The screens:

- ensure the Firebase session is attached to the verified app user,
- call `AvatarSourcePhotoService.uploadPickedImage`,
- store only a local non-URL queued marker such as
  `avatar_generation_queued:{jobId}` in the in-memory photo grid,
- show an avatar-generation pending placeholder,
- call `UserService.saveOnboardingPhotos` only to update upload count/status,
- never write original download URLs to `users/{uid}`.

Existing `onboarding.avatarUrls` can still be loaded to display an approved
avatar. `onboarding.photoUrls` is not used as a display source.
