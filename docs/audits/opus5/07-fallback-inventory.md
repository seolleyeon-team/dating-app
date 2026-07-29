# 07 — Fallback Inventory (Grok 45 refresh)

작성: 2026-07-30

| Location | Pattern | Classification | Action |
|----------|---------|----------------|--------|
| `terms_screen` fake_user_1 | test account | MOVE_TO_DEV_ONLY | `DevEntryPolicy.allowTestAccountEntry` (kDebugMode) — KEEP_WITH_JUSTIFICATION |
| `premium_chat_list_screen` fake_user_1 | fake room | MOVE_TO_DEV_ONLY | gated by DevEntryPolicy |
| `main.dart` App Check catch | failure | REPLACE | now records `AppCheckInitResult` (not silent success) |
| `kakao_auth_screen` scheme catch | empty catch | REPLACE | logs PrivacyLogUtils summary |
| `kakao_callback_screen` scheme catch | empty catch | REPLACE | logs summary |
| `chat_service.getUserProfileDoc` | catch → null | KEEP_WITH_JUSTIFICATION | soft-fail read; now logged |
| `push_notification_service` Firebase not init | catch | KEEP_WITH_JUSTIFICATION | logged skip |
| Cupertino `placeholder:` UI strings | placeholder | NOT_APPLICABLE | UI hint text |
| `core/network/interceptors.dart` TODO token | TODO | KEEP_WITH_JUSTIFICATION | unused/legacy HTTP path; track separately |
| Recommendation empty candidate | empty list | KEEP_WITH_JUSTIFICATION | must NOT restore blocked users |

Production mock admin / release test UID bypass: **not present** (release gated).
