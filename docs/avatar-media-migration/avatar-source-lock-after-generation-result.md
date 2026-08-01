# Avatar source lock after generation start result

## 1. Status

- status: PASS_PARTIAL
- production-ready: false
- project guard: PASS (`seolleyeon.official@gmail.com`, `seolleyeon-final`, Firebase active `seolleyeon-final`)
- staging live smoke: BLOCKED_BY_CONSENT
- production deploy: not run
- staging deploy: not run

## 2. Policy Implemented

- Before backend avatar upload/generation starts, local photo selection can still be changed.
- After avatar upload/generation starts, the source is locked in Flutter and backend upload rejects a different source with `avatar_source_locked`.
- `failed`, `needs_review`, and `no_previewable_candidates` remain source-locked states.
- Approved avatar lock still takes precedence and returns `avatar_already_approved`.
- The backend keeps the `currentAvatarSourcePhotoId` / `currentAvatarJobId` contract as the worker safety guard.
- The user document stores only public-safe recovery metadata (`onboarding.avatarGenerationJobId`, `onboarding.avatarSourceSelectionVersion`) so Flutter can resume polling after app reload without reading private media.

## 3. Flutter Changes

- Onboarding photo upload blocks picker/delete/change after source lock starts.
- Onboarding failed/no-preview states keep the source locked and show same-photo retry guidance.
- Onboarding reload can recover the locked current job from public-safe user onboarding metadata and recreate the queued job token.
- Profile edit blocks add/remove attempts while an avatar source job is already locked.
- Flutter maps backend `avatar_source_locked` to the safe Korean message: `아바타 생성이 시작되어 사진을 변경할 수 없어요.`

## 4. Backend Changes

- `uploadAvatarSourcePhoto` loads `users/{uid}` and `userPrivateMedia/{uid}` before image parsing/storage.
- It rejects approved avatars before object/job/task creation.
- It rejects any existing current source/current job or locked avatar status before accepting new bytes.
- It re-checks the source lock inside the Firestore transaction so concurrent uploads cannot create a second current job.
- It persists only the current job id and selection version on the user onboarding map for client recovery; no source GCS path, source photo refs, signed URL, or private bucket name is written there.
- If queue enqueue fails after the source lock transaction commits, the job/user status is marked failed with `avatar_queue_enqueue_failed`.
- It does not return private GCS refs, signed URLs, `userPrivateMedia`, or `clipEmbeddings`.

## 5. Worker Validation

- Worker still validates payload job/source against `userPrivateMedia.currentAvatarJobId` and `userPrivateMedia.currentAvatarSourcePhotoId`.
- Worker still requires the source path under `users/{uid}/source/`, active source entry, and `avatarGenerationState=current`.
- Worker re-checks the same contract before final preview persistence.
- No Storage "latest source" scan was introduced.

## 6. Retry Same Source Behavior

- New image bytes through `uploadAvatarSourcePhoto` are not accepted after generation starts.
- Existing UI retry continues to poll/retry the current locked job only.
- No new retry callable was added in this change.
- Uploading a different image remains blocked; queue repair should be implemented as a same-current-job operation if later needed.

## 7. Staging Smoke

- photoA upload: not run
- photoB blocked before approval: not run
- jobA result: not run
- approval: not run
- photoC blocked after approval: not run
- debug lineage: not run
- fixture plan: `out/source_lock_uid_photo_consent_required.txt`, `out/source_lock_uid_photo_map_required.txt`
- blocker: exact source-lock consent is not confirmed yet. `source_lock_uid_photo_consent_map.txt` must be created only after explicit user confirmation.
- existing mini calibration consent rows were not reused because they are exact-row scoped and already approved-lock tested.

## 8. Tests

- `gcloud config get-value account`: PASS
- `gcloud config get-value project`: PASS
- `firebase use`: PASS
- `flutter analyze`: PASS
- `npm --prefix functions run build`: PASS
- `npm --prefix functions test`: PASS, 56 tests
- `flutter test test/photo_upload_screen_avatar_flow_test.dart`: PASS, 12 tests
- `flutter test test/profile_display_image_resolver_test.dart test/chat_profile_photo_service_test.dart test/avatar_source_photo_service_test.dart test/avatar_lock_policy_test.dart`: PASS, 27 tests
- `python -m compileall -q lib/ai_recommend_model/avatar_generation scripts tests`: PASS
- `.venv\Scripts\python.exe -m pytest -q tests`: PASS, 336 passed, 6 skipped

## 9. Privacy QA

- `.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning`: PASS
- Flutter/client private ref grep: PASS, no matches
- private bucket literal grep: PASS, no matches
- signed URL marker grep: PASS, no matches
- raw landmark/blendshape grep: PASS, no matches

## 10. Files Changed

- `functions/src/avatarMedia.ts`
- `functions/src/avatarMedia.test.ts`
- `functions/src/avatarApproval.ts`
- `lib/features/onboarding/screens/photo_upload_screen.dart`
- `lib/features/onboarding/widgets/avatar_generation_messages.dart`
- `lib/features/profile/screens/profile_edit_screen.dart`
- `lib/services/avatar_source_photo_service.dart`
- `lib/shared/utils/avatar_lock_policy.dart`
- `test/avatar_source_photo_service_test.dart`
- `test/avatar_lock_policy_test.dart`
- `test/photo_upload_screen_avatar_flow_test.dart`
- `docs/avatar-media-migration/avatar-source-lock-flow-map.md`
- `docs/avatar-media-migration/avatar-source-lock-after-generation-result.md`
- `out/avatar_source_lock_smoke_report.json`
- `out/avatar_source_lock_smoke_report.csv`
- `out/source_lock_uid_photo_consent_required.txt`
- `out/source_lock_uid_photo_map_required.txt`
- `out/source_lock_uid_photo_fixture_plan.json`
- `out/source_lock_exact_consent_validation.json`

## 11. Remaining Blockers

- P0: staging source-lock live smoke needs explicit confirmation for the exact rows in `out/source_lock_uid_photo_consent_required.txt`.
- P1: after staging smoke passes, selective staging deploy/validation can confirm the backend guard against real callable upload paths.
- PR8.5 mini calibration should proceed only after source-lock smoke passes.

아바타 생성이 시작된 후에는 일반 사용자가 사진을 삭제하거나 교체할 수 없고, 생성은 최초로 잠긴 currentAvatarSourcePhotoId/currentAvatarJobId를 기준으로만 진행된다.
