# User-flow defects found during cleanup audit

These entries are based on repository evidence and the baseline gates. They do not replace manual web/mobile or deployed-environment validation.

| ID | Flow | Problem investigated | Severity | Status | Root-cause/evidence | Fix |
|---|---|---|---|---|---|---|
| FLOW-001 | Diagram-to-event flow | Diagram names `random_matching_screen.dart`, `random_meeting_screen.dart`, and `meeting_application_screen.dart` do not match current files/routes | Low documentation drift | FALSE_POSITIVE / NOT_REPRODUCED | Current router uses `random_mathcing_screen.dart`; commit `2cd46c1c` intentionally replaced the old random-meeting/application screens with blind-meeting flow and retained compatibility aliases | No code fix; workflow mapping documented |
| FLOW-002 | AI preference path | Diagram uses `ai_preference.dart` while current implementation is `_screen.dart` | Low documentation drift | FALSE_POSITIVE / NOT_REPRODUCED | `lib/router/app_router.dart` and tests reference `ai_preference_screen.dart` | No code fix; rename mapping documented |
| FLOW-003 | Web release build | Tree-shaken font/IconData and Wasm dry-run messages appeared in verbose build output | Informational | NOT_REPRODUCED | `flutter build web --release` completed successfully; messages were warnings, not runtime failures | No code fix |
| FLOW-004 | External runtime journeys | Physical-device, deployed Functions, and production/staging manual journeys were not run in this cleanup session | Validation gap | CONFIRMED_DEFERRED | Requires external credentials/devices/deployed state not available in the repository audit | Run separately before production deletion/merge |

No new crash, navigation loop, data-loss, eligibility, safety-stamp, notification, or backend regression was reproduced by the baseline checks. The onboarding and eligibility changes visible in the worktree predate this cleanup audit and are not attributed to this audit.
