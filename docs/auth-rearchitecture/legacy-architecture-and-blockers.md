# Legacy Auth Architecture Record + Known Blockers

Snapshot date: 2026-08-31, branch `feat/child-safety-standards-page` @ `fa67fa8d` (working copy).
This documents the PRE-conversion production contract (spec step "현재 production contract를 먼저 문서화한다")
and the externally-blocked items discovered during the forensic audit.

## A. Legacy (pre-conversion) identity model

- Kakao numeric user id == `users/{docId}` == Firebase Auth UID == SharedPreferences namespace.
- Session establishment: local `kakao_user_id` pref → Kakao SDK access token →
  callable `createFirebaseCustomToken` (App Check enforced, no Firebase auth required) →
  `createCustomToken(kakaoId, {kakaoUserId})` → `signInWithCustomToken`.
- Yonsei email was a decoration: `sendStudentVerificationEmail` required a Kakao-backed session
  (`users/{uid}.kakaoUserId === uid`); `completeStudentEmailLink` traded the temporary email-link
  session back for a Kakao-UID custom token.
- Login flow: `/` → `/terms` → `/adult-verification` (PortOne) → `/kakao-auth`
  (Kakao OAuth + mandatory `friends` consent) → `/student-verification` → onboarding → tutorial → main.
- `friends` scope consent was enforced ON the login screen (`_pauseForMissingFriendsConsent`),
  i.e. before the account even reached email verification.
- Firestore rules used no custom claims; identity was purely `request.auth.uid` + standard
  `email`/`email_verified` claims.

## B. Friend-exclusion contract (unchanged by the conversion)

- `recommendationExclusions/{owner}/targets/{target}`: bilateral, sorted `pairId`, `enabledBy` map,
  server-write-only, owner-read-only.
- Sync is CLIENT-TRIGGERED: `beginKakaoFriendRecommendationPrivacySync` (closes the gate fail-closed
  first) → client obtains Kakao access token → `syncKakaoTalkFriendBlocks` (server fetches
  `kapi.kakao.com/v1/api/talk/friends` with pagination/SSRF guards, 5000 cap fail-closed).
- Gate: `users/{uid}.recommendationPrivacyReady` — fail-closed default, consumed by the Python
  pipeline at every stage (CLIP/SVD/KNN export → RRF → daily → verify; verify fails the whole
  Cloud Workflows run on any privacy violation).
- Sync failure NEVER deletes prior exclusions; the user is excluded bilaterally (viewer AND candidate)
  until a successful sync.
- Daily pipeline: Cloud Scheduler `0 4 * * *` KST → Cloud Workflows `recs_pipeline.yaml`
  (export → clip/svd/knn parallel → rrf → daily → verify → season-meeting chain).
  There is NO friend-refresh step in the workflow.

## C. Blockers / findings requiring user decision (not fixed unilaterally)

### RECOMMENDATION_KAKAO_REFRESH_BLOCKER — RESOLVED BY DESIGN (2026-09-01)
Superseded by the one-time-snapshot architecture (`kakao-friend-pairs-contract.md`,
`kakao-friend-pairs-rollout.md`): the product contract now fetches the friend list exactly once per
account at onboarding and never refreshes it (daily/app-open resync intentionally abolished; new
friendships after both snapshots are a documented trade-off). FRESHNESS_MARKERS below is likewise
moot. Historical record kept below.

The stated policy "re-check Kakao friends every day before recommendations" is not implementable
server-side today: no Kakao refresh token is stored anywhere, there is no server-side token refresh,
and the server can call the Kakao API only with an access token the client passes per request.
Current production semantics (preserved by this conversion): friend sync runs on every authenticated
app start; users whose sync is stale-but-last-successful stay ready with the last confirmed snapshot;
users whose sync failed are excluded bilaterally.
A true daily server-driven refresh requires: secure per-user Kakao refresh-token storage (new
credential infrastructure, encryption strategy), Kakao console configuration, a new scheduled
workload (billable), and deployment — all outside this task's authorization. Decision needed.

### FRESHNESS_MARKERS_WRITTEN_BUT_UNREAD
`kakaoFriendReconciledAt` and exclusion `verifiedAt` are written but consumed nowhere. A staleness
gate was deliberately NOT added in this conversion: gating recommendations on same-day sync would
empty recommendations for every user who did not open the app that day (a major product behavior
change). Decision needed if daily freshness must be enforced.

### EXCLUSION_SCOPE_INVENTORY (spec §57 — recorded, not changed)
Kakao friend exclusion applies to: 1:1 daily recs, CLIP/SVD/KNN/RRF sources, mystery/AI client
feeds, paid recommendation refresh (incl. transactional re-check).
It does NOT apply to: season meeting (3:3), blind meeting, team meeting requests, meeting group
index. Those use `blocks` (phone/contact/report) and/or recEvents-derived block pairs only.
Per spec, existing scope was neither reduced nor expanded.

### REJOIN_RESTRICTION_EFFECTIVELY_ABSENT_POST_DELETION
Account deletion hard-deletes `users/{uid}` after setting `canRejoin:false` etc., leaving no
tombstone; a completed deletion allows immediate re-signup. The new email flow enforces the
restriction only while restriction markers exist (during/failed deletion). Introducing a durable
ban/tombstone is a policy decision, not made here.

### PHONE_HASH_SOURCE_REMOVED_FROM_AUTH_FLOW
The only producer of `userPrivate/{uid}.phoneHash` was the Kakao login side effect
(`_savePhoneHashInBackground`). Per spec §20/§51 this side effect is not part of the new friend
connection flow. Contact-block matching for NEW users will not receive a Kakao-sourced phone hash
until a separate, explicitly-consented flow provides one (`syncContactBlocks` device-contacts flow
is unaffected). Decision needed if Kakao phone collection should be re-introduced with its own consent.

### LEGACY_KAKAO_AUTH_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS
`createFirebaseCustomToken`, `sendStudentVerificationEmail`, `completeStudentEmailLink`, the legacy
`emailLinkTokens` shape, and the users-doc email-verified rule branches (create Branch A / update
Branch 1) stay for old binaries and the hosted web completion page. Cleanup list (after force update):
remove those callables + rule branches + the web page's client-side verification write + dead
`evaluateEmailLinkTokenExchange`.

### CI_GAPS (pre-existing, unchanged)
`test/firestore_rules/` (incl. `kakao_login_rules.test.js`) never runs in CI; only 4 of ~59 root
`tests/*.py` files run in CI. Not expanded here to avoid unrelated CI changes.
