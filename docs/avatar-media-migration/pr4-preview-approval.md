# PR4 Avatar Preview And Approval APIs

PR4 adds backend-only access to generated avatar candidates and makes approval
the single path that writes public display avatar fields.

## Functions

Callable exports:

```text
getAvatarJobCandidates
approveAvatarCandidate
```

Source:

```text
functions/src/avatarApproval.ts
functions/src/index.ts
```

Both callables use the existing app-user resolver in `functions/src/index.ts`.
The authenticated app user must own the job or candidate.

## Preview API

Request:

```json
{
  "jobId": "avatar_job_..."
}
```

Response:

```json
{
  "jobId": "avatar_job_...",
  "status": "preview_ready",
  "candidates": [
    {
      "candidateId": "cand_...",
      "previewUrl": "short-lived signed URL generated at request time",
      "qaSummary": {
        "status": "pass"
      }
    }
  ]
}
```

Preview filtering:

- `avatarJobs/{jobId}.uid` must match the authenticated user.
- `avatarCandidates` must match both `jobId` and `uid`.
- Candidate `status` must be `preview_ready`.
- Candidate `qa.previewAllowed` must be `true`.
- Expired candidates are hidden.
- Candidate `imageRef` must be in `gs://seolleyeon-avatar-temp/...`.

The API does not return `imageRef`, source-photo refs, private GCS paths, raw QA
internals, face embeddings, or long-lived preview URLs. Signed preview URLs are
created only for the response and are not written to Firestore.

## Approval API

Request:

```json
{
  "candidateId": "cand_..."
}
```

Response:

```json
{
  "avatarStatus": "approved",
  "approvedAvatarUrl": "https://cdn.example/approved-avatars/users/{uid}/avatar/{avatarId}.png",
  "avatarId": "avatar_...",
  "selectedCandidateId": "cand_..."
}
```

Approval checks:

- Authenticated user owns the candidate and job.
- Candidate is `preview_ready`.
- Production access model is public-readable approved avatars with backend-only
  writes. The approved URL should come from `APPROVED_AVATAR_PUBLIC_BASE_URL` or
  an equivalent CDN/object public path.
- Firebase Storage download-token URLs are compatibility-only and may be used
  only for approved avatar objects, never source photos or temp candidates.
- `qa.previewAllowed == true`.
- Candidate is not expired.
- Candidate source object is in the avatar temp bucket, never the private source
  bucket.
- A different already approved candidate is rejected by default.

Approval copies the candidate from:

```text
gs://seolleyeon-avatar-temp/users/{uid}/jobs/{jobId}/candidates/{candidateId}.png
```

to:

```text
gs://seolleyeon-approved-avatars/users/{uid}/avatar/{avatarId}.png
```

Then it writes:

- `users/{uid}.profileImageMode = "avatar"`
- `users/{uid}.avatar.status = "approved"`
- `users/{uid}.avatar.approvedAvatarUrl`
- `users/{uid}.avatar.approvedAvatarStoragePath`
- `users/{uid}.avatar.avatarId`
- `users/{uid}.avatar.selectedCandidateId`
- `users/{uid}.avatar.sourceJobId`
- `users/{uid}.onboarding.avatarUrls = [approvedAvatarUrl]`
- `avatarJobs/{jobId}.status = "approved"`
- `avatarCandidates/{candidateId}.status = "approved"`

These public display writes are backend-only. Clients may read
`approvedAvatarUrl`/`onboarding.avatarUrls` for display but cannot write them
through normal Firestore rules.

By default the approval API deletes `users/{uid}.onboarding.photoUrls`. If
`WRITE_LEGACY_ONBOARDING_PHOTO_URLS=true`, it writes only
`[approvedAvatarUrl]` for MVP compatibility.

## Environment

- `AVATAR_TEMP_BUCKET`, default `seolleyeon-avatar-temp`
- `APPROVED_AVATAR_BUCKET`, default `seolleyeon-approved-avatars`
- `APPROVED_AVATAR_PUBLIC_BASE_URL`, production public/CDN base URL for the
  public-readable approved avatar bucket
- `AVATAR_PREVIEW_URL_MINUTES`, default `10`, capped at `30`
- `WRITE_LEGACY_ONBOARDING_PHOTO_URLS`, default `false`

## Dependencies

PR4 expects PR5 to create `avatarCandidates` with temp-bucket `imageRef` values
and PR6 to populate `qa.previewAllowed`. Until PR5/PR6 are active, these APIs can
be exercised with fixture candidate documents.
