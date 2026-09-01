# Kakao Friend Pairs Contract (v2) — One-time Snapshot Architecture

Date: 2026-09-01. Worktree `C:\tmp\consolidation-g004`, branch `integration/local-consolidation-20260831` @ `246f29e3`.
This document is the binding contract for replacing the repeated Kakao friend sync
(`beginKakaoFriendRecommendationPrivacySync` / `syncKakaoTalkFriendBlocks` / `recommendationPrivacyReady`
pending gate) with a one-time-per-account friend snapshot + `kakaoFriendPairs`.
It composes with `identity-contract.md` (email-primary auth), which stays in force.
Implementing agents MUST NOT redesign names, schemas, or semantics.

## 1. Final data contract (spec §74)

- AUTH: Yonsei email → ONE appUserId (existing `studentEmailBindings` authority — unchanged).
- KAKAO: appUserId → ONE linked Kakao identity (`kakaoIdentities` — unchanged).
- SNAPSHOT: appUserId → Kakao Friends API → EXACTLY ONCE successful full snapshot.
- RELATIONSHIP: Kakao friendship + both are Seolleyeon users → `kakaoFriendPairs/{pairId}` (directionless, one doc).
- PREFERENCE: `users/{uid}.kakaoFriendAvoidanceEnabled` (bool, server-written via callable only).
- PAIR STATE: `avoidanceActive == (A_enabled OR B_enabled)`.
- SERVING INDEX: active pair → bilateral `recommendationExclusions/{viewer}/targets/{target}` docs; inactive → those docs deleted.
- RECOMMENDATION: full ranked candidates → exclusion filter → take N (backfill inherent). No score/rank mutation, no pending gate, no Kakao API at serving/batch time.

## 2. New collection: `kakaoFriendPairs/{pairId}`

- `pairId` = `buildRecommendationExclusionPairId(uidA, uidB)` = `[a,b].sort().join("_")` (REUSE the existing helper — keeps pairId identical across pairs and exclusion docs).
- Document:
```
{
  pairId: string,
  memberUids: [uidLow, uidHigh],          // always sorted, exactly 2
  source: "kakao_friend_snapshot",
  discoveredByUids: [uid, ...],           // arrayUnion
  avoidanceEnabledBy: [uid, ...],         // subset of memberUids
  avoidanceActive: bool,                  // == avoidanceEnabledBy.length > 0
  createdAt, updatedAt,
  schemaVersion: 1
}
```
- Server-only. Firestore rules: `match /kakaoFriendPairs/{pairId} { allow read, write: if false; }`.
- Never A-B and B-A duplicates. Upserts are `set(..., {merge:true})` + array unions → idempotent from either side's snapshot (spec §13).
- Privacy: appUserId pairs only. No Kakao IDs, nicknames, tokens, or non-member friends persisted. No analytics, no publicProfiles exposure, no raw-UID logging (hash via existing PrivacyLogUtils patterns).

## 3. Snapshot state: `users/{appUserId}.kakaoFriendSnapshot`

```
{
  status: "not_started" | "in_progress" | "completed" | "failed",
  snapshotRunId: string,        // present only while in_progress
  startedAt, completedAt, failedAt,
  pairCount: number,            // set on completed
  errorCode: string,            // set on failed (<=80 chars, no PII)
  schemaVersion: 1
}
```
- Server-written only (already outside every users-rules allowlist; keep it that way).
- Missing field == `not_started` (legacy users → migration gate, spec §30).
- Stale-lease policy: `in_progress` with `startedAt` older than 10 minutes is retryable (a new run may take over the lease in a transaction; old run's completion is rejected by `snapshotRunId` mismatch).
- `status == "completed"` is IMMUTABLE in this scope: no reset path, no re-fetch ever (spec §7, §42). Kakao relink after completion → `relink_required` stays fail-closed (existing `kakaoIdentityLink` behavior).

## 4. New callable: `createKakaoFriendPairsOnce`

`onCall(withAppCheck({ timeoutSeconds: 180, memory: "512MiB" }))`, input `{ kakaoAccessToken }`.

Preconditions (each its own error): auth != null (`unauthenticated`); `users/{uid}` exists with
`isStudentVerified == true` (`failed-precondition` / `primary_email_auth_required`); Kakao identity linked
AND server-verified token's Kakao id resolves to caller uid via `kakaoIdentities` mapping or legacy
uid==kakaoId (`failed-precondition` / `kakao_identity_not_linked` or `identity_conflict`).

Algorithm (spec §36):
1. Transaction A: read snapshot state. `completed` → return `{ alreadyCompleted: true, pairCount }` (NO Kakao API call). Fresh `in_progress` lease → `failed-precondition` / `snapshot_in_progress`. Else (not_started/failed/stale lease) acquire lease: `status:"in_progress", snapshotRunId: randomUUID(), startedAt`.
2. Outside tx: `verifyKakaoAccessToken` → kakao id → identity check (above). `fetchKakaoFriendServiceUserIds(accessToken)` — REUSE existing pagination/SSRF/5000-cap helper; any throw → failure path.
3. Resolve members: REUSE `resolveFriendExclusionAppUserIds` (legacy `users/{kakaoId}` OR `kakaoIdentities` mapping; self-skip; dedupe).
4. For each resolved friend appUserId, in chunks (≤200 reads via `db.getAll`, writes in batches ≤400):
   - read friend's `users` doc field `kakaoFriendAvoidanceEnabled` (and caller's own, read once);
   - upsert `kakaoFriendPairs/{pairId}`: memberUids sorted, `discoveredByUids: arrayUnion(callerUid)`, `avoidanceEnabledBy` = union of currently-enabled members (caller pref + friend pref — spec §37), `avoidanceActive` accordingly, `createdAt` only on create, `updatedAt` always;
   - materialize exclusions: if `avoidanceActive` → upsert BOTH `recommendationExclusions/{A}/targets/{B}` and `{B}/targets/{A}` with the §6 doc shape; if not active → delete both direction docs IF their `source` ∈ {"kakao_friend_pair","kakao_talk_friend"} (legacy reconcile, spec §31 — never touch other sources).
5. Legacy sweep (same run, idempotent): list caller's existing `recommendationExclusions/{caller}/targets/*` with `source == "kakao_talk_friend"`; for any target NOT re-materialized as an active pair this run → delete that doc AND the reverse doc `{target}/targets/{caller}` if reverse `source` ∈ kakao set and `pairId` matches. (General blocks live in `blocks` — untouched by construction.)
6. Completion transaction: re-read snapshot state; `snapshotRunId` mismatch → `aborted` (another run took over). Else set `{status:"completed", completedAt, pairCount, snapshotRunId: delete}`.
7. Failure path (any error after lease): guarded transaction sets `{status:"failed", failedAt, errorCode, snapshotRunId: delete}` — partial pair docs are LEFT IN PLACE (idempotent retry re-upserts). Never mark completed on partial pages (spec §10).

Response: `{ completed: true, pairCount, alreadyCompleted?: bool }`.

## 5. New callable: `setKakaoFriendAvoidanceEnabled`

`onCall(withAppCheck())`, input `{ enabled: boolean }` (strict boolean, else `invalid-argument`).
Preconditions: auth != null; `users/{uid}` exists.

1. Write `users/{uid}.kakaoFriendAvoidanceEnabled = enabled`.
2. Query `kakaoFriendPairs` where `memberUids array-contains uid`; for each pair (chunked, retry-safe):
   - transaction per pair (or batched with re-read): `avoidanceEnabledBy` arrayUnion/arrayRemove(uid); recompute `avoidanceActive = avoidanceEnabledBy.length > 0` (the OTHER member's state comes from the pair doc itself — spec §20);
   - active → upsert bilateral exclusion docs (§6 shape); inactive → delete both direction docs only when `source` ∈ {"kakao_friend_pair","kakao_talk_friend"} (spec §19, §57).
3. Pair docs are NEVER deleted by toggling (spec §43). No Kakao API call ever.
4. Response `{ enabled, pairCount, activePairCount }`. Concurrent A/B toggles are safe via per-pair transactions + array ops (spec §38).

## 6. `recommendationExclusions` doc shape (new writer)

Written/deleted ONLY by the two callables above + snapshot + account deletion:
```
{
  pairId,                       // same value as kakaoFriendPairs doc id
  userIds: [a, b] sorted,
  source: "kakao_friend_pair",
  reason: "kakao_friend_avoidance",
  active: true,                          // for server/client/python active-predicates
  enabledBy: { [uidA]: bool, [uidB]: bool },  // mirrors avoidanceEnabledBy (predicate compat)
  createdAt, updatedAt
}
```
Docs exist ⟺ pair active (delete on deactivate). All three existing active-predicates
(`recommendationRefresh.ts isExclusionActive`, Dart `_fetchRecommendationExcludedUids`,
Python `_is_active_exclusion`) accept this shape unchanged. Deletion anywhere in the new code
MUST check `source` ∈ {"kakao_friend_pair","kakao_talk_friend"} first (defensive; today no other
producer exists — manual/report blocks are in `blocks`, verified 2026-09-01).

## 7. Pending-gate removal (spec §23–§26, §32, §60)

REMOVE the Kakao-sync meaning of `recommendationPrivacyReady` everywhere in the NEW paths:
- Dart `ai_recommendation_service.dart`: delete viewer feed gates (`fetchProfileFeed`/`fetchMysteryFeed` early-return) and the per-candidate `recommendationPrivacyReady != true` filter + its watcher condition. The pair filter (`_fetchRecommendationExcludedUids` unioned into blockedUids, filter-then-take loop in `_hydrateProfiles`) STAYS — it already implements filter→take-N→backfill with no rank/score mutation. Do not change hydration order or the `.take(limit + blockedUids.length)` ban.
- Screens: `KakaoRecommendationPrivacyPrerequisite` consent-gate rendering and the feed-side `syncKakaoTalkFriendBlocks` retry paths are removed from `profile_card_screen` / `mystery_card_screen` (keep `RecommendationLoadFailure`). Live invalidation streams on `recommendationExclusions` stay.
- `recommendationRefresh.ts`: remove the `recommendationPrivacyReady !== true` candidate check (line ~178). Everything else (fetchExcludedCandidateUids, filter-then-take, [3..6) window, TOCTOU re-check on exclusionActive) stays.
- Python `seolleyeon_recommendation_privacy.py`: remove ONLY the `recommendationPrivacyReady` condition from `_is_recommendation_ready_user` (keep isStudentVerified / initialSetupComplete / status / visibility checks — those are account-state, not Kakao). `allows`/`filter_items`/`load_recommendation_privacy_policy`/`excluded_by_viewer` mirroring stay as-is (pair exclusions remain the Kakao filter). Keep existing rank renumbering behavior unchanged (pre-existing, order-preserving).
- `verify_job.py`: gates keep using the (narrowed) ready predicate; per-pair `privacy_policy.allows` check stays and now means "a Kakao-friend pair leaked" → still fatal.
- Server writers of the pending gate (`begin…Sync`/`sync…Blocks`) become DEPRECATED legacy endpoints: unchanged behavior for old binaries, `@deprecated` comment + `LEGACY_KAKAO_SYNC_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS` marker, ZERO call sites in the new client. `onUserRecommendationPrivacyBootstrap` trigger and `publicProfiles` projection of `recommendationPrivacyReady` stay (legacy compat; new code never reads them).
- New-user shell (`primaryEmailAuth.ts`): keep existing fields, ADD `kakaoFriendSnapshot: { status: "not_started", schemaVersion: 1 }`.

## 8. Client architecture

`KakaoFriendConnectionService` (rework):
- keep: `ensureKakaoOAuthSession()` (canonical-session precondition), `hasFriendsConsent()`, `requestFriendsConsent()`, `linkCurrentKakaoIdentity()`.
- replace `verifyFriendsApiAccess` + `syncInitialFriendExclusions` + `verifyFriendConnectionReady` + `markPendingAfterConsentRefusal` with:
  - `createFriendSnapshotOnce()` → callable `createKakaoFriendPairsOnce` (this IS the Friends-API access verification — no separate client-side `TalkApi.friends()` fetch; spec §8),
  - `loadFriendSnapshotStatus()` → server read of `users/{uid}.kakaoFriendSnapshot`,
  - `setFriendAvoidanceEnabled(bool)` → callable `setKakaoFriendAvoidanceEnabled`.
- `runFullConnectionFlow()` order: oauth → friends consent (loginWithNewScopes on missing, re-verify) → identity link → snapshot-once → server status check `completed`. Consent refusal → stay on screen (no server pending write needed anymore). NO syncFriendsEveryLaunch anywhere.

`AccountSetupState`: values become `unauthenticated, emailVerificationPending, adultVerificationRequired, kakaoConnectionRequired, kakaoFriendsConsentRequired (screen-internal), kakaoFriendSnapshotRequired, onboardingRequired, tutorialRequired, complete` (drop `kakaoFriendsVerificationRequired`, drop `initialFriendSyncRequired`). Resolver ladder:
session → studentVerified → adult → `kakaoFriendConnection.connected != true` → kakaoConnectionRequired →
`kakaoFriendSnapshot.status != "completed"` → kakaoFriendSnapshotRequired → onboarding → tutorial → complete.
MIGRATION GATE (spec §30): legacy users (no `kakaoFriendConnection` and/or no snapshot field, regardless of
`recommendationPrivacyReady`) resolve to kakaoConnectionRequired/kakaoFriendSnapshotRequired ONCE; the
connection screen runs consent-check → link (idempotent) → snapshot-once, and never re-runs after `completed`.
It never re-requests profile onboarding.

Remove from client: `AuthProvider._reconcileRecommendationPrivacyIfNeeded` (+ its bootstrap call),
`onboarding_save_helper` sync-before-completeOnboarding (snapshot is pre-onboarding now; helper just calls
`completeOnboarding`), `initial_setup_screen` sync call, `ContactBlockService.syncKakaoTalkFriendBlocks`/
`beginKakaoFriendRecommendationPrivacySync`/`markRecommendationPrivacyPendingAfterConsentRefusal` client
methods (getKakaoFriendAvoidanceStatus is reworked to read pref + snapshot state).
`contact_block_screen` avoidance toggle → `setFriendAvoidanceEnabled` (no consent/API fetch; copy per §43:
"켜면, 가입 시 확인된 카카오 친구 중 설레연 이용자와 서로 추천되지 않아요.").

## 9. Account deletion (spec §41)

Extend the avatarCleanup deletion plan: query `kakaoFriendPairs` where `memberUids array-contains uid` →
delete each pair doc; existing unconditional deletion of `recommendationExclusions/{uid}/targets/*` and
reverse targets already covers the exclusion docs (target account is gone — source-agnostic delete is
correct there). Keep existing kakaoIdentities/binding cleanup. Chunked, idempotent.

## 10. Rules

- Add `kakaoFriendPairs` deny-all match. `users` allowlists already exclude `kakaoFriendSnapshot` (verify + test).
- `recommendationExclusions` rules unchanged (owner read, server write).
- rules_tests: kakaoFriendPairs denied for anon/emailLink/kakao/appSession incl. own-member docs; snapshot field not client-writable; exclusion rules regression kept.
- Mirror text changes into `functions/src/firestoreRules.test.ts`.

## 11. Email uniqueness (spec §4, §5, §49) — verification + hardening only

The existing `studentEmailBindings` transaction in `primaryEmailAuth.ts` already implements
ONE EMAIL ↔ ONE APP USER (binding-hit → same appUserId; no-binding+legacy-1 → reuse; 0 → create; 2+ → conflict).
Required: confirm/add tests for — second signup attempt resolves the SAME appUserId (never a second account),
returning login after logout/reinstall resolves same appUserId, case-insensitive normalization, concurrent
completion attempts cannot create two accounts (single-use token + binding tx), ambiguous binding → fail closed.
No schema change expected; fix only if a gap is proven by a failing test.

## 12. Grep-able invariants (contract tests will assert these strings)

- functions/src: `createKakaoFriendPairsOnce`, `setKakaoFriendAvoidanceEnabled`, `kakaoFriendPairs`,
  `fetchKakaoFriendServiceUserIds(accessToken` (reused), `resolveFriendExclusionAppUserIds` (reused),
  `source` check before exclusion deletion, `kakaoFriendSnapshot`.
- New client: ZERO occurrences of active calls to `syncKakaoTalkFriendBlocks`,
  `beginKakaoFriendRecommendationPrivacySync`, `_reconcileRecommendationPrivacyIfNeeded`;
  ai_recommendation_service keeps `_fetchRecommendationExcludedUids` and the filter-then-take loop; ban on
  `.take(limit + blockedUids.length)` stays.
- Python keeps `load_recommendation_privacy_policy`, `privacy_prefilter_limit`,
  `privacy_policy.filter_items`, `privacy_policy.allows(uid, candidate_uid)`; `_is_recommendation_ready_user`
  no longer contains `recommendationPrivacyReady`.

## 13. Ownership during implementation

- SERVER agent: `functions/src/**` except `firestoreRules.test.ts`.
- PYTHON agent: `lib/ai_recommend_model/**/*.py`, `recsys/**`, `tests/*.py` (only files it must touch).
- CLIENT agent: `lib/**/*.dart`, `test/**` (Dart).
- RULES agent: `firestore.rules`, `rules_tests/**`, `functions/src/firestoreRules.test.ts`.
- No commit / push / deploy / production data mutation. Docs in docs/auth-rearchitecture are main-agent-owned.

## 14. Accepted trade-offs / deliberately out of scope (document, do not "fix")

- Friendships formed AFTER both users' snapshots are never auto-discovered (spec §14). No hidden resync.
- Snapshot reset / Kakao account change recovery: manual support operation, not implemented (spec §7, §42).
- Season/blind/team/group meeting surfaces: no `recommendationExclusions` usage today; scope unchanged (spec §27).
- Legacy binaries keep hitting deprecated sync endpoints until force-update; removal is a documented later step (spec §62).
