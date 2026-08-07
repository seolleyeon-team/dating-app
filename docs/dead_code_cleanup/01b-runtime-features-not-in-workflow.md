# Runtime features not fully represented in the workflow export

The draw.io graph describes user-visible screens, but it cannot prove the absence of backend, notification, native, repair, or safety behavior. The following manifest is therefore protected independently of graph coverage.

| Feature | Entry points / protected areas | Dynamic or external surface | Why it is protected |
|---|---|---|---|
| AUTHENTICATION | `lib/main.dart`, `lib/providers/auth_provider.dart`, `lib/services/auth_service.dart`, `lib/router/app_router.dart`, `functions/src/index.ts` | Firebase Auth state, Kakao token exchange, custom-token callable, email-link continuation | Login can work through callbacks and URLs without a screen import |
| SCHOOL_VERIFICATION | `lib/screens/auth/student_verification_screen.dart`, `lib/features/auth/screens/student_verification_screen.dart`, related auth services | App Links, email-link callback, student verification callable | Deep-link and email completion are external entry points |
| ONBOARDING | `lib/features/onboarding/**`, onboarding repositories/services, onboarding write allowlist | Firestore field names, partial-save/recovery paths, Storage upload | A field can be written or recovered by a service rather than the visible screen |
| PROFILE / PUBLIC PROFILE SYNC | `lib/features/profile/**`, `lib/services/**`, `functions/src/index.ts` | `onUserPublicProfileSync`, profile projection, account deletion | Public projections and deletion repair are trigger-driven |
| AI_AVATAR | `lib/services/avatar_*.dart`, `lib/ai_recommend_model/avatar_generation/**`, `functions/src/avatar*.ts`, `functions/src/index.ts` | Storage, worker jobs, approval/retry/status callables, retention/cleanup | Generation is a pipeline with workers and operational recovery, not a route-only feature |
| RECOMMENDATION / MATCHING | `lib/features/matching/**`, recommendation models/services, `functions/src/**` | Interaction events, recommendation repair, feature flags | Static import counts miss event-triggered and flag-gated paths |
| LIKES / MATCHES | matching screens, repositories, notification services, `functions/src/**` | Firestore writes, mutual-like triggers, notification payloads | Notifications and triggers can reference types/strings |
| ONE_TO_ONE_CHAT | `lib/features/chat/**`, chat repositories/services, `functions/src/**` | Firestore chat documents, push payloads, account deletion/block rules | Chat routes can be opened by notification/deep link |
| GROUP_CHAT / SEASON_CHAT | `lib/features/chat/screens/group_match_screen.dart`, event/team/meeting services | Team membership, meeting state, promise reminders | Group membership and tasks are backend-driven |
| REPORT / BLOCK | report/block screens, services, rules, `functions/src/contactBlockSync.ts` or equivalent exports | Contact sync, security rules, moderation repair | Safety functions may have no direct workflow node |
| COMMUNITY | `lib/features/community/**`, bamboo/tutorial paths, Functions and rules | Posts, comments, moderation, notifications | Community actions and safety reports are data-driven |
| ACCOUNT_DELETION | account-management screens/services, Functions cleanup exports | Storage cleanup, auth deletion, public-profile deletion | Deletion is an operational contract, not a leaf UI |
| BLIND_TASTE_MEETING_3X3 | `lib/features/blind_meeting/**`, `functions/src/blindMeeting/**`, rules/tests | Eligibility, application, matching, schedule, result, follow-up, deep links | The old random-meeting label was replaced; current feature must remain |
| BLIND_MEETING_ELIGIBILITY | blind-meeting policy/domain/data and callable functions | Server-side fail-closed checks, verified student/adult/profile fields | Client-only or import-only analysis cannot prove eligibility safety |
| BLIND_MEETING_SAFETY_STAMP | `lib/features/blind_meeting/**`, `lib/features/chat/screens/safety_stamp_*.dart`, Functions hooks | Safety stamp completion, follow-up, result and notification state | Safety lifecycle can be entered from a result/deep link |
| SEASON_MEETING_3X3 | `lib/features/event/**`, `lib/features/meeting/**`, season Functions and rules | Deposit/cancel/no-show/refund, team setup/invites, scheduled jobs | Must stay separate from blind taste meeting |
| SEASON_TEAM_AND_INVITES | event/team screens and Functions team callables/triggers | Invite response, replacement, team membership | Invites are opened from notification/deep link |
| SEASON_CHAT_AND_PROMISE | chat/event services, `functions/src/meetingIcebreaker/**` | Promise reminders, Cloud Tasks, scheduled jobs | Reminder and task targets are not necessarily imports |
| MEETING_ICEBREAKER | `lib/features/event/meeting_icebreaker/**`, `functions/src/meetingIcebreaker/**`, tests | Callable, Firestore sync, push, Cloud Tasks, Scheduler | Explicitly protected by the master prompt |
| MEETING_ROULETTE | roulette UI/domain, `spinSeasonMeetingRoulette`, notification/deep links | Pre-decided result, state reconciliation, feature flag | UI can be entered only after an event state transition |
| BOMB_PASS_GAME | bomb-pass timer/controller/screen/illustration/audio service and assets | Timers, lifecycle, audio, result sheet | Assets and controller are dynamic consumers |
| QUIET_PROMPT_NOTIFICATIONS | push notification service and meeting-icebreaker notification helpers | Quiet channel, idempotency, suppression, schedule version | Repeated notification behavior is an operational contract |
| PUSH / BACKGROUND_HANDLERS | `lib/main.dart`, `lib/services/push_notification_service.dart` | `FirebaseMessaging.onBackgroundMessage`, FCM/APNs, notification tap | `@pragma('vm:entry-point')` code may have no normal import |
| DEEP_LINKS | splash/auth screens, `app_links`, router aliases, meeting handler | `getInitialLink`, `uriLinkStream`, email-link continuation | Browser/mobile and terminated-state entry are external |
| FEATURE_FLAGS | feature flag services/configuration and route guards | Remote/config string keys and rollout state | Disabled code may still be required for a rollout or rollback |
| FIRESTORE_RULES / STORAGE_RULES / INDEXES | `firestore.rules`, `storage.rules`, `firestore.indexes.json`, rule tests | Emulator/deployed rules and query indexes | Rules are deployed configuration and must not be removed as unused |
| FUNCTIONS / CLOUD_TASKS / SCHEDULERS | `functions/src/index.ts`, `functions/src/**`, `infra/**` | Callable/export names, task queues, Scheduler/Workflows | Backend entry points do not appear in Dart imports |
| REPAIR / MIGRATION / BACKFILL | `functions/src/*Repair*`, `*Migration*`, `*Backfill*`, operational scripts | Admin jobs, recovery commands, incident runbooks | These are intentionally dormant until data repair is needed |
| CI / RELEASE / NATIVE | `.github/**`, `android/**`, `ios/**`, `web/**`, `scripts/**`, `tools/**` | Manifest, entitlements, MethodChannel, service worker, build/deploy | Platform registration and build tooling are not dead because import search misses them |

Every row is `KEEP_*` or `KEEP_UNCERTAIN` for cleanup purposes until the corresponding dynamic, native, Firebase, asset, test, and operational references are audited.
