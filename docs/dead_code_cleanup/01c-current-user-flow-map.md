# Current user-flow map

This map reconciles the supplied screen workflow with the current route and service architecture. It is a protection map, not a claim that every backend branch has been manually exercised.

## Authentication and onboarding

```text
welcome
  -> signup/login choice
  -> terms
  -> Kakao / phone / student-email verification
  -> Firebase Auth session
  -> basic info
  -> height and ideal-height range
  -> interests and keywords
  -> lifestyle / department / major
  -> ideal type
  -> profile Q&A / self introduction
  -> photo upload
  -> tutorial
```

Primary UI entry points are `lib/screens/auth/**`, `lib/router/app_router.dart`, and `lib/features/onboarding/**`. Persistence and recovery also cross `lib/services/**`, repositories/providers, Firebase Storage, Firestore rules, and Functions exports. A screen-only map is insufficient because partial saves, email links, and recovery are external or data-driven.

## Recommendation and chat

```text
tutorial
  -> today's match / profile discovery
  -> AI taste training
  -> profile detail
  -> Like / Pass
  -> mutual match
  -> chat list
  -> 1:1 or group chat
```

Protected UI paths include matching, chat, profile, and tutorial paths listed in `01-workflow-protected-paths.md`. Mutual-like triggers, notifications, block/report, and chat deletion remain protected even when the workflow only shows a card or screen.

## Event flows

```text
event home
  -> season meeting team setup / invite response
  -> 3:3 season matching / team chat / promise
  -> season roulette and result

event home
  -> 3:3 blind taste meeting intro
  -> eligibility
  -> application / waiting
  -> matching
  -> meeting room / safety stamp
  -> result / follow-up
```

The two `3:3` products are separate. The historical random-meeting label maps to the current blind taste meeting only for compatibility/history purposes; it must not be used to remove season-meeting code. Safety-stamp, deep-link, notification, Cloud Tasks, and Scheduler paths are protected.

## Community and profile

```text
bottom navigation
  -> community
  -> post list / detail / write
  -> comments, reports, blocks, notifications

bottom navigation
  -> my page
  -> profile edit / friends / received hearts / heart charge
  -> settings / account management / deletion
```

Community/profile flows have data and moderation paths outside the draw.io export. Their rules, indexes, notifications, and deletion cleanup remain in scope.

## Diagram path reconciliation

| Diagram label | Current route/file conclusion |
|---|---|
| `random_mathcing_screen.dart` | Current active typo-named file; router import and contract test protect it |
| `random_matching_screen.dart` | Stale/absent; no current file to delete |
| `random_meeting_screen.dart` | Historical implementation removed as part of blind-meeting replacement; legacy route alias remains |
| `meeting_application_screen.dart` | Historical implementation removed as part of blind-meeting replacement; legacy route alias remains |
| `ai_preference.dart` | Stale label; current file is `ai_preference_screen.dart` |
| tutorial labels without `lib/` | Same current files after path normalization |

## Entry-point categories that require separate tracing

- route registration and redirects: `lib/router/route_names.dart`, `lib/router/app_router.dart`;
- deep links and email links: splash/auth handlers and meeting icebreaker deep-link handler;
- background push: `lib/main.dart`, `lib/services/push_notification_service.dart`;
- backend exports/triggers: `functions/src/index.ts` and feature directories;
- rules/indexes: `firestore.rules`, `storage.rules`, `firestore.indexes.json`;
- native/web registration: `android/**`, `ios/**`, `web/**`, assets, and build/deploy files.
