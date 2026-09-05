> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](avatar-production/CURRENT_ARCHITECTURE.md).
>

# Chat Real Photo P1 Monitoring Checklist

## Required Log Hygiene

- Do not log full signed URLs.
- Do not log private source bucket paths.
- Do not log `userPrivateMedia` payloads.
- Do not log raw vectors or embeddings.

## Suggested Structured Events

- `chat_real_photo.real_photo_issued`
- `chat_real_photo.avatar_fallback`
- `chat_real_photo.denied`
- `chat_real_photo.signed_url_error`
- `chat_real_photo.copy_created`
- `chat_real_photo.copy_error`

## Suggested Log-Based Metrics

- `getChatRealProfilePhoto.real_photo_count`
- `getChatRealProfilePhoto.avatar_fallback_count`
- `getChatRealProfilePhoto.denied_count`
- `getChatRealProfilePhoto.signed_url_error_count`
- `uploadAvatarSourcePhoto.chat_profile_copy_count`
- `uploadAvatarSourcePhoto.chat_profile_copy_error_count`

## Suggested Alerts

- signed URL generation failures > 0 after deploy
- denied count spike after deploy
- fallback count spike after deploy
- chat-profile copy errors > 0
- privacy QA leakage > 0
- public IAM binding detected on chat-profile bucket

## Manual Checks

```sh
python scripts/qa_media_privacy.py --dry_run --fail_on_warning
bash scripts/p1_verify_chat_profile_bucket_iam.sh
python scripts/p1_chat_real_photo_staging_matrix.py --live
```
