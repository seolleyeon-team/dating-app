> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md).
>

# Avatar production onboarding restoration — audit & rollout status (2026-08-30)

Verdict: **BLOCKED_PRODUCTION_AVATAR_G004_GATE** (source-side restoration
implemented and locally verified; production activation blocked by open
calibration/runtime gates — see §6).

Baseline recorded before work: HEAD `c844ebd1`,
branch `feat/child-safety-standards-page`, worktree `semisemifinal-main`
(pre-existing dirty set = festival retirement session, untouched).

## 1. Root cause of the disabled onboarding pipeline

Commit `0f6349a9` (2026-08-29, "사진 두장 안추가해도 넘겨지도록 임시로")
introduced two dart-define flags defaulting to `false`
(`lib/features/onboarding/config/onboarding_feature_flags.dart`):

- `REQUIRE_ONBOARDING_PHOTOS=false` → photo minimum 0
- `ENABLE_ONBOARDING_AVATAR_GENERATION=false` → avatar pipeline unreachable

No build script/CI passed either define, so **every shipped build allowed
0-photo onboarding with no avatar**. Server admission itself was open
(kill switches off, UID allowlist unset = fail-open) but unreachable from the
client; the Cloud Tasks queue `avatar-generation` is PAUSED (depth 0).

## 2. What was changed in this session (source only, no deploy)

1. Deleted the bypass flag file; photo minimum is a constant 2.
2. Photo picking now uploads every slot via `uploadOnboardingPhoto`
   (server-validated evidence); the avatar source upload moved from pick-time
   to the "다음" press, removing the first-photo-lock deadlock and matching
   `avatar-state-machine.md`.
3. Server admission (`uploadAvatarSourcePhoto`) now requires ≥2
   server-validated onboarding photo objects
   (`functions/src/onboardingPhotoRequirement.ts`), fail-closed.
4. Resume routing requires an approved avatar to pass the photo step
   (was: client-forgeable `sourcePhotoUploadCount > 0`).
5. `firestore.rules`: `sourcePhotoUploadCount/Status/LastQueuedAt`,
   `avatarGenerationJobId`, `avatarSourceSelectionVersion` are now
   client-write-forbidden.
6. Removed additional client bypass branches: loose
   `_hasApprovedAvatarForProceed` (any URL counted as approved), the
   "no job → assume approved → advance" fallthrough, dead
   `savePhotos` raw-URL writes (already rules-blocked), the
   "사진은 나중에 추가할 수 있어요" copy, and the CI-pinned bypass test
   (inverted to assert the gate).
7. Reentrancy guard + stable `clientRequestId` on the fresh source upload
   (rapid taps → exactly one logical admission).

Details: `avatar-production-onboarding-contract.md`.

## 3. Verification (2026-08-30)

| Suite | Result |
| --- | --- |
| `flutter analyze` | No issues |
| Targeted Flutter tests (photo requirement + avatar flow + resolver) | 31/31 pass |
| Full `flutter test` | see final report (run in progress at doc time) |
| Functions `npm test` (build + all) | 463 pass / 0 fail |
| New functions tests (`onboardingPhotoRequirement.test.ts`) | 7/7 pass |
| Rules emulator (`rules_tests`) incl. new forge tests | see final report |
| Final bypass search (`kRequire…`, `kEnable…`, "사진은 나중에", "사진 없이도") | 0 production-reachable hits (only the new tests asserting absence; stale copies remain in tracked `.g002narrow/` snapshots, flagged for cleanup) |

Pre-existing baseline failures NOT caused by this change: ~72 Python
"Avatar WIP RED" tests (bucket-rename fixture drift, documented in
`docs/audits/production_cleanup/15-…`), 2 Flutter recommendation-WIP tests.

## 4. Fresh cloud baseline (read-only, 2026-08-30)

- Project: `seolleyeon-final` only. `seolleyeon` is in ops
  `forbiddenProjects`; the shipped app (`google-services.json`) points at
  `seolleyeon-final`. The task-prompt assumption "production=seolleyeon" is
  drift; repo+cloud evidence wins.
- Cloud Run `seolleyeon-avatar-worker` (asia-southeast1): traffic 100% on
  revision `…azure-foundry-v1-rpm2-20260823` with
  `AVATAR_WORKER_MODE=azure_gpt_image_2`, `AVATAR_PUBLIC_ROLLOUT_ENABLED=false`,
  fidelity corridor shadow/uncalibrated. Latest ready revision
  `…g004-recovery-v10-20260828` (0% traffic). Revisions v8–v10 have **no
  traceable source commit** (provenance gap).
- Cloud Tasks `avatar-generation` (asia-northeast3): **PAUSED**, depth 0,
  rate 1/s, maxAttempts 3.
- Functions deployed 2026-08-10: kill switches `false`, UID allowlist unset
  (fail-open), `JOB_QUEUE_MODE=cloud_tasks`, `ENVIRONMENT=staging`.

## 5. Repo/cloud drift — the central finding

The canonical Azure GPT-Image-2 worker (deployed and serving) is built from
branch `codex/phase2-provenance-baseline-20260824`, NOT from main:

- `model_adapters/azure_gpt_image_2.py` + transport/rate-limit modules
- `analysis/watermark.py` — graduated text/logo/watermark policy
  (hard_reject / needs_review / allow with source-region corroboration) —
  i.e. the "soft QA false-positive" remediation requested for this task is
  **already implemented on that branch**
- calibration suite + artifact `g004-staging-20260823-v1`
  (calibrated CLIP thresholds, face-similarity review band; cohort n=2–4
  "pre_live" — smaller than the G004 10–20 exact-consent requirement)
- `QA_CONTRACT_VERSION = "avatar_qa_v3_watermark_evidence_v1"`

main still carries the FLUX worker whose July staging calibration failed
(0/56 preview-ready) and a pinned test forbidding "gpt-image" strings.
**Re-implementing QA softening on main was deliberately not done** — it
would duplicate and conflict with the Azure line.

## 6. Open gates blocking production activation

1. **G004 calibration**: last authoritative gate docs say
   `QA-007 blocked_external_evidence`, `QUALITY_QA_PRODUCTION_READY=false`;
   the phase2 calibration artifact is real progress but its cohort
   (n=2–4 pre-live) does not meet the documented 10–20 exact-consent +
   human-signoff requirement. → needs a human-run calibration cohort.
2. **Runtime provenance/merge**: the serving Azure worker's source is on an
   unmerged branch; g004-recovery v8–v10 images lack commit provenance.
   → owner decision: merge `codex/phase2-provenance-baseline-20260824`
   (or its successor) into main before any further deploy.
3. **Functions deploy**: the ≥2-photo server gate exists only in source;
   deployed functions (2026-08-10) do not have it.
4. **Queue**: resuming the PAUSED queue is a production mutation requiring
   the §52 checkpoint (queue is empty, so no stale-task purge needed).
5. Client release build with the restored gate must be shipped
   (compile-time contract).

## 7. Rollout order (when unblocked)

1. Merge Azure worker line into main; reconcile the FLUX-era pinned tests
   and the 72 bucket-fixture RED tests.
2. Complete G004 exact-consent calibration + human signoff; pin QA version.
3. Deploy functions (photo gate + rules) with UID allowlist SET
   (internal accounts only — note allowlist is fail-open when unset).
4. Staging live E2E per §43–47 of the task contract (2 photos → Azure →
   QA → preview → approval → canonical object ×1 → restart/resume).
5. `PRODUCTION_AVATAR_MUTATION_READY` checkpoint → resume queue →
   internal canary → bounded canary → full activation.
6. Never re-introduce a skip path on failure: kill switches pause admission
   (fail-closed retry UX), the photo requirement stays.

## 8. Rollback

- Client gate: revert the commit(s) of this change set (photo requirement
  is compile-time; no server data migration involved).
- Server gate: redeploy previous functions revision; the new module is
  additive and its removal restores prior admission behavior.
- Rules: previous rules file redeploy (guards are additive deny — removal
  is the rollback).
- Queue/worker rollback: `config/avatar-ops/avatar-rollback.json` drill
  (unchanged by this session).
