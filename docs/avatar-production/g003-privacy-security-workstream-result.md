# G003 Privacy/Security Workstream Result

Date: 2026-07-20

## Gate decision

- G003 implementation status: `PRIVACY_REPOSITORY_CHECKPOINT_READY=true`
- G003 repository checkpoint: ready for coordinator review
- `PRIVACY_PRODUCTION_READY=false`
- Overall `production-ready=false`
- Public rollout: unauthorized and not executed

G003 closes the repository-level privacy/security checkpoint for the current
root and Festival avatar work. It does not certify deployed IAM, App Check,
nonowner access denial, account deletion, bridge network behavior, or public
traffic readiness.

Independent final review outcomes are closed:

- TEST_GATE: PASS
- RECOMMENDATION: APPROVE
- ARCHITECT_STATUS: CLEAR

## Implementation scope

- Root `functions/src` remains the canonical avatar backend.
- Sensitive avatar callables require Firebase Auth and set server App Check
  enforcement in `functions/src/avatarMedia.ts`, `chatRealPhoto.ts`, and
  `avatarCleanup.ts`.
- Firestore and Storage rules were tightened around private avatar media,
  server-owned avatar fields, jobs, candidates, embeddings, and storage roles.
- Flutter avatar upload now sends `photo_consent_v4` with purpose-specific
  consent payloads from `lib/services/avatar_source_photo_service.dart` and the
  onboarding consent model/widgets.
- Source retention, consent withdrawal, account deletion, candidate cleanup, and
  sanitized user/private-media cleanup are implemented through
  `functions/src/avatarSourceRetention.ts` and `functions/src/avatarCleanup.ts`.
- Worker privacy and bridge guards are present in
  `lib/ai_recommend_model/avatar_generation/worker.py` and
  `job_lease.py`.
- Static privacy QA was expanded in `scripts/qa_media_privacy.py` to scan
  public user/recommendation surfaces, client code, chat rooms, browser storage,
  public reports, public logs, and Festival build artifacts.
- Root and Festival runtime `print`/`debugPrint` calls are checked for raw ids,
  email, tokens, URLs, paths, errors, and stack traces while allowing only
  fingerprints, safe error summaries, and non-sensitive status metadata.

## Auth and App Check

- Avatar upload, status, preview, approval-adjacent sensitive media paths, chat
  real-photo access, and cleanup paths remain Auth-bound.
- Production-like callable options now use `enforceAppCheck: true`.
- The repository checkpoint proves local enforcement wiring and tests only.
  Live non-App-Check denial was not run because the active gcloud project guard
  is `seolleyeon-festival`, not `seolleyeon-final`.

## Rules and data boundaries

- Public-safe avatar display remains limited to approved status and approved
  avatar URL surfaces described in `avatar-data-contract.md`.
- Private media, avatar jobs, candidates, source objects, raw analysis,
  embeddings, and server-owned recovery/source-lock fields are not client-owned
  surfaces.
- `scripts/qa_media_privacy.py --dry_run --fail_on_warning` passed with 359
  client files scanned and all leak counters at zero.
- Firestore/Storage emulator load could not run because Java is absent from
  `PATH`; static Functions rules tests passed.

## Consent lifecycle

- The current source-photo consent version is `photo_consent_v4`.
- Consent purposes are explicit. Avatar generation, CLIP recommendation,
  source-photo retention, original-photo profile display, and chat real-photo
  disclosure are not collapsed into one implicit Generate action.
- Retry/recovery checks preserve consent version and purpose equality for the
  current source/job contract.
- Worker and lease paths reject missing or revoked avatar-generation consent and
  require `profileDisplayOriginalPhoto=false`.

## Retention and deletion

- Normal avatar generation does not automatically delete the source photo when
  retention or downstream consented processing still requires it.
- If source-photo retention is false, deletion is scheduled after terminal
  avatar and consented CLIP processing conditions allow cleanup.
- Consent withdrawal and account deletion paths sanitize or delete source
  objects, temp candidates, private-media records, public avatar mirrors, and
  related cleanup state idempotently.
- Cleanup evidence is sanitized and does not expose private image references.

## Logging redaction

- Queue payload logging redacts uid, source photo id, private source GCS
  references, and idempotency keys; job correlation remains limited to the
  frozen safe logging contract.
- Worker error logging redacts `gs://`/`gcs://` references, signed-token markers,
  and private bucket names.
- Flutter runtime logs use `PrivacyLogUtils` fingerprints/error summaries or
  equivalent bounded helpers. A global parser-backed test scans every Dart file
  under `lib` for unsafe `print`/`debugPrint` arguments.

## Festival isolation

- Festival consumes the same avatar privacy contract and must not fork backend
  state or safety semantics from root `functions/src`.
- The worker bridge treats `production_bridge` as production-like and validates
  `AVATAR_DATA_PROJECT`/`FIRESTORE_PROJECT`/`GCP_PROJECT=seolleyeon-festival`.
- Bridge runtime validation fails fast if `seolleyeon-final` source/temp/avatar
  buckets are configured for the Festival bridge.
- Festival embedding and maintenance surfaces remain isolated from public avatar
  display and from source-photo references by the same public/private data
  boundary. Live endpoint and network verification remains deferred.
- Festival startup recovery now refuses provisional or selection-version-only
  source claims; only an actual current source or active job can resume.

## Review fixes

- Confirmed high-severity issue: forged client-created `chat_rooms` documents
  could previously satisfy participant-only real-photo authorization.
- `functions/src/chatRealPhoto.ts` now requires a safe `matchId`, `one_to_one`,
  explicit active room state, an existing active server-owned `matches` doc, a
  reverse `chatRoomId` link, the exact same two unique UIDs, and requester/target
  membership before issuing a signed URL.
- All chat real-photo attestation failures deny before signing and return a
  generic response.
- Focused `chatRealPhoto` tests pass at 18/18, and the fix is covered by the
  root Functions 132/132 suite.
- Event-team fixes are documented in this checkpoint: `participantUids`,
  backend-owned meeting callables, participant-only rules, indexes, and fixed
  safe client errors.
- Legacy event docs that lack `participantUids` fail closed and require a
  dry-run migration before rollout.

## Dependency and encoding cleanup

- Root and Festival npm audit results have zero high or critical advisories.
- Eleven moderate advisories remain in transitive telemetry/uuid chains. The
  available `npm audit fix --force` path would require breaking changes and was
  not applied.
- Strict UTF-8, BOM, control-character, and mojibake checks are clean.
- Festival built-bundle forbidden-marker scan is clean.
- `git diff --check` is clean.

## Verification matrix

| Area | Evidence | Status |
| --- | --- | --- |
| Root Functions | Latest full suite 132/132 passed | pass |
| Focused chat real-photo tests | 18/18 passed | pass |
| Festival Functions | 63/63 passed | pass |
| Root Flutter analyze | PASS, no issues | pass |
| Root targeted avatar flow suite | Latest targeted suite 58/58 passed; privacy log 3/3 passed | pass |
| Prior broad Root Flutter evidence | 115/115 passed when the unrelated legacy `widget_test.dart` is excluded | prior broad evidence |
| Festival Flutter analyze | PASS, no issues | pass |
| Festival Flutter full suite | 48/48 passed | pass |
| Festival release web build | Succeeded | pass |
| Python full suite | 355 passed, 6 skipped | pass |
| Focused privacy scanner tests | 9/9 passed | pass |
| Media privacy dry-run | `qa_media_privacy` passed; 359 client files; leak counters zero | pass |
| npm audit | Root/Festival high and critical counts zero | pass with moderate advisories |
| Encoding scans | Strict UTF-8, BOM, control-character, and mojibake checks clean | pass |
| Bundle marker scan | Festival built-bundle forbidden-marker scan clean | pass |
| Diff hygiene | `git diff --check` clean | pass |
| Rules emulator load | Blocked by missing Java on `PATH` | blocked |
| Static Functions rules tests | Passed | pass |
| Live cloud privacy gates | Deferred to G005/G006 because active project guard is `seolleyeon-festival`, not `seolleyeon-final` | deferred |
| Independent final review | TEST_GATE PASS; RECOMMENDATION APPROVE; ARCHITECT_STATUS CLEAR | pass |

## Blockers and deferred live gates

- IAM, App Check, nonowner preview/approval denial, deletion cleanup smoke, and
  bridge network/privacy inspection remain deferred to G005/G006.
- No live mutation, deploy, IAM update, App Check enforcement flip, or public
  Hosting rollout was performed.
- The active project guard is `seolleyeon-festival`, not `seolleyeon-final`; the
  checkpoint intentionally stops before live verification.
- Firestore/Storage emulator loading remains blocked until Java is available on
  `PATH`.
- The legacy root `test/widget_test.dart` still initializes `SeolleyeonApp`
  without Firebase test setup; all avatar/privacy Flutter tests pass separately.
- Legacy event docs lacking `participantUids` fail closed and need a dry-run
  migration before rollout.

## Remaining decision boundary

Completing G003 means the repository privacy/security implementation has a
documented checkpoint and a passing local/static evidence matrix. It does not
set `PRIVACY_PRODUCTION_READY=true`.

`PRIVACY_PRODUCTION_READY=false` remains the exact flag decision. Overall
`production-ready=false` remains unchanged. Public rollout unauthorized.
