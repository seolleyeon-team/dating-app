# Residual Technical Defects — Remediation and Re-verification (2026-11-21 … 11-22)

Branch `security/residual-remediation-20261121`, stacked on PR #158
(`security/codebase-audit-20261113`, head `93fd52e8`), base
`security/integration` `9311eb79`. **Source and tests only: nothing in this
document is deployed, no production document was written, no index or ruleset
was released.** Production was read (function metadata, source archives,
index lists, logs, single documents, counts) and never changed.

Scope: the 38 managed items of the 2026-11-13 audit that need no product
decision (Category A, 18) or needed re-verification first (Category B, 20).

## 1. Result per item

State vocabulary: FIXED_AND_VERIFIED · ALREADY_FIXED_AND_VERIFIED ·
PARTIALLY_FIXED · CONFIRMED_OPEN · NOT_APPLICABLE · REQUIRES_PRODUCT_DECISION ·
BLOCKED · NOT_VERIFIED. "Verified" means the tests named in §5 on the local
emulators / fakes; no item is production-verified.

### Category A

| ID | Finding (as re-verified) | State | Change |
|---|---|---|---|
| NEW-24 | The account-state gate existed only inside `resolveAuthedAppUser`; 12 callables took `request.auth.uid` with no state check, the review resolver had none, five modules each carried a different state list | FIXED_AND_VERIFIED (source) — live builds predate it | `accountStatePolicy.ts` (classifier: active / suspended / banned / withdrawn / inactive, read from Firestore on every call), `callableAccountStatePolicy.ts` (all 72 HTTPS exports declared with a gate kind and a reason; a guard test loads the real exports and fails on an undeclared one), gate added to every callable that lacked it. Exempt on purpose: account deletion, sign-in / verification entry points, operator callables, store notifications |
| NEW-25 | The "unknown 09-17 tree / lost generations" record was wrong: the five moderation functions serve two builds whose inputs are retrievable, all 14 retrievable archives are entry-identical (617/617), and `src/communityModeration.ts` in them is byte-identical to git `94f6b0b8` (PR #146). What was missing was hardening | FIXED_AND_VERIFIED (source) | Operator gate also refuses a suspended / banned / withdrawn operator; reviewing and decision transitions are transactional; sanction → Auth-disable failure returns `unavailable` and can be retried; restore is atomic with its audit record and refuses a withdrawn account |
| AUD-11 | Duplicate-identity lookups ran before the transaction (two accounts could verify one person concurrently); an incomplete verification overwrote `adultVerified` to false on a verified account and created a `users` document for a uid without one; the provider-failure log carried the session id and the provider body | FIXED_AND_VERIFIED | `adultIdentityOwnership.ts`: ownership documents `adultIdentityOwners/{kind}_{hash}` planned and applied inside the verification transaction; legacy records still block without a backfill; released on account deletion. Read-only audit / dry-run / apply CLI written, **not run** |
| AUD-08 | Deletion closed the application only; the seat stayed `confirmed`, no search opened, and a seat whose account no longer hydrates made every later fill of that meeting give up | FIXED_AND_VERIFIED | `blindMeeting/seatRelease.ts` — one transaction shape shared by `leaveBlindMeeting` and the deletion cleanup; a vacated seat is filled by the gender recorded at confirmation; idempotent. No refund rule invented |
| REPORT-DEDUP | After the first report of a pair was closed, each call created another report with a random id | FIXED_AND_VERIFIED | The deterministic first report is the pair's tracker (`pairLatestReportId`), read and written in the report + blocks transaction; legacy leftovers found by an in-transaction equality query; a Bamboo report never answers `duplicate` |
| AUD-12 | `autoCompleteExpiredGoodbyeSafetyStamps` re-read and re-transacted every promise ever stamped, every 15 min, on a 60 s timeout; the digest delivered one recipient at a time on a 60 s timeout | FIXED_AND_VERIFIED (the two targets) | Watermark sweep (`goodbyeAutoCompleteSweep.ts`, pages of 200, 8 in flight, 5,000 docs / 120 s per run, forward-only checkpoint); digest 10 in flight, 420 s budget, overflow logged. Explicit timeouts. **No new index** (the existing `promises.meetupCompletedAt` collection-group override serves it). Other schedulers: inventory in §4 |
| AUD-14 | The sweep read the newest 150 reports of any kind and rewrote every alert with `unread: true` | FIXED_AND_VERIFIED | Query by source + status + `createdAt`, cursor-paged; alerts are `create`d once and never rewritten; overlapping runs safe; 300 s timeout. Needs index `reports(source, status, createdAt)` (added to `firestore.indexes.json`; falls back to a slower correct path without it) |
| AUD-16 | One failed forced token refresh left the provider unauthenticated for the session; push listeners were attached after awaited set-up, so one failure meant no listeners | FIXED_AND_VERIFIED (fakes) | `auth_bootstrap_policy.dart` (transient vs session-invalid), bounded retry + resume retry, never sign out on a transient error; push listeners attached first, set-up steps isolated and retried |
| AUD-18 | 95 of 144 `tests/test_*.py`, two script suites and six new emulator suites ran in no job | FIXED (CI RUN PENDING) | New job `python-full` runs the whole `tests/` directory (so a new file is covered automatically); script suites added to the functions job; every `*.emulator-test.ts` is now in a CI step. `tools/gate-tests` is a fixture set of a personal IDE guard with no runner: NOT_APPLICABLE |
| AUD-22 | See §3 | FIXED_AND_VERIFIED | Shared account predicate, shared KST day key, client-writable image fields no longer read, contract test for all four families |
| AUD-23 | Live responses carried no `nosniff` / frame / referrer header; every clean URL except the email link was cached 1 h; the two AASA files differed | FIXED (not deployed) | `firebase.json` headers; both AASA files identical; the assetlinks fingerprint equals the Play app-signing certificate recorded in `scripts/verify_android_production_identity.py`. Play Console itself NOT_VERIFIED |
| AUD-24 | Onboarding steps navigated before the save finished and twice; follow-up screen; tutorial double completion; app-link listener never started after an email-link launch; unbounded listeners | FIXED_AND_VERIFIED (fakes) for the parts listed in §5; see §7 for what is still open | Client only |
| AUD-25 | Six items, all checked — see §2 | 5 FIXED_AND_VERIFIED, 1 REQUIRES_PRODUCT_DECISION | — |
| PR-158-CI | 12 failures: 1 build-number constant (23 vs pubspec `+34`), 11 golden diffs | 1 FIXED, 11 REQUIRES_PRODUCT_DECISION (visual approval) | Constant set to the committed pubspec build. Goldens: differences are glyph and border edge pixels only (1.4 – 7.7 %), no layout shift; the baselines were generated on another machine on 2026-09-03. Not regenerated |
| PYTHON-FULL | — | VERIFIED locally | 2425 passed / 17 skipped / 0 failed (local, Python 3.11) |
| DEPLOY-READINESS | See §6 | Plan written; nothing deployed | — |
| APPCHECK-E2E | Emulator tests call callables through `.run()`, which bypasses App Check | NOT_VERIFIED (live normal path) | All 71 callables set `enforceAppCheck: true` (source); live deny path verified in earlier audits; a real attested device succeeding is still unverified |
| IOS-CRASHLYTICS | `project.pbxproj` has no upload-symbols run script and `Podfile.lock` has no FirebaseCrashlytics entry; Release / Profile use `dwarf-with-dsym`; Dart side sends sanitised errors only, no user identifier | CONFIRMED_OPEN | Needs `pod install`, the run script and a real archive (no macOS here) |

### Category B

| ID | Verified finding | State | Change |
|---|---|---|---|
| AUD-01 | **Production refuses the exact query** (`documents:runQuery` → FAILED_PRECONDITION, "requires an index"); no composite or collection-group exemption on `events`; the trigger has not run since the rollout, so the absence of errors in the log meant "never executed" | FIXED in source — **index must be deployed** | `events(eventType, targetUserId, userId)` COLLECTION_GROUP in `firestore.indexes.json`, pinned by a contract test |
| AUD-06 | A device advertised only during its own 8 s attempt | FIXED — logic verified with fakes, **two-device NOT_VERIFIED** | `SafetyStampPresence` keeps advertising for the phase (10 min idle stop, resume recovery) |
| AUD-09 | (a) fixed 25-document window starved due sources; (b) both admission paths rewrote `status: "queued"` unconditionally after the task was created | FIXED_AND_VERIFIED | (a) id-paged scan with a resume checkpoint, no skipped document mutated; (b) `avatarEnqueueOutcome.ts`: a transaction that changes `status` / `errorCode` only while the job is still dispatch-owned, and a bookkeeping failure is no longer reported as a dispatch failure |
| AUD-17 | Lock-order deadlock: the claim transaction issued its reads as 13 separate RPCs; the emulator resolves it with a non-retryable code. 3 of 20 runs failed | FIXED_AND_VERIFIED (emulator; 20 consecutive green) | One `tx.getAll`; the losing run now loses the claim cleanly. The invariant was never violated |
| AUD-26 | `recommendationConfig/current` does not exist in production → the campus-life-zone filter is dormant everywhere, which is the documented OFF state | REQUIRES_PRODUCT_DECISION | None |
| B-06 | Unauthenticated creates of any size with arbitrary fields | FIXED_AND_VERIFIED (rules) | Canonical session, exact shape, allow-listed bounded params, own-uid hash |
| B-07 | `onboarding.representativeImageUrl` / `profileImageUrl` were client-writable and projected to the public profile after a deny-list check only | FIXED_AND_VERIFIED | Rules protect both; the projection accepts only an image the server stored for that user |
| B-08 | The target of an interaction could read who passed on them or viewed them | FIXED_AND_VERIFIED (rules) | The target reads `like` / `super_like` only |
| B-09 | `FORCE_APP_CHECK_DEBUG`, the QA screen-capture switch and the App Check debug token were honoured in a release build; `ADULT_VERIFICATION_BYPASS` was already guarded | FIXED_AND_VERIFIED | `release_build_guards.dart`; every reader goes through it |
| B-10 | The Kakao token was checked against the profile endpoint only, which answers for a token of any Kakao app | FIXED_AND_VERIFIED — **fails closed until `KAKAO_APP_ID` is set** | Token-info `app_id` must equal the configured numeric app id; new plain env key (manifest 31 → 32) |
| B-11 | Deletion removes every record a re-join restriction could key on; a sanctioned account can delete itself while its ID token is still valid (≤ 1 h) and sign up again | REQUIRES_PRODUCT_DECISION | Email sign-in now uses the shared classifier; no retention added |
| B-12 | The stamp window, the timeout cancellation and "≥ 10 minutes from now" were decided by the device clock only | FIXED_AND_VERIFIED | Server-time window in `submitSafetyStamp`; rules bind a written meeting time and the timeout cancel to `request.time`; client handles the refusals |
| B-13 | The feed reloaded on every snapshot of the viewer's own document | FIXED_AND_VERIFIED (fakes) | Reload only when a field that affects the result changes |
| B-14 | Irrelevant writes were already skipped; every relevant write ran one transaction per department member | FIXED_AND_VERIFIED | 300-member department: 300 → 6 transactions for a join / change / deletion |
| B-15 | See §7 | see §7 | — |
| B-16 | See §7 | see §7 | — |
| B-17 | Splash routed on a fixed 1.5 s timer independent of the provider | FIXED_AND_VERIFIED (fakes) | Splash waits for the bootstrap to settle (10 s cap) and offers retry / explicit logout |
| B-18 | Emulator routing covered Auth / Firestore / Functions but not Storage | FIXED_AND_VERIFIED | All four services or none; refused in release |
| B-19 | No backup attributes: Auth session store, cached identifiers and the safety-stamp location log were backed up | FIXED (contract test + `aapt2` link; device restore NOT_VERIFIED) | `allowBackup=false` plus exclusion rules |
| B-20 | Functions enforce; Storage ENFORCED; Firestore and Auth UNENFORCED (documented owner decision R-01); 12 debug tokens | ALREADY_FIXED_AND_VERIFIED (Functions) | None |

## 2. AUD-25, item by item

1. **Icebreaker decline before activation** — a decline stored before the participant document existed was a stub the activation ignored. Fixed.
2. **`purgeExpiredEmailLinkTokens`** — fixed 500-document window with no order. Now id-paged with a resume checkpoint (700 expired tokens behind 500 kept ones: 0 → 700 deleted).
3. **Bamboo like notification** — a redelivery pushed and wrote twice. Idempotency key derived from a hash of the event id (never from the like document id, which is the liker's uid).
4. **Paid-retry responses** — (a) `grantPurchasedHearts` replay returned the balance stored at the first grant; it now returns the balance read in the same transaction. (b) `purchaseRecommendationRefresh`: three prechecks ran before the transaction that recognises a completed purchase, so a retry could end in `refresh_unavailable` after five hearts were spent; the stored purchase is now answered first, with the current balance.
5. **`notificationDispatchLog`** — entries now carry `expireAt` (90 days). The TTL policy itself and existing entries: owner decision.
6. **`sendUpcomingPromiseReminderPushes`** — an intentional no-op (reminders go through Cloud Tasks). Remove or repurpose: owner decision.

## 3. AUD-22 — the four helper families

| Family | Copies found | Divergence | Action |
|---|---|---|---|
| Id / path-segment validators | 11 functions, 38 regex literals | None that matters: every one is `^[A-Za-z0-9_-]…$`; only the length bound differs | Not rewritten. Contract test: every such literal is anchored and admits no separator, dot or Unicode |
| Display image | 5 readers | Four read `onboarding.profileImageUrl` / `representativeImageUrl`, which a client could write | Those reads removed; `publicProfileSync` is the only reader left and compares against server-stored images |
| Inactive-account predicate | 6 | Push and recommendation missed `banned` and a deletion in progress; several missed `accountStatus` | `isRestrictedAccountData` added to each. It deliberately ignores `loginDisabled` alone: Play review fixtures carry it and must stay visible as candidates |
| KST day key | 4 server copies, 4 client sites | None (all UTC+9 arithmetic) | Server copies delegate to `shared/kstDate.ts`; boundary and time-zone-independence tests |

## 4. Scheduler inventory (AUD-12)

| Function | Timeout | Scan | State |
|---|---|---|---|
| `autoCompleteExpiredGoodbyeSafetyStamps` | 300 s | watermark, paged | fixed |
| `sendDailyUnreadChatDigests` | 540 s | paged rooms, bounded-parallel delivery | fixed |
| `purgeExpiredEmailLinkTokens` | 300 s | id pages + checkpoint | fixed |
| `recoverAvatarSourceRetention` | 180 s | id pages + checkpoint | fixed |
| `checkCommunityModerationDeadlines` | 300 s | source + status + age, paged | fixed |
| `sendUpcomingPromiseReminderPushes` | default | none (no-op) | owner decision |
| `purgeAccountDeletionRetention` | 60 s | fixed `limit(100)` window for empty teams; private-media scan restarts from the first id | **open** (RES-07) |
| `blindMeetingMatchingTick` / `blindMeetingLifecycleTick` | 60 s | unbounded status queries, sequential | **open** (RES-08) |
| `meetingIcebreakerReconcileTick` | 60 s | fixed `limit(200)` window | **open, suspected** (RES-09) |

Measured on the emulator: goodbye sweep, 2,000 promises — before 1,900 reads +
1,900 transactions every run; after 1,900 reads + 300 transactions on the first
run, 0 reads 15 minutes later, 100 reads for 100 newly due. Deadline sweep,
1,850 reports / 1,050 due — 1,050 alert creates on run 1, 0 writes on run 2.

## 5. Tests added

Emulator suites (all in CI steps of `security-emulators`):
`accountStateGate`, `adultIdentityOwnership`, `safetyStamp`,
`blindMeeting/accountDeletionSeat`, `blindMeeting/genderBalance` (rewritten
assertions, now in CI), `reportAndBlockDedup`, `communityModeration`,
`communityModerationDeadlines`, `schedulerResidual`, `schedulerScale`,
`departmentRecommendationFanout`, `recommendationRefreshReplay`,
`avatarEnqueueOutcome`.

Unit / contract: `callableAccountStatePolicy`, `kakaoAccessTokenVerification`,
`sharedHelperContracts`, `schedulerResidual`,
`avatarSourceRetentionRecoveryScan`, additions to `publicProfileSync`,
`safetyStamp`, `reportAndBlock`, `communityModeration`,
`departmentRecommendationPrivacy`, `accountDeletionMeetingCleanup`,
`adultVerificationPolicy`, `firestoreRules`.

Rules: `firestore.analytics`, `firestore.interactionsprivacy`,
`firestore.profileimageauthority`, `firestore.promisetime`,
`firestore.indexcontract`; attack-suite analytics block realigned.

Flutter: `hosting_security_headers_contract`, `android_backup_contract`,
`release_build_guards_contract`, `firebase_emulator_config`,
`auth_provider_bootstrap`, `splash_screen_routing`, `push_notification_setup`,
`safety_stamp_presence_lifecycle`, `safety_stamp_server_refusal`,
`onboarding_step_save_guard`, `blind_meeting_follow_up_screen`,
`tutorial_completion`, `recommendation_privacy_watch`.

Bug reproduction observed on the pre-fix code (same test, old source or old
query shape): NEW-24 (5 cases), AUD-11 (3), B-10, AUD-08 (8 of 9), AUD-17
(3 of 20 runs), REPORT-DEDUP (6 of 11), AUD-14 (2), B-06 / B-07 / B-08 / B-12
rules (27 of 42), B-07 server (3 of 5), B-12 server (6 of 8), AUD-12 goodbye
shape, token purge, retention window, AUD-25 4b (3 of 4), tutorial (2).
Confirmed by reading only (no failing run observed): AUD-16, B-17, AUD-06,
B-09, B-18, B-19, AUD-25 items 1, 3 and 4a, the NEW-25 console additions.

## 6. Deployment readiness (nothing executed)

Order, each step through the existing approval path:

1. **Indexes** (`firebase deploy --only firestore:indexes`):
   `events(eventType, targetUserId, userId)` COLLECTION_GROUP — until it is
   READY every rec-path like makes `onRecEventCreated` throw; and
   `reports(source, status, createdAt)`.
2. **Environment**: the owner supplies the numeric Kakao app id; add
   `KAKAO_APP_ID` to the operator dotenv. The manifest already lists it
   (32 keys), so the guard refuses a dotenv without it — deploying
   `createFirebaseCustomToken`, `linkKakaoFriendIdentity`,
   `createKakaoFriendPairsOnce`, `syncKakaoTalkFriendBlocks` or
   `beginKakaoFriendRecommendationPrivacySync` without the key would break
   Kakao verification, including the legacy Kakao sign-in. Every guarded
   deploy needs `--allow-add-key KAKAO_APP_ID` once per function.
3. **Rules** (`firestore:rules`) together with `submitSafetyStamp` and the
   client-facing callables below. Installed clients: the tightened rules
   refuse nothing an installed build sends (analytics sinks are not wired in
   any build; both image fields were never written by a client; the client
   list queries already carry the `action in` filter; a promise time in the
   server's past was never valid).
4. **Functions**, per function through `scripts/deploy_functions_guarded.sh`.
   Lists by cause:
   - NEW-24 gate, live builds predate it (44): the list in
     `callableAccountStatePolicy.ts` kinds `app_user` (24), `review_capable`
     (9), `account_state` (13 after this change), `play_review` (3),
     `cleanupAvatarMedia`.
   - Moderation: `getCommunityModerationAccess`,
     `listCommunityModerationReports`, `setCommunityReportReviewing`,
     `decideCommunityReport`, `restoreCommunityAccount`,
     `checkCommunityModerationDeadlines`, `reportAndBlockUser`. The five
     console functions are safe to redeploy from git (same responses; a
     sanctioned operator and a withdrawn restore target are newly refused).
     Their live environment has 9 – 10 keys against 37 – 38 on recent
     deploys: the guard will list the additions to declare.
   - Blind meeting: `blindMeetingAction`, `blindMeetingMatchingTick`,
     `blindMeetingLifecycleTick`, `cleanupAvatarMedia`.
   - Schedulers / triggers: `autoCompleteExpiredGoodbyeSafetyStamps`,
     `sendDailyUnreadChatDigests`, `purgeExpiredEmailLinkTokens`,
     `recoverAvatarSourceRetention`, `onBambooPostLikeCreated`,
     `onDepartmentRecommendationPrivacySync`, every sender through
     `sendPushOnce`.
   - Others: `verifyAdultIdentityAfterLogin`, `grantPurchasedHearts`,
     `purchaseRecommendationRefresh`, `submitSafetyStamp`,
     `submitSafetyStampFollowUp`, `meetingIcebreakerAction`, the avatar
     admission / retry callables, and every function bundling
     `publicProfileSync`.
   The exact per-function drift (reachable symbols vs the live archive) must
   be recomputed against the merged tip before each batch, as in
   `05-p1-production-rollout.md`; it was not recomputed in this change.
5. **Hosting** (`hosting`): headers and the AASA file. The header rules were
   evaluated with the Hosting emulator's own matcher using POSIX path
   semantics; on Windows the local emulator applies no header at all
   (`glob-slasher` produces back-slash globs), so a live `curl -I` after the
   deploy is the real check.
6. **Optional backfill**: `adultIdentityOwnershipBackfillCli --audit`, then
   `--dry-run`, then `--apply` (21 ownership documents expected for the 7
   records). Uniqueness holds without it.

Guard dry-run on this tree: see §8.

## 7. Client items B-15 / B-16 and the rest of AUD-24

**AUD-24**

- Onboarding (keyword, profile Q&A, lifestyle): a second tap during a slow
  save pushed the next route before the write finished and the first tap
  pushed it again; a failed save escaped with no feedback; the back button did
  nothing. `OnboardingStepSaveGuard` (saved / failed / already running, 15 s
  bound) now decides. Eight other onboarding screens still carry the old
  pattern (RES-22).
- Blind follow-up screen: the client never asked the server for the selectable
  set (`getBlindMeetingFollowUpTargets`), so it listed opponents the server
  then refused; raw SDK error strings; an `already_submitted` answer left the
  cards open. Fixed on the client; the season 3:3 meeting is untouched.
- Tutorial: no single-flight guard and no bound on a pending offline write.
  Fixed.
- App links after an email-link launch: the listener returned for the whole
  session. Now only the launch link itself is skipped.
- Unbounded lists: notifications (window 50, badge cap 100), asks (50 / 20),
  likes (60), with pagination; the query shapes and the rule-required
  `action in ['like', 'super_like']` filter are unchanged and every shape is
  served by an existing index.

**B-13** — 20 irrelevant viewer-document updates after start-up: 1 feed load
(the initial one) instead of one reload per snapshot; a relevant change
(preference toggle, new exclusion) reloads exactly once.

**B-15** — FIXED_AND_VERIFIED for the shared avatar path. The client has no
image disk cache at all (memory only), so the disk-cache part is
NOT_APPLICABLE. Nothing passed a decode size: a 1024 px source was decoded in
full for a 48 px avatar. `ImageDecodeSize` (box × device pixel ratio, bucketed)
is applied in `CaptureProtectedImage` and the friend-list avatar; it is still
`Image.network`, so consent-gated photos keep their no-persist behaviour. The
process-wide image cache is now emptied on every session reset
(`clearSessionImageCache`). Not measured on a device; about 25 other call
sites are unchanged.

**B-16** — FIXED_AND_VERIFIED for the notification list, asks inbox, hearts
screens, my page and the mystery-card badges (`KeyedStream`: one instance
across rebuilds, a new one when the uid or the window changes). CONFIRMED_OPEN
for the blind-meeting (other than follow-up), event / team and friends-list
`StreamBuilder`s, which are created and destroyed by loading flags over
single-subscription repository streams and need per-screen lifecycle work
(RES-23).

## 8. Verification

Local, on the final tree of this branch (2026-11-22, Windows, JDK 21 for the
emulators, firebase-tools 15.18.0 locally; CI uses 15.30.2). "Before" is PR
#158 head `93fd52e8` as measured in that PR's CI run or locally at the start.

| Suite | Before | After |
|---|---|---|
| Functions `tsc --noEmit` (the `lint` script) | pass | pass |
| Functions unit (`node --test "**/*.test.js"`) | not measured at the start (CI green on PR #158) | 1,235 / 1,235 |
| Operator script tests | not in CI | 26 / 26 |
| Emulator suites, every `security-emulators` step | 18 steps (green in the PR #158 CI run) | 26 steps, 395 / 395 |
| `rules_tests` (Firestore) | 320 / 320 | 367 / 367 |
| Storage rules | 8 / 8 | 8 / 8 |
| Rules attack suite (`test/firestore_rules`) | 208 / 208 | 209 / 209 |
| `dart format --set-exit-if-changed lib test` | clean | clean (601 files) |
| `flutter analyze` | no issues | no issues |
| `flutter test` (whole suite) | 1,209 pass / 12 fail | 1,381 pass / 11 fail — the 11 golden diffs only |
| Python `pytest tests recsys/tests` | 2,422 pass / 3 fail (2026-11-13) | 2,425 pass / 17 skipped / 0 fail |
| `flutter build apk --debug --flavor production` | green in the PR #158 CI run | built locally; the merged manifest carries `allowBackup="false"` and both rule files |
| `flutter build web --release` | green in the PR #158 CI run | built locally |
| Python, the 95 files CI did not run, with CI-absent packages made unimportable | — | 4 collection errors + 20 failures without `httpx` / `Flask`; all green with them |

One step failed in the first full emulator pass: the two new blind-meeting
suites had been put in one emulator session, and the matcher (which reads
every open application of a date) saw the other suite's applicants. They are
separate CI steps now and pass separately (9 / 9 and 6 / 6).

Two Flutter failures appeared in the first full run and were test-side:
`widget_test` (the push listeners now attach first, so the 45 s heartbeat
timer exists in a bare app launch; the test resets the service) and
`meeting_icebreaker_parity_test` (it pinned the old deny-list text of the
analytics rule; it now checks the allow-list).

Guard dry-run on this tree
(`deploy_functions_guarded.sh --dry-run … reportAndBlockUser`):
`ENV DEPLOY CONTRACT: FAIL — ENV_KEY_MANIFEST_MISMATCH … missing:
KAKAO_APP_ID`. Expected: no function can be deployed from this branch until
the owner supplies the key (§6 step 2).

Not run: iOS build (no macOS), the staging-flavor APK, an Android release
bundle (signed or CI throwaway key), two-device
BLE, any real-device run, GitHub CI for this branch (not pushed). The
`python-full` job and the eleven new emulator steps have therefore never run
on GitHub.

## 9. New findings (not part of the 38)

| ID | Priority | Finding | State |
|---|---|---|---|
| RES-01 | P1 | Promise reminders: `schedulePromiseReminderTask` enqueues with `dateTime − 1 h − now`; Cloud Tasks refuses schedule times more than 30 days ahead and the date picker allows 180 days, so such a promise gets no reminder unless its document is written again inside the last 30 days (read, not reproduced) | OPEN — cap the delay near 29 days and re-enqueue on early delivery |
| RES-02 | P1 | A sanctioned account can delete itself while its ID token is valid and sign up again with the same mailbox (B-11) | OPEN — owner decision |
| RES-03 | P2 | Account reports (`reportKind: "profile"`) have no operator workflow; with the duplicate tracker an open one blocks the pair from filing another until it is closed by hand | OPEN — owner decision |
| RES-04 | P2 | Live orphans with no source: callable `saveUserPhoneHash`, triggers `onUserPhoneHashUpsert`, `onFestivalChatMessageCreated` | OPEN — owner-approved deletion |
| RES-05 | P2 | `firestore.rules` gates only chat writes on account state; other client writes of a sanctioned account stay open until the ID token expires (≤ 1 h). Callables are closed | OPEN |
| RES-06 | P2 | The season schedule lock is released when a party re-requests the promise on the day (P1-13 follow-up): the cancel window then reads `after_match_before_schedule` and no-show reports become impossible | OPEN — owner decision |
| RES-07 | P2 | `purgeAccountDeletionRetention`: fixed `limit(100)` window for empty teams; private-media scan restarts from the first id each run, sequential, 60 s timeout | OPEN |
| RES-08 | P2 | Blind-meeting ticks: 60 s timeout, unbounded queries, sequential per-meeting work, no per-meeting error isolation in several steps | OPEN |
| RES-09 | P3 | `meetingIcebreakerReconcileTick`: fixed `limit(200)` window; only malformed rows can stick | OPEN (suspected) |
| RES-10 | P2 | A friend party that loses a member to account deletion stays unmatchable until a remaining member cancels it (cancelling refunds everyone: policy) | OPEN — owner decision |
| RES-11 | P3 | An overdue report creates one alert document per open report per hour, without bound (live contract, kept) | OPEN — owner decision |
| RES-12 | P3 | `decideCommunityReport` writes the operator uid (`moderationActionedBy`) on the client-readable Bamboo document | OPEN |
| RES-13 | P2 | Function source archives in the GCF bucket contain `.env.seolleyeon-final` (plain keys by contract; readable by anyone with bucket read access) | OPEN — review bucket IAM |
| RES-14 | P3 | iOS: user defaults (email, onboarding draft, stamp location log) and the Firestore cache may be part of iCloud / iTunes backups | NOT_VERIFIED |
| RES-15 | P3 | iOS has no `bluetooth-peripheral` background mode: stamp presence stops while the app is suspended | OPEN — owner decision |
| RES-16 | P3 | `account_setup_flow.dart` `resolveCurrentState` swallows a users-document read failure and resolves `emailVerificationPending` (Splash defends itself; other callers do not) | OPEN |
| RES-17 | P3 | `scripts/build_android_app_check_diagnostic.sh` and its debug-provider sibling pass defines that a release build now ignores | OPEN — retire or switch to `--profile` |
| RES-18 | P3 | `chat_rooms` update rule is near the 1,000-expression evaluation limit (emulator warning on denied updates) | OPEN — care with further additions |
| RES-19 | P3 | 12 App Check debug tokens registered | OPEN — owner review |
| RES-20 | P3 | The local Hosting emulator applies no header on Windows; `lib/main.dart.rej` is a tracked reject leftover | OPEN |
| RES-22 | P3 | Eight more onboarding screens use the `_isSavingOnExit` pattern fixed in three (basic info, department, height, interests, major, self introduction, ideal lifestyle, ideal personality) | OPEN — `OnboardingStepSaveGuard` is reusable |
| RES-23 | P3 | `StreamBuilder`s created in `build()` remain in blind-meeting party / result / waiting screens, event and team screens and the friends list | OPEN |
| RES-24 | P3 | Not yet in the moderation console: `accountSummary` counts reports across partitions and kinds; `hideAuthorCommunityContent` is unbounded and runs before the sanction transaction; restore has no "was sanctioned by moderation" provenance check | OPEN |
| RES-21 | P3 | Leave / replacement never removes the room's `participantInfo[uid]` (merge with a map lacking the key does not delete it); the roulette transaction does not re-apply zone / shared-member checks to the re-read candidate (only relevant once the flag is on) | OPEN |

## 10. Product decisions waiting for the owner

AUD-26 (enable the campus-life-zone filter), B-11 / RES-02 (re-join and
self-deletion of a sanctioned account), golden baselines (11 images),
`KAKAO_APP_ID` value, `notificationDispatchLog` TTL policy, the no-op reminder
schedule, a refund rule for a pre-match application on deletion, RES-03,
RES-06, RES-10, RES-11, in-app appeal for a suspended account
(`submitInquiry` is refused today), Firestore / Auth App Check enforcement
(R-01), the diagnostic build scripts.

UI behaviour and copy introduced here that the owner should confirm: the
onboarding back button leaves the step even when the save failed (15 s save
bound); the follow-up screen hides non-selectable opponents instead of
showing them disabled, with two new strings; the notification header reads
"N개 이상" while the loaded window is full; page sizes (notifications 50,
asks 50, likes 60) and badge caps (100 / 20); the four safety-stamp refusal
messages; the 5-minute clock-skew grace of the stamp window.
