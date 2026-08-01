# PR3 CLIP Private GCS Job Processing

PR3 makes CLIP consume backend-only private source photos and keeps user-facing
recommendation exports display-safe.

## Job Handler

Script and HTTP service:

```text
lib/ai_recommend_model/seolleyeon_clip_job_handler.py
lib/ai_recommend_model/clip_job_service.py
```

The Cloud Tasks HTTP service accepts `POST /tasks/clip-embedding` and reuses the
same handler as the CLI. Accepted direct Cloud Tasks/HTTP JSON or Pub/Sub push
wrapper:

```json
{
  "uid": "user_123",
  "sourcePhotoIds": ["src_001"],
  "sourcePhotoRefs": [
    "gs://seolleyeon-private-source-photos/users/user_123/source/src_001.jpg"
  ],
  "embeddingVersion": "clip-vit-large-patch14_v1",
  "jobType": "clip_embedding",
  "schemaVersion": "clip_job_v1",
  "idempotencyKey": "user_123:src_001:clip_embedding_v1"
}
```

Runtime behavior:

1. Validate `schemaVersion == clip_job_v1` and `jobType == clip_embedding`.
2. Load authoritative `userPrivateMedia/{uid}`.
3. Require `photoConsent.clipRecommendation == true`.
4. Require `photoConsent.profileDisplayOriginalPhoto == false`.
5. Select only active `sourcePhotos` where
   `purpose.clipRecommendation == true`.
6. Use only `gs://` or `gcs://` refs from the private media document.
7. Reject non-allowlisted GCS buckets.
8. Compute normalized CLIP profile embedding from up to 3 private source refs.
9. Write backend-only `clipEmbeddings/{uid}`.
10. Update `userPrivateMedia/{uid}.clip.embeddingStatus`.

The handler ignores payload `sourcePhotoRefs` as an authority source and uses
the private media document instead. This prevents a queued payload from swapping
in an HTTP URL or public image source.

## CLI

Dry-run with an existing private media document:

```sh
python lib/ai_recommend_model/seolleyeon_clip_job_handler.py \
  --firestore_project seolleyeon \
  --uid USER_ID \
  --source_photo_id src_001 \
  --dry_run
```

Process a payload file:

```sh
python lib/ai_recommend_model/seolleyeon_clip_job_handler.py \
  --firestore_project seolleyeon \
  --payload_json /path/to/clip_job_payload.json
```

Important environment:

- `ALLOWED_GCS_IMAGE_BUCKETS`, default `seolleyeon-private-source-photos`
- `MAX_IMAGE_BYTES`
- `CLIP_MODEL_ID`

## Export Boundaries

`seolleyeon_clip_train_export.py` and `seolleyeon_clip_train_export_v3.py`
default to:

```text
--photo_source private_gcs
--private_media_collection userPrivateMedia
--require_approved_avatar_for_candidates true
--clip_embeddings_collection clipEmbeddings
```

Legacy `users/{uid}.onboarding.photoUrls` loading is migration/debug only and
requires both:

```text
--photo_source legacy_onboarding_photo_urls
--allow_legacy_photo_urls
```

Public recommendation output is filtered through
`filter_recommendation_items_for_display_ready`. Candidate users without an
approved avatar are skipped with `missing_approved_avatar`, and public rec items
must not contain source-photo refs, private bucket names, signed URLs, raw CLIP
vectors, or face embeddings.

SVD, KNN, and RRF exports also default to approved-avatar candidate gating.
