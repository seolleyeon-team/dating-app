# Firestore rules audit — Kakao friend recommendation privacy

Date: 2026-08-29
Target: `seolleyeon-final`, database `(default)`, Firestore Native, Standard edition, `asia-northeast3`

## Baseline and merge decision

- Compared the user-provided 1,635-line production rules snapshot with the local rules in full.
- Kept the local server-only `emailLinkTokens` create/update/delete policy. Replacing it with the attachment's client-create policy would weaken the current design.
- Restored the attachment's `chatRoomCreateHasNoMeetingLinkage` create-time guard.
- Restored the attachment's authenticated read/server-write-only `recommendationConfig` rule.
- Kept the local `recommendationExclusions/{viewerUid}/targets/{targetUid}` rule required by Kakao friend mutual exclusion.
- The remaining content now matches the union of the attachment baseline and the local privacy hardening.

## Codebase access-pattern inventory

The repository was scanned across Dart, TypeScript/JavaScript, and Python for Firestore collection/document reads, queries, transactions, and batch writes. Generated build output and dependency directories were excluded; operational scripts and the festival subproject were included in the inventory pass.

Relevant Kakao recommendation paths:

- `users/{uid}`: the authenticated app reads/writes its own profile; Cloud Functions set `kakaoFriendAvoidanceEnabled`, `recommendationPrivacyReady`, and reconciliation state. Recommendation jobs read users through Admin SDK.
- `publicProfiles/{uid}`: clients perform signed-in point reads for cross-user display. Cloud Functions alone synchronize writes. The public projection contains `recommendationPrivacyReady`, but not the private Kakao preference or reconciliation details.
- `recommendationExclusions/{viewerUid}/targets/{targetUid}`: the signed-in viewer reads only their own target documents. All creates, updates, and deletes are performed by Admin SDK callables and account-cleanup code.
- `modelRecs/{uid}/daily/{dateKey}/sources/{algo}`: the app reads only the authenticated user's recommendation documents. Python batch jobs write them with Admin credentials.
- `recommendationConfig/{docId}`: signed-in clients may point-read rollout state; writes and list queries are server-only/denied.

Other high-impact paths reviewed for interaction with these rules:

- `blocks/{viewerUid}/targets/{targetUid}` remains owner-readable and server-write-only for block creation/update.
- `chat_rooms/{roomId}` and its subcollections use participant-scoped reads/writes; client-created rooms cannot claim meeting or match linkage fields.
- `emailLinkTokens/{token}` permits unauthenticated point reads because the opaque token is carried in the email link, but denies all client writes and list operations.
- `recEvents/{uid}/events/{eventId}` is read by recommendation exporters through Admin SDK and is not opened by the new rules.
- Avatar, blind-meeting, event, community, account-deletion, and festival collections were present in the scan but the Kakao privacy merge does not widen their permissions.

## Query/rules compatibility

- The client exclusion query is a subcollection list under the caller's own `viewerUid`, matching `isSelf(viewerUid)`.
- Cross-user profile loading uses point reads from `publicProfiles`; collection listing remains denied.
- Recommendation reads are scoped by path to the caller's UID, matching `isSelf(userId)`.
- No client query depends on listing another user's exclusions or private `users` documents.

## Red-team assessment

```json
{
  "score": 5,
  "summary": "The Kakao recommendation privacy additions are fail-closed and do not grant clients authority to assert friendships, readiness, or exclusion pairs.",
  "findings": []
}
```

Attack checks performed:

- Update bypass: clients cannot create, update, or delete exclusion documents, so a valid document cannot be changed into a forged pair.
- Authority source: friendship verification, readiness, and pair writes are derived and persisted by Admin SDK code; no rule trusts client-supplied roles or ownership fields for these paths.
- Cross-user read: a caller cannot substitute another `viewerUid` because every exclusion read is bound to `request.auth.uid`.
- Query leakage: top-level exclusion documents and cross-user list operations are denied.
- Batch bypass: stale recommendations are still filtered in the app against the owner's exclusion set and candidate readiness; batch exporters also apply the same eligibility policy.
- Storage abuse/type safety: exclusion writes are server-only, so untrusted clients cannot create oversized maps/lists or malformed field types on this collection.
- Denial behavior: missing consent or failed synchronization leaves `recommendationPrivacyReady != true`, excluding that account from both viewer and candidate participation.

## Required verification before deployment

- Rule/function contract suite: passed (`npm test` in `functions`).
- Firebase CLI Firestore Rules dry-run against `seolleyeon-final`: compiled successfully; no deployment was performed.
- The compiler reported existing non-fatal warnings for built-in `request`/`resource` references inside helper functions and four unused helper functions. These warnings are also present in the baseline area and do not prevent compilation; they are not permissions granted by this Kakao privacy change.
- Review the dry-run diff and deploy only with an explicit `--project seolleyeon-final` flag.
