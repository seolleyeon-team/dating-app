# Reference graph and runtime entry points

## Graph layers

```text
workflow labels and edges
        |
        v
routes / redirects / deep links ---- notification payloads
        |                              |
        v                              v
Flutter screens/widgets ---- services/providers/repositories
        |                              |
        v                              v
assets/native registration       Firebase callable/trigger exports
                                       |
                                       v
                             Firestore/Storage/rules/indexes
                                       |
                                       v
                         Cloud Tasks / Scheduler / repair jobs
```

The workflow export covers the first layer and part of the route layer. The other layers are protected because their references are often string-based, generated, platform-registered, or externally invoked.

## Confirmed central hubs

| Hub | Evidence in current tree | Dependents that make deletion unsafe |
|---|---|---|
| `lib/main.dart` | Firebase initialization, App Check setup, push background registration, app bootstrap | Auth, notifications, deep links, all routes |
| `lib/router/app_router.dart` | Current route imports, legacy aliases, `random_mathcing_screen.dart`, `ai_preference_screen.dart` | Every screen reachable by route or notification |
| `lib/router/route_names.dart` | Current and compatibility route names | Deep links, notification taps, old URLs |
| `lib/services/push_notification_service.dart` | Background/foreground handling, quiet channels and meeting notifications | FCM/APNs payloads, terminated-state entry, platform channels |
| `functions/src/index.ts` | Callable and trigger exports, including avatar, blind meeting, meeting icebreaker, auth, repair, and scheduled functions | Deployed Firebase names, Cloud Tasks, Scheduler, triggers |
| `firestore.rules` / `storage.rules` / `firestore.indexes.json` | Security and query deployment configuration | Client reads/writes, emulator tests, deployed rules/indexes |
| `functions/src/meetingIcebreaker/**` | Prompt scheduling, quiet/idempotent notification, reconciliation | Tasks, Scheduler, push, promise sync, deep links |
| `lib/features/event/meeting_icebreaker/**` | Roulette, bomb pass, audio, deep-link and UI flow | Event state transitions, assets, notifications |
| `lib/features/blind_meeting/**` and `functions/src/blindMeeting/**` | Eligibility, application, matching, safety stamp, result/follow-up | 3:3 blind taste meeting and compatibility routes |
| `infra/**`, `.github/**`, `scripts/**`, `tools/**` | Deployment, pipeline, build, migration, operational helpers | Release and incident recovery |

## Firebase/operational exports protected by name

`functions/src/index.ts` exports or re-exports authentication/custom-token, avatar upload/status/approval/retry/cleanup, public-profile sync, blind-meeting, season meeting, team/invite, meeting icebreaker, notification, recommendation/interaction, chat/bamboo/ask/match, safety-stamp, promise reminder, scheduled digest, contact block, and repair/state-sync surfaces.

Representative dynamic names include `createFirebaseCustomToken`, `uploadAvatarSourcePhoto`, `getCurrentAvatarGenerationStatus`, `retryCurrentAvatarGeneration`, `approveAvatarCandidate`, `getChatRealProfilePhoto`, `cleanupAvatarMedia`, `spinSeasonMeetingRoulette`, `dispatchMeetingIcebreakerPrompt`, `meetingIcebreakerReconcileTick`, `syncMeetingIcebreakerFromPromise`, scheduled upcoming/daily digests, and safety-stamp completion hooks. These names are evidence of deployed contracts, not deletion candidates.

## Native/web and asset surfaces

- Android: manifest activities/services/receivers, notification channels, Gradle source sets, ProGuard/keep configuration, Google service registration.
- iOS: Info.plist, AppDelegate/SceneDelegate, URL schemes/associated domains, entitlements, notification/background modes, privacy manifest, Pods.
- Web: `web/index.html`, Firebase bootstrap, service worker, App Check, JS interop, renderer assets, email-link continuation URL.
- Assets: `pubspec.yaml` declarations, audio for bomb pass, icons/splash/store compliance, fonts, generated resources, and dynamic asset path construction.

## Static reference status

The audit confirmed the current router imports and critical user-journey contract for the typo-named random-matching file, and confirmed the historical deletion/replacement commit for the three stale event/meeting paths. A full per-candidate static/string/native/Firebase/asset/test reference graph has not been completed because candidate authorization is not yet granted; the CSV therefore uses conservative `not-proven-dead` statuses.

## Evidence commands used

```text
rg --files lib functions/src test tests rules_tests android ios web assets scripts tools infra
rg -n "random_mathcing|random_matching|random_meeting|meeting_application|ai_preference" lib test functions
git log --all --follow -- <candidate>
git grep <route-or-function-name> -- :!build :!.dart_tool :!node_modules
flutter analyze / flutter test / web and APK builds / Functions and rules tests
```

Deletion requires these surfaces to be checked for every file, not just the import graph.



## Phase 2 impact check

Batch 001 contains only ten local pytest *current pointer files. The post-removal reference check found no changed route, Firebase export, native registration, asset declaration, workflow label, test fixture contract, or operational path. The pytest_tmp_avatar_qa_escalated analyzer/editor directory exclusions remain harmless when the exact pointer files are absent. The remaining 35 generated image/report files stay outside the deletion diff.
> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** See [the current avatar architecture](../avatar-production/CURRENT_ARCHITECTURE.md).
>
