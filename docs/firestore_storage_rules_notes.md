# Firestore And Storage Rules Notes

Required deployment rules for the avatar media architecture:

- `users/{uid}`: app reads may access public-safe profile fields. Client writes
  are guarded against source photo fields, private/temp bucket references, signed
  URLs, vectors, candidate preview URLs, and backend-owned avatar display fields
  including `avatar.approvedAvatarUrl`, `avatar.approvedAvatarStoragePath`,
  `onboarding.avatarUrls`, and legacy `onboarding.photoUrls`.
- `userPrivateMedia/{uid}`: client read denied, client write denied. Backend
  service accounts only.
- `clipEmbeddings/{uid}`: client read denied, client write denied. Backend
  service accounts only.
- `avatarJobs/{jobId}` and `avatarCandidates/{candidateId}`: client read/write
  denied. Owner preview must be served through backend authorization, not direct
  Firestore reads.
- `seolleyeon-private-source-photos`: client read/write denied. Backend upload,
  CLIP, and avatar workers only.
- `seolleyeon-avatar-temp`: client read/write denied. Backend/worker only.
  Apply the 3-day lifecycle config in `docs/gcs_lifecycle_avatar_temp.json`.
- `seolleyeon-approved-avatars`: public-readable display bucket, backend write
  only. Direct app display should use `APPROVED_AVATAR_PUBLIC_BASE_URL` in
  production. No source or temp candidates may be stored here.

`onboarding.avatarUrls` is backend-only compatibility state. The approval API may
write `[approvedAvatarUrl]`; Flutter clients should upload source photos through
the backend upload API and must not persist source/original URLs in public user
documents.

Public recommendation documents under
`modelRecs/{uid}/daily/{dateKey}/sources/*` and meeting daily recs may include
candidate IDs, ranks, scores, source ranks, score components, and approved avatar
display fields. They must not include `sourcePhoto*`, `gcsUri`, private bucket
names, avatar temp URLs, signed URLs, raw CLIP vectors, or face similarity
embeddings.

## Queue And Worker Auth

Avatar and CLIP queue producers should enqueue only object IDs, job IDs, and GCS
paths. Queue payloads must not include signed URLs or raw image bytes.

Worker endpoints should accept only OIDC/IAM-authenticated calls from the
expected Cloud Tasks or Pub/Sub service account. Cloud Tasks targets are
`/tasks/avatar-generation` and `/tasks/clip-embedding`. Workers should verify
audience, issuer, project, and topic/task identity before reading private
buckets.

## Deployment Checks

Targeted local checks:

```sh
python -m compileall -q scripts tests lib/ai_recommend_model
python scripts/qa_media_privacy.py --dry_run --fail_on_warning
pytest -q tests/test_avatar_media_privacy.py tests/test_avatar_media_upload.py
```

Targeted project checks that may require local tooling or credentials:

```sh
npm --prefix functions run build
flutter test test/profile_display_image_resolver_test.dart
firebase emulators:exec --only firestore,storage "echo rules loaded"
```
