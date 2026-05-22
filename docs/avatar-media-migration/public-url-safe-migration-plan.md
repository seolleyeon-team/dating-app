# Public HTTPS Original Photo Safe Migration Plan

Existing public HTTPS original photo URLs must not be automatically converted
into private source-photo assets.

`scripts/migrate_avatar_media_fields.py` intentionally does not download public
originals, does not strip EXIF from those originals, and does not write those
URLs into `userPrivateMedia/{uid}.sourcePhotos`. It only backfills private media
from existing `gs://seolleyeon-private-source-photos/...` references when consent
exists.

## Required Controlled Path

1. Confirm consent for avatar generation, CLIP recommendation use, and source
   retention.
2. Fetch or request the source image through a backend-controlled flow only.
3. Validate image type and size.
4. Strip EXIF and normalize the cleaned image.
5. Write cleaned bytes to
   `gs://seolleyeon-private-source-photos/users/{uid}/source/{photoId}.jpg`.
6. Write only private metadata to `userPrivateMedia/{uid}`.
7. Queue CLIP/avatar jobs with private `gs://` source refs.
8. Remove or tombstone old public-original URL fields after verification.
9. Run `scripts/qa_media_privacy.py --dry_run --fail_on_warning`.

## Explicit Non-Goals

- Do not persist signed URLs.
- Do not write public HTTPS originals into `users/{uid}`,
  `userPrivateMedia/{uid}`, or public recommendation docs.
- Do not make `onboarding.photoUrls` a display fallback.
- Do not claim migrated avatars are fully anonymous.

## Rollback

If a controlled migration fails, keep the user in a non-display-ready state until
an approved avatar exists. Do not restore public source photo fallbacks.
