# P1-1 to P1-12 — Remediation and Production Verification (2026-11-04)

Scope: the twelve P1 findings of the 2026-10-07 production-readiness audit,
worked in order on `security/integration` (`09fefca1`, PR #152 + PR #153
merged 2026-11-04; `main` = PR #154 of the same tree). P1-13 (season-meeting
callable trusts client time/status) is out of scope and stays OPEN in
`00-backlog.md`.

Method per item: current-state classification against the integrated source →
reproduction (failing test on the base source, emulator where authorisation or
concurrency is involved) → minimal fix → focused and integration regression →
commit. Every item below names its commit, its tests and what still needs the
owner. Statuses follow the ledger vocabulary: SOURCE CLOSED / TESTS VERIFIED /
PRODUCTION DEPLOYED / PRODUCTION VERIFIED / CLIENT RELEASE DEFERRED / BLOCKED.

## 0. Baseline (fresh, this session)

| Check | Result |
|---|---|
| Git | `security/integration` = `09fefca1` (merge of #153 over #152); `main` = `8a2c3b0b` (PR #154, same tree). `git diff 7dd3b992 09fefca1 -- functions/src firestore.rules storage.rules lib` is empty: the integration tree equals the deployed P0-3 candidate's runtime paths. |
| Toolchain in this environment | Node 22, firebase-tools 15.30.2 emulators (Firestore/Auth/Storage), Flutter 3.47.2 (SDK cloned). **No Firebase/gcloud credentials**: production reads, deploys, live Rules inspection and the Functions environment guard could not be executed here. Everything marked PRODUCTION below is an owner step. |
| Functions `npm run lint` / `npm test` | clean / 1128 pass |
| `rules_tests` Firestore / Storage | 291 / 8 pass |
| Security emulator suites (CI set) | P0-1 14 + 6, P0-2 35, drift 4, NEW-19 11, P0-3 10 + 21 — all pass |
| Flutter `analyze` / `test` | No issues / **1169 pass, 14 fail** — the NEW-13 baseline set (`app_compatibility` ×1, `interests_selection_repair` ×1, `google_play_purchase_security` ×1, `heart_cost_confirmation_screenshot` ×3, `profile_edit_showcase_screenshot` ×1, `requested_ui_changes_screenshot` ×7), none touching the P1 areas |

## 1. Results

| Issue | Classification | Fix (commit) | Tests | Production | Status |
|---|---|---|---|---|---|
| P1-1 | CONFIRMED_UNFIXED | `51d51c0f` one transactional match authority, pair-based like idempotency, block enforcement | emulator 11 (8 fail on base), drift 4 | deploy `onInteractionCreated`, `onRecEventCreated` | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING (owner) |
| P1-2 | CONFIRMED_UNFIXED | `4de28e11` transactional send authz, idempotent `clientMessageId`, server-owned room metadata, strict message schemas | unit 4, emulator 9 (base: 3/3 defects reproduced), rules 13 (9 fail on base) | deploy `sendChatText`, `onChatMessageCreated`; deploy Rules | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING |
| P1-3 | CONFIRMED_UNFIXED | `53dea7d4` token ownership registry + trigger, delivery-time check, logout unregistration | unit 3, emulator 8 (base: cross-account delivery reproduced), Dart 2 | NEW function `onDeviceTokenWritten` (`--new-function`), backfill CLI, redeploy every push sender; client release | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING · CLIENT RELEASE DEFERRED |
| P1-4 | PARTIALLY_FIXED (P0-3 lazy reset) | `55f12491` eager `bindUser` via `ChangeNotifierProxyProvider` | Dart 5 (1 new) | client release | SOURCE CLOSED · TESTS VERIFIED · CLIENT RELEASE DEFERRED |
| P1-5 | CONFIRMED_UNFIXED (4 parts) | `e492c280` nested participantInfo, group detach, blind-meeting data, onboarding photos; residue CLI | unit 10, emulator 4 (base: literal dotted key reproduced) | deploy `cleanupAvatarMedia` (+ retention purge sharing the module); residue audit/apply | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING · DATA AUDIT PENDING |
| P1-6 | CONFIRMED_UNFIXED | `78758a33` Crashlytics + privacy-safe facade | Dart 4 | native release build; dSYM upload step | SOURCE CLOSED · TESTS VERIFIED · RELEASE VERIFICATION DEFERRED |
| P1-7 | CONFIRMED_UNFIXED (server side) | `03dc7049` adult eligibility at every entry point; release bypass impossible | unit 2 (+chat 1), emulator 2, rules 4, Dart contract | deploy Rules + `sendChatText`, `unlockDirectChat`, `onInteractionCreated`, `onAskCreated`, blind callables; account audit | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING |
| P1-8 | ALREADY_FIXED BY P0-2 (one delivery-order gap) | this commit: push before in-app record, both idempotent | emulator 3 (scale) + P0-2-L | deploy `sendDailyUnreadChatDigests` | ALREADY FIXED BY P0-2 — VERIFIED · gap SOURCE CLOSED · DEPLOY PENDING |
| P1-9 | CONFIRMED_UNFIXED | `e02b7cec` bounded pick, isolate encoding, server validation, slot cleanup | unit 5, Dart 2 | deploy `uploadOnboardingPhoto`; client release; owner confirms 2048 px bound vs avatar QA | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING · CLIENT RELEASE DEFERRED |
| P1-10 | CONFIRMED_UNFIXED | this commit: strict asks/interactions schema, no client snapshots, blocks; inbox resolves identity from `publicProfiles` | rules 6 (4 fail on base), Dart | deploy Rules; client release; legacy snapshot audit | SOURCE CLOSED · TESTS VERIFIED · PRODUCTION DEPLOY PENDING · CLIENT RELEASE DEFERRED |
| P1-11 | CONFIRMED_UNFIXED | this commit: `ChatSendController` (draft restore, idempotent retry, double-tap, room/account reset) | Dart 8 | client release | SOURCE CLOSED · TESTS VERIFIED · CLIENT RELEASE DEFERRED |
| P1-12 | SUPERSEDED_BY_NEW_ARCHITECTURE (P0-2) | this commit: concurrency pins only | emulator 5, rules 2 (+ P0-2 suites) | — | SUPERSEDED BY P0-2 — VERIFIED CLOSED |

Final suite counts after all commits: Functions unit **1152/1152**; Flutter
**1186 pass / 14 fail** (identical NEW-13 set, zero new failures), `flutter
analyze` clean; `rules_tests` Firestore **316/316** / Storage 8/8; every CI
emulator suite (P0-1 14+6, P0-2 35, drift 4, NEW-19 11, P0-3 10+21) plus the
six new ones (P1-1 12, P1-2 10, P1-3 8, P1-5 4, P1-8 3, P1-12 5) green on the
final tree `81ca4473`.

**Push blocked.** `git push origin claude/tender-tesla-lu2ljk` was refused
(403: the Claude GitHub App has no access to `seolleyeon-team/dating-app`
for this organisation), so the nine commits exist only in this session's
checkout; a git bundle and a `format-patch` series were produced for
hand-off. No pull request could be opened.

## 2. Per-item record

### P1-1 — Mutual match duplication, block bypass, like spam

- **Original claim.** `onInteractionCreated` lost `ensureMutualMatch`
  (regression `22ca7307`), checks blocks nowhere, and the like notification id
  `like_${interactionId}` lets a client re-notify at will.
- **Current state.** CONFIRMED_UNFIXED. `874cb3aa`/`09fefca1` ran a
  non-transactional `matches where userIds array-contains` scan and then
  `matches.doc()` (random id) + batch; `mutualMatchCreation.ts` had no importer
  (NEW-16). `onRecEventCreated` → `checkAndCreateRecMatch` was a second,
  room-less copy of the same race.
- **Reproduction.** `functions/src/mutualMatch.emulator-test.ts` on the base
  source: 8 of 11 fail (A two matches for simultaneous mutual likes, B/C
  repeated notifications, D/D2 blocked pair matched, G existing room
  overwritten, H/I rec+interaction paths race into two matches).
- **Fix.** `ensureMutualMatch` is the only `matches/*` writer. One transaction
  reads `match_<a>_<b>`, every legacy random-id match naming both users, the
  reverse like (interactions or recEvents collection group), both block
  directions and the direct room, then: blocked → nothing; no reverse like →
  nothing; existing inactive (unmatched/ended) → nothing (no resurrection,
  rematch is not implicit); existing active without room → room attached
  (`room_attached`); else create. A pre-existing direct room (paid chat) is
  linked by `matchId` only. Welcome message id `system_match_<matchId>`.
  Notification id `like_<from>_<to>` + `notificationDispatchLog` key
  `profile_like_<from>_<to>`; a block ends the event before notification.
  Client: like/super_like/nope use `<from>_<to>_<action>` ids (rules unchanged
  for installed builds). NEW-16 closes by reuse.
- **Legacy compatibility.** Random-id matches stay authoritative for their
  pair (test E/F); no second canonical match is created beside them; the
  recEvents path keeps producing room-less matches that the interactions path
  upgrades (test H). No migration needed.
- **Remaining risk.** None in source. Production: the matching trigger pair
  must be redeployed together (guarded, 0 env additions expected).

### P1-2 — Chat authorisation, room mutation, moderation bypass

- **Current state.** CONFIRMED_UNFIXED. `sendChatText` read the room outside
  its transaction, ignored `status`/`writable`, checked blocks only for
  `type == one_to_one` (client-mutable), created a message per retry. Rules
  let a 1:1 participant rewrite `status, type, roomType, participantInfo,
  matchId, dataPartition, photoBlurUnlocked*`; any message with `type !=
  'text'` was accepted and the chat UI renders unknown types as text bubbles.
- **Reproduction.** Base `createSendChatTextFunction.run()` on the emulator:
  sends into closed/read_only/archived rooms, a spoofed `type:"group"` skips
  the block, a retry duplicates (3/3 fail). Base rules: 9 of 13
  `firestore.chatauthz.test.mjs` fail.
- **Fix.** Room lifecycle set derived from the code: sendable iff `status`
  absent or `active` and `writable != false` (`closed` from unmatch/account
  deletion, `read_only`/`archived` from blind-meeting lifecycle refuse). Blocks
  for any two-person room. Partition check. `clientMessageId`
  (`^[A-Za-z0-9_-]{8,64}$`) → deterministic message id; duplicate →
  `{deduplicated:true}`; distinct ids with the same text are two messages.
  Rules: client-mutable room keys exactly `lastMessage, lastMessageAt,
  updatedAt, activePromise`; messages create only `promise_request` /
  `promise_deleted` with exact field sets and bounds, closed rooms accept
  nothing; promises create gated by the same lifecycle. `onChatMessageCreated`
  skips push when the sender is not a participant. The P0-2 own-read-state
  branch and NEW-18 tolerance are untouched; `firestore.p03-transition.rules`
  regenerated (drift check green). The promise fixture in
  `firestore.chat.test.mjs` gained `dateTime` (what the real client writes).
- **Client message types inventory.** Client-created: `promise_request`
  (createPromise), `promise_deleted` (cancelPromise); updates only:
  `promise_confirmed/rejected/cancelled` lifecycle; server-only: `text`
  (callable), `system`, `promise_in_progress/completed`, support replies.

### P1-3 — FCM token ownership and logout

- **Current state.** CONFIRMED_UNFIXED. Logout never touched
  `users/{uid}/deviceTokens`; `fetchUserTokenRecords` delivered to every
  token registered under the recipient. Base emulator run: A's stale
  registration still deliverable after B registered the same token.
- **Fix.** `pushTokenOwners/{sha256(token)}` registry (server-only rules),
  `onDeviceTokenWritten` trigger (claim / refresh / transfer with deletion of
  the previous owner's registration / stale late event deletes the older
  registration / release only by the owner; `retry: true`, idempotent).
  `fetchUserTokenRecords` skips and deletes registrations the registry assigns
  elsewhere; registrations without a record (legacy, pre-backfill) are
  delivered and logged (transitional). Invalid tokens are released from the
  registry. `pushTokenOwnershipBackfillCli --dry-run/--apply` (newest
  registration wins, conflicts reported, idempotent). Client:
  `unregisterCurrentDevice` in `AuthService.signOutAll` (delete own
  registration, then `deleteToken()` rotates the FCM token; 5 s timeouts) —
  every sign-out path, including account deletion, goes through it.
- **Production order (owner).** 1 deploy `onDeviceTokenWritten` with
  `--new-function`; 2 redeploy every function that sends push (all users of
  `shared/notify.ts`); 3 `--dry-run` then `--apply` backfill; 4 verify: conflict
  count reported by the CLI, registry size == distinct tokens. Until the
  backfill, legacy tokens behave as before (documented transitional window).

### P1-4 — CommunityProvider session isolation

- **Current state.** PARTIALLY_FIXED by P0-3: per-request `_resetIfAccountChanged`
  and in-flight discard verified by the existing tests; the gap was timing
  (reset only on the next request). **Fix.** `bindUser` via
  `ChangeNotifierProxyProvider<AuthProvider, CommunityProvider>` clears lists,
  cursors and ownership marks on logout/switch immediately; lazy check kept.

### P1-5 — Account deletion personal data

- **A nested field.** Confirmed on the real engine: base `closeChatRoom`
  produced keys `…,participantInfo,participantInfo.a,…` with nested `a` still
  `{"nickname":"앨리스"}`. Fixed with a nested-map merge; the Firestore fake
  models set-merge semantics so the unit test proves the same. Similar dotted
  keys: only `party.ts` `memberProfiles.<uid>` under `update()` (correct
  semantics there); the new party scrub uses a nested map.
- **B onboarding photographs.** `users/{uid}/onboarding/photos/*` (default
  bucket, `uploadOnboardingPhoto`) were outside the uid-bound allowlist and
  never listed. Now listed at load time and deleted with generation match;
  allowlist admits exactly that bucket+prefix. Replacement cleanup is P1-9.
  Other media (source bucket, temp candidates, approved avatar, chat profile)
  were already covered. No Storage lifecycle rule exists for this prefix
  (checked `storage.rules` / code; bucket lifecycle policy is a production
  setting the owner can confirm).
- **C blind/season data.** New `accountDeletionMeetingCleanup.ts`: DNA, DNA
  draft, party membership, stats deleted; application closed (open:false,
  cancelled, preferences removed, meeting link kept for the lifecycle);
  `blindMeetings/*/publicProfiles/{uid}` and `blindMeetingParties.memberProfiles.{uid}`
  anonymised in place. Kept on purpose: restrictions (safety), match history
  (uid-only), hearts/refund ledgers (financial). Season event teams were
  already handled (`accountDeletionEventTeamCleanup`).
- **D group rooms.** Rooms with >2 participants are detached (member scrubbed,
  `accountDeletedUserIds`), never closed; membership arrays stay with the
  meeting lifecycle; unread model untouched. 1:1 rooms still close.
- **E historical residue.** `chatRoomParticipantInfoResidueCli --audit` (read-only)
  / `--apply` (FieldPath repair). Not run: no credentials. Owner step.

### P1-6 — Crash reporting

- `firebase_crashlytics ^5.4.1`, Android plugin 3.0.6; `CrashReporting`
  facade: FlutterError.onError (non-fatal), PlatformDispatcher.onError
  (fatal), root zone (fatal), ErrorHandler.logError (non-fatal); identity
  dedupe; `SanitizedCrashError` = type + `PrivacyLogUtils.errorSummary` +
  stack, never the raw message; collection only in release on Android/iOS.
- **Release-gated.** iOS dSYM upload run-script (`${PODS_ROOT}/FirebaseCrashlytics/run`)
  and an installed-build smoke (force a test crash, confirm the issue in the
  console) are NEW-12 steps. Data Safety / App Privacy disclosures: Crashlytics
  collects crash logs, device state and an installation id — the owner
  updates the store forms from the actual collected set before release.

### P1-7 — Server-authoritative adult verification

- **Policy verified.** `MINIMUM_SERVICE_AGE = 20` (연 나이, KST year
  difference) in `verifyAdultIdentityAfterLogin`; provider KG Inicis via
  PortOne; `adultVerified && realNameVerified` written only there (Admin SDK);
  no client-writable allowlist contains them (users create/update branches
  checked). Age policy unchanged.
- **Gap fixed.** Enforcement existed only in the Flutter route guard and the
  bypass flag applied to release builds. Now: `adultEligibility.ts`, enforced
  in `sendChatText`, `unlockDirectChat`, `onInteractionCreated`,
  `onAskCreated`, blind-meeting `requireVerifiedUser`, and the rules
  (`isAdultVerifiedCaller()` on interactions/asks create, chat room update,
  messages/promises create, promises update). Review partition exempt.
  `isTemporarilyDisabled = !kReleaseMode && _bypassRequested`.
- **Existing accounts (owner).** Read-only count of production `users` with
  `adultVerified != true`; such accounts were already routed to verification
  by the client and are now refused server-side — nobody is auto-marked
  verified.

### P1-8 — Daily unread digest

- `collectDailyUnreadDigest` is paged over `chat_rooms where status == active`
  by document id, reads no message document, aggregates per user with
  dedupe (verified by P0-2-L and the new scale suite: 100 users/45 rooms/1,350
  messages and 1,000 users/400 rooms/4,000 messages → `roomsScanned ==
  active rooms`, 0 message reads, paging completeness at page size 7).
  MEASURED DOCUMENT OPERATIONS only; no billing estimate.
- **Gap fixed.** The in-app record was created before the push; a push
  failure after it was never retried. Now `sendPushOnce` (dispatch-log key
  `chat_digest_<date>_<uid>`) runs first and the in-app record second; both are
  idempotent, so a retry completes either half and neither duplicates.

### P1-9 — Onboarding photo upload

- Client: bounded pick (2048/2048, q88), `compute()` base64, no forced token
  refresh, 12 MB ceiling. Server: real-format validation, pixel ceiling before
  decode, EXIF orientation applied, longest side 2048 (no enlargement), JPEG
  88 with metadata stripped; same-slot predecessors deleted after upload
  unless an avatar workflow is active (queued source-set jobs validate by
  generation). **Owner confirmation:** the 2048 px cap against the avatar QA
  baseline (quality and normalization version unchanged).

### P1-10 — Asks / interactions schema

- Asks: field allowlist (`fromUserId, toUserId, text ≤ 500, status == 'sent',
  createdAt/updatedAt == request.time, readAt null, sourceScreen ≤ 64,
  dataPartition`), blocks both directions. The client no longer writes
  `fromUserProfileSnapshot/toUserProfileSnapshot`; the inbox resolves the
  counterpart from `publicProfiles/{uid}` through `ProfileDisplayImageResolver`
  (display-safe hosts only) and uses a legacy snapshot only as a text nickname
  fallback — never its image URL (no external image fetch).
- Interactions: `action in [like, super_like, nope, view, message]`, source ≤
  64, `metadata` null or `{messagePreview ≤ 200}`, `createdAt == request.time`,
  self-target refused, blocks both directions; consistent with P1-1's
  deterministic one-shot ids (create-only → second write refused).
- `onAskCreated` additionally skips notification for blocked or ineligible
  pairs (P1-7). **Historical asks** with snapshots keep working (text
  fallback); an optional scoped cleanup of the two snapshot fields is an owner
  step (no credentials here).

### P1-11 — Send-failure draft recovery

- `ChatSendController`: one in-flight send (double tap ignored), failed
  attempt kept with its `clientMessageId`, `retry` and re-submitting the
  restored text re-use it (a timeout after a server commit cannot duplicate —
  P1-2 dedupes), `draftToRestore` never overwrites newer typing,
  `bindContext` drops the draft on room/account change, `describeError` maps
  `failed-precondition / permission-denied / not-found / invalid-argument /
  unauthenticated / deadline-exceeded / unavailable` to short Korean text and
  never exposes backend details. The screen restores the draft, shows a
  SnackBar with "다시 시도" (semantics label "전송 실패 …") and keeps multiline
  text and cursor at the end.

### P1-12 — Group read state

- P0-2's room-level `unreadCounts.{uid}` / `lastReadAt.{uid}` already holds:
  P0-2-H2 (20 concurrent increments), P0-2-I (two devices), P0-2-K (delayed
  trigger high-water mark). Added pins: six members concurrently (emulator +
  rules), mark-read racing accounting, delayed and duplicated trigger, departed
  member inert, 25 concurrent writes from six members; rules: own two keys
  only, model version protected, outsider denied. No `readBy` dependency was
  added; NEW-18 untouched.

## 3. Security regression matrix (executed here)

| Area | Evidence |
|---|---|
| Identity / sessions | rules canonicalsession (6), adultgate (4), chat/room reads unchanged |
| Matching | mutualMatch emulator 12 + drift 4 |
| Chat | chatSafety unit 4 + emulator 10, chatauthz rules 13, chat/promisestamp/chatunread rules unchanged |
| Notifications | pushTokenOwnership unit 3 + emulator 8, digest scale 3, pushDeliveryContext/pushTokenCleanup unit |
| Community | P0-3 emulator 10 + migration 21, bamboo rules unchanged, provider Dart 5 |
| Account deletion | social/meeting/avatar unit 10, emulator 4 |
| Onboarding | onboardingPhotoUpload unit 5, Dart 2; adult gate as above |
| P0 preservation | P0-1 14+6, P0-2 35, P0-3 10+21, NEW-19 11, blind FSM 67, gender 6, no-deposit 14 — all green on the final tree |

## 4. Deployment plan (owner; nothing deployed from this environment)

Changed Functions (compiled code): `onInteractionCreated`,
`onRecEventCreated`, `sendChatText`, `onChatMessageCreated`, `onAskCreated`,
`unlockDirectChat`, `sendDailyUnreadChatDigests`, `uploadOnboardingPhoto`,
`cleanupAvatarMedia` (+ `purgeDeletedAccounts…` retention purge if it shares
the module — verify by archive diff), every function importing
`shared/notify.ts` (ownership check), blind-meeting callables importing
`store.ts`, and NEW `onDeviceTokenWritten`. Use `scripts/deploy_functions_guarded.sh`
per function with the live-archive diff first (NEW-20: never redeploy
`reportAndBlockUser` / the Bamboo writers from this tree). Rules: deploy
`firestore.rules` after `rules_tests` on the exact file; the transition file
is regenerated and drift-checked. Expected env guard: 0 removals / 0
changes / 0 missing / declared additions only for the new function.
