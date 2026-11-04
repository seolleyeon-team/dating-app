# Functions environment contract and live drift inventory (OPS-02)

Read-only inventory taken 2026-10-14 of every Cloud Run service in
`seolleyeon-final` / `asia-northeast3` (99 services after the OPS-01 deletion:
98 Firebase Functions + the `seolleyeon-avatar-orchestrator-phase3` Cloud Run
service, which has its own deployment unit and is excluded below). Only KEY
names and counts are recorded here — never values.

## Intended model (made explicit)

Firebase deploys **one dotenv file per project** (`functions/.env.seolleyeon-final`)
to every function it targets in the `default` codebase. There is no
per-function environment in this repository: a difference between two
functions' live environments is **time skew** (they were deployed from
different versions of that file), not design. The contract therefore has three
layers:

| Layer | Artifact | Catches |
|---|---|---|
| Static key manifest (new) | `scripts/functions_env_key_manifest.seolleyeon-final.json` (tracked; keys only) | a local dotenv that is incomplete, carries an undeclared key, or carries a Secret Manager parameter as plain text — refused by `deploy_functions_guarded_contract.py validate` before anything runs |
| Serving-revision guard | `scripts/functions_env_regression_guard.py` | per function: removal, value change, undeclared addition, and a source-read key about to be dropped (`missing_required`); each intentional change must be declared with `--allow-{remove,add,change}-key KEY` |
| Wrapper | `scripts/deploy_functions_guarded.sh` | runs both, builds, deploys exactly the named functions, re-runs the guard after deploy |

Guard change in this pass: `required_env_keys_from_source` now also sees
helper-form reads (`envValue("KEY", fallback)`, `truthyEnv("KEY")`), which is
how the avatar modules read buckets and queue names. Before, dropping
`APPROVED_AVATAR_BUCKET` produced no `missing_required` finding.

Secrets (`defineSecret`): `PLAY_REVIEW_ENABLED`, `PLAY_REVIEW_FIREBASE_UID`,
`PLAY_REVIEW_LOGIN_ID`, `PORTONE_API_SECRET`, `RESEND_API_KEY` stay in Secret
Manager and are bound per function (`playreviewsignin`,
`sendprimarystudentemaillink`, `sendstudentverificationemail`,
`verifyadultidentityafterlogin`). No function carries a secret as plain env
(verified: 0 of 98).

## Canonical plain key set (31)

The manifest equals the union of plain keys live on any function (no function
carries a key outside it) and the 31-key file used for the P0-1 deploy.

Classification of each key:

| Class | Keys |
|---|---|
| Read by source (direct or helper) | `APPLE_IAP_APPLE_ID`, `APPLE_IAP_BUNDLE_ID`, `APPROVED_AVATAR_BUCKET`, `AVATAR_COST_KILL_SWITCH_ENABLED`, `AVATAR_DISABLE_NEW_GENERATION`, `AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS`, `AVATAR_TEMP_BUCKET`, `AVATAR_UPLOAD_ALLOWED_UIDS`, `CHAT_PROFILE_PHOTO_BUCKET`, `CHAT_REAL_PHOTO_SIGNED_URL_TTL_SECONDS`, `CLIP_EMBEDDING_QUEUE_ENABLED`, `CLOUD_TASKS_PROJECT`, `ENVIRONMENT`, `GCP_LOCATION`, `IAP_VERIFICATION_MODE`, `JOB_QUEUE_MODE`, `RESEND_FROM_EMAIL`, `RESEND_REPLY_TO`, `SOURCE_PHOTO_BUCKET`, `TASK_INVOKER_SERVICE_ACCOUNT`, `WRITE_LEGACY_ONBOARDING_PHOTO_URLS`, `AVATAR_GENERATION_QUEUE_NAME`, `AVATAR_GENERATION_TASK_URL` (the last two are selected by variable name before the helper call) |
| LEGACY — live on revisions, not read by current source | `AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS`, `AVATAR_QUEUE_MAX_ATTEMPTS`, `AVATAR_QUEUE_MAX_BACKOFF_SECONDS`, `AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES`, `AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND`, `AVATAR_QUEUE_MAX_DOUBLINGS`, `AVATAR_QUEUE_MIN_BACKOFF_SECONDS`, `AVATAR_QUEUE_TERMINAL_STRATEGY` — kept in the manifest so no deploy removes them silently; retire them in a reviewed change that updates the manifest and declares `--allow-remove-key` |
| Read by source, **not** in the manifest, code default applies | `APPROVED_AVATAR_PUBLIC_BASE_URL` (""), `AVATAR_PREVIEW_IMAGE_SIZE`, `AVATAR_RETRY_LIMIT` ("2"), `AVATAR_SOURCE_DELETION_LEASE_MS`, `AVATAR_SOURCE_PHOTO_BUCKET` (falls back to `SOURCE_PHOTO_BUCKET`), `AVATAR_SOURCE_RECOVERY_GRACE_MS`, `SEASON_DEPOSIT_PROVIDER_READY` (unset = not ready, fail-closed), `TASK_OIDC_AUDIENCE` (falls back to the task URL) — live nowhere; adding any of them is a reviewed manifest change |
| `.example` keys that belong to the Python avatar worker, not Functions | `AVATAR_COST_*`, `AVATAR_QA_*`, `AVATAR_REFERENCE_*`, `CLIP_EMBEDDING_QUEUE_NAME`, `CLIP_EMBEDDING_TASK_URL`, `CLOUD_RUN_MEMORY_GIB`, `CLOUD_RUN_VCPU` — the example file is documentation and mixes two deployment units; it is not a deploy input |

## Live drift matrix (98 Firebase Functions, 2026-10-14)

`missing` = manifest keys absent on the serving revision; `extra` = live keys
outside the manifest (0 everywhere); `changed` = value differs from the local
file (fingerprint comparison).

| Group | Functions | Keys live | Drift class |
|---|---|---|---|
| 0 keys | `blindmeetingops`, `cancelseasonmeeting`, `claimseasonmeetingreplacementseat`, `createseasonmeetingdepositintent`, `dispatchmeetingicebreakerprompt`, `meetingicebreakeraction`, `meetingicebreakerreconciletick`, `refundseasonmeetingdeposit`, `reportseasonmeetingnoshow` (9) | 0 | ACCIDENTAL MISSING (deployed with an empty dotenv); handlers do not read the missing keys on their own paths, so they run on code defaults |
| 2 keys | `verifyadultidentityafterlogin` (1) | 2 | ACCIDENTAL MISSING (29) |
| 4 keys (`APPLE_IAP_*`, `RESEND_*`) | 41 functions incl. `sendchattext`, `onchatmessagecreated`, `grantpurchasedhearts`, `googleplayrefundrtdn`, `blindmeeting*`, community moderation, play review, `sendprimarystudentemaillink` | 4 | ACCIDENTAL MISSING (27) — time skew from a 4-key file era |
| 12 keys | `acceptfriendinvite`, `createeventteaminvite`, `createeventteamshareinvite`, `createfriendinvite`, `createteammeetingrequest`, `ensureeventteamsetup`, `previewinvitetoken`, `redeemeventteamshareinvite`, `respondeventteaminvite`, `respondteammeetingrequest`, `spinseasonmeetingroulette` (11) | 12 | ACCIDENTAL MISSING (19; 5 source-read: queue/task keys) |
| 26 keys | `autocompleteexpiredgoodbyesafetystamps`, `createfirebasecustomtoken`, `dispatchpromisereminder`, `getchatrealprofilephoto`, `onaskcreated`, `onbamboocommentcreated`, `onbamboopostlikecreated`, `oneventteamsetupwritten`, `onfestivalchatmessagecreated`, `oninteractioncreated`, `onmatchupdated`, `onreceventcreated`, `onuserphonehashupsert`, `purgeexpiredemaillinktokens`, `saveuserphonehash`, `schedulepromiseremindertask`, `senddailyunreadchatdigests`, `sendupcomingpromisereminderpushes`, `synccontactblocks` (19) | 26 | ACCIDENTAL MISSING (5: `APPLE_IAP_*`, `IAP_VERIFICATION_MODE`, `RESEND_*`) |
| 29–30 keys | `approveavatarcandidate`, `beginavatargenerationfromonboardingphotos`, `getavatarjobcandidates`, `getcurrentavatargenerationstatus`, `onavatarclipafterselection`, `onavatargenerationstatesync`, `onavatarjobsourceretention`, `onclipembeddingsourceretention`, `prewarmavatarworker`, `purgeaccountdeletionretention`, `recoveravatarsourceretention`, `replaceavatargeneration`, `retrycurrentavatargeneration`, `uploadonboardingphoto` (14) | 29–30 | missing `IAP_VERIFICATION_MODE` (+1); 9 of them carry the **old `RESEND_FROM_EMAIL` sender** (VALUE VARIANT; none of them sends mail) |
| 31 keys | `completeprimarystudentemailauth`, `completestudentemaillink`, `sendstudentverificationemail` (3) | 31 | matches manifest (P0-1 deploy, 2026-10-13) |

Known, accepted value: `ENVIRONMENT=staging` on production (NEW-03;
`functions/src/avatarMedia.ts:162` derives the real environment from
`K_SERVICE`). Changing it is a reviewed `--allow-change-key` deploy.

## Dangerous drift assessment

- No function carries a secret as plain text. No function carries a key the
  manifest lacks.
- No live difference was proven to change behaviour on the function that
  carries it: the 0/4/12-key groups lack keys their own handlers do not read,
  and the `RESEND_FROM_EMAIL` variant sits only on non-mail functions. The
  risk they pose is latent — a future code path reading a key on a function
  that lacks it falls back silently. That risk is closed at deploy time by the
  guard: redeploying any of these functions with the manifest file produces
  only `added` findings, each of which must be declared.
- Therefore **no reconciliation deploy was run in this pass** (99 new
  revisions for a latent risk is not a smaller risk than the drift itself).
  Convergence happens on each function's next guarded deploy, which the
  manifest now forces to be complete.

## Procedure (operators)

1. `functions/.env.seolleyeon-final` must have exactly the manifest's 31 keys
   (`python scripts/deploy_functions_guarded_contract.py validate …` prints
   `keys=31 manifest=…`); restore missing values from a serving revision
   (`gcloud run services describe <fn> --region asia-northeast3 --format=json`),
   never from the `.example`.
2. Deploy only through `scripts/deploy_functions_guarded.sh`, declaring every
   `added` key the guard reports (expected for every function in the drift
   groups above), and never `--allow-remove-key` / `--allow-change-key`
   without a reviewed reason.
3. Adding or retiring a variable = one reviewed change that edits the source,
   the manifest, and the operator's dotenv together.

## Status

OPS-02: contract hardened (manifest + helper-aware guard + tests, 89 passed in
`tests/test_functions_env_*.py` / `tests/test_deploy_functions_guarded_contract.py`).
Remaining live drift: DEFERRED to per-function guarded redeploys (table above),
tracked in `00-backlog.md`.
