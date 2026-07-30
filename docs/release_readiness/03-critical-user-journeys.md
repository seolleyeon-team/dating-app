# 03 — Critical User Journeys

작성: 2026-07-31

## Contract tests

`test/critical_user_journey_contract_test.dart` guards presence of auth, onboarding, recommendation, chat, report/block, deletion, push, season meeting paths.

## Existing focused tests (non-exhaustive)

| Area | Tests |
|------|-------|
| Auth / bootstrap | kakao_login_firestore_bootstrap_test, auth_service_diagnostics_test, terms_screen_test_account_gate_test |
| Avatar / photos | photo_upload_screen_avatar_flow_test, avatar_* tests |
| Security | security_users_list_and_rec_fallback_test, hardening_guards_test |
| Push | push_notification_service_test |
| Rec events | rec_event_contract_test + rules_tests/firestore.recevents.test.mjs |
| Functions deletion | accountDeletionSocialCleanup.test.ts |

## Remaining E2E gap

Full emulator multi-step UI journey (signup→delete) is still PARTIAL. Prefer expanding emulator integration rather than brittle golden-only flows.
