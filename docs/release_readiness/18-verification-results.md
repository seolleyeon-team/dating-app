# 18 — Verification Results

작성: 2026-07-31

| Command | Directory | Exit | Result | Notes |
|---------|-----------|------|--------|-------|
| dart format --set-exit-if-changed lib test | root | 0 | PASS | |
| flutter analyze --no-fatal-infos --no-fatal-warnings | root | 0 | PASS | 20 infos/warnings |
| flutter test | root | 0 | PASS | 126 tests |
| npm run lint | functions | 0 | PASS | |
| npm test | functions | 0 | PASS | 192 tests |
| pytest recsys/tests | root | 0 | PASS | 4 tests, PYTHONPATH=. |
| Protected blind SHA256 | — | — | UNCHANGED | 94BA6240…8849C |

Not run yet in this session: flutter build apk/web, local firebase emulators:exec, bandit, trivy.

| flutter build apk --debug | root | 0 | PASS | app-debug.apk built after a11y fix |
| flutter build web | root | 0 | PASS | build/web |
| firebase emulators:exec (rules) | root | 1 | BLOCKED | Java not on PATH locally; CI rules job remains source of truth |
| accessibility_semantics_test | root | 0 | PASS | nav/auth semantics |

