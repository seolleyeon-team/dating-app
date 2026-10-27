# P0-3 / SEC-04 — Bamboo Forest anonymity (2026-10-28)

**Invariant.** An ordinary signed-in user must not be able to link an anonymous
Bamboo post, comment, reply or like to a real account through app-controlled
data — even when they already know the victim's uid, use the Firestore SDK
directly, enumerate every readable document, read their own notifications, or
provoke notifications on purpose. Firestore Rules cannot redact fields of a
readable document, so the fix has to remove identity at the storage and
authorization boundary, not in the UI.

## 1. Confirmed identification paths (before this change)

| # | Path | Data exposed | Reader | Class | Fix |
|---|---|---|---|---|---|
| 1 | `bamboo_posts/{id}.authorId` (+ `where('authorId','==',uid)` allowed by the open `list` rule and a composite index) | author uid → `publicProfiles/{uid}` join | any signed-in user | PUBLIC_IDENTITY_LEAK | writers stop writing it; migration deletes it; rules never read it |
| 2 | `bamboo_posts/*/comments/{id}.authorId` | commenter uid | any signed-in user | PUBLIC_IDENTITY_LEAK | same |
| 3 | `likes/{uid}` under posts and comments, `get, list` open | liker uids (doc id) | any signed-in user | LIKES_ENUMERATION | `get` only by the liker, `list` denied; denial is independent of existence (no oracle) |
| 4 | `users/{owner}/notifications/*.actorId/actorName` for `community_comment/reply/post_like` | commenter / liker uid + nickname | the post/comment owner | NOTIFICATION_LEAK | producers write `actorName:"익명"`, no `actorId`; the shared writer force-strips actor fields for these types; migration sanitizes history (production: 0 such docs) |
| 5 | `reportAndBlockUser` for Bamboo content: client sends `reportedUserId = post.authorId`; server answers success/not-found by comparing to `authorId`; writes **mutual** `blocks/{a}/targets/{b}` readable by each side | author uid to the reporter; reporter uid to the author; an authorship oracle once the uid is hidden | reporter / author | OWNERSHIP_LEAK | Bamboo reports go to `reportBambooContent` (server resolves the owner from the mapping into the server-only `reports` doc; the reporter gets a content-id-only hide entry); `reportAndBlockUser` refuses Bamboo content before any lookup |
| 6 | Feed filtering by the viewer's real block list (`blocks/{me}/targets` ids vs `authorId`) | "block X, see which posts vanish" | any user who can block | CLIENT_DEPENDENCY (oracle) | removed; reported content is hidden per item instead |
| 7 | Ownership mapping create rules trusted `getAfter(public).authorId` | claim path tied to the field being removed | client | OWNERSHIP_LEAK (latent) | client mapping create denied; mappings are server-written in the same commit as the content |
| 8 | Server notification owner resolution fell back to public `authorId` | — | server | MIGRATION_DEPENDENCY | mapping-only, fail closed (`missing`/`malformed` → nobody notified, no rights) |
| 9 | Account deletion: soft-deleted content kept `authorId`; the production executor (`avatarCleanup.ts`) had no case for `deleteBambooOwnershipMapping`, so mappings of deleted accounts survived | deleted account uid | server data | SERVER_ONLY residue | soft delete removes `authorId`; executor case added |
| 10 | `CommunityProvider` (app-global) kept "내가 쓴 글" and the cached uid across logout / account switch | previous account's authorship | next user on the device | CLIENT_DEPENDENCY | provider resets on uid change and discards responses that arrive after a switch |
| 11 | Play Review reset asserted `authorId` on review posts | — | server | MIGRATION_DEPENDENCY | reset checks the partition and mapping owner; seed is authorless |
| — | Cloud Logging lines with commenter/liker uids | operator-only | operators | SERVER_ONLY | actor uids removed from Bamboo log lines |
| — | `notificationDispatchLog` | recipients only | server-only (rules deny) | SAFE |
| — | FCM data payloads (`type, postId, commentId, notificationId`) | `notificationId` embeds the recipient's own uid | recipient | SAFE_PUBLIC_DATA |
| — | `lib/services/post_service.dart` (`posts` collection, `authorId/authorNickname`) | — | unreferenced; rules default-deny `posts` | HISTORICAL_ARTIFACT (not touched) |

Also fixed (counter integrity, ATTACK 9): any signed-in user could move a
post's `commentCount` and `score7d` by ±1 repeatedly (popularity
manipulation), and the production comment `likeCount` was only ±1-gated
(not bound to a like document).

## 2. Final architecture

- **Public content** — `bamboo_posts/{postId}`: `postId, content, category,
  tags, createdAt, updatedAt, likeCount, commentCount, score7d, isDeleted`
  (+ `dataPartition, reviewFixture` in the review root). Comments: `commentId,
  content, parentCommentId, createdAt, updatedAt, likeCount, isDeleted`.
  No author field, no hash of one.
- **Private ownership mapping** — the only authority:
  `bamboo_post_authors/{postId}` and `bamboo_comment_authors/{postId}__{commentId}`
  (`ownerUid`, `postId`, `commentId`). Readable only by the owner and only
  through `where('ownerUid','==',me)`; never client-writable.
- **Server authority** (`functions/src/communitySafety.ts`):
  `createCommunityPost` / `createCommunityComment` write content + mapping in
  one commit (`create`, never overwrite); `deleteCommunityPost` /
  `deleteCommunityComment` check the mapping inside the transaction and
  return the same `permission-denied` for "not yours", "no mapping" and
  "malformed mapping"; `reportBambooContent` stores the mapped owner in the
  server-only `reports` doc and writes `users/{reporter}/bambooHiddenContent/{key}`.
- **Rules** — clients may only write their own `likes/{uid}` together with
  `likeCount ±1` (and `score7d` moving with it). Everything else on public
  Bamboo docs is server-only. Review partition mirrors the same contract.
- **Notifications** — Bamboo types carry `actorId: null, actorName: "익명"`;
  recipients are resolved from the mapping; self-notification suppression uses
  the mapping too.
- **Client** — models have no author field; "내가 쓴 글" pages the caller's
  mappings (`ownerUid == me` ordered by `createdAt`, index added) and fetches
  those posts with one `whereIn`; "is this mine" is one mapping query per feed
  page; delete/report through callables; likes only under the session uid.
- **Blocking decision.** Hiding Bamboo content by the viewer's real-identity
  block list is itself a deanonymization oracle (block a suspect, watch which
  posts disappear), so it is not done. A Bamboo report now hides that post or
  comment for the reporter and goes to moderation with the real owner attached
  server-side. Dating/chat blocks are unchanged. The report sheet copy no
  longer promises a real-name block. **Owner product confirmation requested.**

## 3. Tests (all local; CI steps added)

| Suite | Result | Kind |
|---|---|---|
| `rules_tests` (incl. new `firestore.bamboo.privacy.test.mjs`, 21 attacks) | 281/281 | VERIFIED EMULATOR |
| same attack suite against the **old** rules | 6/21 fail (likes list/oracle, partition, hidden list, comment-like binding, legacy `commentCount`/`score7d` forgery) | VERIFIED EMULATOR |
| `bambooPrivacy.emulator-test.ts` (writers, notifications, fail-closed, delete, report, oracle, shared writer, account deletion) | 9/9 | VERIFIED EMULATOR |
| migration unit + emulator (`scripts/bamboo_privacy_migration*.mjs`) | 8/8 + 5/5 | VERIFIED EMULATOR |
| functions unit | 1125/1125 | VERIFIED |
| P0-1 14/14 + 6/6, P0-2 35/35, drift 4/4, replacement 4/4 | pass | VERIFIED EMULATOR |
| Flutter analyze | clean | VERIFIED STATIC |
| Flutter tests | 1168 pass / 14 fail — all 14 pre-existing unrelated (screenshots, build-number constant, MBTI, purchase price); the 4 stale Bamboo Phase-A source-contract failures are now fixed | VERIFIED |

## 4. Production data (read-only, 2026-10-28)

| Collection | Count | Classification |
|---|---|---|
| `bamboo_posts` | 22 (0 comments, 0 likes) | 1 MAPPING_VERIFIED, 21 MAPPING_MISSING (18 of them: author is a legacy numeric Kakao uid with a Firebase Auth account but no `users` doc — MAPPING_MISSING_AUTH_ACCOUNT_ONLY) |
| `playReviewBambooPosts` | 3 posts, 1 comment, 1 like | 4 MAPPING_VERIFIED |
| mappings | prod 4 post / 1 comment, review 3 / 1 | 4 orphan mappings (no public doc; owner-readable only — not a leak) |
| notifications | 38 total, 0 Bamboo-type | nothing to sanitize |
| conflicts / malformed / unverifiable | 0 / 0 / 0 | dry-run exit 0 |

Dry-run plan: create 21 mappings, redact `authorId` from 25 posts + 1 comment,
0 notification writes. `--verify` today: 47 violations (expected before apply).

## 5. Rollout order (not executed — review gate)

1. Merge the PR after owner review.
2. Deploy `firestore:indexes` (mapping `ownerUid + createdAt`).
3. Deploy **Rules** first: they never read `authorId`, so they work on both
   legacy and redacted documents; like toggles keep working on legacy docs
   (tested). This closes likes enumeration and counter forgery immediately.
4. Guarded Functions deploy (`scripts/deploy_functions_guarded.sh`, env
   additions declared one by one) of exactly the functions whose code path
   changed:
   - content writers: `createCommunityPost`, `createCommunityComment`;
   - new callables: `deleteCommunityPost`, `deleteCommunityComment`,
     `reportBambooContent`;
   - notification triggers: `onBambooCommentCreated`, `onBambooPostLikeCreated`;
   - `reportAndBlockUser` (refuses Bamboo content);
   - account deletion: `cleanupAvatarMedia` (social soft delete + mapping
     executor case); `purgeAccountDeletionRetention` only if its live archive
     diff shows it runs the social plan (it imports the same executor);
   - Play review: `preparePlayReviewSession` (authorless seed, reset check).
   `shared/notify.ts` changes behaviour only for Bamboo types, so no other
   notification producer needs a redeploy. Diff each live archive against the
   merged tip first (deployment-drift lesson, `02-p0-2-chat-unread.md`). New
   writers stop producing identity-bearing docs before step 5.
5. Migration: `--dry-run` → `--apply --allow-production --limit 1` (canary) →
   `--verify` → full `--apply --checkpoint` → `--verify` must report
   `violations: 0`.
6. Production penetration checks with namespaced test identities through the
   client SDK against live Rules (likes list/get, mapping get/list/query,
   public field set, partition crossing), residue cleanup.

Exposure window: between step 3 and the end of step 5 the 26 legacy docs still
carry `authorId` (minutes). Fail-closed alternative if the owner prefers zero
window: run step 5 immediately after step 4 in the same session.

## 6. Installed-client compatibility (release-dependent)

Old builds (≤ current Play build) keep working for: reading the feed, posting
and commenting (already callable-based), liking. They lose: "내가 쓴 글"
(queries public `authorId` → empty), deleting own posts (client check on
`authorId` fails; direct update now denied), reporting Bamboo content
(`reportAndBlockUser` refuses Bamboo with an "update the app" message), and
block-based feed filtering (no `authorId` to compare). **No privacy regression
on old clients**; functional loss only. This is a CLIENT RELEASE gate, deferred
by the owner with the AAB/Play work.

## 7. Residual risks

- **Accepted / inherent:** authors can still identify themselves through
  content or outside channels; stylometry; timing correlation with a known
  person's activity; push notifications already delivered to devices cannot
  be recalled (none existed in production for Bamboo types); operators with
  Admin access can read mappings and `reports.reportedId` by design.
- **Historical:** blocks previously created from Bamboo reports via
  `reportAndBlockUser` already disclosed uids to both sides; they are normal
  dating-app blocks now and are not rewritten.
- **Not done:** the mutual-block disclosure of the *reporter* in non-Bamboo
  `reportAndBlockUser` flows (profile/chat) is unchanged — those reporters are
  not anonymous by product design, but the reverse block document does tell
  the reported user who reported them (unrelated finding, logged for P1).
