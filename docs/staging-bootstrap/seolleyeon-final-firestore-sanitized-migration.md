# seolleyeon-final Firestore sanitized migration

Generated: 2026-05-19 KST

## SG-5 result

Status: `SCRIPT_READY_DRY_RUN_REQUIRED`

Script:

- `scripts/migrate_firestore_sanitized_to_staging.py`

Default behavior:

- dry-run by default
- source project: `seolleyeon`
- target project: `seolleyeon-final`
- refuses when source and target are equal
- refuses apply unless `--apply --sanitize_ack`
- refuses destructive delete
- preserves document IDs

## Denied private collections

Default denylist includes:

- `userPrivateMedia`
- `clipEmbeddings`
- `avatarJobs`
- `avatarCandidates`
- `privateMedia`
- `sourcePhotoMetadata`
- `faceEmbeddings`

Collection names containing private, embedding, sourcePhoto, avatarCandidate, avatarJob, temp, signedUrl, or face are denied.

## Sanitized fields and values

The sanitizer recursively drops:

- `photoUrls`
- `onboarding.photoUrls`
- `avatarUrls`
- `approvedAvatarUrl`
- `approvedAvatarStoragePath`
- `realProfilePhotoUrl`
- `chatRealPhotoUrl`
- `sourcePhoto*`
- `gcsUri`
- image refs/URLs
- preview/download/signed URLs
- face/clip embeddings and raw vectors
- temp/candidate image refs

It also drops string values containing:

- `gs://`
- `gcs://`
- private/source/chat-profile/temp/approved avatar bucket markers
- `X-Goog-*`, `GoogleAccessId`, `Signature=`, `Expires=`
- unsafe Firebase Storage source URLs

For `users`, only safe profile-ish fields are retained and `profileImageMode` is forced to `avatar`.

## Commands

Dry-run:

```sh
.venv/Scripts/python.exe scripts/migrate_firestore_sanitized_to_staging.py \
  --source_project seolleyeon \
  --target_project seolleyeon-final \
  --dry_run \
  --report_json out/staging_migration_dry_run.json
```

Apply, only after dry-run review:

```sh
.venv/Scripts/python.exe scripts/migrate_firestore_sanitized_to_staging.py \
  --source_project seolleyeon \
  --target_project seolleyeon-final \
  --apply \
  --sanitize_ack \
  --report_json out/staging_migration_apply.json
```

## SG-5 handoff

```json
{
  "subagent": "SG-5",
  "status": "partial",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firestore_migration": [
    "custom sanitizer script created",
    "apply is guarded",
    "private/image data denied by default"
  ],
  "required_followups": [
    "Run dry-run with credentials after deciding collection allowlist and max doc count.",
    "Review out/staging_migration_dry_run.json.",
    "Apply only if no leakage appears."
  ]
}
```
