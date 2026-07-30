# Avatar Internal Canary Checklist

This checklist is for `seolleyeon-final` staging only. Do not use it for
production rollout approval.

## Scope

- 3-5 internal users only.
- Use only photos with explicit consent for staging avatar testing.
- Do not use school logos, text-heavy images, private/signed URLs, or production
  user photos.
- Approved avatars remain the public display image model; source photos remain
  private generation assets.

## Required Staging Configuration

- Cloud Run service: `seolleyeon-avatar-worker`
- Project: `seolleyeon-final`
- Region: `asia-southeast1`
- Min instances: `0`
- Max instances: `1`
- Concurrency: `1`
- Timeout: `900s`
- Batching: off or conservative (`AVATAR_BATCH_MAX_JOBS=1`)
- `AVATAR_WORKER_DRY_RUN=false`
- `AVATAR_REFERENCE_PRIVACY_PREPROCESS=true`
- `AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH=/app/models/face_landmarker.task`
- `AVATAR_PREVIEW_FILL_HARD_REJECT=false`
- `AVATAR_PREVIEW_REQUIRE_FOUR=false`

## Consent and Cleanup

- Record internal tester consent before upload.
- Tell testers source photos are private generation/recommendation assets.
- Consent must include:
  - use of one staging-only source photo for avatar generation QA.
  - temporary storage in `seolleyeon-final` private media buckets.
  - manual review of generated avatar candidates by the product team if needed.
  - permission to collect non-identifying metrics such as timing, QA tier, and
    approval status.
- If a tester asks for cleanup after the test, remove staging-only source and
  temp candidate artifacts through the approved admin/account-deletion cleanup
  path. Do not delete production data.
- Never commit consent photos, generated previews, source paths, signed URLs,
  or tester tokens to the repository.

## Photo Input Quality

- Use one clearly visible adult face.
- Avoid group photos, cropped-half faces, heavy occlusion, masks, sunglasses,
  or extreme angles.
- Avoid text, logos, school names, branded uniforms, and private location
  details.
- Prefer neutral indoor lighting or soft outdoor lighting.
- Do not use production user photos unless the same person explicitly consents
  to this staging canary.

## Safety Gates

- Hard-reject candidates are never shown.
- Preview candidates must be `hard_pass` or `soft_pass` only.
- No raw landmarks or raw embeddings are stored.
- No signed source URL or private GCS reference is stored in Firestore client
  documents or returned to Flutter.
- App Check must be enabled and callable polling must not be blocked.
- Stop the canary immediately if any source path, `gcsUri`, signed URL, raw
  landmark, raw embedding, or private bucket name appears in Flutter-visible
  data.
- Stop the canary if hard-reject candidates are shown, if generated avatars are
  too identifiable, or if childlike/sexualized candidates pass preview.

## Pause / Rollback

Set both flags in staging if generation must stop:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --region=asia-southeast1 `
  --project=seolleyeon-final `
  --update-env-vars=AVATAR_DISABLE_NEW_GENERATION=true,AVATAR_COST_KILL_SWITCH_ENABLED=true
```

Resume only after the issue is understood:

```powershell
gcloud run services update seolleyeon-avatar-worker `
  --region=asia-southeast1 `
  --project=seolleyeon-final `
  --update-env-vars=AVATAR_DISABLE_NEW_GENERATION=false,AVATAR_COST_KILL_SWITCH_ENABLED=false
```

Confirm rollback readiness before starting:

```powershell
gcloud run services describe seolleyeon-avatar-worker `
  --region=asia-southeast1 `
  --project=seolleyeon-final `
  --format="value(status.latestReadyRevisionName)"
```

## Metrics to Collect

- `preview_ready` rate
- candidate count per job
- approval rate
- trait satisfaction feedback
- `totalWorkerSeconds`
- `estimatedUsd`
- `too_identifiable` rate
- childlike risk rate
- beautification risk rate
- `modelLoadSeconds`
- `faceDetectSeconds`
- `traitExtractSeconds`
- `generationSeconds`
- `qaSeconds`
- `rerankSeconds`
- `uploadSeconds`
- preview API payload size
- participant feedback scores

Generate the redacted report after the run:

```powershell
.venv\Scripts\python.exe scripts\avatar_internal_canary_report.py `
  --project seolleyeon-final `
  --uids "<uid1>,<uid2>,<uid3>" `
  --since "<ISO timestamp>" `
  --output_json out/avatar_internal_canary_report.json `
  --output_csv out/avatar_internal_canary_report.csv `
  --redact
```

## Canary Exit Criteria

- At least one valid-face staging job reaches `preview_ready`.
- Approval succeeds and writes `users/{uid}.avatar.approvedAvatarUrl`.
- Approved-avatar lock blocks follow-up generation for the same user.
- No privacy QA warning is introduced.
- Cost and timing remain within the staging budget target.

## User Feedback Questionnaire

Ask each tester after they see the candidate set:

1. 내 분위기가 어느 정도 살아 있나요? 1-5
2. 너무 나 같아서 특정될 것 같나요? 1-5
3. 너무 미화됐나요? 1-5
4. 안경/머리/수염/의상 느낌이 맞나요? 1-5
5. 설레연 프로필로 신뢰감 있나요? 1-5
6. 4장 중 고를 만한 후보가 있었나요? yes/no
7. 다시 생성하고 싶나요? yes/no
8. 기타 의견

## Stop Criteria

- Any privacy leakage into Flutter-visible payloads.
- Any hard-reject candidate shown in preview.
- `preview_ready` rate is 0 for all valid single-face participants.
- Median `totalWorkerSeconds` is above the staging budget target.
- Estimated cost per approved avatar exceeds the internal canary budget.
- Repeated `too_identifiable`, childlike, or beautification QA failures without
  a clear calibration path.

## Post-Canary Cleanup

- Keep only redacted metrics and tester feedback needed for threshold
  calibration.
- Do not retain consent photos in local folders.
- Run the approved staging cleanup path for testers who requested deletion.
- Keep production rollout blocked until a separate production canary gate is
  defined and passed.
