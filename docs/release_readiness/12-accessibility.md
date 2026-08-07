# 12 — Accessibility

작성: 2026-07-31

## Status

PARTIAL → improved in this branch for high-traffic controls.

## Implemented

- Bottom nav: Semantics button/selected + 44px minimum target
- Kakao auth: primary CTA + back button semantics
- Chat composer: attach + send semantics and 44px targets
- Tests: 	est/accessibility_semantics_test.dart

## Remaining

- Text scale 1.3 / 1.6 smoke across onboarding/profile
- Reduce-motion for season roulette only (not blind SlotMachineScreen)
- Broader semantics pass on report/block/delete flows

Protected blind UI excluded from a11y edits.
