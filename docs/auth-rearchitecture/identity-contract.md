# Seolleyeon Auth Re-architecture — Identity Contract (v1)

Date: 2026-08-31. Branch: `feat/child-safety-standards-page` @ `fa67fa8d`.
This document is the single source of truth for the Yonsei-email-primary auth conversion.
All subsystem implementations (functions, rules, Flutter client, tests) MUST follow it exactly.
Based on the 2026-08-31 forensic audits of the working copy (client, functions, rules, recsys).

## 1. Identity definitions

| Concept | Definition |
|---|---|
| PRIMARY CREDENTIAL | Verified `@yonsei.ac.kr` mailbox (Firebase Email Link proof) |
| appUserId | The `users/{docId}` document ID. Existing users: the legacy Kakao numeric ID (unchanged, forever). New users: the Firebase email-link UID created at first sign-in (stable per mailbox). |
| Firebase runtime UID | After canonical session establishment, `FirebaseAuth.currentUser.uid == appUserId`, always. |
| Kakao identity | External identity used ONLY for friend-exclusion authorization. Never an authentication credential in the new client. |

Invariants:
- EMAIL AUTH → SEOLLEYEON AUTHENTICATION. KAKAO OAUTH → FRIEND EXCLUSION AUTHORIZATION ONLY.
- The new client binary contains NO code path `Kakao access token → Firebase custom token`.
- Legacy backend callables (`createFirebaseCustomToken`, `sendStudentVerificationEmail`,
  `completeStudentEmailLink`) remain deployed for old binaries but are UNREACHABLE from the new client.
- Existing appUserIds are never migrated/re-keyed. No automatic account merge, ever.

## 2. Canonical session custom claims

Minted only by `completePrimaryStudentEmailAuth`:

```
{
  appSession: true,
  primaryAuth: "yonsei_email",
  // ONLY when users/{appUserId}.kakaoUserId === appUserId (legacy invariant users):
  kakaoUserId: appUserId
}
```

Legacy sessions (old binaries, grandfathered) carry `{ kakaoUserId }` only.
Temporary email-link sessions carry neither.

Rules predicate (rollout-compatible canonical session check):

```
function isCanonicalAppSession() {
  return request.auth != null &&
    (request.auth.token.appSession == true || request.auth.token.kakaoUserId != null);
}
```

## 3. New/changed server-owned collections

### `studentEmailBindings/{emailHash}` (server-only; rules: all access denied)
- `emailHash` = lowercase hex `sha256(normalizedEmail)` where normalized = trim+lowercase, must match `/^[^@\s]+@yonsei\.ac\.kr$/` (reuse `normalizeYonseiEmail`).
- Fields: `{ appUserId: string, emailHash: string, createdAt, updatedAt }`. Never store raw email in the doc ID. Raw email may appear only inside the doc if strictly needed — default: do NOT store raw email here.

### `kakaoIdentities/{kakaoIdentityHash}` (server-only; rules: all access denied)
- `kakaoIdentityHash` = lowercase hex `sha256("kakao_identity:" + kakaoUserId)` (kakaoUserId = numeric string from `kapi.kakao.com/v2/user/me` id).
- Fields: `{ appUserId: string, kakaoUserId: string, linkedAt, status: "active" }`.
- Invariant: ONE Kakao identity ↔ ONE appUserId. No automatic re-binding.

### `users/{appUserId}` additions (server-written; client may read own doc)
```
kakaoFriendConnection: {
  connected: bool,
  kakaoIdentityHash: string,
  linkedAt, lastVerifiedAt,
  initialSyncComplete: bool,
  lastSuccessfulSyncAt
}
```
`friendConnectionReady` (spec name) is realized by the EXISTING server-owned field
`recommendationPrivacyReady` (fail-closed, already consumed by the recsys pipeline).
Do NOT introduce a duplicate readiness flag. Client resolvers read
`recommendationPrivacyReady == true` as "friend connection ready".

### `emailLinkTokens/{token}` — new token shape for the primary flow
Legacy shape (kept, old binaries): `{ email, kakaoUserId, createdAt, expiresAt }`.
Primary-flow shape (new): `{ email, purpose: "primary_auth", createdAt, expiresAt }` — NO kakaoUserId.
TTL 30min unchanged. On first completion, the same transaction changes the token to
`{ status:"completed", completedAppUserId, completedIsNewUser, completedAt }`.
This is logically single-use for account mutation, while the same server-verified mailbox may
retry until expiry to recover a custom-token response lost after the transaction committed.

## 4. New callables (functions/src)

### 4.1 `sendPrimaryStudentEmailLink`
`onCall(withAppCheck({ timeoutSeconds:30, memory:"256MiB", maxInstances:3, concurrency:10, secrets:[RESEND_API_KEY] }))`
- Auth: NOT required (pre-login). App Check enforced.
- Input `{ email: string, requestId: string }`; `requestId` matches `SAFE_EMAIL_REQUEST_ID`.
- Validation: `normalizeYonseiEmail` (reject non-Yonsei with `invalid-argument`, generic message).
- Rate limit: reuse `studentVerificationEmailRateLimits/{sha256("email:"+email)}` +
  `decideStudentVerificationRateLimit` (2/min, 10/day) transactionally.
- Idempotency: `studentVerificationEmailRequests/{sha256("primary:"+emailHash+":"+requestId)}`
  with `kind:"primary_auth"`; duplicate `sent` → `{accepted:true, duplicate:true}`.
- Token: `emailLinkTokens/{randomUUID()}` primary shape (above), created in the same transaction as the rate-limit bump.
- Link: `getAuth().generateSignInWithEmailLink(email, buildStudentVerificationContinueUrl(token))` (same ActionCodeSettings builder as legacy). Delivery via Resend, same idempotency header pattern, never log the action link/token/raw email.
- Response: `{ accepted: true, duplicate: bool }`.

### 4.2 `completePrimaryStudentEmailAuth`
`onCall(withAppCheck())`
- Auth preconditions (same rigor as legacy `completeStudentEmailLink`):
  `request.auth != null`; token email claim normalizes to `@yonsei.ac.kr`;
  `email_verified === true`; server re-read `auth.getUser(uid)` email+emailVerified match.
- Input `{ token }` matching `TOKEN_ID_RE`. Kakao ID never appears in input or output.
- Transaction over `emailLinkTokens/{token}`, `studentEmailBindings/{emailHash}`, `users/*`:
  1. Token must exist, `purpose == "primary_auth"`, not expired (reuse expiry/clock-skew logic), token email == authenticated email → else map to: malformed → `failed-precondition`; expired → `deadline-exceeded`; consumed/missing → `already-exists`/`failed-precondition`; email mismatch → `permission-denied`.
  2. Resolve appUserId:
     - binding exists → `appUserId = binding.appUserId`; `users/{appUserId}` must exist, else `failed-precondition` (`identity_conflict` class — manual remediation).
     - no binding → legacy query `users.where("studentEmail","==",normalizedEmail).limit(2)`:
       - 2+ docs → `failed-precondition` code detail `identity_conflict` (NO auto-merge).
       - 1 doc → require `isStudentVerified == true`; `appUserId = doc.id`; lazily create binding.
       - 0 docs → NEW USER: `appUserId = request.auth.uid` (the email-link UID); create `users/{appUserId}` shell:
         `{ appUserId, studentEmail, isStudentVerified: true, studentVerifiedAt, createdAt, lastLoginAt, profileImageUrl:"", profileImageMode:"avatar", kakaoFriendAvoidanceEnabled:false, recommendationPrivacyReady:false, kakaoFriendReconcileStatus:"pending" }`
         (fail-closed recommendation defaults); create binding.
  3. Rejoin/withdrawal guard: if resolved `users/{appUserId}` has `status in {deleting, banned, blocked, restricted_rejoin, suspended, withdrawn}` or `loginDisabled == true` or `isWithdrawn == true` → `failed-precondition` detail `rejoin_restricted`. NEVER create a fresh account to bypass.
  4. Existing user merge: if stored non-empty `studentEmail` != verified email → `permission-denied` (same message class as legacy). Merge `{ studentEmail, isStudentVerified:true, studentVerifiedAt, lastLoginAt }`.
  5. Mark the token `completed` in the same transaction. A retry for the same
     server-verified mailbox may re-read the recorded user and mint the same canonical session;
     it never repeats account resolution or creates a second account. Expiry/purge removes the marker.
- After the transaction: `createCustomToken(appUserId, claims per §2)`.
- Response: `{ customToken, appUserId, email, isNewUser, initialSetupComplete, adultVerified, recommendationPrivacyReady }`.

### 4.3 `linkKakaoFriendIdentity`
`onCall(withAppCheck())`
- Preconditions: `request.auth != null` (uid = appUserId); `users/{uid}` exists with `isStudentVerified == true`, else `failed-precondition` detail `primary_email_auth_required`.
- Input `{ kakaoAccessToken }`. Never logged.
- `verifyKakaoAccessToken` → server-resolved `kakaoUserId`; `hash = sha256("kakao_identity:"+kakaoUserId)`.
- Transaction:
  - `kakaoIdentities/{hash}` exists:
    - `.appUserId == uid` → idempotent success.
    - `.appUserId != uid` → `failed-precondition` detail `identity_conflict` (fail closed, manual remediation).
  - not mapped:
    - LEGACY COLLISION: if `users/{kakaoUserId}` exists AND `kakaoUserId != uid` → that Kakao identity IS another legacy account → `failed-precondition` detail `identity_conflict`.
    - if `users/{uid}.kakaoFriendConnection.kakaoIdentityHash` set and != hash → `failed-precondition` detail `relink_required` (no silent swap).
    - else create mapping + merge `users/{uid}.kakaoFriendConnection { connected:true, kakaoIdentityHash, linkedAt, lastVerifiedAt }`.
- Response: `{ linked: true, alreadyLinked: bool }`.

## 5. Modified callables

### `syncKakaoTalkFriendBlocks` (and `beginKakaoFriendRecommendationPrivacySync`)
- Caller identity check extended (rollout-compatible OR-chain): verified token's `kakaoUserId` is accepted iff
  `authUid === kakaoUserId` (legacy) OR `request.auth.token.kakaoUserId === kakaoUserId` (legacy claim)
  OR `kakaoIdentities/{hash}.appUserId === authUid` (new).
- Friend→member resolution extended (fixes the fail-open): a friend Kakao id `f` matches a member iff
  `users/{f}` exists (legacy invariant) OR `kakaoIdentities/{sha256("kakao_identity:"+f)}.appUserId` exists →
  use the RESOLVED appUserId for the exclusion pair. Chunked `getAll` as today (200/chunk); both lookups batched.
- On full success additionally merge `users/{uid}.kakaoFriendConnection { initialSyncComplete:true, lastSuccessfulSyncAt: serverTimestamp }` alongside the existing `recommendationPrivacyReady:true` finalization (same generation-guard transaction).
- All existing fail-closed semantics, pagination guards, generation guard, OFF-reconcile, error handling: UNCHANGED.

### Account deletion (`avatarCleanup.ts` PII plan)
Add to `planAccountDeletionPiiOperations`:
- delete `studentEmailBindings/{sha256(normalize(users/{uid}.studentEmail))}` when the binding's `appUserId == uid`.
- delete `kakaoIdentities/{users/{uid}.kakaoFriendConnection.kakaoIdentityHash}` when present and `appUserId == uid`; legacy fallback: `kakaoIdentities/{sha256("kakao_identity:"+uid)}`.

### Legacy endpoints — DO NOT MODIFY
`createFirebaseCustomToken`, `sendStudentVerificationEmail`, `completeStudentEmailLink` stay as-is
(old-binary compatibility). Mark with a comment: `LEGACY_KAKAO_AUTH_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS`.

## 6. Firestore rules changes (minimal, rollout-compatible)

- Add `isCanonicalAppSession()` (§2) and apply it (replacing bare `isSignedIn()`) ONLY to:
  - `publicProfiles/{uid}` `get`
  - `interactions/{id}` `create`
  - `asks/{askId}` `create`
  - `chat_rooms/{roomId}` `create`
  - `bamboo_posts` `create` (post create; likes/comments keep current predicates)
- Add explicit deny-all matches for `studentEmailBindings/{doc}` and `kakaoIdentities/{doc}`.
- KEEP the email-verified write branches on `users` (create Branch A / update Branch 1) — required by the legacy web completion page until force-update. Do not touch the uncommitted promises WIP.
- `users` update allowlists: allow no new client-writable fields. `kakaoFriendConnection` and `recommendationPrivacyReady` are server-only (they are already outside every allowlist — verify with tests).
- Mirror every text change into `functions/src/firestoreRules.test.ts`; add emulator tests in `rules_tests/` (new file `firestore.canonicalsession.test.mjs`): temp email-link session denied on the five surfaces above; kakao-claim session allowed; `{appSession:true}` session allowed; bindings/identities denied to everyone incl. owners.

## 7. Client architecture (lib/)

- `AuthService` additions: `sendPrimaryStudentEmailLink({email, requestId})` (NO Kakao preconditions),
  `completePrimaryStudentEmailAuth({token})` → sign in with custom token → assert `uid == appUserId` →
  returns `PrimaryStudentEmailAuthCompletion { appUserId, normalizedEmail, isNewUser, ... }`,
  `ensureCanonicalAppSession()` → true iff `FirebaseAuth.currentUser != null` (grandfathered legacy sessions included). No Kakao token exchange anywhere.
- DELETE from the new client call graph: `loginWithKakao*` as auth entrypoints, `ensureFirebaseSessionForKakao`, `ensureFirebaseSessionForVerifiedUser` (all call sites move to `ensureCanonicalAppSession()`), `KakaoAuthScreen`, `KakaoLoginFirestoreBootstrap`, `_savePhoneHashInBackground` Kakao side effect.
- New `KakaoFriendConnectionService`: `ensureKakaoOAuthSession()` (KakaoTalk→account fallback, bundleId handling preserved; PRECONDITION: canonical session, else throw `primary_email_auth_required`), `hasFriendsConsent()` / `requestFriendsConsent()` (reuse `KakaoTalkFriendService` scopes/loginWithNewScopes), `verifyFriendsApiAccess()` (`TalkApi.friends(limit:1)` success; empty list == success), `linkCurrentKakaoIdentity()` (new callable, passes access token, never logs), `syncInitialFriendExclusions()` (existing begin+sync callables), `verifyFriendConnectionReady()` (server read: `recommendationPrivacyReady == true` AND `kakaoFriendConnection.connected == true`). Kakao OAuth success NEVER sets `_isAuthenticated`.
- `StorageService`: new canonical API `saveAppUserId/getAppUserId/clearAppUserId` backed by the SAME pref key `kakao_user_id` (legacy install compatibility); legacy names remain as deprecated delegates. New pre-auth keys (global, no Kakao namespace): `pending_student_email`, `pending_student_email_request_id`. Local cache is UX only — never authentication proof.
- `AuthProvider` state: `_appUserId`, `_firebaseUid`, `_isAuthenticated`, `_isStudentVerified`, `_kakaoFriendConnection`, `_setupState`. Bootstrap: `FirebaseAuth.currentUser` → `users/{uid}` → hydrate → `AccountSetupResolver`. Keep the email-link single-consumer race guard (`_emailLinkPendingAtBootstrap`).
- `AccountSetupState` enum: `unauthenticated, emailVerificationPending, adultVerificationRequired, kakaoConnectionRequired, kakaoFriendsConsentRequired, kakaoFriendsVerificationRequired, initialFriendSyncRequired, onboardingRequired, tutorialRequired, complete` — resolved by ONE pure function `resolveAccountSetupState(...)` fed by server-truth fields.
- Routing: `/login` → email login screen (refactored `StudentVerificationScreen`, all Kakao preconditions removed); `/kakao-auth` → safe redirect to `/login`; NEW `/kakao-friend-connect` → `KakaoFriendConnectionScreen` (post-auth only); Splash ladder per resolver; adult verification gate exit → `/login`. Onboarding resolver untouched (WIP preserved). No deep link (email link, invite, push, scheme) may reach `/main` without `resolveAccountSetupState == complete`.
- UI copy: Kakao screen is "카카오 친구 연결" / "아는 사람 추천 차단" — never "카카오 로그인". Login screen has NO Kakao CTA.

## 8. What is intentionally NOT changed

- recsys/Python pipeline (privacy policy, daily job, verify): unchanged; the readiness gate contract is preserved.
- Season/blind/team meeting exclusion scope: unchanged (documented inventory; no arbitrary expansion).
- No server-side Kakao refresh-token storage / daily server-driven friend re-fetch:
  reported as `RECOMMENDATION_KAKAO_REFRESH_BLOCKER` (requires new credential infrastructure + Kakao console
  work + deployment; current fail-closed client-triggered contract is preserved verbatim).
- Legacy web completion page keeps working for legacy tokens; primary-flow tokens get a
  "complete in the app" guidance branch.
- No deploy, no commit, no push, no console mutation.

## 9. File ownership during implementation

- SERVER agent: `functions/src/**` (except `firestoreRules.test.ts`), `public/auth-email-link.html`.
- RULES agent: `firestore.rules`, `rules_tests/**`, `functions/src/firestoreRules.test.ts`.
- CLIENT agent: `lib/**`, `test/**` (Dart).
- Nobody touches: uncommitted WIP hunks (blind meeting, notifications, photo upload, promises rules block, ci.yml release job), `functions/src/avatarMedia.ts` (UTF-16), staged deletions.
