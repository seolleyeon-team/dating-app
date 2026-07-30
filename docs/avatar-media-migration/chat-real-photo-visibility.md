# Chat Real Profile Photo Visibility

This policy extends the avatar/source-photo separation model without changing
public recommendation display.

## Public and Pre-Chat Surfaces

Recommendation cards, received-like screens, matching screens, public profile
previews, and pre-chat profile screens must continue to use only the approved
privacy-preserving avatar. They must not read `onboarding.photoUrls`, private
source photo metadata, temp avatar candidates, signed URLs, `userPrivateMedia`,
or `clipEmbeddings`.

## Chat-Only Real Photo Rule

Real uploaded profile photos may be shown only after an active chat room exists
between the requester and the target user. Access is authorized by:

- Firebase Auth requester UID.
- `chat_rooms/{chatRoomId}.participantIds` containing both requester and target.
- active chat room status.
- no blocked/deleted/suspended participant state when those fields exist.
- `userPrivateMedia/{targetUid}.photoConsent.chatPartnerRealPhotoDisclosure == true`.
- an enabled `userPrivateMedia/{targetUid}.chatRealPhoto` asset in the
  restricted chat-profile bucket.

If any product eligibility check fails for an otherwise authorized participant,
the UI falls back to the approved avatar. Non-participants are denied.

## Asset Separation

The private source bucket remains backend-only:

- `seolleyeon-private-source-photos`: source photo assets for avatar generation
  and CLIP only.
- `seolleyeon-chat-profile-photos`: restricted copy of the EXIF-stripped upload
  for chat-partner display only.
- `seolleyeon-approved-avatars`: public-safe approved avatar display assets.
- `seolleyeon-avatar-temp`: temp candidate assets, never public display.

Flutter does not read source buckets, `userPrivateMedia`, or private GCS refs.
The callable `getChatRealProfilePhoto` returns either an approved-avatar
fallback or a short-lived runtime URL for the chat-profile copy. Signed URLs are
not stored in Firestore.

## Consent

New uploads include an explicit checkbox for:

`photoConsent.chatPartnerRealPhotoDisclosure`

Existing users with missing consent are treated as false. The dry-run migration
script reports users who can be migrated, but `--apply` is required for writes
and only consented users are eligible.

## Migration

Dry-run:

```bash
python scripts/migrate_chat_real_photo_visibility.py --firestore_project seolleyeon
```

Apply, after consent and bucket/IAM verification:

```bash
python scripts/migrate_chat_real_photo_visibility.py --firestore_project seolleyeon --apply
```

The migration never writes real photo URLs to `users/{uid}` or `chat_rooms`, and
it does not persist signed URLs.
