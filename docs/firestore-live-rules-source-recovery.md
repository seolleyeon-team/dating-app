# Firestore live rules source recovery

Status: `SOURCE_RECOVERY_ONLY` / `NO_PRODUCTION_DEPLOY`

## Authority

- Repository authority: `github/main` at `d6e4e61c6558d1ddb5864434b75217e2e4805cb7`.
- Production project: `seolleyeon-final`, Firestore Native, database `(default)`, location `asia-northeast3`.
- Live release: `projects/seolleyeon-final/releases/cloud.firestore`.
- Live release create time: `2026-05-18T20:03:23.059378Z`.
- Live release update time: `2026-09-17T11:13:36.892988Z`.
- Live ruleset: `projects/seolleyeon-final/rulesets/9a675a65-ba51-4792-b1fa-24145a9e5a38`.
- Live ruleset create time: `2026-09-17T11:13:33.364527Z`.
- Live source file: `firestore.rules`.
- Live source encoding/line ending: UTF-8, LF-only, final LF, 104,352 bytes.
- Live source SHA-256: `975f8dc7d33a7f7dfa8ba629bcdf89cb792ae3eda5577cf281f4a106b767657a`.

The unnormalized API source is retained outside Git at `recovery-evidence/live-firestore.rules` in this isolated worktree. No credentials or tokens are stored in this evidence.

## Diff classification against fresh main

The pre-recovery diff was limited to these blocks:

- `LIVE_REVIEW_FIXTURE_SUPPORT`: the approved review identity set in `callerDataPartition()` and `isPlayReviewSession()` includes `play-fixture-b-01` alongside `play-reviewer-v1`.
- `LIVE_REVIEW_FIXTURE_SUPPORT`: `reviewFixtureLoginEnabled` and `reviewFixtureLoginActivatedAt` are protected by `reviewAuthorityFieldsUnchanged()`.
- `LIVE_SECURITY_HARDENING`: `hasActiveChatAccount()` requires an existing user document, rejects `loginDisabled == true`, rejects `isActive == false`, and rejects `banned`, `blocked`, `deleted`, `suspended`, and `withdrawn` statuses. The helper gates chat-room reads/updates and existing-room participant operations.
- `MAIN_ONLY_RULE`: fresh main used the narrower single-UID reviewer check. That is not present in live and would exclude the approved fixture identity.
- `FORMAT_ONLY`: none.
- `UNKNOWN`: none.

No other live-only rule block was found in the repository comparison.

## Provenance

Exact Git-history/ref/reflog searches for `play-fixture-b-01`, `reviewFixtureLoginEnabled`, `reviewFixtureLoginActivatedAt`, and `hasActiveChatAccount` found no matching `firestore.rules` source. Therefore each live-only rules block is classified `LIVE_RULES_SOURCE_NOT_FOUND_IN_GIT`. The fixture UID does have related application/test provenance, but not an exact rules-file provenance.

## Security semantic audit

- Authentication: anonymous access is explicit; canonical app sessions and isolated Play Review sessions use separate claim predicates.
- Active/suspended accounts: the recovered live chat gate denies missing, disabled, inactive, banned, blocked, deleted, suspended, and withdrawn accounts.
- Review fixture: the approved fixture remains in the isolated `play_review` partition; client writes cannot alter review-login authority fields.
- Chat and meeting paths: room membership, participant immutability, sender identity, message mutation, promise lifecycle, and meeting-room constraints remain enforced.
- Users/profile: private user documents are owner-scoped, protected fields are server-controlled, and public profiles are read-only from the client.
- Admin/moderation: admin metadata, moderation state, reports, and backend avatar/router/job paths are not client-writable.
- Avatar paths: private media, embeddings, jobs, candidates, and provider-router state remain backend-only; user avatar fields retain protected-field validation.

## Verification

TDD was performed before the recovery patch:

1. Fresh-main RED: 221 tests, 210 pass, 11 fail. The three new recovery tests failed as expected: approved fixture access, suspended chat access, and inactive chat access. Eight unrelated baseline failures were recorded separately.
2. Targeted GREEN after the minimal patch: 6/6 pass.
3. Full suite after recovery: 221 tests, 195 pass, 26 fail. The same eight baseline failures remain. Eighteen additional legacy chat/promise/support tests use authenticated UIDs without seeding the `users/{uid}` documents now required by the exact live `hasActiveChatAccount()` gate; these are recorded as test-fixture compatibility gaps, not additional rule-text differences. The recovery tests remain green.
4. Exact parity: repository `firestore.rules` and the preserved live source are both 104,352 bytes with SHA-256 `975f8dc7d33a7f7dfa8ba629bcdf89cb792ae3eda5577cf281f4a106b767657a`; byte comparison returned no difference.

The emulator loaded the recovered source successfully. No production Rules deployment, Firestore write, Functions/Hosting/Cloud Run/Queue mutation, push, merge, reset, or rebase was performed as part of this recovery.

## Follow-up: fixture compatibility remediation

- Starting PR head: `896dbba327a8dd4a88939f9b2f134fd957454cd3`.
- `firestore.rules` was not edited. Pre-remediation SHA-256 remained `975f8dc7d33a7f7dfa8ba629bcdf89cb792ae3eda5577cf281f4a106b767657a`, with 104,352 bytes.
- The 18 introduced failures were all `EXPECTED_ACTIVE_USER_SUCCESS_PATH` cases. They exercised an authenticated participant success path but did not seed the live gate's required `users/{uid}` active record.

The exact 18-gap inventory was:

- `firestore.chat.test.mjs`: `a participant can list rooms with an array-contains participant query`; `a recipient can mark a message as read`; `an existing promise message can move through its lifecycle`; `both promise parties can cancel and record the cancellation`; `a participant can still update lastMessage without touching participantIds`.
- `firestore.promisestamp.test.mjs`: `a participant CAN create a normal promise for themselves`; `a participant CAN create a promise carrying the optional place fields`; `the requestedTo user CAN accept the request`; `the recipient CAN edit the promise, which swaps requestedBy/requestedTo`; `an honest room update still works after the server recorded a stamp`; `the requestedTo user CAN reject the request`; `the requester CAN cancel their own pending promise`; `the recipient CAN also cancel the promise (both parties may cancel)`; `a party CAN cancel a confirmed promise on safety-stamp timeout`; `a participant CAN read a promise in their own room`; `a party CAN clear activePromise when cancelling on safety-stamp timeout`.
- `firestore.support.test.mjs`: `support room is visible only to its user and operator`; `a support participant cannot reassign its operator or case fields`.

The remediation adds a minimal `seedActiveUser()` test helper and uses it only in the affected success-path fixtures. It does not seed missing-user, suspended, inactive, or non-participant identities indiscriminately. Existing expected allow/deny assertions were not inverted.

The recovery regression file retains the original six contract tests and adds table-driven `hasActiveChatAccount()` coverage for: active allow, missing-user deny, `loginDisabled` deny, inactive deny, banned/blocked/deleted/suspended/withdrawn deny, and status-absent default-active allow.

Verification after the fixture-only changes:

- Targeted recovery + chat/promise/support tests: 91 total, 90 pass, 1 fail. The only failure is the pre-existing baseline test `a support participant can reply with bounded text but cannot forge a case card`; all 18 introduced failures are 0.
- Recovery semantics: 16/16 pass, including the original six and the new active-account table.
- Full Firestore suite: 231 total, 223 pass, 8 fail. The eight failures are the same baseline set recorded above: four Bamboo ownership tests, two canonical-session tests, `Phase D 후보 규칙은 배포 대상이 아니다`, and the support reply test.
- No `SEMANTIC_AMBIGUITY` classification occurred.
- Post-remediation `firestore.rules` SHA-256 remains `975f8dc7d33a7f7dfa8ba629bcdf89cb792ae3eda5577cf281f4a106b767657a`; bytes changed in `firestore.rules`: `0`.
