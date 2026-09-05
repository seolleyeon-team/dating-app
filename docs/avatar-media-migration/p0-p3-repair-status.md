> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# PR6.5 Avatar Media Privacy Repair Evidence

Status: complete for PR6.5 redo scope as of 2026-05-14.

Changed PR6.5 files:
- `functions/src/index.ts`
- `functions/src/indexPrivacy.test.ts`
- `lib/shared/utils/profile_display_image_resolver.dart`
- `test/profile_display_image_resolver_test.dart`
- `lib/ai_recommend_model/seolleyeon_clip_embedder.py`
- `scripts/qa_media_privacy.py`
- `firestore.rules`
- `tests/test_avatar_media_privacy.py`
- `docs/avatar-media-migration/p0-p3-repair-status.md`

Verified behavior:
- CLIP HTTPS loading rejects signed, private-source, temp-avatar, and storage `/source/` image URLs before `requests.get`.
- Fixture QA flags private/temp/source/signed leakage in public user fields, onboarding `avatarUrls` and `photoUrls`, private media metadata, CLIP metadata, and public recommendation payloads.
- Firestore client writes cannot create avatar display fields and cannot change `avatar.approvedAvatarUrl`, `avatar.approvedAvatarStoragePath`, `onboarding.avatarUrls`, or `onboarding.photoUrls` on normal client update.
- Backend Cloud Functions display snapshots use `readSafePhotoUrl()`, which only returns safe approved avatar URLs or safe `onboarding.avatarUrls[0]`.
- Backend callable email fallback now requires `auth.token.email_verified === true` and a Yonsei email before mapping by `studentEmail`.
- Dart `ProfileDisplayImageResolver` rejects lower-case signed markers, X-Amz markers, GoogleAccessId/signature/expires markers, private/temp buckets, and storage `/source/` paths.
- Firestore `isSafePublicMediaUrl()` lower-cases marker checks and rejects storage `/source/` paths as far as rules string matching allows.

Commands run:
- `npm --prefix functions test`
  - First RED run: failed on missing `readSafePhotoUrl` and `verifiedYonseiEmailFromAuthToken` exports.
  - Final run: TypeScript build passed; `19` Node tests passed.
- `flutter test test\profile_display_image_resolver_test.dart`
  - First RED run: failed on lower-case signed URL and storage `/source/` path cases.
  - Focused final run: `9` tests passed.
- `flutter test test\profile_display_image_resolver_test.dart test\avatar_source_photo_service_test.dart`
  - Final run: `12` Dart tests passed.
- `flutter analyze --no-pub lib test`
  - Pass: `No issues found! (ran in 13.3s)`.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_media_privacy.py -q`
  - First RED run: failed on missing Firestore helper coverage.
  - Redo RED run: failed on missing lower-case/source-path rules assertions.
  - Final run: `43 passed in 16.06s`.
- `python scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `python -m compileall -q scripts lib\ai_recommend_model`
  - Pass, exit code `0`.
- `rg -n "seolleyeon-avatar-temp|seolleyeon-private-source-photos" lib\features lib\services lib\shared`
  - Expected Dart profile display resolver guard matches only.
- `rg -n "userPrivateMedia|clipEmbeddings" lib`
  - Expected backend AI/avatar pipeline matches only.
- `rg -n "X-Goog-Signature|x-goog-signature|X-Amz-Signature|x-amz-signature|GoogleAccessId|googleaccessid|Signature=|signature=|Expires=|expires=|signedUrl|getSignedUrl" functions lib\features lib\services lib\shared scripts lib\ai_recommend_model tests`
  - Expected tests, QA, migration checks, backend signed URL generation, backend/Dart guards, and AI-model sanitizer matches.

Remaining risks / out of scope:
- `functions/src/avatarApproval.ts` still contains backend `getSignedUrl` usage observed by `rg`; not changed because this redo targeted display propagation guards and auth fallback, not approval URL issuance semantics.
- Full Firebase emulator rule execution was not run; rules were hardened and covered by static privacy regression tests.

## PR6.6 Upload / Approval Idempotency Repair

Status: complete for PR6.6 P1-A scope as of 2026-05-14.

Changed PR6.6 files:
- `functions/src/avatarMedia.ts`
- `functions/src/avatarMedia.test.ts`
- `functions/src/avatarApproval.ts`
- `functions/src/avatarApproval.test.ts`
- `docs/avatar-media-migration/p0-p3-repair-status.md`

Verified behavior:
- Duplicate upload uses the existing sha256 source photo and stable avatar job idempotency key.
- Existing `queued`, `running`, `qa_pending`, `preview_ready`, `approved`, or `completed` avatar jobs are not reset to `queued`.
- Upload retry does not regress an already approved `users/{uid}.avatar.status`.
- Cloud Tasks mode uses deterministic task names derived from idempotency keys and treats `ALREADY_EXISTS` as idempotent success.
- Pub/Sub payload builders include `idempotencyKey`.
- Approval reserves the candidate/job/user state before copying, writes `approvedAvatarUrl` only after the approved-bucket copy succeeds, and returns existing approved state for same-candidate repeat calls.
- Different-candidate approval conflicts with `avatar_already_approved`.

Commands run:
- `npm --prefix functions test`
  - Pass: `13` Node tests passed after `tsc` build.
- `python scripts/qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `rg -n "idempotencyKey|selectedCandidateId|avatar_already_approved|approve" functions scripts lib`
  - Expected upload/approval functions, tests, worker payloads, and recommendation gating references.
- `rg -n "onboarding\.photoUrls|photoUrls|approvedAvatarUrl" lib functions`
  - Expected backend approval writes, upload deletion of legacy `photoUrls`, resolver/recommendation reads of approved avatar fields, and migration/debug references.

Remaining risks / out of scope:
- The tests cover pure planning helpers and compile-time integration. Full Firestore transaction race behavior still requires emulator or staging verification.

## PR6.7 FLUX Worker Staging Repair

Status: implemented for staging handoff as of 2026-05-14.

Changed PR6.7 files:
- `lib/ai_recommend_model/avatar_generation/model_adapters/flux2_klein.py`
- `lib/ai_recommend_model/avatar_generation/worker.py`
- `lib/ai_recommend_model/avatar_generation/worker_service.py`
- `lib/ai_recommend_model/avatar_generation/Dockerfile`
- `requirements_avatar_worker.txt`
- `scripts/avatar_worker_smoke_test.py`
- `tests/test_avatar_generation_worker.py`
- `docs/avatar-media-migration/pr6.7-flux-worker-staging.md`
- `docs/avatar-media-migration/p0-p3-repair-status.md`

Verified behavior targeted by PR6.7:
- `Flux2KleinAdapter.generate_candidates()` uses the local Diffusers FLUX path
  through `Flux2KleinImageGenerator`, deterministic seeds, source GCS loading,
  and temp candidate refs instead of a placeholder exception.
- Missing `diffusers.Flux2KleinPipeline` fails fast.
- `ENVIRONMENT=production` defaults to `flux`, rejects dry-run mode, and rejects
  `AVATAR_WORKER_DRY_RUN=true`.
- Production HTTP requests require explicit Cloud Run IAM posture or app-level
  shared secret posture.
- Local smoke testing exercises the dry-run fixture path and QA interface while
  redacting source refs from the report.

Commands run:
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_generation_worker.py -q`
  - Pass: `13 passed in 11.62s`.
- `python -m compileall -q lib\ai_recommend_model\avatar_generation scripts tests`
  - Pass, exit code `0`.
- `python scripts\avatar_worker_smoke_test.py --dry_run --output_report_json tmp\avatar_worker_smoke_report.json`
  - Pass: report status `ok`, mode `dry_run`, `previewReadyCount` `4`, and source ref redacted as `gs://<private-source-photo-redacted>`.
- `rg -n "NotImplemented|Unimplemented|dry_run|Flux2Klein|black-forest-labs/FLUX.2-klein-4B|diffusers" lib\ai_recommend_model\avatar_generation scripts tests requirements_avatar_worker.txt docs\avatar-media-migration`
  - Expected matches only; no production `NotImplemented`/`Unimplemented` remains in the avatar generation path.

Remaining risks / out of scope:
- Real FLUX inference requires a GPU host with a diffusers build that exposes
  `Flux2KleinPipeline` and access to the gated model if Hugging Face requires it.
- Local verification environment is CPU-only (`torch 2.10.0+cpu`) and does not
  have `diffusers.Flux2KleinPipeline`; real GPU smoke is `BLOCKED_BY_ENV`.
- PR6.7 does not implement PR6.8+ real ML QA scoring.

## PR6.8 QA v1 Local Signals Repair

Status: complete for PR6.8 P1-C scope as of 2026-05-14.

Changed PR6.8 files:
- `lib/ai_recommend_model/avatar_generation/qa.py`
- `tests/test_avatar_qa_cleanup.py`
- `tests/test_avatar_generation_worker.py`
- `docs/avatar-media-migration/p0-p3-repair-status.md`

Verified behavior:
- `run_avatar_candidate_qa()` performs local/GCS best-effort image loading.
- QA hard-rejects signed URL markers, corrupt/undecodable images, blank or near-monochrome candidates, identical source/candidate images, and high similarity.
- QA computes a local similarity signal using resized image difference plus perceptual hash.
- Missing or unavailable hard checks remain `needs_review` with `previewAllowed=false` unless non-production dev bypass is explicitly enabled.
- `AVATAR_QA_ALLOW_DEV_BYPASS=true` cannot bypass QA in production.
- Hard local rejects override otherwise passing injected QA signals.
- Worker integration stores `needs_review` candidate/job states when QA requires review.
- QA result documents store scores and decisions only, not raw embeddings.

Commands run:
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_qa_cleanup.py -q`
  - Pass: `18 passed in 3.00s`.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_generation_worker.py -q`
  - Pass: `14 passed in 80.58s`.
- `python scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `rg -n "previewAllowed.*true|always pass|return true|stub|TODO|NotImplemented|AVATAR_QA_ALLOW_DEV_BYPASS" lib\ai_recommend_model\avatar_generation scripts tests`
  - Expected matches only: dev bypass guard and its test.

Remaining risks / out of scope:
- OCR/text/logo detection is conservative in local QA v1. Explicit signed/text markers reject; richer OCR/vision classification still needs production calibration data.
- Similarity thresholds are heuristic and require calibration against a Seolleyeon validation set.

## PR6.9 Worker Auth / Cleanup Wiring Repair

Status: complete for PR6.9 P2 scope as of 2026-05-14.

Changed PR6.9 files:
- `functions/src/avatarMedia.ts`
- `functions/src/avatarMedia.test.ts`
- `lib/ai_recommend_model/avatar_generation/worker_service.py`
- `lib/ai_recommend_model/clip_job_service.py`
- `lib/ai_recommend_model/avatar_generation/cleanup.py`
- `scripts/avatar_ttl_cleanup.py`
- `tests/test_clip_job_service.py`
- `tests/test_avatar_generation_worker.py`
- `tests/test_avatar_qa_cleanup.py`
- `docs/avatar-media-migration/pr6.9-auth-cleanup.md`
- `docs/avatar-media-migration/p0-p3-repair-status.md`

Verified behavior:
- Production Cloud Tasks HTTP targets now fail fast unless
  `TASK_INVOKER_SERVICE_ACCOUNT` is configured.
- Cloud Tasks HTTP requests include OIDC tokens with the configured service
  account and `TASK_OIDC_AUDIENCE` when supplied.
- Local unauthenticated Cloud Tasks/worker invocation requires
  `ENVIRONMENT=local` plus `ALLOW_INSECURE_WORKER_LOCAL=true`.
- Production avatar worker requests require Cloud Run IAM posture or explicit
  shared-secret posture.
- Production CLIP worker requests require Cloud Run IAM posture or explicit
  shared-secret posture; local unauthenticated CLIP calls require
  `ENVIRONMENT=local` plus `ALLOW_INSECURE_WORKER_LOCAL=true` or
  `CLIP_WORKER_ALLOW_INSECURE_LOCAL=true`.
- `cleanup_user_media()` rejects normal avatar-generation cleanup reasons,
  deletes source photos and CLIP embeddings only for consent/account/admin/
  retention reasons, and writes a redacted `avatarMediaCleanupAudit` entry.
- `scripts/avatar_ttl_cleanup.py` is a deployable scheduled cleanup wrapper for
  temp candidate TTL cleanup; default mode is dry-run and it can emit a JSON
  report.

Commands run:
- `.venv\Scripts\python.exe -m pytest tests\test_clip_job_service.py -q`
  - Pass: `5 passed, 6 skipped in 17.00s`. Skipped tests require Flask in the
    local virtualenv; helper-level auth posture tests ran and passed.
- `python -m compileall -q lib\ai_recommend_model scripts tests`
  - Pass, exit code `0`.
- `python scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `rg -n "CLIP_WORKER_AUTH_MODE|CLIP_WORKER_CLOUD_RUN_IAM_ENFORCED|CLIP_WORKER_REQUIRE_SHARED_SECRET|CLIP_TASK_SHARED_SECRET|ALLOW_INSECURE_WORKER_LOCAL" lib\ai_recommend_model tests docs scripts`
  - Expected matches in CLIP/avatar worker auth implementation, tests, and
    docs.
- `npm --prefix functions test`
  - Pass: TypeScript build plus `16` Node tests passed.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_qa_cleanup.py::test_user_media_cleanup_writes_redacted_audit_log tests\test_avatar_qa_cleanup.py::test_avatar_ttl_cleanup_script_defaults_to_dry_run_and_writes_report -q`
  - Pass: `2 passed in 3.83s`.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_generation_worker.py::test_worker_service_local_insecure_bypass_must_be_explicit tests\test_avatar_generation_worker.py::test_worker_service_production_cloud_run_iam_posture_allows_request -q`
  - Pass: `2 passed in 3.99s`.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_qa_cleanup.py tests\test_avatar_generation_worker.py -q`
  - Pass: `37 passed in 78.08s`.
- `python -m compileall -q scripts lib\ai_recommend_model\avatar_generation functions\src`
  - Pass, exit code `0`.
- `python scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `python scripts\avatar_ttl_cleanup.py --help`
  - Pass; confirms `--apply`, `--max_delete_per_run`, and
    `--output_report_json` are exposed.
- `python scripts\avatar_ttl_cleanup.py --firestore_project fake-project --output_report_json tmp\avatar_ttl_cleanup_report.json`
  - Expected environment failure: local credentials/project are not authorized
    for `fake-project` (`403 PermissionDenied`). Fixture-backed tests above
    verified dry-run/report behavior without touching live GCP.
- `rg -n "TASK_INVOKER_SERVICE_ACCOUNT|oidc|run\.invoker|ALLOW_INSECURE_WORKER_LOCAL|cleanup_user_media|AVATAR_CANDIDATE_TTL|avatar_ttl_cleanup|CLEANUP_REQUIRE_AUTH" .`
  - Expected matches in implementation, tests, and docs.
- `rg -n "delete.*seolleyeon-private-source-photos|source.*delete|clipEmbeddings.*delete" .`
  - Expected tests/docs and a noisy generated Android build cache match; no
    normal avatar-generation source deletion path found.

Remaining risks / out of scope:
- Live scheduled cleanup requires real Firestore/GCS credentials, IAM, and a
  Cloud Scheduler or Cloud Run Jobs deployment.
- Existing product account-deletion/consent-withdrawal UI flow still needs to
  call the documented cleanup worker/endpoint in production deployment wiring.

## PR6.10 Production Readiness Cleanup

Status: complete for PR6.10 P3 cleanup scope as of 2026-05-14.

Changed PR6.10 files:
- `scripts/migrate_avatar_media_fields.py`
- `tests/test_avatar_media_privacy.py`
- `docs/avatar_media_security.md`
- `docs/firestore_storage_rules_notes.md`
- `docs/avatar-media-migration/pr4-preview-approval.md`
- `docs/avatar-media-migration/public-url-safe-migration-plan.md`
- `docs/avatar-media-migration/flutter-analyze-known-issues.md`
- `docs/avatar-media-migration/p0-p3-repair-status.md`
- `storage.rules`

Verified behavior:
- `flutter analyze` was separated from avatar-specific checks. One coordinator
  run timed out at a 304-second local command limit; a wider timeout run from
  the PR6.10 subagent completed cleanly. Targeted `lib`/`test` and resolver
  analyzer checks pass quickly and are documented in
  `docs/avatar-media-migration/flutter-analyze-known-issues.md`.
- Existing public HTTPS original photo URLs are reported as needing controlled
  safe migration and are not downloaded, backfilled, or persisted into
  `userPrivateMedia/{uid}` by the migration script.
- Private `gs://seolleyeon-private-source-photos/...` refs can be backfilled
  only when CLIP/photo consent exists.
- Dry-run migration mode does not create a bulk writer or issue Firestore
  writes; `--apply` is required for mutation.
- User document migration updates remove legacy source-photo public fields and
  never carry a public original source URL into `users/{uid}`.
- Approved avatars use the settled access model: public-readable approved
  avatar bucket/CDN path with backend-only writes. Source-photo and temp
  candidate buckets remain denied to clients.
- `onboarding.avatarUrls` and legacy `onboarding.photoUrls` are backend-owned
  display compatibility fields; clients may read display-safe values but normal
  Firestore client writes cannot create or modify them.
- Public recommendation docs may include `approvedAvatarUrl` under this model,
  while QA rejects private/temp/signed/source refs and raw vector/embedding
  fields.

Commands run:
- `flutter analyze`
  - Coordinator run: timed out after 304 seconds with no findings printed.
  - PR6.10 subagent wider-timeout rerun: pass, `No issues found! (ran in
    318.1s)`.
- `flutter analyze --no-pub lib test`
  - Pass: `No issues found!`.
- `dart analyze lib test`
  - Pass: `No issues found!`.
- `flutter analyze --no-pub lib/shared/utils/profile_display_image_resolver.dart test/profile_display_image_resolver_test.dart`
  - Pass: `No issues found!`.
- `flutter test test/profile_display_image_resolver_test.dart`
  - Pass: `7` Dart tests passed.
- `.venv\Scripts\python.exe -m pytest tests\test_avatar_media_privacy.py -q`
  - First RED run for the new dry-run helper test failed because
    `run_migration` did not exist.
  - Final PR6.10 subagent run: `43 passed in 21.04s`.
  - Coordinator rerun after overlap reconciliation: `43 passed in 18.03s`.
- `.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all counts at `0`.
- `.venv\Scripts\python.exe -m compileall -q scripts tests lib\ai_recommend_model`
  - Pass, exit code `0`.
- `.venv\Scripts\python.exe scripts\migrate_avatar_media_fields.py`
  - Pass: command validation only; printed dry-run mode, public HTTPS originals
    are not automatically migrated to private GCS, and the safe migration plan
    doc path.
- `rg -n 'photoUrls|avatarUrls|sourcePhotoUrls|sourcePhotoRefs|sourcePhotoGcsUri|sourcePhotoIds|userPrivateMedia|clipEmbeddings|avatarJobs|avatarCandidates|seolleyeon-private-source-photos|seolleyeon-avatar-temp' lib\features lib\services lib\shared`
  - Expected client matches only: display resolver reads `avatarUrls` and guards
    the temp bucket marker; upload/save code uses local `photoUrls` parameter
    names while `UserService.saveOnboardingPhotos` removes legacy
    `onboarding.photoUrls` and writes only pending/count metadata. No Flutter
    client references to `userPrivateMedia`, `clipEmbeddings`, `avatarJobs`,
    `avatarCandidates`, `seolleyeon-private-source-photos`, or source-photo
    public fields were found in these app/client paths.

Remaining risks / out of scope:
- Live migration `--apply` was not run. It still requires an explicit project,
  credentials, operator approval, and a controlled rollout.
- Public HTTPS original photo migration remains a separate safe backend
  re-upload/reprocessing project; PR6.10 only documents and enforces that the
  dry-run-first migration will not silently perform it.
- Full Firebase emulator rule execution was not run in this pass; rules were
  inspected and covered by fixture/string privacy tests.

## Final Coordinator Verification Snapshot

Status: P0/P1/P2/P3 repair bundle accepted for staging preparation as of
2026-05-14. Real production GPU execution and live GCP deployment remain
environment work, not local verification claims.

Additional final changes verified:
- Final code-review blocker fixes were applied after the initial review:
  backend display serialization now uses `isSafePublicMediaUrl`, avatar
  callable email fallback now requires a verified Yonsei auth email, CLIP worker
  HTTP auth fails closed in production, and the Flutter resolver no longer
  contains private/temp bucket-name literals.
- `functions/src/avatarMedia.ts` upload response includes the safe `photoId`
  required by the upload contract and still omits source `gcsUri`, signed URLs,
  and private storage paths.
- `lib/services/avatar_source_photo_service.dart` parses `photoId` from the
  callable response without accepting or exposing source refs.
- `test/avatar_source_photo_service_test.dart` covers the safe `photoId`
  response parse.

Final commands run:
- `npm --prefix functions test`
  - Pass: TypeScript build plus `19` Node tests passed.
- `flutter test test\avatar_source_photo_service_test.dart test\profile_display_image_resolver_test.dart`
  - Pass: `12` Dart tests passed.
- `python scripts\qa_media_privacy.py --dry_run --fail_on_warning`
  - Pass with all warning counts at `0`.
- `npm --prefix functions run build`
  - Pass.
- `.venv\Scripts\python.exe -m pytest tests -q`
  - Pass: `97 passed, 6 skipped`.
- `python scripts\avatar_worker_smoke_test.py --dry_run --output_report_json tmp\avatar_smoke_report.json`
  - Pass: dry-run worker report emitted with source refs redacted.
- `$env:PYTHON_BIN='.venv\Scripts\python.exe'; bash scripts/check_avatar_media_privacy.sh`
  - Pass: privacy QA, Python tests, TypeScript build, and targeted Flutter
    tests passed.
- `flutter analyze --no-pub lib test`
  - Pass: `No issues found!`.
- `rg -n "seolleyeon-avatar-temp|seolleyeon-private-source-photos" lib\features lib\services lib\shared`
  - Pass: no matches after replacing Flutter bucket-name literals with generic
    storage-source/candidate path guards.
