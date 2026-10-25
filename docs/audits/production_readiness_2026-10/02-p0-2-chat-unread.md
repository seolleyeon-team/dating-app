# P0-2 — Chat unread/read scalability remediation

Audit finding (2026-10-07): the chat badge, the per-room unread flag, mark-read
and the daily digest all scanned every message of every room; marking a room
read rewrote every unread message in one batch (>500 unread fails); the room
screen listened to the entire history. Cost scaled with total message history
and multiplied across five always-mounted tabs.

Branch `security/p0-2-chat-unread` (base `becd5f28`).

## Current structure (C1, verified 2026-10-14)

| Path | Before | Cost class |
|---|---|---|
| Tab badge `hasAnyUnreadChats` (5 screens, created in `build()`) | rooms query → `messages.get()` per room, re-run on every room change | rooms × history × tabs |
| Chat-list row `unreadCountStream` | `messages.snapshots()` per visible row | rooms × history (live) |
| Room screen `messagesStream` + `markMessagesAsRead` from the builder | unbounded history listener; full `messages.get()` + one batch on every snapshot/rebuild | history per rebuild; >500 unread = failure |
| Digest `sendDailyUnreadChatDigests` | `users.get()` × rooms × `messages.get()` | users × rooms × history |

Message creation paths (all covered by the new accounting): `sendChatText`
(callable), mutual-match / unmatch / blind-meeting / season / Play-review
system messages, client promise messages, safety-stamp promise messages,
support messages. Every writer still writes `readBy: [sender]` (or `[]` for
system) so old clients keep working.

## Behavior contract (C2) — preserved from the pre-existing client

- A message is unread for every participant except its sender; **system and
  promise messages count** (the client always treated `senderId != me` as
  unread). The old digest excluded system messages; the new one follows the
  client rule, so the badge and the digest can no longer disagree.
- Unread is per user and server-authoritative; reading on one device clears
  every device. Each user clears only their own state; a participant can
  never modify another participant's state.
- Closed / blocked / read-only rooms: a participant can still clear what they
  already received (the read-state rule stands apart from the write gates).
- `readBy` is kept for old clients. The per-message checkmark in the UI never
  depended on it (`isRead: senderId == me`), so no receipt feature is lost.

## Model (C4)

`chat_rooms/{roomId}`:

| Field | Writer | Meaning |
|---|---|---|
| `unreadCounts.{uid}` | server (`FieldValue.increment`) / participant resets own key to 0 | unread messages for `uid` |
| `lastReadAt.{uid}` | participant, own key, server time | last mark-read |
| `unreadModelVersion: 1` | server | room carries server-maintained counts (absent = legacy room) |
| `unreadBackfilledAt` | backfill | idempotency / resume marker |

`messages/{id}.unreadAccountedAt` — written in the same transaction as the
increments; a redelivered trigger or the backfill revisiting a message cannot
count it twice. Clients cannot write it (rules).

Chosen over per-user `readState/{uid}` documents because the room-list
stream already delivers every room document (badge = 0 extra reads), the
increment is one atomic field update on a document that is written per
message anyway, 1:1 and 3:3 rooms have ≤ 6 keys, and old clients ignore the
new fields.

## Authority (C5)

- `onChatMessageCreated` (index.ts) calls `accountMessageUnread` **before** its
  push logic (so system messages count) and re-throws on failure so the
  platform retries; idempotent via the marker. The deployed wiring is tested
  through `index.ts` (`chatUnreadTrigger.emulator-test.ts`).
- Mark read = `update({unreadCounts.me: 0, lastReadAt.me: serverTimestamp})`
  — one write, no message reads.
- Rules: `onlyOwnUnreadReadStateUpdate()` (own keys, count exactly 0,
  `lastReadAt == request.time`); the general room-update branch refuses the
  four model keys; message create refuses the marker.
- Digest: paged query over active rooms, aggregates `unreadCounts`, 0 message
  reads, deterministic `chat_digest_<date>` notification id.

## Concurrency / idempotency proofs (emulator, `chatUnread.emulator-test.ts`)

- P0-2-G both interleavings and a concurrent markRead/increment end at 0 or 1
  (increment is atomic, reset zeroes only what existed).
- P0-2-H sequential and 3-way concurrent redelivery count once; P0-2-H2 20
  concurrent messages lose no increment.
- P0-2-I two devices reading concurrently; the peer's counter untouched.
- Backfill: messages already accounted by the trigger are skipped; 905
  messages chunk in ≤ 400-op transactions; reruns are no-ops; the run is
  paged, checkpointed and `--limit`-bounded.

## Evidence: same assertions, legacy vs new port

| Test | Legacy port (before) | New port (after) |
|---|---|---|
| P0-2-A badge reads, 3 rooms, history ×10 | 18 → **168** reads (FAIL) | 3 → 3 (+1 tolerance) PASS |
| P0-2-B mark 600 unread read | **600 writes** in one batch (FAIL) | 1 write PASS |
| P0-2-C open a room with 120 messages | **120** loaded (FAIL) | 50 PASS |
| P0-2-L digest with 60 messages | **120** message reads (FAIL) | 0 PASS |

Rules: `firestore.chatunread.test.mjs` — 7 of 11 fail before the rules change
(A could reset B's counter, forge B's `lastReadAt`, set own counter to 99,
smuggle keys through the general branch), all pass after; full suite 258/258.

## Client (C7/C8)

- `ChatUnreadProvider` (Provider, `ChangeNotifierProxyProvider<AuthProvider,…>`)
  — one room-list subscription per signed-in user; badge and chat-list rows
  read it; logout (`appUserId == null`) cancels and clears; legacy rooms
  (no `unreadModelVersion`) report 0 — explicit, bounded fallback, never a
  history scan.
- Room screen: `roomStream`/`latestMessagesStream` created once in
  `_initChat`; newest page `limit 50` realtime; older pages via
  `startAfterDocument` on scroll-to-top with viewport anchoring; promise
  groups split by the page boundary are completed with one bounded
  `where promiseId ==` fetch; mark-read issued once per newest message.
- Static guard `test/features/chat/chat_unread_cost_contract_test.dart` pins
  the absence of the legacy APIs and the bounded query shapes.

## Backfill (C6)

`node functions/lib/chatUnreadBackfillCli.js --project seolleyeon-final
--dry-run | --apply --checkpoint <id> [--limit N] | --verify`.
Production dry-run 2026-10-16: 23 rooms, 25 messages inspected, 3 counted
(2 for the `fake_user_1` fixture room, 1 in the Play-review fixture room), 0
anomalies, 0 writes.

## Compatibility (C10)

| Room | Client | Result |
|---|---|---|
| legacy (no model) | old | unchanged (`readBy` scan) |
| legacy | new | 0 unread, no scan; counts appear after backfill / first new message |
| backfilled | old | unchanged (`readBy`); old client never resets counters → stale counts until that user opens the room on a new client |
| backfilled / new | new | fast path |

Old clients (≤ build 35) keep computing from `readBy`; the server keeps
writing it. **Legacy storage retained; expensive legacy execution remains
active only on old installs** — retirement gate: `minimumSupportedBuild` ≥ the
first build carrying this change.

## Rollout order (C13)

1. Functions `onChatMessageCreated`, `sendDailyUnreadChatDigests` (guarded
   deploy; additive fields; old clients unaffected).
2. Firestore rules (read-state branch; old clients' `readBy` writes still
   allowed).
3. Backfill `--apply` (idempotent, checkpointed) then `--verify`.
4. Client release with the provider / pagination.
5. After `minimumSupportedBuild` passes the release: stop writing `readBy`
   (separate change).

## Final audit (2026-10-22) — concurrency, triggers, closure

Commits `2bdb060b` (fix) and `5dc38497` (reconciliation) on
`security/p0-2-chat-unread`, PR #147 → `security/integration`.

### Message lifecycle (as deployed)

```
writer commit (createTime)            ──► Eventarc / Pub/Sub (at-least-once, ack 600 s, retention 24 h)
   │                                          │
   │                                          ▼
   │                                 onChatMessageCreated
   │                                   1. accountMessageUnread  — ONE transaction: read message + room;
   │                                      skip if `unreadAccountedAt`; recipients = participants − sender
   │                                      − { u : lastReadAt[u] ≥ message.createTime }; increment; mark
   │                                   2. sendPushOnce          — dispatch-log transaction, then FCM
   ▼
client room stream ──► ChatUnreadProvider (badge / row) ; room screen marks read once per newest message:
                       update(unreadCounts.me = 0, lastReadAt.me = serverTimestamp)  [rules: own keys only]
```

Writers (every one stamps `createdAt` with the server time; the trigger uses
the unforgeable `createTime` anyway): `sendChatText` callable, system messages
(`mutualMatchCreation.ts`, unmatch in `index.ts`, `teamMeetingRequest.ts`,
season/Play-review `playReviewAccess.ts` with `Timestamp.now()`),
`chatSafety.ts`, `safetyStamp.ts`, `supportOperations.ts`, client promise /
`promise_deleted` messages (`chat_service.dart`, `serverTimestamp`).
`chatRealPhoto.ts` and `accountDeletionChatLifecycle.ts` only read messages.

### Strict correctness

For every room and participant `u`:

```
unreadCounts[u] == |{ m : m.senderId != u  ∧  m.createTime > lastReadAt[u] }|
```

(`lastReadAt[u]` absent ⇒ every message counts). The client's mark-read and
the trigger's increment both go through Firestore transactions on the room
document, so the invariant holds in every interleaving. A message that is
committed but not yet on screen when the user marks read is not counted; the
user is in the room, the message arrives a moment later, and the next
mark-read covers it — the invariant stays true at every instant.

### Critical Risk A — delayed trigger after mark-read (fixed)

Before `2bdb060b` the transaction incremented every recipient unconditionally,
so a trigger that ran after the recipient had already marked the room read
left a counter of 1 that nothing cleared until the room was reopened. The
emulator interleavings (`chatUnread.emulator-test.ts`, P0-2-K) drive the
trigger by hand so each order is deterministic:

| Case | Order | Expected | Old code | New code |
|---|---|---|---|---|
| K-A | trigger → markRead | 0 | pass | pass |
| K-B | commit → markRead → trigger (delayed) | 0 | **FAIL (1)** | pass |
| K-C | markRead → commit → trigger | 1 | pass | pass |
| K-D | two commits on screen → markRead → both triggers late | 0 | **FAIL** | pass |
| K-E | m1 → markRead → m2; triggers delivered m2 then m1 | 1 | **FAIL** | pass |
| K-F | trigger → markRead → redelivery | 0 | pass | pass |
| K-G | group of 6: two members read after the commit, three did not | 0/0/0/1/1/1 | **FAIL** | pass |
| K-H | garbage `lastReadAt` | 1 (fail toward counting) | pass | pass |
| K-I | markRead racing the delayed trigger, 10 rounds | 0 every round | **FAIL** | pass |

Also tested through the deployed wiring (`chatUnreadTrigger.emulator-test.ts`:
mark-read before the delayed delivery, plus a redelivery → 0).

Reproduced in production on the live revision `00008` (strict smoke
`p02_smoke_v2`, namespaced test accounts, everything deleted afterwards):
17/19 — the two checks that fail are exactly "message committed → B marks
read before the trigger lands → B == 0" (actual 1) and "B equals the
invariant" (actual 1, expected 0). The rules, system-message and race
checks pass. This is the before-evidence for the deploy of `2bdb060b`.

After the deploy of revision `00009` the same smoke passes **19/19**
(trigger accounting, sender excluded, rules ALLOW/DENY matrix with real ID
tokens, system message, delayed trigger → 0, invariant, race → invariant), and
a group addendum (`p02_smoke_group`, six members) passes **21/21**: sender
excluded, five recipients counted once, one member's read leaves peers
untouched, read boundary (readers before the commit get only the new message),
delayed trigger in a group → 0, invariant for all six, marker idempotency,
serving revision `00009-mod`; residue audit 0 (users, publicProfiles, room,
messages, dispatch logs, per-user notifications).

### Critical Risk B — the trigger's actual retry configuration

Verified on the live function, not assumed:

| Evidence (2026-10-22) | Value |
|---|---|
| `gcloud functions describe onChatMessageCreated --gen2` → `eventTrigger.retryPolicy` | `RETRY_POLICY_DO_NOT_RETRY` |
| Pub/Sub subscription `eventarc-asia-northeast3-onchatmessagecreated-826606-sub-487` | ack 600 s, retention 86400 s, backoff 10 s–600 s, no dead-letter |
| Revision | `onchatmessagecreated-00008-ved` (2026-10-16), timeout 60 s, 256 Mi, concurrency 80, max 10 |

So the comment "re-throw so the platform retries" was false in production:
a thrown accounting error dropped the event and lost the increment. The
fix declares `retry: true` on the trigger (`__endpoint.eventTrigger.retry`
is asserted by the emulator test). Retries are safe: accounting is
idempotent (marker in the same transaction), push is deduplicated
(`notificationDispatchLog`). Pub/Sub is at-least-once regardless of the
policy, so idempotency was required either way.

Failure matrix (post-fix behaviour; "current prod" = revision `00008`):

| Case | Behaviour |
|---|---|
| A. transaction fails transiently (UNAVAILABLE / ABORTED after the SDK's own retries) | throws → platform retries with backoff; current prod: event dropped |
| B. message deleted before the trigger runs | `message_missing`, returns, no retry loop |
| C. room deleted before the trigger runs | marks the message, `room_missing`, returns |
| D. accounting ok, push throws | event retried → accounting `already_accounted`, push skipped by the dispatch log (at-most-once push) |
| E. duplicate delivery | `already_accounted`, push skipped |
| F. out-of-order delivery (m2 before m1) | commutative increments + high-water mark; K-E |
| G. persistent failure (bug, permission) | retried until the retention window (CLI warns up to 7 days; subscription retention 24 h); `chat_unread_accounting_failed` alert fires; `--repair` after recovery |

**Deployed 2026-10-22 10:39Z** as `onchatmessagecreated-00009-mod` (commit
`ed0413ed` tree; function code from `2bdb060b`) through the guarded script
with the new `--allow-failure-policy onChatMessageCreated` opt-in (one named
function, single target, env guard before and after: 31 keys, removals =
changes = 0, 38 live variables, 0 secret refs). Verified on the live
resource, not from the exit code:

| Check | Value |
|---|---|
| `eventTrigger.retryPolicy` | `RETRY_POLICY_RETRY` |
| Cloud Run | `onchatmessagecreated-00009-mod` Ready, 100 % traffic, nodejs22, 60 s / 256 Mi / max 10 / concurrency 80 (unchanged) |
| Service account / trigger SA | `810450765203-compute@…` (unchanged) |
| Eventarc trigger / subscription | `onchatmessagecreated-826606` / `…-sub-487` (unchanged) |
| Functions in region | 98 before and after (no deletion) |
| Logs after deploy | 4 deploy-time unauthenticated probes (403, same as every deploy), then only 204s; accounting logs show `alreadyRead: 1` for the high-water-mark cases; 4 pushes sent, 0 duplicates, 0 `accounting failed` |

Failure classification as implemented (`accountMessageUnread` + trigger):

| Class | Example | Behaviour |
|---|---|---|
| TRANSIENT | Firestore UNAVAILABLE / DEADLINE_EXCEEDED / ABORTED beyond the SDK's own transaction retries | handler throws → platform retry with backoff (now active) |
| PERMANENT (code/config) | permission denied, bug in the handler | throws → retried until the retention window closes (CLI: up to 7 days; subscription retention 24 h); each attempt is 2 reads; `chat_unread_accounting_failed` alert; recovery = fix + `--repair` |
| PERMANENT (data) | message without sender, garbage `participantIds` / `lastReadAt` | never throws: `no_recipients` / counted, marker written, no loop |
| ALREADY PROCESSED | redelivery, retry after a push failure | `already_accounted`, push skipped by the dispatch log |
| RESOURCE REMOVED | message or room deleted before the trigger ran | `message_missing` (nothing to mark) / `room_missing` (message marked); no loop |

### Read boundary semantics (decision, explicit)

`markRoomRead` stamps `lastReadAt = request.time` (server time of the
mark-read request), issued by the room screen once per *newest live message
id*. The boundary is therefore "everything committed before the mark-read
request", not "the newest message the user looked at". Scenario *M1 displayed,
M2 committed but not yet delivered, user marks read*: M2 is treated as read
and not counted. This is the pre-existing room-level product behaviour
(opening the room marks the room read) and is kept deliberately: the user is
on the room screen, M2 arrives within the stream latency, and the next
mark-read (newest id changed) covers it; the invariant stays true at every
instant. Only a per-message acknowledgement model would change this, which
is out of P0-2's scope.

### Critical Risk C — push idempotency under retries

`sendPushOnce` creates `notificationDispatchLog/chat_<roomId>_<messageId>` in a
transaction *before* calling FCM: a retried or duplicated event never sends a
second push. The trade-off is at-most-once: a crash between the log write and
the FCM call loses that one push (no retry re-sends it). Accepted — a
duplicate push is user-visible, a lost push is covered by the badge and the
daily digest.

### Reconciliation (`chatUnreadBackfillCli --verify | --repair`)

`verifyRoomUnreadCounts` recomputes the expectation per participant: the
strict invariant when `lastReadAt` exists, the legacy `readBy` rule otherwise
(which also folds reads done by old clients into the counter). Messages
younger than `--grace-seconds` (default 300) may still sit in the trigger
queue and are never reported as lost. `--repair` fixes a room in ONE
transaction that re-checks `lastReadAt`, the counters and the markers of the
counted messages, skips the room if anything moved, and marks those messages
accounted so a late trigger cannot double count. Emulator tests cover a clean
room, a phantom (`over_count`), a lost increment (`under_count` + late
trigger), old-client reads, and a room that moved between verify and repair.

Production, 2026-10-22, read-only, before and again after the `00009`
deploy and the smokes: `rooms=23 withUnreadModel=23 legacy=0
structuralIssues=0 mismatches=0 unverifiable=0 skipped=0 messagesRead=25`.
No `--repair` was needed or run.

### Digest, old clients, multi-device, groups, rules

- Digest: scheduled runs observed every day 04:00Z from 2026-10-16 to
  2026-10-22 (`roomsScanned: 2`, `users: 0`, 0 errors). Notification id
  `chat_digest_<date>` lives under `users/{uid}/notifications`, so the scope is
  per user per day; a retried run cannot notify twice.
- Old clients keep computing from `readBy` and never reset counters; a user's
  counter can read stale until they open the room on a new client — or until
  `--repair` (legacy basis). Nothing an old client writes can corrupt the
  model (rules refuse the model keys on the general branch).
- Multi-device: state is per user; any device's mark-read clears all (P0-2-I).
- Groups: per-member high-water marks (K-G); increments stay commutative.
- Rules attack matrix (11 rules tests + production smoke): reset another
  participant's counter, forge another's `lastReadAt`, set own counter to a
  non-zero value, smuggle model keys through the general update, write the
  accounting marker on create, non-participant access — all DENY. A client
  cannot influence accounting through `createdAt` because the trigger uses
  `createTime`.

### Monitoring

Log-based metric `chat_unread_accounting_failed` (filter: service
`onchatmessagecreated`, `jsonPayload.message = "chat unread accounting failed"`)
and alert policy "Chat unread accounting failed" (> 0 in 5 min). Every
accounting now logs `chat unread accounted` with `reason`, `incremented`,
`alreadyRead`.

**ALERT EXISTS — DELIVERY CHANNEL NOT CONFIGURED.** The project has no
notification channel at all (the ten avatar alert policies have none either),
so an incident is visible only in the Cloud Monitoring console. Creating a
channel (e-mail / Slack) is an owner decision (backlog NEW-11); until then the
operational check is the reconciliation procedure: after any accounting
failure, `node functions/lib/chatUnreadBackfillCli.js --project
seolleyeon-final --verify`, and `--repair --checkpoint <id>` only for the
rooms it reports.

### Cost (final)

| Path | Status | Figure |
|---|---|---|
| Badge / chat list | MEASURED (emulator, same assertions) | rooms per change (3 → 3) vs 168 reads legacy |
| Mark read | MEASURED | 1 write vs 600 |
| Open room | MEASURED | 50 docs vs 120 (history) |
| Trigger accounting | MEASURED (code path) | 2 reads + 2 writes per message (+ `already_accounted` reads on retry) |
| Digest | MEASURED (production logs) | `roomsScanned: 2`, 0 message reads |
| Reconciliation `--verify` | MEASURED (production) | 23 room reads + 25 message reads for the whole dataset |
| Platform retries | ESTIMATED | only on failures; bounded by the retention window |
| Production billing delta | NOT VERIFIED | no billing export queried |

### PR #147 / CI (2026-10-22)

Head `0deba328` → `security/integration` (no branch protection, no required
reviewers, mergeable). Workflow `ci`, run 39766953041: 10 of 11 jobs green —
Functions build/lint/test, Firebase security emulator tests (P0-1 + P0-2
suites), Firestore rules, Storage rules, Recsys / script unit tests (incl. the
guard contract tests), Functions bootstrap recovery guard, Secret scan
(gitleaks), Web build smoke, Android debug APK smoke, Android production AAB
compile smoke. Red: `Flutter analyze/test` — analyze is clean, `flutter test`
reports 1162 passed / 18 failed, the same pre-existing set as locally (backlog
NEW-13; none in chat/unread code). The PR was **not merged**: a red required
job is a repository-policy question for the owner, not something to force.

### Cost re-measurement with the final code (2026-10-22)

Same emulator assertions, legacy port vs final port: badge 18 → **168** reads
with 10× history (legacy, FAIL) vs 3 → 3 (final); mark 600 unread read
**600** writes vs **1**; open room **120** docs vs **50**; digest **120**
message reads vs **0**. Per-message accounting cost with the high-water mark:
unchanged (2 reads + 2 writes in one transaction); a retry costs 2 reads and
no writes; push dedup is 1 read + 1 write per message (pre-existing).
Production billing delta: NOT VERIFIED (no billing export queried; traffic is
too small for a statistical comparison).

### Client release artifact (2026-10-22)

`flutter build apk --release --flavor production` on `270e49a2` with a
throwaway signing key (the repo has no `android/key.properties`; CI's AAB
smoke uses the same throwaway approach; the key file was removed afterwards).
Artifact `app-production-release.apk` (98.5 MB, `com.seolleyeon.app`,
pubspec `1.0.0+34`, `currentKnownReleaseBuild = 23` on this branch — the
35/35 sync lives in the owner's uncommitted branding change). Symbol scan of
`lib/arm64-v8a/libapp.so`:

| Symbol | Count |
|---|---|
| `ChatUnreadProvider` | 2 |
| `MessagePageMerger` | 2 |
| `ChatRoomUnread` | 1 |
| `markRoomRead` / `latestMessagesStream` / `olderMessagesPage` | 1 each |
| legacy `hasAnyUnreadChats` / `unreadCountStream` / `markMessagesAsRead` | 0 |
| `useFirestoreEmulator` (release build strips the `kReleaseMode`-gated branch) | 0 |

Not a store-uploadable build: the Play upload key is pending (owner), so the
Play / App Store state is NOT VERIFIED, real-device validation was not
performed, and the client is NOT RELEASED.

### Closure status

- SOURCE: CLOSED (final-audit fixes committed, tested, reviewed in PR #147).
- DATA: COMPLETE (backfill 2026-10-16; strict verify 0 mismatches before and
  after the `00009` deploy).
- BACKEND: CLOSED — `onchatmessagecreated-00009-mod` with
  `RETRY_POLICY_RETRY`, strict smoke 19/19 + group 21/21, env guard preserved,
  no other function changed.
- PRODUCTION: PARTIAL — the client with the provider / pagination is not
  published (no upload key, store state unverifiable from here); `readBy`
  retirement gated on `minimumSupportedBuild` (NEW-06); alert delivery channel
  not configured (NEW-11).

## Pre-launch closure (2026-10-25) — legacy `readBy` retirement

Owner decision: the app has not launched, there are no public users and
legacy client support is not required, so the per-message `readBy` receipt
model is retired instead of being carried behind `minimumSupportedBuild`.
Branch `security/p0-2-readby-retirement` (from the PR #147 merge `69a85520`).

### Final single model

```
chat_rooms/{roomId}
  unreadCounts.{uid}        server increments (trigger transaction), participant resets own key to 0
  lastReadAt.{uid}          participant, own key, request.time
  unreadModelVersion        1
  unreadBackfilledAt        one-time backfill marker (2026-10-16)
  legacyReadBoundaryMigratedAt / legacyReadBoundaryMigrationVersion   one-time boundary migration marker
messages/{id}.unreadAccountedAt   server-only accounting marker
```

A missing `lastReadAt[u]` means exactly "every message not sent by u is
unread" — identically for the trigger (`recipientsToIncrement`), the client
(`ChatRoomUnread.fromRoomData` reads counters only), the digest (counters
only), the reconciliation (`basis: no_boundary`) and the rules.

### Inventory and disposition

| File | Occurrence | Class | Disposition |
|---|---|---|---|
| `functions/src/{blindMeeting/automaticReplacement,blindMeeting/store,chatSafety,index(×3),mutualMatchCreation,playReviewAccess,safetyStamp(×2),supportOperations(×2),teamMeetingRequest}.ts` | `readBy: [...]` on message create | ACTIVE_RUNTIME (write) | removed — 12 server writer sites |
| `lib/features/chat/services/chat_service.dart` (promise request / edit / delete) | `'readBy': [...]` | ACTIVE_RUNTIME (write) | removed — 3 client writer sites |
| `functions/src/chatUnread.ts` `legacyMessageIsUnreadFor`, backfill, reconciliation `basis: readBy` | read | RECONCILIATION / MIGRATION | moved to `chatUnreadLegacyMigration.ts` (one-time); reconciliation fallback replaced by `no_boundary` |
| `firestore.rules` `isValidClientSupportMessage` (`readBy` key + `is list`), `onlyMessageReadReceiptUpdate`, promise-lifecycle allowlist | SECURITY_RULE | removed; `readBy` added to the forbidden create keys; `canUpdateChatMessage` = promise lifecycle only |
| `lib/**` `isRead` (bubble tick = `senderId == me`, notifications' own flag) | not `readBy` | ACTIVE_RUNTIME (unrelated) | unchanged |
| `functions/src/chatRealPhoto.ts`, `accountDeletionChatLifecycle.ts`, `playReviewAccess.ts:460` | message reads | no `readBy` dependency | unchanged |
| rules tests, emulator/unit tests, `test/firestore_rules` fixtures | TEST | fixtures rewritten; receipt tests flipped to DENY; historical-data tests keep `readBy` explicitly |
| `docs/audits/**`, `.tmp/**` | DOCUMENTATION / HISTORICAL_ARTIFACT | kept |

Indirect dependencies checked: push (`sendPushOnce` — participants, not
receipts), digest (counters), room list (counters), group chat (counters),
account deletion (no receipts), support/admin ops (writers only), analytics
(none), fixtures (`playReviewAccess` welcome message — writer only).

### Behaviour contract (unchanged, now the only one)

1:1: `A → M1` ⇒ A unchanged, B +1. Group of six: sender unchanged, five
recipients +1 each; one member's read never touches a peer. System and
promise messages count for every non-sender. Mark-read: `unreadCounts.me = 0`,
`lastReadAt.me = request.time`, one write, room level — acknowledging every
message committed before the read request (documented decision, § Read
boundary semantics). High-water mark: `message.createTime ≤ lastReadAt[u]` ⇒
no increment; `>` ⇒ increment; server `createTime`, never a client clock.
Multi-device: per-user state, any device's read clears all.

Model initialization: new room — no fields until the first accounted message
(`unreadModelVersion` set by the trigger); room without messages — 0
everywhere; room without `lastReadAt[u]` — everything unread for u; malformed
`lastReadAt` (non-Timestamp) — ignored, counts (fail toward unread), reported
by `--verify` as a structural issue only if a counter is malformed; deleted
room — `room_missing`, message marked; removed participant — stale key
tolerated (`checkRoomUnreadIntegrity` flags only a positive count for a
stranger).

### Regression tests (written first, failing on the old code)

- `chatUnreadLegacyGuard.test.ts`: no runtime source writes/reads `readBy`
  (only the migration module may), the accounting module has no legacy rule,
  the rules forbid the field and carry no receipt branch — 3/3 FAIL before,
  PASS after.
- Dart cost-contract test: no `readBy` string in `lib/` — FAIL before, PASS after.
- Rules: receipts no longer writable (flipped to DENY in `firestore.chat` and
  `firestore.chatunread`), promise message accepted without `readBy` and
  refused with it (new), `firestoreRules.test.ts` pins the absence of the
  receipt branch.
- Emulator (`chatUnread.emulator-test.ts`): every message seed is now
  `readBy`-free (TEST A/B/C/D/E/G through the existing P0-2-E…K suites),
  TEST I historical receipts ignored, TEST J1 boundary migration (contiguous)
  → clean verify + idempotent, TEST J2 non-contiguous / counter mismatch →
  reported, nothing written, TEST F transient failure → surfaced, retry
  accounts once; deployed-wiring test creates `readBy`-free messages.

### Reconciliation / migration decision

`--verify` now has two bases: `lastReadAt` (strict invariant) and
`no_boundary` (every message not sent by the user). Production audit
(read-only, 2026-10-25): 23 rooms, 25 messages, 50 participant slots, 0
boundaries, 48 slots already consistent, 2 slots in `dm_4705818223_fake_user_1`
with counter 0 derived from receipts that say "all read" (contiguous
`RRRRRRRRR` / `RRRRRRRRRRRRR`). Policy: a receipt history is representable by
one timestamp only when it is a contiguous suffix; then
`lastReadAt[u] := createTime(newest read message)` reproduces the counter
exactly. Non-contiguous histories or counters that disagree with the receipts
are reported as anomalies and never written. Implemented as the one-time
`--init-boundaries-dry-run | --init-boundaries-apply --checkpoint` modes
(`runReadBoundaryInitialization`, one transaction per room that re-checks
the room and the counters first). Dry run: `participantsInitialized 2,
consistent 48, anomalies 0, unverifiable 0, writes 0`. The apply (1 room, 2
keys) is pending owner approval (NEW-14); until it runs, `--verify` reports
exactly those two `under_count … no_boundary` rows. Historical `readBy`
fields stay physically stored; nothing deletes them.

### Verification (final code, 2026-10-25)

| Suite | Result |
|---|---|
| Functions `tsc --noEmit` | clean |
| Functions unit (`node --test lib/**/*.test.js`) | 1125 / 1125 (incl. 3 new guards) |
| Firestore emulator P0-2 + trigger | 35 / 35 (4 new: I, J1, J2, F) |
| `rules_tests` (CI suite) | 259 / 259 (1 new) |
| `test/firestore_rules` (non-CI suite) | 158 / 160 — the 2 failures pre-exist on the base content (NEW-17) |
| `flutter analyze` | No issues found |
| `flutter test test/features/chat test/core/compatibility` | 69 pass / 1 fail (NEW-05 build-number test) |
| `flutter test` (all) | 1162 pass / 18 fail — the same 18 as before (NEW-13) |
| Legacy-port cost evidence (`CHAT_UNREAD_PORT=legacy`) | still fails exactly A/B/C/L: 168 reads, 600 writes, 120 docs, 120 message reads vs 3 / 1 / 50 / 0 |

Cost of the retirement itself: one fewer field per message write; trigger,
mark-read, pagination and digest costs unchanged (2 reads + 2 writes per
message, 1 write per mark-read, 50 docs per page, 0 message reads per digest).

### Deployment status (gated)

Nothing was deployed in this pass. The model that runs in production is
unchanged (`onchatmessagecreated-00009-mod`, rules `113e93ec…`). Deployed
Functions keep writing `readBy` on new messages until redeployed — harmless,
the field is ignored everywhere. The new Rules deny `readBy` from clients and
remove the receipt update, which breaks promise messages and mark-read on any
installed OLD build (incl. the one under Play review). Deploy order when the
owner releases the new client: writer Functions (guarded, per function) →
Rules → `--verify` + strict smoke. See NEW-15 for the list and the guard
dry-run results.

Guard dry-runs (read-only, 2026-10-25, dotenv 31 keys sha256 `78dac231…`):
every affected function passes the dotenv contract, and the regression guard
reports **0 removals, 0 changes, 0 missing required keys** — only *additions*
(keys present in the canonical dotenv but absent from the function's serving
revision, the OPS-02 drift). Each deploy therefore needs the additions
declared one by one with `--allow-add-key`, which is the convergence OPS-02
intended:

| Function | Live env keys | Additions to declare | Removals / changes |
|---|---|---|---|
| `sendChatText` | 10 | ≥ 8 | 0 / 0 |
| `submitSafetyStamp` / `submitSafetyStampFollowUp` | 9 / 10 | ≥ 8 | 0 / 0 |
| `submitInquiry` / `submitIssueReport` | 11 / 11 | ≥ 8 | 0 / 0 |
| `onInteractionCreated` / `onMatchUpdated` / `autoCompleteExpiredGoodbyeSafetyStamps` | 33 each | ≥ 5 (Apple IAP keys) | 0 / 0 |
| `respondTeamMeetingRequest` | 18 | ≥ 8 | 0 / 0 |
| `preparePlayReviewSession` / `playReviewSignIn` | 9 / 9 | ≥ 8 | 0 / 0 |
| `blindMeetingAction` / `blindMeetingOps` / `blindMeetingMatchingTick` / `blindMeetingLifecycleTick` | 10 / 7 / 10 / 11 | ≥ 8 | 0 / 0 |

(`≥` because the dry-run log kept the first ten guard lines per function; the
exact key list is printed by `scripts/deploy_functions_guarded.sh --dry-run
<fn>`.) `mutualMatchCreation.ts` has no importer (dead module, NEW-16) and
needs no deploy.

## Closure execution (2026-10-25, second pass) — PR #148, NEW-14, NEW-15

### Integration

PR #148 merged into `security/integration` as `dc9f682e` (merge commit;
head `33333072`, which adds the transitional rule below on top of
`8435effe`). Live Firestore rules before the pass were byte-identical to the
merged base `69a85520`; the reviewed diff touched only the chat-message
functions (50 lines). CI on `33333072` (run 40169290214): 10/11 green,
`Flutter analyze/test` red with the same 18 baseline failures (NEW-13), none
introduced.

### Old-client gate → PATH B (transitional, NEW-18)

Evidence that an installed old build may still be exercised: Play-review
sign-in requests in the last 30 days (2) and `preparePlayReviewSession` (1),
`playReviewSessions` last updated 2026-09-29, newest client promise message
2026-09-02, no public users. Because an old build writes `readBy: [own uid]`
on the messages it creates and appends its own uid as a receipt, the strict
rules would have broken its promise messages and mark-read. Decision: keep
the retirement but tolerate exactly those two shapes —
`legacyReadByOnCreateTolerated()` (create: no `readBy`, or `readBy ==
[request.auth.uid]`), `legacyOwnReceiptAppend()` (update: affected keys ⊆
{`readBy`, `updatedAt`} and `after.readBy == before.readBy.concat([uid])`),
and `readBy == [request.auth.uid]` inside the promise-lifecycle allowlist.
Nothing else is accepted; the model ignores the field. Retirement condition
and steps: NEW-18. Rules suite 259/259 and guard tests pin the exact shape.

**OLD CLIENT GATE: PASS (transitional)** — the breaking rules were not
deployed; the tolerant final rules were.

### NEW-14 — read-boundary migration (CLOSED)

From the integrated source `dc9f682e`: dry run 23 rooms / 2 to initialise /
48 consistent / 0 anomalies / 0 unverifiable; apply with checkpoint
`p02-boundaries-20261025` → 1 transaction, room `dm_4705818223_fake_user_1`,
`lastReadAt.4705818223 = 2026-08-31T07:57:06.037Z`,
`lastReadAt.fake_user_1 = 2026-08-31T07:46:20.495Z` (commit time of each
participant's newest read message), `legacyReadBoundaryMigratedAt`,
`legacyReadBoundaryMigrationVersion: 1`; counters unchanged, participants
and all 22 messages (historical `readBy` included) untouched. Post-apply
`--verify`: rooms 23, structuralIssues 0, mismatches 0, unverifiable 0.
Re-run: 0 initialised, 2 alreadyBounded, 0 writes. Rollback by deleting the
two keys is valid only while no newer message or read exists in that room;
afterwards use the forward `--repair` path.

### NEW-15 — writer Functions (7 deployed, 8 gated) and Rules (deployed)

Per-function source-drift audit (Phase 4.2): a redeploy ships every change
since that function's last deployment, so each target's module history was
compared with its live revision date.

| Function | Live before | Drift since last deploy | Disposition |
|---|---|---|---|
| `onMatchUpdated` | `00005-fow` (08-10) | handler region: `readBy` removal only | **DEPLOYED → `onmatchupdated-00006-roy`** |
| `submitSafetyStamp` / `submitSafetyStampFollowUp` | `00001-lib` / `00001-hol` (09-07) | `safetyStamp.ts`: `readBy` only | **DEPLOYED → `00002-med` / `00002-ziz`** |
| `submitInquiry` / `submitIssueReport` | `00001-mav` / `00001-ren` (09-03) | `supportOperations.ts`: `readBy` only | **DEPLOYED → `00002-bat` / `00002-cud`** |
| `respondTeamMeetingRequest` | `00008-ref` (09-05) | `teamMeetingRequest.ts`: `readBy` only | **DEPLOYED → `00009-wes`** |
| `playReviewSignIn` | `00003-dij` (09-17) | `playReviewAccess.ts`: `readBy` only (09-06/07 commits already live) | **DEPLOYED → `00004-new`** |
| `sendChatText` | `00001-lah` (09-10) | `chatSafety.ts` created 09-15 (`10bf9392`: content-safety / report feature) | GATED — unrelated moderation change |
| `onInteractionCreated` | `00007-kug` (08-10) | handler changed 09-06 (`c989d8f8`: data-partition checks) | GATED — unrelated security-relevant change |
| `autoCompleteExpiredGoodbyeSafetyStamps` | `00006-vuj` (08-10) | region changed 09-01 (`5232a3e7`) | GATED |
| `preparePlayReviewSession` | `00004-mas` (09-06) | `c989d8f8` (09-06), `1f72caf5` (09-07) | GATED |
| `blindMeetingAction` / `MatchingTick` / `LifecycleTick` | 09-09 02:36Z | `b9956e11` (09-09 17:17 KST, leave-room feature in the writer module) | GATED |
| `blindMeetingOps` | `00001-qiv` (08-10) | 19 blind-meeting commits | GATED |

Every deploy used `scripts/deploy_functions_guarded.sh` with each addition
declared one by one (`--allow-add-key`, 5–27 keys from the canonical 31-key
dotenv `78dac231…`): ENV DEPLOY CONTRACT PASS, ENV REGRESSION GUARD PASS
before and after (0 removals, 0 changes, 0 missing required, 0 undeclared
additions), new revisions Ready at 100 % traffic, 98 functions before and
after, `onChatMessageCreated` untouched (`00009-mod`, `RETRY_POLICY_RETRY`).
The only ERROR log lines are the two deploy-time probe entries per callable
("Invalid request, unable to process", same as every deploy); none
afterwards. The 8 gated functions keep writing the ignored `readBy` field on
the messages they create; the owner decides whether to ship their
September changes (NEW-15 follow-up).

Rules: `firebase deploy --only firestore:rules` from `dc9f682e` → ruleset
`0b9d5a12-1a72-4470-9bbd-0c1189870628` (2026-10-25T07:04:02Z); live source
byte-identical to the reviewed file; P0-1 helpers
(`emailLinkTokenBindsCallerTo`, …) and `onlyOwnUnreadReadStateUpdate`
present, `onlyMessageReadReceiptUpdate` absent.

### Production smoke after the deploys

`p02_smoke_v3` **33/33** (namespaced accounts, residue 0): 1:1 accounting
with a `readBy`-free stored message, mark-read through the live rules,
cross-user / non-participant / forged counter / `unreadModelVersion` DENY,
delayed trigger after mark-read → 0 (invariant), marker idempotency, promise
create without `readBy` ALLOW, `readBy == [own]` ALLOW (NEW-18) and
accounted, `[other]` / `[own, other]` DENY, `unreadAccountedAt` forgery DENY
on create and update, receipt append own uid ALLOW / other uid / replacement
/ text rewrite DENY, counters untouched by the tolerated receipt, serving
revision and live ruleset asserted. `p02_smoke_group` **21/21** (six
members). Final `--verify`: 23 rooms, 0 structural issues, 0 mismatches, 0
unverifiable. Logs in the window: 13 pushes sent, 0 "already dispatched"
(no duplicate deliveries), 0 accounting failures, 0 errors.

### Status after this pass

- SOURCE CLOSED · CLIENT SOURCE READY · DATA VERIFIED (NEW-14 closed).
- BACKEND: model live; rules final (transitional tolerance, NEW-18); 7 of 15
  writer functions redeployed; 8 gated on an owner review of unrelated
  September changes (NEW-15 follow-up) — their `readBy` writes are inert.
- PRE-LAUNCH TECHNICAL: not fully closed while the 8 gated redeploys and the
  NEW-18 retirement remain; everything else is done and verified.
- CLIENT RELEASE VERIFICATION: DEFERRED BY OWNER.
