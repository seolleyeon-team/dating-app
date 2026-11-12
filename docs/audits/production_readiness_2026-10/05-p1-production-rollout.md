# P1-1 to P1-12 — Production Rollout (2026-11-10)

Candidate: PR #156 head `f460c3cf` = `security/integration` `8caab917` (PR #155,
P1-1…P1-12) + the rollout commits:

| Commit | Change |
|---|---|
| `f3b060cc` | Android: `com.google.gms.google-services` 4.3.15 → **4.4.2** (Crashlytics Gradle plugin 3.0.6 requires ≥ 4.4.1). Root cause of the two Android CI failures of run 42635931630. |
| `a9c92ddb` | Deploy guard: `--new-function X` + `--allow-failure-policy X` accepted for the same single function only (new `retry: true` trigger). |
| `f460c3cf` | P1-3: race-safe per-token transactional backfill (`create()` for missing records, never overwrites a trigger-written record), `--max-tokens` canary, read-only `--verify`; delivery fails closed for tokens without a record. |

CI on the candidate (run 42739138527): 10/11 green — Android debug APK and
production AAB compile smoke **pass** (were failing); Flutter `analyze` clean,
`test` 1186 pass / 14 fail = the NEW-13 baseline set, identical.

## 1. Fresh regression on the candidate

| Suite | Result |
|---|---|
| Functions lint / unit | clean / 1152/1152 |
| Firestore rules / Storage rules | 316/316 / 8/8 |
| Security emulator job (P0-1, P0-2, drift, NEW-19, P0-3, P1-1, P1-2, P1-3 (12, 4 new), P1-5, P1-8, P1-12) | green (CI) |
| Flutter analyze / test | No issues / 1186 pass, 14 fail (NEW-13 baseline, 0 new) |
| Android debug APK (production, staging) / production AAB (throwaway key, bundle deleted) | ✓ / ✓ (local and CI) |
| Web build | ✓ (CI) |

## 2. Source-archive drift audit (before any deploy)

Method: TypeScript-AST reachability per exported function (symbol level, from
the export through every referenced top-level declaration across modules) on
three trees — the live archive of each function, the base `09fefca1`, and the
candidate — plus a comparison of every module's top-level side effects and of
`package*.json`. A redeploy changes behaviour only where a *reached* symbol or
a side effect differs.

21 deployed functions reach a P1-changed symbol; 1 is new.

| Function | Live revision (rollback) | Drift live ≠ base on reached code | Class |
|---|---|---|---|
| onDeviceTokenWritten | — (new) | — | INTENDED_P1_CHANGE (new) |
| onInteractionCreated | 00008-xaq | `notify.createInAppNotification` P0-3 anonymisation | INTENDED_P1_CHANGE + ALREADY_MERGED (P0-3) |
| onRecEventCreated | 00007-fib | review-partition isolation in the handler; `import "./secureSharp"` | INTENDED_P1_CHANGE + ALREADY_MERGED |
| sendChatText | 00002-nuz | none | INTENDED_P1_CHANGE |
| onChatMessageCreated | 00009-mod | `chatUnread` rename `applyIncrements`→`applyUnreadIncrements` (no behaviour change) | INTENDED_P1_CHANGE + ALREADY_MERGED |
| unlockDirectChat | 00006-kur | none | INTENDED_P1_CHANGE |
| onAskCreated | 00007-bif | delivery-context push suppression in `sendPushToUsers`, P0-3 anonymisation, notification type set, sharp hardening | INTENDED_P1_CHANGE + ALREADY_MERGED |
| createEventTeamInvite | 00009-xis | sharp hardening side effect | INTENDED_P1_CHANGE + ALREADY_MERGED |
| onBambooCommentCreated / onBambooPostLikeCreated | 00008-jaz / 00007-saz | none (deployed from P0-3 candidate) | INTENDED_P1_CHANGE |
| autoCompleteExpiredGoodbyeSafetyStamps | 00007-cow | P0-3 anonymisation | INTENDED_P1_CHANGE + ALREADY_MERGED |
| dispatchPromiseReminder | 00007-jam | **recipient restricted to server-owned room participants** (security fix in git), notify suppression, sharp | INTENDED_P1_CHANGE + ALREADY_MERGED |
| dispatchMeetingIcebreakerPrompt | 00002-gab | notify suppression, collection names, sharp | INTENDED_P1_CHANGE + ALREADY_MERGED |
| sendDailyUnreadChatDigests | 00008-miz | P0-3 anonymisation | INTENDED_P1_CHANGE + ALREADY_MERGED |
| blindMeetingAction | 00019-jen | NEW-19 replacement-search fix (`fillBlindMeetingVacancies`), P0-3 anonymisation | INTENDED_P1_CHANGE + REQUIRED_DEPENDENCY (NEW-19 already on the ticks) |
| blindMeetingOps | 00002-nex | P0-3 anonymisation | INTENDED_P1_CHANGE + ALREADY_MERGED |
| blindMeetingMatchingTick / LifecycleTick | 00005-pig / 00004-duc | none | INTENDED_P1_CHANGE |
| cleanupAvatarMedia | 00015-taq | none | INTENDED_P1_CHANGE |
| purgeAccountDeletionRetention | 00006-yer | P0-3 account-deletion scrub (`authorId`, `bambooHiddenContent`, nested `metadata.inviterEmail`), `requireFirestoreDocumentId` | INTENDED_P1_CHANGE + ALREADY_MERGED |
| uploadOnboardingPhoto | 00004-lot | none | INTENDED_P1_CHANGE |

UNKNOWN_CHANGE: files absent from every git ref exist only in the 08-10/08-18
archives (`teamMeetingRequest.ts` — an older uncommitted snapshot lacking the
later concurrency guard — `triggerGraphManifest.ts`,
`avatarTriggerRecursionRegression.ts`); **none is reachable** from any of the
21 functions and none has a module side effect, so they are UNRELATED_DRIFT
replaced by the reviewed git version. `package*.json` of the four oldest
archives: earlier committed versions (sharp 0.34 → 0.35, two dependencies
added) already running on every newer function.

NEW-20: `reportAndBlockUser`, `createCommunityPost/Comment` and the
moderation callables are not in the set and were not touched.

Env guard (dry run of all 20 existing targets): **0 removed / 0 changed /
0 missing**; 94 additions on 8 old revisions, all canonical keys of the 31-key
file. Each added key was checked against the text of every symbol the
receiving function reaches: **none is read on that function's code path**.
Declared one key at a time per stage.

## 3. Read-only data audits (counts only)

| Audit | Result |
|---|---|
| P1-3 FCM registrations | 8 registrations, 6 tokens, **2 tokens under two accounts** (the defect), 0 registry records |
| P1-7 adult verification (`adultVerified && realNameVerified`, KST year age ≥ 20 set only by `verifyAdultIdentityAfterLogin`) | 23 users docs: 7 verified, 9 review partition (exempt), **7 active production accounts unverified** (1 with a chat room, 0 open blind application) → refused for dating actions; **nobody marked verified** |
| P1-5 participantInfo dotted-key residue | 23 rooms, 0 residue |
| P1-5 deletion coverage | 20 rooms show nicknames for 18 ids with no users doc — all synthetic seed ids (not Firebase uids; the existing `fake_user_1` follow-up), not deletion residue. Blind DNA / applications without users doc: 2 + 2, fixture ids. **10 onboarding photo objects of 3 real uids that no longer exist in Auth** (dated 2026-09-02 and 09-15) — see NEW-23. Default bucket: no lifecycle rule; soft delete 7 days |
| P1-10 legacy asks | 3 asks, all with snapshots (`nickname`, `uid`, `universityName`), **no image URL**, none in the last 30 days → no migration needed (text-only fallback; the external-image vector is absent) |
| P1-1 | matches 0, interactions 25 |

## 4. Rollout (executed 2026-11-10, all through `scripts/deploy_functions_guarded.sh`)

| Stage | Targets | Result | Rollback / forward repair |
|---|---|---|---|
| A | `onDeviceTokenWritten` (new, retry) `--new-function` + `--allow-failure-policy` | 101 → 102 functions; `00001-xug` ACTIVE, `RETRY_POLICY_RETRY`, `users/{uid}/deviceTokens/{token}`; post-deploy env == file; **live check 13/13** (claim, transfer + previous registration removed, client cannot read/write the registry or another account's registrations, release on logout), residue 0 | delete the function (no data dependency; senders still on old code) |
| B | FCM backfill: verify → dry-run → canary `--max-tokens 1` → full → re-run → verify | registrations backed up locally first; canary 1 created / 5 deferred; full: 5 created, 1 already recorded, **2 stale cross-account registrations deleted**; re-run 0 writes; **verify ok** (6 tokens, 6 records, 0 multi-account, 0 not owned) | restore the 2 registrations from the backup + delete `pushTokenOwners` (would re-open the leak — forward repair preferred) |
| C | `onInteractionCreated`, `onRecEventCreated` (together; shared `ensureMutualMatch`) | `00009-zap`, `00008-sub`; guard PASS (5 declared additions) | `gcloud run services update-traffic` to `00008-xaq` / `00007-fib` |
| D | `sendChatText`, `onChatMessageCreated`, `unlockDirectChat` | `00003-dun`, `00010-vok`, `00007-dac`; guard PASS (27 declared) | traffic to `00002-nuz`, `00009-mod`, `00006-kur` |
| E | push senders: `onAskCreated`, `createEventTeamInvite`, `onBambooCommentCreated`, `onBambooPostLikeCreated`, `autoCompleteExpiredGoodbyeSafetyStamps`, `dispatchPromiseReminder`, `dispatchMeetingIcebreakerPrompt`, `sendDailyUnreadChatDigests` (after B verified) | all updated; guard PASS (31 declared) | traffic to the revisions in §2 |
| F | `blindMeetingAction`, `blindMeetingOps`, `blindMeetingMatchingTick`, `blindMeetingLifecycleTick` | `00020-dip`, `00003-laz`, `00006-fes`, `00005-guh`; 0 env difference | traffic to §2 revisions |
| G | `cleanupAvatarMedia`, `purgeAccountDeletionRetention`, `uploadOnboardingPhoto` | `00016-cap`, `00007-din`, `00005-mim`; guard PASS (1 declared) | traffic to §2 revisions |
| H | Firestore Rules | ruleset `19d95b64` (03:27:05Z), byte-identical to `firestore.rules`; the previous `183f15d7` was byte-identical to `09fefca1` | re-release `183f15d7` |

Post-deploy: all 21 redeployed archives byte-identical to the candidate (236
files, diff 0), all ACTIVE.

## 5. Production security tests (live Rules + live triggers, client SDK)

Throwaway e-mail/password identities (`.invalid` domain, `appSession` claim;
the "verified" fixtures carry the adult flags on the test account only), all
artefacts removed, residue counted.

**55/55 PASS, residue 0**: D FCM (12), A adult gate (3: unverified like / ask
refused, self-assertion refused), B matching (11: deterministic like, one-shot,
blocked pair refused both ways, forged sender, extra fields, mutual like → one
deterministic match + direct room through the live trigger, ≤ 1 like
notification, client cannot create a match, blocked pair never matched), C chat
(12: status / type / participantInfo / membership immutable, metadata-only
update allowed, free-text / system / unknown message types refused, outsider
cannot read, cannot touch another member's unread state, closed room accepts
nothing), E asks (6: snapshot refused, blocked refused, exact schema accepted,
text immutable, read marking, outsider cannot read), H callables (5:
`sendChatText`, `unlockDirectChat`, `uploadOnboardingPhoto`,
`cleanupAvatarMedia`, `blindMeetingAction` refuse without App Check, HTTP 401),
I P0 preservation (4).

Limitation (unchanged from P0-3): the operator credential has no
`iam.serviceAccounts.signBlob`, so App Check / custom tokens cannot be minted
and callable *behaviour* (P1-2 send authorisation, P1-5 deletion, P1-7 in
callables, P1-9 upload) is verified on the emulator suites of the identical
source, with App Check enforcement verified live.

## 6. Post-deploy reliability

- Errors (severity ≥ ERROR) since 02:30Z: **0**. Warnings: exactly the 5
  App-Check-less probes.
- Executions on the new revisions: lifecycle tick 5×200, matching tick 2×200,
  goodbye auto-complete 2×200, trigger events 2xx.
- Schedulers ENABLED, no failure code. `sendDailyUnreadChatDigests`
  (`0 13 * * *` Asia/Seoul): first run on the new revision 2026-11-10 04:00Z —
  `00009-quq` started / collected / finished, HTTP 200, no warning or error.
- Integrity: FCM `--verify` ok after the tests; P0-2 unread `--verify` 23 rooms,
  0 mismatches, 0 structural issues; P0-3 Bamboo `--verify` 0 violations.

## 7. Open after the rollout

- NEW-23 (owner decision): 10 orphan onboarding photos of 3 accounts no longer in
  Auth — possibly QA / consent material; not deleted.
- Client release (NEW-12): P1-3 logout rotation, P1-4, P1-6 installed-build
  smoke, P1-9 client resize, P1-10 (installed builds' ask creates now refused —
  0 asks in 30 days), P1-11.
- NEW-11 DEFERRED, NEW-13, NEW-18, NEW-20 open; P1-13 out of scope.
