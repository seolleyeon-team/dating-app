# Avatar Media Data Contract

This contract separates private source photos from display avatars. It does not
claim complete anonymity; it limits public and client-side photo exposure while
allowing backend safety, support, and deletion workflows.

## Public User Document

`users/{uid}` is display-safe:

```json
{
  "profileImageMode": "avatar",
  "avatar": {
    "status": "none | generating | preview_ready | approved | rejected | failed",
    "approvedAvatarUrl": "https://...",
    "approvedAvatarStoragePath": "gs://seolleyeon-approved-avatars/users/{uid}/avatar/{avatarId}.png",
    "avatarId": "avatar_...",
    "selectedCandidateId": "cand_...",
    "sourceJobId": "avatar_job_...",
    "updatedAt": "server_timestamp"
  },
  "onboarding": {
    "avatarUrls": ["https://..."],
    "photoUrls": ["https://... approved avatar compatibility only"]
  }
}
```

`onboarding.photoUrls` is deprecated. Public UI and recommendation display must
not read it. The only MVP-compatible value is `[approvedAvatarUrl]`; source photo
URLs, signed URLs, avatar temp URLs, and private GCS URIs are forbidden.

Display order:

1. `avatar.approvedAvatarUrl` when `avatar.status == "approved"`
2. `onboarding.avatarUrls[0]`
3. placeholder

Public user docs must never contain:

- `sourcePhoto*`, `sourcePhotos`, or private source-photo GCS paths.
- `seolleyeon-private-source-photos` or `seolleyeon-avatar-temp` references.
- Signed URL query material such as `X-Goog-Signature`, `X-Goog-Credential`, or
  `X-Goog-Expires`.
- CLIP vectors, face embeddings, QA embeddings, or long-lived candidate preview
  URLs.

## Private Media Document

`userPrivateMedia/{uid}` is backend-only and stores private source photos,
consent, retention state, and CLIP status.

Required invariants:

- `photoConsent.profileDisplayOriginalPhoto == false`.
- Active `sourcePhotos[].gcsUri` starts with
  `gs://seolleyeon-private-source-photos/users/{uid}/source/`.
- Active source photos have `purpose.clipRecommendation == true` when used for
  CLIP.
- No `downloadUrl`, `signedUrl`, or temp preview URL is stored.

Source photos are not deleted merely because an avatar was generated. They are
deleted only through consent withdrawal, account deletion, explicit moderation,
or retention policy.

## CLIP Embedding Document

`clipEmbeddings/{uid}` is backend-only. It may contain raw vectors and
`sourcePhotoIds`; Flutter must not read it.

Required metadata:

- `modelId`: non-empty string.
- `embeddingVersion`: non-empty string.
- `dims`: positive integer.
- `normalized`: boolean.
- `sourcePhotoIds`: list of source photo IDs.

## Avatar Jobs And Candidates

`avatarJobs/{jobId}` and `avatarCandidates/{candidateId}` are backend worker
state. Candidate previews are temporary and point to `seolleyeon-avatar-temp`.
Owner preview access is through backend authorization or a short-lived signed URL
generated at request time only.

Rejected candidates, temporary signed URLs, and QA face embeddings must be
deleted by explicit cleanup or the avatar-temp bucket lifecycle TTL.

## Public Recommendation Documents

`modelRecs/{uid}/daily/{dateKey}/sources/{algo}` and related public
recommendation outputs may include IDs, ranks, scores, source names, confidence,
and approved avatar display fields.

They must not include `sourcePhoto*`, `gcsUri`, private bucket names, avatar temp
URLs, signed URLs, raw CLIP vectors, face similarity embeddings, or candidate
preview URLs.
