# seolleyeon-final staging resource map

Generated: 2026-05-19 KST

## Project/account guard

| Check | Expected | Observed | Status |
|---|---|---|---|
| gcloud active account | `seolleyeon.official@gmail.com` | `seolleyeon.official@gmail.com` | PASS |
| gcloud active project | `seolleyeon-final` | `seolleyeon-final` | PASS |
| Firebase active project | `seolleyeon-final` | `seolleyeon-final` | PASS |
| Firebase alias | `staging -> seolleyeon-final` | present in `.firebaserc` | PASS |
| ADC quota project | `seolleyeon-final` | `seolleyeon-final` | PASS |
| source project | `seolleyeon` | visible, read-only only | PASS |
| target project | `seolleyeon-final` | visible, ACTIVE | PASS |

No access tokens, refresh tokens, signed URLs, or service account keys were recorded.

## Firebase CLI map

- `firebase.json`
  - functions source: `functions`
  - codebase: `default`
  - firestore rules: `firestore.rules`
  - firestore indexes: `firestore.indexes.json`
  - storage rules: `storage.rules`
  - hosting public: `public`
- `.firebaserc`
  - `default`: `seolleyeon`
  - `staging`: `seolleyeon-final`

Use explicit project flags for staging commands:

```sh
firebase use staging
firebase deploy --project seolleyeon-final --only <target>
gcloud ... --project=seolleyeon-final
```

## Client app identifiers

| Platform | Identifier | Current local config status |
|---|---|---|
| Android | `com.yonsei.dating` | existing config still references old project until SG-3 regenerates it |
| iOS | `com.yonsei.dating` | existing config still references old project until SG-3 regenerates it |

Files that currently require SG-3 staging regeneration:

- `android/app/google-services.json`
- `ios/Runner/GoogleService-Info.plist`
- `lib/firebase_options.dart`
- Flutter metadata in `firebase.json`

## Firebase Functions exports

Functions exported by `functions/src/index.ts` include:

- `uploadAvatarSourcePhoto`
- `getAvatarJobCandidates`
- `approveAvatarCandidate`
- `getChatRealProfilePhoto`
- `createFirebaseCustomToken`
- `createFirebaseCustomTokenFromEmailLinkToken`
- `createFriendInvite`
- `acceptFriendInvite`
- `ensureEventTeamSetup`
- `createEventTeamInvite`
- `respondEventTeamInvite`
- `onEventTeamSetupWritten`
- `spinSeasonMeetingRoulette`
- `onRecEventCreated`
- `onInteractionCreated`
- `onChatMessageCreated`
- `onBambooCommentCreated`
- `onBambooPostLikeCreated`
- `onAskCreated`
- `onMatchUpdated`
- `autoCompleteExpiredGoodbyeSafetyStamps`
- `schedulePromiseReminderTask`
- `dispatchPromiseReminder`
- `sendUpcomingPromiseReminderPushes`
- `sendDailyUnreadChatDigests`
- `syncContactBlocks`
- `onUserPhoneHashUpsert`
- `saveUserPhoneHash`

SG-2 should deploy the smallest required set first:

- `getChatRealProfilePhoto`
- `uploadAvatarSourcePhoto`
- avatar approval/upload functions if staging avatar flow requires them

## Cloud Run and recommendation candidates

Source project `seolleyeon` has existing Cloud Run services in `asia-northeast3`, mostly Firebase Functions second-generation services. Repo-local deployment candidates also include:

- avatar worker: `lib/ai_recommend_model/avatar_generation/Dockerfile`
- recommendation jobs/pipeline candidates from `infra/deploy.sh` and `infra/workflows/recs_pipeline.yaml`
- likely jobs/services: `recs-export`, `recs-clip`, `recs-svd`, `recs-knn`, `recs-rrf`, `recs-verify`, `seolleyeon-avatar-worker`

SG-4 must keep source project access read-only and redeploy with staging-safe environment variables and buckets.

## Staging bucket names

- `seolleyeon-final-private-source-photos`
- `seolleyeon-final-chat-profile-photos`
- `seolleyeon-final-approved-avatars`
- `seolleyeon-final-avatar-temp`
- `seolleyeon-final-firestore-migration`

Production bucket names must not be hardcoded into staging deployments.

## SG-0 handoff

```json
{
  "subagent": "SG-0",
  "status": "complete",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "project_guard": "pass_after_gcloud_and_adc_alignment",
  "blocked_by_env": [],
  "blocked_by_permission": [],
  "remaining_risks": [
    "Client Firebase config files still point to seolleyeon until SG-3 regenerates staging configs.",
    "infra/deploy.sh must be invoked with GCP_PROJECT=seolleyeon-final or patched before Cloud Run migration."
  ]
}
```
