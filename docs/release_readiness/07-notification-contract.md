# 07 — Notification / Deep-link Contract

작성: 2026-07-31

## Coordinator

`lib/services/push_notification_service.dart` — singleton `PushNotificationService`.

## Hardening in this branch

| Control | Status |
|---------|--------|
| Initialize idempotency (`_initialized` / `_initializing`) | Implemented |
| Open/tap deep-link dedupe (`buildOpenDedupeKey` + `claimOpenHandling`) | Implemented |
| Foreground suppress for open chat room | Existing |
| User notificationSettings category filter | Existing |
| PII-safe diagnostics | Existing + tests |
| Server push recipient filter (block/deleted) | `functions/src/pushRecipientPolicy.ts` |

## Inventory (minimum)

| type | deep link | category |
|------|-----------|----------|
| chat / chat_digest | main tab chat | chat |
| community_comment / reply | post detail | community |
| profile_like / community_post_like | received hearts | matching/community |
| ask_received | asks inbox | asks |
| event_team_invite | invite response | events |
| safety_stamp_follow_up | safety follow-up | safety |

## Tests

- `test/push_notification_service_test.dart`
- `functions/src/pushRecipientPolicy.test.ts` (existing)
