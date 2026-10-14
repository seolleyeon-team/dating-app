# Production-readiness backlog — 2026-10 audit

Source: full-project production-readiness audit of 2026-10-07 (50-item review:
correctness, lifecycle, Firestore cost/rules, trust boundaries, deletion,
observability). This file is the single ledger for everything that audit and
its remediation sessions left open. Statuses are only moved by evidence, never
by documentation alone.

Status vocabulary: `CLOSED` (verified), `DEFERRED` (documented, gated),
`BLOCKED` (cannot proceed), `OPEN` (not started), `IN PROGRESS`.

## Closed P0 — reference

| ID | Finding | Status | Evidence |
|---|---|---|---|
| P0-1 | Cross-account student verification + mailbox uniqueness | SOURCE CLOSED / PRODUCTION CLOSED (2026-10-13) | commit `fc99ebd8` on `security/integration` (pushed 2026-10-14); rules 247/247, emulator E2E 20/20 + issuance 6/6; production smoke 9/9 (cross-account DENY, positive control ALLOW); Functions revisions `sendstudentverificationemail-00004-xuk`, `completestudentemaillink-00003-mir`, `completeprimarystudentemailauth-00002-nan`; ruleset `0cf89a6f-…` (2026-10-13T12:25Z); hosting release 21:25:19 KST |

## Operations ledger

| ID | Finding | Severity | Status | Evidence | Next action | Blocking condition | Owner/Area |
|---|---|---|---|---|---|---|---|
| OPS-01 | `createFirebaseCustomTokenFromEmailLinkToken` (SEC-P0-01 bearer-token → custom-token callable) removed from source (`c21cde5d`, 2026-07-31, build +3) but still deployed in `seolleyeon-final`/`asia-northeast3` | P1 | CLOSED (2026-10-14) | No tracked caller (`git grep` hits only docs and `.tmp/merge-restore/*` artifacts); Cloud Monitoring `run.googleapis.com/request_count` = 0 over 90 days; request logs 0 over 30/60/90 d; last log entries are 2026-07-30 deploy events; rev `…-00003-duy`, 256Mi/60s/max 10, SA `810450765203-compute@…`, ingress all, invoker `allUsers`, env keys = avatar/queue set (no secret refs; source zip retained in `gcf-v2-sources-810450765203-asia-northeast3`). Deleted with `firebase-tools@15.30.2 functions:delete … --force`; `functions:list` and Cloud Run both confirm it is gone; sibling verification callables intact | — | — | Functions / auth |
| OPS-02 | Functions env drift across deployed revisions (P0-1 deploy found a 12-key local file vs 26–30 live keys; revisions with `ENVIRONMENT=staging`; `completestudentemaillink` rev `00002` dated 2026-08-03 with no RESEND keys) | P1 | CLOSED (contract, 2026-10-14) / live drift DEFERRED | Inventory of all 98 Firebase Functions + source env reads in `01-functions-env-contract.md` (keys/counts only). No plaintext secrets, no key outside the 31-key union. Drift is time skew of one global dotenv: 9 functions with 0 keys, 41 with 4, 11 with 12, 19 with 26, 14 with 29–30 (9 of them with the old `RESEND_FROM_EMAIL` sender), 3 matching. Hardening commit `ace1a74b`: tracked key manifest `scripts/functions_env_key_manifest.seolleyeon-final.json` + `validate` refuses incomplete/extra/plaintext-secret dotenv; guard now sees `envValue("KEY")`/`truthyEnv("KEY")` reads; 89 guard tests pass; the old 12-key file is demonstrably refused | Converge each function on its next guarded deploy (every `added` key declared). Retire the 8 LEGACY `AVATAR_QUEUE_*` keys and decide `ENVIRONMENT` in one reviewed change that edits source + manifest + dotenv | No reconciliation deploy without removals = 0 / changes = 0 / missing_required = 0; a mass redeploy of 98 functions was judged a larger risk than the latent drift | Functions / ops |
| OPS-03 | `users/fake_user_1` fixture in production (`isStudentVerified: true`, password-provider Auth user `…@seolleyeon-final.local`, created 2026-08-29, last sign-in 2026-08-31) | P2 | DEFERRED — requires manual ownership verification | Read-only scan 2026-10-14: `publicProfiles/fake_user_1`, `recEvents/fake_user_1`, 7 `chat_rooms` (`dm_<uid>_fake_user_1`, created 2026-03-09 … 2026-05-12; 2 rooms hold messages), 4 `interactions`, 1 `asks`, 2 `bamboo_posts`. Counterparts: one is a real verified user (`4850097844`, room created 2026-04-16, 0 messages); six have no `users` doc but two still have Auth records (last sign-in 2026-08-30 / 2026-09-02) | Owner decides: (a) confirm fixture + who the counterparts are; (b) run the canonical account-deletion path for `fake_user_1` (it purges rooms/posts/bindings/Auth) or a scoped admin script with `--dry-run`; (c) decide fate of auth-only ghost accounts | Do not delete while a real user's room and auth-only ghosts are attached without owner confirmation | Data / product owner |
| OPS-04 | P0-1 emulator suites (`studentEmailBinding`, `studentEmailReservation`, `studentEmailIssuance`) not run by CI (`npm test` only runs `*.test.js`) | P1 | CLOSED (source, 2026-10-14, commit `f394c2e2`) — awaits first green CI run on a PR | New `security-emulators` job in `.github/workflows/ci.yml` (YAML validated; build step dry-run locally): JDK 21, firebase-tools 15.30.2 (pinned to the guarded deploy version), CI-only `functions/.ci-emulator-lib`, demo project only, no `continue-on-error` | Open a PR from `security/integration` so the job runs (CI triggers: `main`, `audit/**`, `release/**`, `semisemifinal`, pull requests — not `security/**` pushes) | — | CI |
| OPS-05 | `blindmeetinglifecycletick` ERROR every 5 min since 2026-08-09 (288/day) | P1 | CLOSED (2026-10-14) | Root cause CONFIRMED from `jsonPayload`: step `scheduleVotes`, gRPC 9 FAILED_PRECONDITION "The query requires an index", hint decodes to `blindMeetings` COLLECTION `serverStatus ASC, scheduleVoteDeadlineAt ASC`; query `functions/src/blindMeeting/orchestrator.ts:2210-2214` (`finalizeExpiredScheduleVotes`); live indexes == `firestore.indexes.json` (34/34) and neither had it. Fix commit `393d306d` (one index); `firebase deploy --only firestore:indexes` → READY at 05:44Z; last error 05:36:03Z; ticks at 05:46Z/05:51Z and after ran with 0 errors | Watch for a full day of clean ticks; the other audit-suggested indexes stay unproven (see P1-4 row) | — | Functions / blind meeting |

## P0-1 follow-ups

| ID | Item | Status | Evidence / gate |
|---|---|---|---|
| P0-1-F1 | Full Yonsei mailbox E2E (send → link → hosted page / app → completion) never executed against production | DEFERRED | Needs a controlled `@yonsei.ac.kr` test mailbox. Rules-level hosted write and the issuance/completion callables were verified (production smoke 9/9; emulator issuance 6/6) |
| P0-1-F2 | `/auth/email-link` rewrite served with `Cache-Control: max-age=3600` (the `**/*.html` `no-store` header does not match the rewrite source path) | OPEN (P3) | Links carry `v=` and `t=` query params, so stale cache hits are unlikely; fix is a `firebase.json` headers entry for `/auth/email-link**` |
| P0-1-F3 | Legacy issuance reservation lets a third party who knows a mailbox block legacy issuance for ≤30 min per request (rate limit 2/min, 10/day per mailbox) | ACCEPTED (design) | Primary flow unaffected; documented in `functions/src/studentEmailBinding.ts` |
| P0-1-F4 | `onUserPublicProfileSync` creates `publicProfiles/*` for smoke/test users; smoke cleanup must include it | NOTE | Observed 2026-10-13; cleaned manually |
| P0-1-F5 | Local `functions/.env.seolleyeon-final` was 12 keys; rebuilt to 31 keys from live revisions for the P0-1 deploy. Backup of the 12-key file: `.env.seolleyeon-final.bak-p01-20261013-211415` (repo root, untracked) | NOTE → folds into OPS-02 | — |

## Newly discovered (2026-10-14), not fixed here

| ID | Finding | Severity | Status | Next action |
|---|---|---|---|---|
| NEW-01 | `.tmp/merge-restore/*` (47 files, merge-conflict artifacts incl. full copies of `functions/src/index.ts`) are tracked in git | P3 | OPEN | Confirm not referenced, then remove in a dedicated cleanup commit |
| NEW-02 | CI does not run on pushes to `security/**` branches (only `main`, `audit/**`, `release/**`, `semisemifinal`, PRs) | P3 | OPEN | Either add `security/**` to the push trigger or always work through PRs |
| NEW-03 | Production Functions carry `ENVIRONMENT=staging` (known; `avatarMedia.ts:162` works around it via `K_SERVICE`) | P3 | OPEN | Decide canonical value in OPS-02 contract; change only via guarded deploy with `--allow-change-key` |
| NEW-04 | Six `dm_*_fake_user_1` counterparts have Auth users without `users` docs (ghost accounts) | P2 | OPEN | Part of OPS-03 owner review; check account-deletion completeness (`deleteAuthUser` op) |

## Remaining audit findings (referenced, not implemented here)

| ID | Finding | Severity | Status |
|---|---|---|---|
| P0-2 | Chat unread/read scans full message history; mark-read batch >500 risk; unbounded `messagesStream`; daily digest scans users × rooms × messages | P0 | OPEN — next remediation stage |
| P0-3 | Bamboo (anonymous board) de-anonymizable via `authorId`, notification `actorId/actorName`, like-doc listing (SEC-04 unfinished) | P0 | OPEN |
| P1-1 | Mutual-like match creation lost `ensureMutualMatch` (regression in `22ca7307`); no block check; like-push spam | P1 | OPEN |
| P1-2 | Chat access-control bypasses: `sendChatText` ignores room `status`/`writable`; 1:1 room fields rewritable; non-text message types skip moderation | P1 | OPEN |
| P1-3 | FCM token not removed on logout | P1 | OPEN |
| P1-4 | `CommunityProvider` survives logout | P1 | OPEN |
| P1-5 | Account deletion leaves `participantInfo.<uid>` (dotted key with `set`), onboarding photos, blind-meeting data | P1 | OPEN |
| P1-6 | No crash reporting | P1 | OPEN |
| P1-7 | Adult verification enforced client-side only; `ADULT_VERIFICATION_BYPASS` not gated by `!kReleaseMode` | P1 | OPEN |
| P1-8 | `sendDailyUnreadChatDigests` full scan | P1 | OPEN (folds into P0-2) |
| P1-9 | Onboarding photo upload unresized base64 | P1 | OPEN |
| P1-10 | `asks`/`interactions` schema + block checks | P1 | OPEN |
| P1-11…13 | Send-failure draft loss; group `readBy` lost updates; season-meeting client-trusted time | P1 | OPEN |
| P1-4 (index) | Other likely-missing composite indexes from the audit (`blindMeetings(serverStatus, createdAt desc)`, `events` collection-group, `promises(status, meetupCompletedAt)`) | P2 | OPEN — verify each against a real failing query before adding (only the OPS-05 one is proven) |
