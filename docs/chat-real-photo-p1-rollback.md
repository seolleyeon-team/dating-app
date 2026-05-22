# Chat Real Photo P1 Rollback

Rollback must preserve approved avatar display and must not delete source photos unless consent/account deletion policy requires it.

## Immediate Functional Rollback

1. Disable client entry to chat real photo fetching by shipping Flutter fallback if needed.
2. Deploy callable code that returns avatar fallback only, or temporarily remove the callable from chat UI config.
3. Keep recommendation/public display unchanged: approved avatar only.

## Infrastructure Rollback

Revoke chat-profile bucket access:

```sh
bash scripts/p1_verify_chat_profile_bucket_iam.sh
gcloud storage buckets remove-iam-policy-binding gs://$CHAT_PROFILE_PHOTO_BUCKET \
  --member=serviceAccount:$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT \
  --role=roles/storage.objectAdmin
```

If Token Creator was granted:

```sh
gcloud iam service-accounts remove-iam-policy-binding $FUNCTIONS_RUNTIME_SERVICE_ACCOUNT \
  --member=serviceAccount:$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT \
  --role=roles/iam.serviceAccountTokenCreator
```

## Data Rollback

- Do not delete source photos during feature rollback.
- Chat-profile copies may be deleted only as feature-specific derived assets.
- Preserve `userPrivateMedia.sourcePhotos` and approved avatar fields.
- If disabling the feature, set or migrate `userPrivateMedia.{uid}.chatRealPhoto.enabled=false` through a dry-run/apply migration.

## Verification After Rollback

Run:

```sh
python scripts/p1_chat_real_photo_staging_matrix.py --live
python scripts/qa_media_privacy.py --dry_run --fail_on_warning
```

Expected:

- authorized chat requests return `avatar` fallback
- non-participants remain denied
- no signed URLs in users/chat_rooms/public docs
- Flutter public/recommendation screens still show approved avatars
