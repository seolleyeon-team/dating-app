# Chat Real Photo P1 Staging Verification

## Status

Current status: `BLOCKED_BY_DEPLOY_PREREQ` until the staging bucket and callable are live.

## A/B/C Matrix

| Case | Expected | Result | Evidence |
|---|---|---|---|
| A requests B in active chat room, B consent true | `real_photo` | NOT_RUN | Requires live callable and staged users |
| A requests B, B consent false | `avatar` fallback | NOT_RUN | Required fixture |
| C requests B in A/B chat room | deny | NOT_RUN | Requires C ID token |
| A requests non-participant target | deny | NOT_RUN | Required fixture |
| inactive/deleted chat room | deny/fallback | NOT_RUN | Optional fixture |
| blocked relationship | deny/fallback | NOT_RUN | Optional fixture |
| suspended/deleted target | deny/fallback | NOT_RUN | Optional fixture |
| self-view request | deny | NOT_RUN | Required fixture |
| missing chatRealPhoto | `avatar` fallback | NOT_RUN | Optional fixture |

Run:

```sh
python scripts/p1_chat_real_photo_staging_matrix.py --live
```

Dry-run:

```sh
python scripts/p1_chat_real_photo_staging_matrix.py
```

## Upload/Copy Verification

After staging deploy, upload a safe fixture image with `chatPartnerRealPhotoDisclosure=true`.

Verify:

- cleaned source exists in `gs://$SOURCE_PHOTO_BUCKET/users/{uid}/source/{photoId}.jpg`
- chat-profile copy exists in `gs://$CHAT_PROFILE_PHOTO_BUCKET/users/{uid}/chat-profile/{photoId}.jpg`
- `userPrivateMedia/{uid}.chatRealPhoto.enabled == true`
- `users/{uid}` contains no real photo URL or private GCS path
- `chat_rooms/{roomId}` contains no real photo URL, signed URL, or bucket path

## Response Safety

Every callable response must exclude:

- `sourcePhotoRefs`
- `sourcePhotoGcsUri`
- `gcsUri`
- `userPrivateMedia`
- `seolleyeon-private-source-photos`
- `clipEmbeddings`
- raw vectors

If `displayMode == real_photo`, `imageUrl` must be runtime-only and redacted in reports.
The `expiresAt` timestamp must be present and within the configured max TTL of 300 seconds.
The signed URL must point to `CHAT_PROFILE_PHOTO_BUCKET`, not the private source bucket.
Deny cases must report explicit Firebase callable denial statuses such as `PERMISSION_DENIED`, `UNAUTHENTICATED`, or `NOT_FOUND`.
