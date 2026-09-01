# App Review Notes — Kakao Usage (Draft, English)

> Draft prepared 2026-08-31 for the Yonsei-email-primary auth re-architecture.
> This text must remain byte-accurate to the shipped behavior. Do not submit wording
> that the code does not implement.

## Reviewer notes (App Store Connect draft)

Kakao is not used to create or authenticate a Seolleyeon account.

Users create and authenticate their Seolleyeon account exclusively using a verified
Yonsei University email address (`@yonsei.ac.kr`), via a Firebase email sign-in link.

After primary authentication is complete, Kakao authorization is used solely for a
privacy and safety exclusion feature that prevents users who are already Kakao friends
from being recommended to each other. The friend list is accessed during the required
onboarding authorization, exactly once per account (with the user's explicit `friends`
scope consent): the server fetches it a single time, matches it against registered
members, and stores only internal acquaintance-exclusion relationships between
Seolleyeon accounts. The friend list is NOT re-checked on app launch, daily, or at
recommendation time.

Kakao friend data is not used for ranking, advertising, profile display, or social
graph exposure. The raw friend list is never shown in the app and is never persisted —
only pair relationships between registered members are stored, in a server-only
collection. Kakao profile data (nickname, profile image, email, phone number) is not
collected for account creation or profile population.

Users control the feature with an "avoid Kakao friends" preference: when either member
of a pair enables it, the two users are excluded from each other's 1:1 recommendations;
when both disable it, the exclusion is lifted. Disconnecting Kakao does not delete or
disable the user's Seolleyeon account.

## Guideline 4.8 alignment checklist (must be proven by static audit before submission)

1. Primary login UI: Yonsei email only — no Kakao CTA on the login screen.
2. Kakao OAuth is reachable only after the Firebase primary (email) session exists.
3. Kakao access tokens are never exchanged for a primary Firebase session in the new binary.
4. Kakao ID is never used as a primary account lookup/login credential in the new binary.
5. Kakao disconnect never destroys account identity.
6. Kakao CTA copy means "friend connection / acquaintance-exclusion", not "login".
7. Kakao profile/email/phone are not used to create the primary account.
8. New client call graph contains no `Kakao token → Firebase custom token` path
   (enforced by source-contract tests).

## Guideline 5.1 privacy risk (open, documented — NOT resolved by 4.8 alignment)

Product requirement: onboarding cannot proceed without Kakao `friends` consent
(no "skip / later" option). Apple may independently evaluate whether mandatory access
to the friend list is proportionate to core functionality.

Mitigations shipped:
- Purpose limitation is enforced in code: friend data feeds only the exclusion pipeline
  (`recommendationExclusions`), never ranking features, ads, analytics enrichment, or UI.
- In-app disclosure on the connection screen states the exclusion-only purpose.
- Server-only storage; no raw friend graph is client-readable.

Residual risk: rejection under 5.1.1 (data minimization / forced consent) is possible.
If Review pushes back, the fallback product decision (offering a skip path with a
degraded-recommendations mode) is a product/legal call — not made unilaterally here.

## Related disclosures to keep in sync

- Privacy policy: Kakao friends purpose = acquaintance-exclusion only (verify wording
  before each release).
- App Privacy (App Store Connect) data types: "Contacts / friend list — app functionality,
  not linked to tracking" — verify against actual collection before submission.
  (No App Store Connect changes are made from this workspace.)
