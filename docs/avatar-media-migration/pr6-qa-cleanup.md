# PR6 Avatar QA, Cleanup, And Deletion Hardening

PR6 adds the production-facing safety interface for avatar QA decisions and the
cleanup/deletion workers for temporary candidates, consent withdrawal, and
account deletion.

## QA Interface

Implementation:

```text
lib/ai_recommend_model/avatar_generation/qa.py
```

Main function:

```python
run_avatar_candidate_qa(source_image_ref, candidate_image_ref, metadata)
```

Returned document fields:

- `adultQa`
- `childlikeRisk`
- `privacyQa`
- `brandQa`
- `beautificationRisk`
- `cropConsistency`
- `uniqueMarkCopyRisk`
- `logoTextWatermarkRisk`
- `faceSimilarityScore`
- `identifiabilityRisk`
- `previewAllowed`
- `requiresHumanReview`
- `rejectReasons`
- `qaVersion`
- `completedAt`

The default behavior is conservative. If local QA models/signals are unavailable,
the result is `requiresHumanReview=true` and `previewAllowed=false`, not a pass.

## QA Signals

Local model integrations can pass summarized signals in `metadata["qaSignals"]`.
Raw face embeddings must never be persisted.

Supported MVP signals include:

- `adultLike`
- `childlikeScore`
- `faceSimilarityScore`
- `beautificationScore`
- `uniqueMarkCopied`
- `idolModelInfluencerLook`
- `cropExpandedToUnseenBody`
- `logoTextWatermarkDetected`
- `notAdultUniversityStudentTone`
- `sexualizedOrNightlife`
- `cropConsistent`
- `brandFit`

Automatic reject reasons include:

- `childlike_or_teenager`
- `too_identifiable`
- `unique_mark_copied`
- `idol_model_influencer_look`
- `too_beautified`
- `crop_expanded_to_unseen_body`
- `logo_text_watermark`
- `not_adult_university_student_tone`

Configurable thresholds:

- `AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD`, default `0.65`
- `AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD`, default `0.50`
- `AVATAR_QA_CHILDLIKE_REJECT_THRESHOLD`, default `0.70`
- `AVATAR_QA_CHILDLIKE_REVIEW_THRESHOLD`, default `0.45`
- `AVATAR_QA_BEAUTIFICATION_REJECT_THRESHOLD`, default `0.75`
- `AVATAR_QA_BEAUTIFICATION_REVIEW_THRESHOLD`, default `0.50`

These thresholds are placeholders and require empirical calibration with a
Seolleyeon test set. QA reduces re-identification and brand risk; it is not a
complete anonymity guarantee.

## Cleanup Worker

Implementation:

```text
lib/ai_recommend_model/avatar_generation/cleanup.py
scripts/avatar_media_cleanup.py
```

Dry-run expired temp candidate cleanup:

```sh
python scripts/avatar_media_cleanup.py \
  --mode expired_candidates \
  --firestore_project seolleyeon
```

Apply expired temp candidate cleanup:

```sh
python scripts/avatar_media_cleanup.py \
  --mode expired_candidates \
  --firestore_project seolleyeon \
  --apply
```

The expired-candidate cleanup deletes only objects in
`seolleyeon-avatar-temp`. It includes rejected, expired, unselected, failed, and
TTL-expired `preview_ready` or `needs_review` candidates. It does not delete
private source photos or approved avatars. Dry-run output separates planned
deletes from actual deletes.

## Consent Withdrawal And Account Deletion

Dry-run user media cleanup:

```sh
python scripts/avatar_media_cleanup.py \
  --mode user_media \
  --uid USER_ID \
  --reason consent_withdrawal \
  --firestore_project seolleyeon
```

Apply user media cleanup:

```sh
python scripts/avatar_media_cleanup.py \
  --mode user_media \
  --uid USER_ID \
  --reason account_deletion \
  --firestore_project seolleyeon \
  --apply
```

Supported reasons:

- `consent_withdrawal`
- `account_deletion`
- `admin_delete`
- `retention_policy`

Actions:

- Delete private source photo objects from `seolleyeon-private-source-photos`.
- Mark `userPrivateMedia/{uid}.sourcePhotos` as `deleted`.
- Set photo consent to false and `sourcePhotoRetention=false`.
- Delete `clipEmbeddings/{uid}`.
- Mark `userPrivateMedia/{uid}.clip.embeddingStatus = "deleted"`.
- Delete temp avatar candidate objects for the user.
- Delete approved avatar object by default for consent withdrawal/account
  deletion.
- Set `users/{uid}.avatar.status = "none"`, clear public avatar URLs, clear
  `onboarding.avatarUrls`, and clear deprecated `onboarding.photoUrls`.
- Cancel pending avatar jobs for the user.

Normal avatar generation completion does not delete source photos. Source photos
are deleted only through the explicit cleanup reasons above or a documented
retention/legal policy.

## Observability

Cleanup summaries return counts only:

- `tempCandidatesDeleted`
- `tempCandidatesPlannedForDelete`
- `sourcePhotosDeleted`
- `approvedAvatarsDeleted`
- `clipEmbeddingsDeleted`
- `usersUpdated`
- `jobsUpdated`
- `candidatesUpdated`

Logs and summaries should not include signed URLs, raw embeddings, or raw image
bytes. GCS refs should be treated as internal operational data and redacted in
user-facing logs.
