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
| `AiRecommendationService` users scan | `/users` list fallback | REPLACE | removed; empty feed when no `modelRecs` |
| `AiPreferenceScreen` random gender pool | unknown gender → mixed pool | REPLACE | return null / empty cards |
| `AiPreferenceScreen` placehold.co | Storage miss → fake image success | REPLACE | nullable URL; no placeholder cards |
| `AuthProvider` local `isStudentVerified` | missing Firestore doc → trust prefs | REPLACE | force false + clear local flag |
| `AdultVerificationService.isTemporarilyDisabled` | always-true bypass | REPLACE | local WIP: release fail-closed (`!kReleaseMode`); commit with adult-verification feature |
| `firestore.rules` `users` list | signed-in collection list | REPLACE | `allow list: if false` |
| `terms_screen` test-account button | release skip of Kakao/Yonsei | KEEP_WITH_JUSTIFICATION | already gated by `DevEntryPolicy` on branch |
| `premium_chat_list_screen` fake room inject | error/empty → invent fake room | KEEP_WITH_JUSTIFICATION | already gated by `DevEntryPolicy` on branch |
| `ApiService` placeholder | `api.example.com` client | REPLACE | throw in `kReleaseMode` |
| Kakao scheme empty catches | silent swallow | REPLACE | `logCaughtError` |
| `functions/src/index.ts` bare `onCall` | App Check regression | REPLACE | all public callables re-wrapped with `withAppCheck` |
| Heart charge/recharge package tap | TODO / silent no-op | REPLACE | `InAppPurchasePolicy` + unavailable dialog |

Production mock admin / release test UID bypass: **not present** (release gated).

**Note:** Release builds now require real adult (PortOne) verification. If PortOne is not ready for prod, treat as external ops blocker before store ship. Firebase Console App Check **Enforce** remains external.
