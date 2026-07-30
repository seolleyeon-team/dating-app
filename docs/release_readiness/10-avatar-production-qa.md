# 10 — Avatar Production QA

작성: 2026-07-31

## Existing coverage

Functions: `avatarApproval`, `avatarCleanup`, `avatarExactReplay`, `avatarGenerationStateSync`, `avatarMedia`, `avatarSourceRetention` (+ tests).  
Flutter: photo upload avatar flow + multiple avatar_* widget/unit tests.  
Python: large `tests/test_avatar_*` suite.

## Forced-failure matrix (status)

| Case | Coverage |
|------|----------|
| provider timeout / failed status | Flutter poll tests |
| no previewable candidates | Flutter tests |
| multi-face rejection | Flutter tests |
| retention / cleanup | Functions tests |
| exact replay auth | pytest |

## Remaining

Wire stale avatar_pending through scheduled repair apply (currently dry-run plan only).
