# Terms Gate Contract (v1) — Terms → Email Auth → Kakao → Snapshot → Onboarding → Home

Date: 2026-09-02. Worktree `C:\tmp\consolidation-g004` @ `2ad95323`
(branch `integration/local-consolidation-20260831`; another session holds a staged index-only
cleanup — never use broad `git add`).
Composes with `identity-contract.md` (email-primary auth) and `kakao-friend-pairs-contract.md`
(one-time friend snapshot). Both remain in force and are NOT redesigned here.

## 0. Audit findings this contract must close (all verified 2026-09-02)

| # | Finding | Evidence |
|---|---|---|
| F1 | Terms is **not a gate** — it is merely what `unauthenticated` renders. No resolver rung, no server record consulted. | `account_setup_state.dart:62-116`, `account_setup_flow.dart:75` |
| F2 | `savePendingLegalConsents()` takes **no arguments** and writes five hardcoded `true`s, including `ageOver18` which is never shown in the UI. The user's actual checkbox state is never read. | `storage_service.dart:273-287` |
| F3 | Optional consents (marketing / push / email) are collected and **silently discarded**. | `terms_screen.dart:98-100`, no persistence |
| F4 | `_toggleAll` force-enables push/email but never disables them (asymmetric); master checkbox cannot be checked without the OPTIONAL marketing item. | `terms_screen.dart:233-245`, `:106` |
| F5 | Consent record is a **direct client Firestore write**, allowed by three `firestore.rules` allowlists, with `_readConsentBool(..., fallback: true)` — a malformed blob still records full consent. Nothing ever reads it back; no version comparison exists anywhere. | `user_service.dart:118-158`, `firestore.rules:894,946,973` |
| F6 | Consent flush is fire-and-forget with a swallowed catch, invoked from exactly one screen. | `account_setup_flow.dart:142-153` |
| F7 | **Deep-link bypass**: cold-start email-link branch routes straight to student verification; account creation succeeds with no terms at all. | `splash_screen.dart:79-86` |
| F8 | **Rules bypass (critical)**: `users` create Branch A lets ANY `{email, email_verified:true}` session create `users/{ARBITRARY_ID}` with `isStudentVerified:true`. No doc-id↔uid binding. A second account-creation path that never touches the callable. | `firestore.rules:844-861` |
| F9 | **Temp-session privilege escalation (critical)**: `resolveAuthedAppUser` falls back to `users.where("studentEmail","==", token.email)` **without checking `email_verified`**, and 20+ privileged callables consume it (hearts, spendHearts, unlockDirectChat, friend invites, avatar, season-meeting refunds). | `index.ts:1234-1240, 1247-1275` |
| F10 | Hosted email-link page renders the **raw sign-in URL incl. `oobCode`/`apiKey`** into the DOM. | `public/auth-email-link.html:111` |
| F11 | Push-notification tap routes `pushNamedAndRemoveUntil(RouteNames.main)` with no session/setup-state check. | `push_notification_service.dart:476,486,499,511,565,580` |

## 1. Final flow (source of truth)

```
APP START → TERMS (required consents)
          → YONSEI EMAIL LOGIN  → email link → temporary session
          → completePrimaryStudentEmailAuth (canonical appUserId + custom token)
          → ADULT / REAL-NAME VERIFICATION (PortOne)
          → KAKAO FRIEND CONNECTION (OAuth → friends scope → identity link)
          → ONE-TIME FRIEND SNAPSHOT
          → EXISTING ONBOARDING → TUTORIAL → HOME
```
Adult/real-name verification (PortOne) is retained as a gate, but it runs **after** the canonical
appUserId exists. `verifyAdultIdentityAfterLogin` requires `request.auth.uid`, so there is no
server path that attributes a pre-auth PortOne result to an account; running it before email auth
produced a result with nothing to attach to.

## 2. Terms document contract

Authority is the existing `lib/constants/legal_texts.dart`. Do NOT invent document ids or
rewrite legal copy.

REQUIRED (all four must be checked to proceed):
`termsOfService`, `privacyPolicy`, `kakaoNamePhone`, `ageOver20`

OPTIONAL (never blocking): `marketing`, and the `push` / `email` notification switches.

`ageOver18` is NOT a UI item and MUST NOT be fabricated in any record.

Version: single repo-wide `LegalTexts.version` (currently `'2026-05-16'`). Do not invent
per-document versions — the repo has one constant covering all four documents.

## 3. Server-owned record: `users/{appUserId}.termsAcceptance`

Server-written ONLY (Admin SDK). MUST stay absent from `firestore.rules` entirely, matching the
`kakaoFriendSnapshot` precedent, and MUST be added to the negative scan in
`functions/src/firestoreRules.test.ts` (the list that also holds `kakaoFriendSnapshot`,
`kakaoFriendConnection`, `recommendationPrivacyReady`).

```
termsAcceptance: {
  schemaVersion: 1,
  version: "2026-05-16",              // the accepted LegalTexts.version
  requiredDocumentIds: ["termsOfService","privacyPolicy","kakaoNamePhone","ageOver20"],
  acceptedAt: serverTimestamp,
  source: "primary_auth_token" | "authenticated_reconsent",
  optionalConsents: { marketing: bool, push: bool, email: bool },
  optionalUpdatedAt: serverTimestamp
}
```

The legacy client-written `users/{uid}.legalConsents` map STAYS (removing it breaks the
publicProfile exclusion test and legacy rules tests) but is demoted to a UX receipt. It is never
the authority for any gate. Its client-writable allowlist entries are left untouched.

Server constants (functions): `CURRENT_TERMS_VERSION = "2026-05-16"`,
`SUPPORTED_TERMS_VERSIONS = ["2026-05-16"]`, `REQUIRED_TERMS_DOCUMENT_IDS` as above.
Validation rejects unknown versions and any payload missing a required document id.

## 4. Pre-auth proof carrier: the existing `emailLinkTokens` doc

No new pre-auth collection. `sendPrimaryStudentEmailLink` already is the only pre-auth,
App-Check-enforced, rate-limited, idempotent, TTL'd, purged, server-only-writable document
writer in the system, and it is reachable only from the email screen that follows terms.

`sendPrimaryStudentEmailLink` input gains:
```
termsAcceptance: {
  version: string,
  acceptedDocumentIds: string[],           // must cover REQUIRED_TERMS_DOCUMENT_IDS
  optionalConsents?: { marketing?: bool, push?: bool, email?: bool }
}
```
Validation (fail closed): version ∈ SUPPORTED_TERMS_VERSIONS else `terms_version_outdated`;
required ids all present else `terms_acceptance_required`.

`emailLinkTokens/{token}` gains ONLY non-PII fields (the doc is world-readable by id —
`firestore.rules:23`):
```
termsVersion: string,
termsAcceptedAt: Timestamp,
termsOptionalConsents: { marketing: bool, push: bool, email: bool }
```
No raw acceptance payload, no identity beyond the `email` field that already exists.

**Honest security characterization (document this, do not overclaim):** this proves
(a) ordering — an account cannot be created without an acceptance recorded in the same
transaction, (b) version validity against a server allowlist, and (c) a server-written,
non-client-rewritable record. It does not cryptographically prove a human read the text; its
anti-forgery strength equals App Check.

## 5. `completePrimaryStudentEmailAuth` changes

- Extend the pure `evaluatePrimaryEmailLinkToken` with rejections `"terms-missing"` and
  `"terms-stale"`, mapped in `tokenError` to `failed-precondition` with
  `details: {detail: "terms_acceptance_required" | "terms_version_outdated"}`.
- **Enforce for the account-creating branch** (`decision.isNewUser`): no valid terms proof on the
  token ⇒ throw before any write. Existing-user merge branch is unchanged (no lockout, no
  migration).
- Write `termsAcceptance` (source `"primary_auth_token"`) into `buildPrimaryAuthNewUserShell`,
  and ALSO merge it for the existing-user branch when the token carries a proof (this is how a
  returning user who re-accepted a bumped version at login gets recorded).
- Response gains `termsVersion` (nullable) so the client can confirm.
- `primaryEmailAuth.test.ts:359` ("shell carries exactly the contract fields") must be updated,
  not deleted.

## 6. New callable: `recordTermsAcceptance` (canonical-only)

For an already-signed-in user whose accepted version went stale (§13 case B). Required because
`termsAcceptance` is server-only and the client cannot write it.

`onCall(withAppCheck())`, input `{ version, acceptedDocumentIds, optionalConsents? }`.
Preconditions: `request.auth?.uid` (else `unauthenticated`); `users/{uid}` exists (else
`failed-precondition`). Validates exactly as §4. Writes `termsAcceptance` with
`source: "authenticated_reconsent"`. Idempotent (same version ⇒ same terminal state).
Declare it inline in `index.ts` as `export const recordTermsAcceptance = onCall(withAppCheck(...)`
and add the name to the `required` list in `appCheckPolicy.test.ts:25-50`.

## 7. Client state machine

New `AccountSetupState.termsAcceptanceRequired`, routed to `RouteNames.terms`.

Resolver rung order (inserted after student verification, before adult verification):
1. no session → `unauthenticated` (routes to terms — unchanged)
2. `isStudentVerified != true` → `emailVerificationPending`
3. **terms stale** → `termsAcceptanceRequired`
4. adult verification → 5. kakao connection → 6. snapshot → 7. onboarding → 8. tutorial → 9. complete

Terms-stale predicate (pure, server fields only):
```
accepted = userDoc.termsAcceptance?.version
if (accepted == CURRENT) -> satisfied
otherwise -> termsAcceptanceRequired
```
`termsAcceptance.version` is the ONLY authority. `legalConsents` is never consulted: it sits in
three client-writable rules allowlists, so treating it as gate truth would let an account open
its own gate. An account lacking the server record re-consents once, which writes
`termsAcceptance` and nothing else — no account, Kakao, snapshot, or onboarding reset.

Terms screen behavior:
- Pre-auth (no session): submit stores the REAL selections locally (pending), then continues to
  the Yonsei email entry route. PortOne is a POST-auth gate — `verifyAdultIdentityAfterLogin`
  requires `request.auth.uid`, so a result produced before the canonical appUserId exists has no
  account to attach to.
- Post-auth (canonical session, stale version): submit calls `recordTermsAcceptance`, then
  re-enters `AccountSetupFlow.resolveNextRoute()`. Never pushes `/main` directly.

`StorageService.savePendingLegalConsents(...)` MUST take the actual values
(required doc ids + optional consents + version). Remove the fabricated `ageOver18`.
Add the pending-consent key to `clearUserScopedSession`.
`sendPrimaryStudentEmailLink` client wrapper passes the stored acceptance; if none is stored it
must not silently send — surface `terms_acceptance_required` and route to terms.
Client maps server `terms_acceptance_required` / `terms_version_outdated` errors to a terms
redirect (this is what closes the F7 deep-link bypass end to end).

`_toggleAll` fix: un-checking must clear push/email symmetrically. Required-only progression must
remain possible with every optional item unchecked (assert in a widget test).

## 8. Security fixes (separate ownership — these make the gate real)

- **F8** `firestore.rules` users create Branch A: the email-verified create branch is REMOVED.
  Justification verified: in the legacy flow the users doc always pre-exists before an email is
  ever sent (`createFirebaseCustomToken` builds the shell; legacy
  `sendStudentVerificationEmail` requires `users/{uid}.kakaoUserId === uid`), and the new flow
  creates the doc server-side with the Admin SDK. The email-verified **update** branch stays so
  the legacy hosted page can still stamp verification. The regression test in
  `rules_tests/firestore.canonicalsession.test.mjs` that currently pins the create open must be
  REWRITTEN to assert denial, keeping an update-branch positive case.
- **F9** `resolveAuthedAppUser`: remove the `studentEmail` email-claim fallback. Per
  `identity-contract.md` §7 the email→appUserId resolution belongs solely inside primary auth
  completion. Add a reproduction test first. If any consumer legitimately needs it, gate on
  `email_verified === true` AND report the consumer — do not keep the unverified path.
- **F10** `public/auth-email-link.html`: remove the raw-URL/token debug rendering (and any
  `oobCode`/`apiKey` echo). Keep user-facing error copy without internal detail.
- **F11** push-notification navigation: route through the setup resolver instead of an
  unconditional `pushNamedAndRemoveUntil(RouteNames.main)`.

QA test-account shortcut: `DevEntryPolicy.resolveTestAccountEntry` requires a debug build AND
the compile-time define `ALLOW_TEST_ACCOUNT_ENTRY` (default `false`). Release and profile
artifacts can never enable it, and the flavor name grants nothing — `appFlavor` is no longer
referenced by the policy.

## 9. Error contract (machine-readable `details.detail`)

`terms_acceptance_required`, `terms_version_outdated`, `identity_conflict`,
`rejoin_restricted` (existing), plus existing HttpsError codes. No raw internal errors or user
data in messages. Never log raw tokens, action links, emails, or acceptance payloads.

## 10. File ownership (no overlap)

- CLIENT agent: `lib/**/*.dart`, `test/**` (Dart).
- SERVER-TERMS agent: `functions/src/primaryEmailAuth.ts` (+ its test), the new
  `recordTermsAcceptance` wiring in `functions/src/index.ts` (ONLY the new export block and its
  imports), `functions/src/appCheckPolicy.test.ts`.
- SECURITY agent: `firestore.rules`, `rules_tests/**`, `functions/src/firestoreRules.test.ts`,
  `functions/src/index.ts` `resolveAuthedAppUser`/`emailFromAuthToken` region ONLY,
  `public/auth-email-link.html`.
- Both functions agents touch `index.ts` in disjoint regions; each must re-read before editing
  and never reformat unrelated code.

## 11. Prohibited

No commit, no push, no deploy, no production mutation. No broad `git add`. No unrelated
refactors, dead-code cleanup, or UI redesign. No test deletion to reach green.
