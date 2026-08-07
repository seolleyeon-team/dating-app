# Non-workflow runtime protection matrix

This is the feature-level manifest required before any deletion candidate can be marked safe. It includes behavior that may be reachable only through backend state, notifications, native registration, operational tools, or recovery procedures.

| Feature | Entry point | Route / trigger / data surface | Tests or evidence | Decision |
|---|---|---|---|---|
| Authentication and Kakao/Firebase session | `lib/services/auth_service.dart`, `lib/providers/auth_provider.dart`, `functions/src/index.ts` | Auth state listener, custom token callable, Kakao access-token verification, email-link continue URL | Auth service tests, router/session diagnostics | KEEP_RUNTIME_FEATURE |
| Student email verification | `lib/screens/auth/student_verification_screen.dart`, `lib/features/auth/**` | App Links initial/stream URI, Firebase email action, student verification completion | Auth/email-link tests and Firebase Auth config | KEEP_DEEP_LINK |
| Onboarding partial-save recovery | `lib/features/onboarding/**`, onboarding services/repositories | Firestore field names and Storage upload state; recovery after interruption | Existing onboarding and persistence tests | KEEP_RUNTIME_REFERENCED |
| AI avatar generation | `lib/services/avatar_generation_client.dart`, `lib/ai_recommend_model/avatar_generation/**`, `functions/src/avatar*.ts` | Storage source/derived media, job lease, approval/retry/status, retention/cleanup | `functions` avatar and Python test suites | KEEP_OPERATIONAL |
| Public profile projection | profile services and `onUserPublicProfileSync` | Firestore trigger and public/private projection fields | Functions trigger tests and rules | KEEP_FIREBASE_BACKEND |
| Recommendation and interaction events | matching services, recommendation model, Functions triggers | Interaction strings, feature flags, recommendation repair | Matching/recommendation tests | KEEP_RUNTIME_REFERENCED |
| Like/pass/mutual match | matching screens/services, notification handlers | Firestore event and push notification type | Matching and notification tests | KEEP_DYNAMIC_ENTRY |
| Chat and group chat | `lib/features/chat/**`, chat service/repositories | Notification tap, chat document listeners, deletion/block rules | Chat tests and rules tests | KEEP_DYNAMIC_ENTRY |
| Report/block and moderation | profile/community actions, rules, contact-block sync | Contact synchronization and moderation repair | Rules and Functions tests | KEEP_SECURITY |
| Account deletion | account-management screen/services and cleanup exports | Auth deletion, Firestore/Storage cleanup, public projection removal | Deletion/cleanup tests | KEEP_OPERATIONAL |
| Blind taste meeting | `lib/features/blind_meeting/**`, `functions/src/blindMeeting/**` | Eligibility/application/matching/schedule/result/follow-up and legacy aliases | Blind-meeting tests and rules tests | KEEP_WORKFLOW_CORE |
| Blind-meeting eligibility | blind-meeting policy/domain/data and Functions | Server fail-closed eligibility, verified/student/adult/profile conditions | Eligibility tests | KEEP_SECURITY |
| Safety stamp | blind-meeting result/follow-up, chat safety-stamp screens, Functions hook | Result state, completion state, notification and deep link | Safety-stamp tests | KEEP_SECURITY |
| Season meeting | event/meeting screens, season Functions | Deposit, cancel, no-show, replacement, refund, team/invite, season chat | Season and rules tests | KEEP_WORKFLOW_CORE |
| Meeting icebreaker | `lib/features/event/meeting_icebreaker/**`, `functions/src/meetingIcebreaker/**` | Callable, Firestore sync, push, Cloud Tasks, Scheduler, deep link | Icebreaker tests and rules tests | KEEP_DYNAMIC_ENTRY |
| Roulette | roulette screen/domain and `spinSeasonMeetingRoulette` | Deterministic/pre-decided result, notification/deep link, reconciliation | Roulette/meeting tests | KEEP_RUNTIME_FEATURE |
| Bomb pass | bomb timer/controller/screen/illustration/audio | Timer lifecycle, audio assets, result sheet | Widget/domain tests and asset registration | KEEP_RUNTIME_FEATURE |
| Quiet notifications | push service and meeting-icebreaker notification helpers | Quiet channel, idempotency, suppression, schedule version, opt-out | Notification tests | KEEP_DYNAMIC_ENTRY |
| Push/background handling | `lib/main.dart`, `lib/services/push_notification_service.dart` | FCM background entry point, APNs/Android channel, tap callback | App startup and notification code | KEEP_NATIVE_OR_PLATFORM |
| Deep links | splash/auth handlers, router aliases, meeting handler | Initial link, stream link, terminated-state replay | AppLinks code and route tests | KEEP_COMPATIBILITY |
| Firestore/Storage rules and indexes | `firestore.rules`, `storage.rules`, `firestore.indexes.json` | Deployed configuration and emulator test target | 174 rules tests passed | KEEP_SECURITY |
| Functions, Tasks, Schedulers | `functions/src/index.ts`, `functions/src/**`, `infra/**` | Exports, triggers, task queues, Scheduler/Workflows | 351 Functions tests passed | KEEP_FIREBASE_BACKEND |
| Repair, migration, backfill | Functions repair files and scripts/tools | Admin-only recovery and data repair | Operational references require owner audit | KEEP_MIGRATION_OR_ROLLBACK |
| Native/web/CI/release | Android/iOS/web manifests, `.github`, scripts/tools | MethodChannel, URL scheme, entitlements, service worker, build/deploy | APK/web gates passed | KEEP_NATIVE_OR_PLATFORM |

Until the entry point, trigger, data surface, test, and owner are all verified, no row may be reclassified as `SAFE_TO_REMOVE_CONFIRMED`.
