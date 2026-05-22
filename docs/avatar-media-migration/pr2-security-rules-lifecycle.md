# PR2 Security, Rules, Lifecycle

This PR owns the guardrails around the avatar/source-photo split. It does not
implement upload, CLIP processing, avatar generation, preview, approval, or ML
QA business logic.

## Buckets

Bucket names can be overridden per environment:

- `SOURCE_PHOTO_BUCKET`, default `seolleyeon-private-source-photos`
- `AVATAR_TEMP_BUCKET`, default `seolleyeon-avatar-temp`
- `APPROVED_AVATAR_BUCKET`, default `seolleyeon-approved-avatars`

Private source photos live at:

```text
gs://seolleyeon-private-source-photos/users/{uid}/source/{photoId}.jpg
```

Avatar temp candidates live at:

```text
gs://seolleyeon-avatar-temp/users/{uid}/jobs/{jobId}/candidates/{candidateId}.png
```

Approved avatars live at:

```text
gs://seolleyeon-approved-avatars/users/{uid}/avatar/{avatarId}.png
```

## IAM Plan

Use uniform bucket-level access and service-account specific permissions. Do
not commit service account keys.

Example deployment commands, with placeholders:

```sh
gcloud storage buckets update gs://seolleyeon-private-source-photos --uniform-bucket-level-access
gcloud storage buckets update gs://seolleyeon-avatar-temp --uniform-bucket-level-access
gcloud storage buckets update gs://seolleyeon-approved-avatars --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-private-source-photos \
  --member=serviceAccount:upload-api-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-private-source-photos \
  --member=serviceAccount:clip-worker-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-private-source-photos \
  --member=serviceAccount:avatar-worker-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-avatar-temp \
  --member=serviceAccount:avatar-worker-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-avatar-temp \
  --member=serviceAccount:cleanup-worker-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

gcloud storage buckets add-iam-policy-binding gs://seolleyeon-approved-avatars \
  --member=serviceAccount:avatar-approval-api-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

Service-account responsibilities:

- `upload-api-sa`: verify authenticated upload requests, write cleaned private
  source photos, write `userPrivateMedia`.
- `clip-worker-sa`: read private source photos and write backend-only
  `clipEmbeddings`.
- `avatar-worker-sa`: read private source photos and write temp candidates.
- `avatar-approval-api-sa`: copy temp candidates to approved avatars and update
  public-safe avatar fields.
- `cleanup-worker-sa`: delete temp candidates and consent/account-deletion media.
- `app-functions-sa`: enqueue tasks and perform backend-only Firestore writes
  when used by existing Firebase Functions.

## Lifecycle

Apply temp-candidate lifecycle only to `seolleyeon-avatar-temp`:

```sh
gcloud storage buckets update gs://seolleyeon-avatar-temp \
  --lifecycle-file=docs/gcs_lifecycle_avatar_temp.json
```

The lifecycle deletes candidate objects under `users/` after 3 days and
temporary working objects under `tmp/` or `working/` after 1 day.

Do not apply generation-complete TTL deletion to
`seolleyeon-private-source-photos`. Source photos are retained for CLIP and
avatar regeneration while consent and account status allow retention.

## Rules And Public Document Invariants

`firestore.rules` denies client access to `userPrivateMedia`, `clipEmbeddings`,
`avatarJobs`, and `avatarCandidates`. Public `users/{uid}` writes are guarded so
source-photo fields, private/temp buckets, signed URL material, CLIP vectors, QA
embeddings, and temp preview URLs cannot be written by clients.

`storage.rules` denies client access to private source and avatar temp paths.
Approved avatars can be read by authenticated app users as display assets, while
client writes are denied.

Firestore rules cannot reliably inspect every deeply nested public
recommendation payload after backend export. Exporters and
`scripts/qa_media_privacy.py` enforce that public recommendation docs do not
contain `sourcePhoto*`, `gcsUri`, private bucket names, signed URLs, raw CLIP
vectors, face embeddings, or long-lived candidate preview URLs.

## Queue Auth

Cloud Tasks or Pub/Sub producers should enqueue job IDs, user IDs, source photo
IDs, and private GCS refs only. They must not enqueue signed URLs or raw image
bytes. Worker endpoints should verify OIDC/IAM calls from the configured task or
topic service account before reading private buckets.

## Local Checks

Run:

```sh
bash scripts/check_avatar_media_privacy.sh
```

Or run the core checks directly:

```sh
python -m compileall -q lib/ai_recommend_model scripts tests
python scripts/qa_media_privacy.py --dry_run --fail_on_warning --scan_client_code
```

The privacy QA script supports fixture mode with `--fixtures_path` and Firestore
mode with `--firestore_project`, `--firestore_database`, collection flags, and
`--model_recs_collection`.
