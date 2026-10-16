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
