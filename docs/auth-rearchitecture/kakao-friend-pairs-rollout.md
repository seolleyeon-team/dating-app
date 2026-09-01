# Kakao Friend Pairs — Rollout & Migration Plan (spec §61–§62, §65)

Date: 2026-09-01. Companion to `kakao-friend-pairs-contract.md`. No production mutation, deploy,
commit, or push has been performed; every step below that touches production requires separate approval.

## A. Safe rollout order (spec §62)

1. Deploy schema-compatible server (new callables `createKakaoFriendPairsOnce`,
   `setKakaoFriendAvoidanceEnabled`; deprecated-but-unchanged legacy sync endpoints; rules with
   `kakaoFriendPairs` deny-all; python privacy-predicate narrowing deployed WITH or AFTER the
   serving-side gate removal — never before the new client exists, see note below).
2. New snapshot/pair creation becomes available (new client binary released).
3. Users migrate one-time via the client migration gate (§30): existing authenticated user without
   `kakaoFriendSnapshot.status == "completed"` → connection screen → consent check → idempotent
   identity link → `createKakaoFriendPairsOnce` → completed. Onboarding/profile steps are NOT re-asked.
4. Pair materialization confirmed via the dry-run counter
   (`scripts/kakao_friend_pairs_migration_dryrun.mjs`, READ-ONLY): watch
   `usersRequiringSnapshot` ↓, `friendPairDocs` ↑, `legacyExclusionDocs` ↓ (per-user legacy sweep
   runs inside each snapshot), `otherSourceExclusionDocs` stays 0.
5. Avoidance state materialized (toggle callable; pair docs carry `avoidanceEnabledBy`).
6. Remaining legacy `source == "kakao_talk_friend"` exclusions belong to users who have not yet
   migrated — they keep serving their fail-closed purpose for legacy binaries and are reconciled
   per user at snapshot time. NO bulk deletion.
7. Old sync clients disabled via force update.
8. Deprecated backend removal (separate change): `beginKakaoFriendRecommendationPrivacySync`,
   `syncKakaoTalkFriendBlocks`, `onUserRecommendationPrivacyBootstrap` pending defaults,
   `recommendationPrivacyReady` publicProfiles projection, `KakaoRecommendationPrivacyPrerequisite`
   leftovers, remaining `kakao_talk_friend` docs (only after zero legacy binaries remain).

**Ordering caveat (fail-closed direction):** during the window where the OLD python batch (still
gating on `recommendationPrivacyReady`) runs against NEW users who never sync, those new users are
absent from recommendations (fail-closed, temporary). The reverse order (new python before new
client) is also safe: legacy users keep their pair exclusions via the legacy docs. Either interim
is safe; recommended: ship python + functions + client in one release train.

## B. Transition semantics for mixed binaries

- Legacy binaries keep calling the deprecated sync endpoints; those still write
  `recommendationPrivacyReady` / reconcile fields — harmless: new serving code no longer reads them.
- Legacy sync may also overwrite `kakao_talk_friend` exclusion docs for not-yet-migrated users —
  by design (their protection until migration).
- A migrated user who then opens a legacy binary would re-run the legacy sync; its docs
  (`source: "kakao_talk_friend"`) are re-reconciled at next new-binary launch only if the snapshot
  is re-... — it is NOT re-run (exactly-once). Residual risk: a migrated user on a legacy binary can
  re-create `kakao_talk_friend` docs that outlive their preference-OFF state until force update.
  Impact: over-exclusion only (never under-exclusion) — acceptable, fail-safe direction. Documented.

## C. Deliberate product trade-off (spec §14)

After both users' snapshots are complete, NEW Kakao friendships are never auto-discovered.
No hidden resync compensates for this. Any future re-snapshot/recovery is a separate, manual,
support-driven operation (spec §7/§42: snapshot immutable after completed; Kakao account change
requires manual recovery).

## D. 1:1 surface inventory (spec §65)

| Surface | Data source | Kakao friend avoidance |
|---|---|---|
| Mystery card / locker board + preview | `modelRecs/.../sources/rrf→clip→svd` via AiRecommendationService | **APPLIES** (client filter-then-take + batch pair prune) |
| Profile card swipe deck | `modelRecs/.../sources/svd` via AiRecommendationService | **APPLIES** |
| Paid recommendation refresh (1:1 window) | `recommendationRefresh` callable | **APPLIES** (incl. in-transaction TOCTOU re-check) |
| AI preference screen | `ai_profiles` synthetic deck | DOES_NOT_APPLY (not real users) |
| Profile discovery / AI match card | static mock data | DOES_NOT_APPLY (no pipeline) |
| `dailyRecs` batch output | written by daily_job, read by nothing client-side | Defense-in-depth only (not a serving surface) |
| Season meeting (3:3), blind meeting, team meeting, roulette/icebreaker, group index | `blocks` / recEvents-based only | OUT OF SCOPE (unchanged; never read recommendationExclusions — verified 2026-09-01) |
| Friend invite / community | not recommendation surfaces | OUT OF SCOPE |

Block/report exclusions (`blocks` collection) keep their existing, wider scope everywhere — untouched.

## E. Dry-run tooling (spec §61)

`scripts/kakao_friend_pairs_migration_dryrun.mjs` — Admin-SDK, READ-ONLY, emulator-compatible
(`FIRESTORE_EMULATOR_HOST`). Reports: usersTotal, usersWithCompletedSnapshot, usersRequiringSnapshot,
usersWithKakaoConnection, usersAvoidanceOn, legacyExclusionDocs, newPairExclusionDocs,
otherSourceExclusionDocs, kakaoIdentityMappings, friendPairDocs, activeFriendPairDocs,
potentialIdentityConflicts. Production runs require approval (read-only, but touches production data).

## F. App Review wording (spec §64)

`app-review-notes.md` must state (updated alongside this change): the friend list is accessed during
required onboarding authorization, exactly once per account, to establish internal
acquaintance-exclusion relationships; it is NOT re-checked on every launch; friend data is not used
for ranking, advertising, profile display, or social graph exposure. Remove any "checked daily/every
launch" phrasing.
