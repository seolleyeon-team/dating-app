# Seolleyeon — Auth & Onboarding Flow (single page)

Date: 2026-09-02. Implementation authority: this page + `terms-gate-contract.md`,
`identity-contract.md`, `kakao-friend-pairs-contract.md`. Nothing here is deployed.

## 1. The flow

```
APP START (splash)
  └─ TERMS  (required: termsOfService, privacyPolicy, kakaoNamePhone, ageOver20
             optional, never blocking: marketing, push, email)
  └─ YONSEI EMAIL LOGIN  ──► sendPrimaryStudentEmailLink (pre-auth, App Check,
                              carries the terms acceptance)
        └─ email link ──► temporary Firebase email session (NOT an app session)
              └─ completePrimaryStudentEmailAuth
                    ├─ terms proof required to CREATE an account (fail closed)
                    ├─ studentEmailBindings: ONE email ↔ ONE appUserId
                    └─ custom token, uid == appUserId, claims
                       {appSession:true, primaryAuth:"yonsei_email"}
  └─ CANONICAL appUserId  (FirebaseAuth.currentUser.uid == appUserId)
  └─ ADULT / REAL-NAME VERIFICATION (PortOne)
        verifyAdultIdentityAfterLogin requires request.auth.uid, so this gate
        can only run once the canonical account exists
  └─ KAKAO FRIEND CONNECTION  (OAuth → friends scope → loginWithNewScopes →
                               re-verify → linkKakaoFriendIdentity)
  └─ ONE-TIME FRIEND SNAPSHOT (createKakaoFriendPairsOnce → kakaoFriendPairs)
  └─ EXISTING ONBOARDING (unchanged resolver: basic info → interests → lifestyle
                          → major → photo → self-intro → QA → keywords → ideal
                          type → ideal lifestyle)
  └─ TUTORIAL
  └─ HOME
```

Single authority: `resolveAccountSetupState()` (`lib/models/account_setup_state.dart`)
→ `AccountSetupFlow.routeForState()`. No screen decides the next route on its own, and no
screen pushes `/main` outside the resolver. The debug-only QA shortcut (§6) is the single
exception and cannot exist in any release or profile artifact.

## 2. Ladder (server fields only)

| # | Condition | State → route |
|---|---|---|
| 1 | no Firebase session | `unauthenticated` → `/terms` |
| 2 | `isStudentVerified != true` | `emailVerificationPending` → `/student-verification` |
| 3 | terms version stale | `termsAcceptanceRequired` → `/terms` |
| 4 | `adultVerified && realNameVerified` not both true | `adultVerificationRequired` → `/adult-verification` |
| 5 | `kakaoFriendConnection.connected != true` | `kakaoConnectionRequired` → `/kakao-friend-connect` |
| 6 | `kakaoFriendSnapshot.status != "completed"` | `kakaoFriendSnapshotRequired` → `/kakao-friend-connect` |
| 7 | onboarding steps remain | `onboardingRequired` → next onboarding route |
| 8 | `hasSeenTutorial != true` | `tutorialRequired` → `/tutorial/welcome` |
| 9 | — | `complete` → `/main` |

## 3. Terms version semantics

- One repo-wide version constant: `LegalTexts.version` (client) / `CURRENT_TERMS_VERSION`
  (server), currently `2026-05-16`. Server rejects any version outside
  `SUPPORTED_TERMS_VERSIONS`.
- Authoritative record: `users/{appUserId}.termsAcceptance` — **Admin SDK only**, never named
  in `firestore.rules` (enforced by a negative scan in `functions/src/firestoreRules.test.ts`).
  Shape: `{schemaVersion, version, requiredDocumentIds, acceptedAt, source, optionalConsents,
  optionalUpdatedAt}`; `source ∈ {primary_auth_token, authenticated_reconsent}`.
- Legacy `users/{uid}.legalConsents` remains as a **UX receipt only**. It is client-writable and
  is never the authority for a gate.
- **`termsAcceptance.version` is the ONLY gate authority.** There is no grandfather clause:
  `legalConsents` sits inside three `firestore.rules` client-writable allowlists, so accepting it
  as gate truth would let any account open its own gate. An account without the server record
  re-consents **once**; that writes `termsAcceptance` and nothing else, so the appUserId,
  profile, Kakao identity, friend pairs, snapshot, chats, likes, recommendations, and payment
  history all survive untouched. No account is reset and no Kakao re-link or re-snapshot occurs.
- Version bump → rung 3 fires → terms screen in post-auth mode → `recordTermsAcceptance`
  callable → back into the ladder. The account, Kakao identity, friend snapshot, and onboarding
  are untouched.

## 4. Pre-auth proof lifecycle

1. Terms screen stores the **actual** selections locally (`pending_legal_consents`):
   accepted required ids + `{marketing, push, email}` + version. No value is fabricated.
2. `sendPrimaryStudentEmailLink({email, requestId, termsAcceptance})` validates the payload
   **before** consuming rate-limit quota; an absent/invalid payload fails closed with
   `terms_acceptance_required` / `terms_version_outdated`.
3. The proof rides on the existing single-use, 30-minute, server-only-writable
   `emailLinkTokens/{token}` doc as `{termsVersion, termsAcceptedAt, termsOptionalConsents}` —
   non-PII only, because that doc is readable by anyone holding the UUID.
4. `completePrimaryStudentEmailAuth` requires the proof to **create** an account (throws inside
   the transaction, before any write) and records `termsAcceptance` in the same transaction that
   consumes the token and writes the email binding — an account cannot exist without it.
   Existing users are never locked out; if their token carries a proof it is merged.
5. The nightly `purgeExpiredEmailLinkTokens` job disposes of unused proofs.

**Honest strength claim:** this guarantees ordering (no account without a recorded acceptance),
version validity against a server allowlist, and a server-written record the client cannot
rewrite. It does not cryptographically prove a human read the text; its anti-forgery strength
equals App Check.

## 5. Deep-link / cold-start / warm-start behavior

- Cold-start email link routes to the verification screen without rendering terms — that is
  safe because the **server** is the gate: completion without a proof fails, and the client maps
  `terms_acceptance_required` to a redirect to `/terms`.
- Push-notification taps resolve the setup state first; an incomplete account is sent to its
  prerequisite route, and an unexpected resolver error fails closed to `/terms`.
- Friend-invite links, Kakao OAuth callbacks, and warm-start resume all re-enter the same
  resolver.
- Killing the app at any step resumes from server state: terms (local pending only), email sent,
  link clicked, canonical session, Kakao consent, snapshot in progress, onboarding, home.

## 6. QA test-account shortcut — debug + explicit opt-in only

The terms screen still offers a test-account entry for local development, but it can no longer
exist in a shipped artifact. `DevEntryPolicy.resolveTestAccountEntry` is a pure function of two
inputs and requires **both**:

1. `isDebugBuild` — every release and profile artifact is excluded, and
2. `explicitQaEntryEnabled` — the compile-time define `ALLOW_TEST_ACCOUNT_ENTRY`, default `false`.

A flavor name grants nothing: `staging` is a signed release artifact that real testers install,
so treating the flavor as an authorization previously shipped a full gate bypass. `appFlavor` is
no longer referenced by the policy at all.

Enable it locally with:

```bash
flutter run --dart-define=ALLOW_TEST_ACCOUNT_ENTRY=true
```

Everything else — normal navigation, deep links, push taps — always goes through the resolver.

## 7. Session isolation invariants

- A temporary email-link session has **no** canonical claims. It cannot read `publicProfiles`,
  create `interactions`/`asks`/`chat_rooms`/`bamboo_posts`, and — after this change — cannot
  create a `users` document at all (the email-verified create branch was removed; only the
  verification **update** branch remains for the legacy hosted page).
- `resolveAuthedAppUser` no longer resolves an account from a JWT email claim. Email →
  appUserId resolution exists solely inside `completePrimaryStudentEmailAuth`.
- The hosted email-link page no longer renders the sign-in URL, `oobCode`, `apiKey`, or internal
  error details.
