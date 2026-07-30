# PR8.4 Canary Rerun Runbook

This runbook is for `seolleyeon-final` staging only. It prepares normalized
fixture images, validates UID/photo eligibility, and runs the guarded internal
avatar canary only when at least three consented users are safe to process.

Do not use this for production rollout approval.

## Safety Rules

- Use only photos with explicit consent for staging avatar QA.
- Do not use chat attachment images directly.
- Do not deploy to production or mutate the source project `seolleyeon`.
- Do not commit photos, tokens, consent files, signed URLs, generated previews,
  private bucket paths, or auth secret JSON files.
- Do not expose `sourcePhotoRefs`, `gcsUri`, private bucket paths, signed URLs,
  `userPrivateMedia`, `clipEmbeddings`, raw landmarks, or raw embeddings.
- Do not bypass QA, and never preview hard-reject candidates.
- Do not mark production-ready from this canary.

## Required Inputs

Create `canary_uid_photo_map.txt` in the repository root. The file is ignored by
git and should use normalized image paths:

```text
REAL_FIREBASE_UID=C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs\normalized\uid_1_photo_plain.jpg
REAL_FIREBASE_UID_2=C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs\normalized\uid_2_photo_plain.jpg
```

For PR8.4 prepared-user reruns, `canary_uid_photo_map.txt` is only historical
operator context. It is not exact UID/photo consent, and its rows must not be
copied into `pr84_uid_photo_consent_map.txt` unless they exactly match the PR84
required rows below.

Create `canary_uid_photo_consent.txt` in the repository root. It is also ignored
by git. Keep it simple: note that the listed UID participants explicitly
consented to use their photos for `seolleyeon-final` staging avatar QA and
privacy monitoring.

`canary_consent.txt` is also accepted as fallback local general canary consent
evidence when `canary_uid_photo_consent.txt` is absent. If it includes the exact
PR8.4 `UID=photoFile` rows, it can satisfy general exact UID/photo evidence, but
activation still requires the same rows in the separate ignored
`pr84_uid_photo_consent_map.txt` gate file. The general consent validator reports
`scope=general_canary_consent_evidence`,
`consentFileSelection=default|fallback|explicit`, and
`exactUidPhotoConsent.satisfiedByThisFile=true|false`. If the general consent
file contains `UID=photo` rows, the validator normalizes them to `UID=fileName`
and reports matched, missing, and unexpected rows against the PR84 required rows.
A file that says "3 pairs" but contains four legacy rows remains valid general
consent evidence and still fails exact UID/photo activation. When those
general-consent `UID=photo` rows do not match the PR84 required rows, the
post-consent report and completion audit also surface
`general_consent_exact_uid_photo_mismatch`.

Each mapped UID must satisfy all of these before upload:

- It is a real Firebase Auth UID, not a placeholder.
- The local auth secret maps to the same UID.
- The Firestore user is active and staging-eligible.
- The user does not already have an approved avatar lock.
- The mapped file is a normalized plain JPEG under `canary_inputs\normalized`.
- MediaPipe preflight recommends `PASS`.

## Optional Staging User Preparation

If the available local auth secrets are all approved-avatar locked, prepare a
new PR8.4-only staging canary set. Dry-run is the default and does not mutate
staging:

```powershell
.venv\Scripts\python.exe scripts\pr84_prepare_canary_auth_users.py `
  --target_project seolleyeon-final `
  --report_json out\pr84_prepare_canary_auth_users_dry_run.json
```

Apply only after manual review. This mutates `seolleyeon-final` staging Auth and
Firestore, writes generated passwords under `.local_secrets`, and does not touch
production:

```powershell
.venv\Scripts\python.exe scripts\pr84_prepare_canary_auth_users.py `
  --target_project seolleyeon-final `
  --apply `
  --confirm_staging_mutation `
  --secret_file .local_secrets\staging_pr84_canary_users.json `
  --report_json out\pr84_prepare_canary_auth_users_apply.json
```

After apply, the PR8.4 gate, validation, inventory, and runner scripts include
`.local_secrets\staging_pr84_canary_users.json` in their default local secret
lookup. You can still pass `--auth_secret_json` explicitly for stricter control.
Do not commit or print the secret file.

Build a local UID/photo template after the PR84 users exist:

```powershell
.venv\Scripts\python.exe scripts\pr84_canary_mapping_template.py `
  --prepared_users_report_json out\pr84_prepare_canary_auth_users_apply.json `
  --preflight_json out\canary_preflight_report_mediapipe.json `
  --existing_mapping_file canary_uid_photo_map.txt `
  --normalized_dir canary_inputs\normalized `
  --output_txt out\pr84_canary_uid_photo_map_template.txt `
  --output_json out\pr84_canary_uid_photo_map_template.json
```

Then create `pr84_uid_photo_consent_map.txt` only after UID-specific photo
consent is confirmed. Use file names, not private URLs:

```text
pmmHkAR9jpUuMBMnWcqm4tIKLW53=uid_2_photo_plain.jpg
47VcfOmL2nTkzN8LHSbBhY8CEJl2=uid_4_photo_plain.jpg
UzqFhD0o3fg7tZKpWU4ws3wLrCJ2=uid_5_photo_plain.jpg
```

Activate a runnable mapping only after that explicit review:

```powershell
.venv\Scripts\python.exe scripts\pr84_activate_canary_mapping.py `
  --template_json out\pr84_canary_uid_photo_map_template.json `
  --uid_photo_consent_map pr84_uid_photo_consent_map.txt `
  --confirm_uid_photo_consent `
  --output_mapping out\pr84_canary_uid_photo_map_activated.txt `
  --output_json out\pr84_canary_uid_photo_map_activation.json
```

Use `out\pr84_canary_uid_photo_map_activated.txt` as `--mapping_file` only if
the activation status is `READY`. Until it is `READY`, do not run upload/apply
commands. `BLOCKED_CONSENT_MISMATCH` means the consent map contains rows that do
not match the current PR84 prepared UID/photo pairs, often because the historical
`canary_uid_photo_map.txt` was copied. The post-consent report and completion
audit surface this as `uid_photo_consent_map_mismatch`. The activation report
should show:

```json
{
  "status": "READY",
  "activeRowCount": 3,
  "blockedRowCount": 0,
  "matchedConsentPairCount": 3,
  "unexpectedConsentPairCount": 0
}
```

When activation is blocked, the expected next input is an exact
`pr84_uid_photo_consent_map.txt` row for each PR84 UID/photo pair:

```text
pmmHkAR9jpUuMBMnWcqm4tIKLW53=uid_2_photo_plain.jpg
47VcfOmL2nTkzN8LHSbBhY8CEJl2=uid_4_photo_plain.jpg
UzqFhD0o3fg7tZKpWU4ws3wLrCJ2=uid_5_photo_plain.jpg
```

The activation report records the local consent-map state:

```json
{
  "uidPhotoConsentMap": {
    "present": false,
    "pairCount": 0,
    "matchedPairCount": 0,
    "unexpectedPairCount": 0
  }
}
```

Do not infer these rows from general canary consent. Two current PR84 rows reuse
photos that were previously mapped to another UID, so exact UID/photo consent is
required before creating `pr84_uid_photo_consent_map.txt`. A request to
"reference `canary_uid_photo_map.txt`" is ambiguous for PR8.4 and must be treated
as blocked until the exact three PR84 rows are confirmed.

After the consent map exists, use the post-consent runner first. It performs the
project guard, activates only exact consented rows, and then runs the activated
mapping gate:

```powershell
.venv\Scripts\python.exe scripts\pr84_post_consent_canary.py `
  --project seolleyeon-final `
  --general_consent_file canary_consent.txt `
  --report_json out\pr84_post_consent_canary_report.json
```

If `--consent_file` is not supplied, the post-consent runner reuses
`--general_consent_file` for the activated-mapping gate's consent validation.
Without either flag, it falls back to `canary_uid_photo_consent.txt`.

Expected blocked output before the consent map exists includes:

```json
{
  "status": "BLOCKED",
  "inputBlockers": [
    "general_consent_exact_uid_photo_mismatch",
    "uid_photo_pair_consent_missing"
  ],
  "generalConsentEvidence": {
    "valid": true,
    "scope": "general_canary_consent_evidence",
    "exactUidPhotoConsent": {
      "satisfiedByThisFile": false
    }
  },
  "consentMap": {
    "present": false,
    "pairCount": 0,
    "matchedPairCount": 0,
    "unexpectedPairCount": 0
  },
  "gate": {
    "executed": false,
    "safeToApply": false
  },
  "missingConsentRowCount": 3,
  "nextAction": "activate_3_uid_photo_consent_rows"
}
```

When activation is blocked, stale `out/pr84_canary_gate_summary.json` content
must not be treated as fresh gate readiness; the post-consent report keeps
`gate.executed=false` until the activated-mapping gate actually runs in that
same command.

The completion audit follows the same rule. If `post_consent.gate.executed` is
`false`, it keeps stale gate values only as `rawEligibleUploadRows` and
`rawSafeToApply`, reports `freshForPostConsent=false`, and does not count those
raw values toward `mappingHasThreeEligibleRows` or `gateSafeToApplyOrAlreadyRan`.

If `--apply` is requested and the activated-mapping gate step fails, the
post-consent report must stay `BLOCKED_GATE` with `gate_execution_failed` instead
of reporting `APPLY_ATTEMPTED`.

If `--apply` is requested but the guarded runner reports a dry-run or minimum
eligible block such as `BLOCKED_MIN_ELIGIBLE_NO_UPLOAD`, the gate summary should
use `apply_requested_but_runner_did_not_upload`, and the post-consent report
should stay `BLOCKED_RUNNER_NO_UPLOAD` with `apply_runner_did_not_upload`.

If the guarded runner reaches apply mode but any row records a top-level job
error, the runner reports `COMPLETE_WITH_ERRORS` with `jobErrorCount`, exits
non-zero, and the post-consent report must stay `BLOCKED_RUNNER_ERRORS` with
`apply_runner_completed_with_errors`.

The same `COMPLETE_WITH_ERRORS` path is used when any callable response recorded
by the runner has `safeResponse=false`; the runner adds
`responseSafetyViolationCount` and marks the row with `unsafe_callable_response`.
Gate summaries map this status to `fix_runner_errors_before_completion`.

## Project Guard

Stop if any value differs from the expected staging target.

```powershell
gcloud config get-value account
gcloud config get-value project
firebase use
```

Expected:

- `seolleyeon.official@gmail.com`
- `seolleyeon-final`
- Firebase active project `seolleyeon-final`

## Normalize Fixtures

This converts `jpg/jpeg/png/webp/mpo` inputs to plain EXIF-stripped JPEGs and
never overwrites originals.

```powershell
.venv\Scripts\python.exe scripts\normalize_canary_images.py `
  --input_dir C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs `
  --output_dir C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs\normalized `
  --manifest_json out\canary_normalized_manifest.json
```

Expected output includes `normalizedCount`. Normalized file names are
deterministic, such as `uid_1_photo_plain.jpg`.

## MediaPipe Preflight

Use the local MediaPipe Tasks venv when available, because OpenCV fallback does
not match Cloud Run's Face Landmarker behavior closely enough for canary gates.

```powershell
.venv_mediapipe_preflight\Scripts\python.exe scripts\preflight_canary_images_mediapipe_task.py `
  --manifest_json out\canary_normalized_manifest.json `
  --output_json out\canary_preflight_report_mediapipe.json `
  --model_path .cache\avatar_models\face_landmarker.task
```

Allowed recommendations for upload are only:

- `PASS`

Blocked recommendations must not be uploaded unless a separate negative test is
explicitly requested:

- `BLOCK_NO_FACE`
- `BLOCK_MULTI_FACE`
- `BLOCK_FACE_TOO_SMALL`
- `BLOCK_LOW_QUALITY`
- `NEEDS_MANUAL_REVIEW`

## Validate UID Mapping

Run validation before any upload. This checks consent, normalized paths,
preflight output, Firestore user state, local auth UID match, and approved avatar
lock.

```powershell
.venv\Scripts\python.exe scripts\validate_canary_uid_photo_map.py `
  --project seolleyeon-final `
  --mapping_file canary_uid_photo_map.txt `
  --consent_file canary_uid_photo_consent.txt `
  --preflight_json out\canary_preflight_report_mediapipe.json `
  --output_json out\canary_mapping_validation_mediapipe.json `
  --google_services_json android\app\google-services.json `
  --auth_secret_json .local_secrets\staging_test_users.json `
  --auth_secret_json .local_secrets\staging_test_users_de.json
```

The canary runner should only proceed when `eligibleUploadRows >= 3`.

For PR84 prepared users, validate the activated mapping rather than the original
operator mapping:

```powershell
.venv\Scripts\python.exe scripts\validate_canary_uid_photo_map.py `
  --project seolleyeon-final `
  --mapping_file out\pr84_canary_uid_photo_map_activated.txt `
  --consent_file canary_uid_photo_consent.txt `
  --preflight_json out\canary_preflight_report_mediapipe.json `
  --output_json out\canary_mapping_validation_mediapipe.json `
  --google_services_json android\app\google-services.json `
  --auth_secret_json .local_secrets\staging_pr84_canary_users.json
```

Common blockers:

- `block_face_too_small`: use a closer single-face source photo.
- `auth_uid_mismatch_or_missing_secret`: provide a local staging auth secret for
  the exact mapped UID, or map to the UID owned by the available secret.
- `student_email_not_yonsei`: fix staging-only user eligibility metadata, if the
  participant is intended to be eligible.
- `approved_avatar_lock`: do not regenerate for this user; use a different
  consented staging UID.

## Guarded Dry Run

This command must be run before `--apply`. It uploads nothing.

```powershell
.venv\Scripts\python.exe scripts\run_canary_from_validated_map.py `
  --project seolleyeon-final `
  --region asia-northeast3 `
  --mapping_file out\pr84_canary_uid_photo_map_activated.txt `
  --validation_json out\canary_mapping_validation_mediapipe.json `
  --output_json out\pr84_canary_runner_dry_run.json `
  --google_services_json android\app\google-services.json `
  --min_users 3 `
  --auth_secret_json .local_secrets\staging_pr84_canary_users.json
```

Expected dry-run status before live upload:

- `READY_DRY_RUN`
- `eligibleCount >= 3`

If status is `BLOCKED_MIN_ELIGIBLE`, do not use `--apply`.

## Apply Canary

Run only after the dry run is clean. This uploads photos through the actual
staging callable path, waits for worker completion, calls preview API, approves
one preview candidate when available, and retests approved-avatar lock.

```powershell
.venv\Scripts\python.exe scripts\run_canary_from_validated_map.py `
  --project seolleyeon-final `
  --region asia-northeast3 `
  --mapping_file out\pr84_canary_uid_photo_map_activated.txt `
  --validation_json out\canary_mapping_validation_mediapipe.json `
  --output_json out\pr84_canary_runner_apply.json `
  --google_services_json android\app\google-services.json `
  --min_users 3 `
  --apply `
  --auth_secret_json .local_secrets\staging_pr84_canary_users.json
```

Do not use `--allow_partial` for the PR8.4 3-user rerun unless the explicit goal
changes from "3 valid users" to "all currently eligible users."

## One-Command Gate

For the normal PR8.4 path, prefer the gate script. It normalizes inputs, runs
MediaPipe preflight, validates mapping, and performs the guarded runner dry run.
It does not upload unless `--apply` is provided.

```powershell
.venv\Scripts\python.exe scripts\pr84_canary_gate.py `
  --project seolleyeon-final `
  --input_dir C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs `
  --output_dir C:\Users\samsung\StudioProjects\semisemifinal\canary_inputs\normalized `
  --mapping_file out\pr84_canary_uid_photo_map_activated.txt `
  --consent_file canary_uid_photo_consent.txt `
  --auth_secret_json .local_secrets\staging_pr84_canary_users.json `
  --google_services_json android\app\google-services.json `
  --min_users 3
```

## Reports

Generate the redacted internal canary report after upload/approval:

```powershell
.venv\Scripts\python.exe scripts\avatar_internal_canary_report.py `
  --project seolleyeon-final `
  --uids "<uid1>,<uid2>,<uid3>" `
  --since "<ISO timestamp>" `
  --output_json out\avatar_internal_canary_report.json `
  --output_csv out\avatar_internal_canary_report.csv `
  --redact
```

Generate the expanded trait coverage report:

```powershell
.venv\Scripts\python.exe scripts\avatar_trait_coverage_report.py `
  --project seolleyeon-final `
  --uids "<uid1>,<uid2>,<uid3>" `
  --since "<ISO timestamp>" `
  --output_json out\avatar_trait_coverage_report.json `
  --output_csv out\avatar_trait_coverage_report.csv `
  --redact
```

## Current PR8.4 Blocker Snapshot

Latest post-consent apply summary:

- Project guard account: `seolleyeon.official@gmail.com`
- gcloud project: `seolleyeon-final`
- Firebase active project: `seolleyeon-final`
- UID/photo consent map: `pr84_uid_photo_consent_map.txt` present with 3 exact
  PR84 rows
- Activation status: `READY`
- Missing exact UID/photo consent rows: `0`
- Eligible upload rows: `3`
- Runner status: `COMPLETE`
- Completion audit: `PASS_INTERNAL_CANARY_3USER`
- Privacy QA: `pass`

The PR84 prepared users, pass fixtures, exact consent rows, staging eligibility,
apply runner, redacted internal canary report, trait coverage report, and privacy
QA now support the 3-user internal canary pass for `seolleyeon-final` staging.
This remains internal canary evidence only; it is not production rollout
approval.

If `preflight.unmappedPassFixtures` is non-empty, those are normalized JPEG file
names that passed local MediaPipe preflight but are not present in
`canary_uid_photo_map.txt`. They are only a hint for fixing the mapping; do not
upload them unless they are paired with a real consented UID and a matching
staging auth secret.

## Verification

Run privacy QA before reporting canary readiness:

```powershell
.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning
```

Recommended greps:

```powershell
rg -n "userPrivateMedia|clipEmbeddings|sourcePhotoRefs|sourcePhotoGcsUri|gcsUri" lib/features lib/services lib/shared lib/data
rg -n "seolleyeon-private-source-photos|seolleyeon-final-private-source-photos|seolleyeon-avatar-temp|seolleyeon-final-avatar-temp" lib/features lib/services lib/shared lib/data
rg -n "X-Goog-Signature|X-Goog-Credential|X-Goog-Expires|GoogleAccessId|Signature=|signedUrl|getSignedUrl" lib/features lib/services lib/shared lib/data
rg -n "raw_landmarks|face_landmarks|blendshapes" lib/features lib/services lib/shared lib/data
```

## Exit Criteria

PR8.4 can be marked as `PASS_INTERNAL_CANARY_3USER` only when:

- At least three eligible UID/photo rows are uploaded through staging.
- Each uploaded photo belongs to the authenticated mapped UID.
- Each valid job reaches `preview_ready`, `no_previewable_candidates`, `failed`,
  or timeout with a redacted reason.
- Preview API responses contain no private refs or signed URLs.
- Approved candidates write `users/{uid}.avatar.approvedAvatarUrl`.
- Approved-avatar lock rejects a second upload for approved users.
- Timing/cost metrics and trait coverage are reported.
- Privacy QA passes.
