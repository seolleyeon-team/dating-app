# 02 — Phase 0 Baseline

작성: 2026-07-31  
브랜치: `release/grok45-integrated-readiness`  
HEAD at baseline start: `733a7764`

## Toolchain

| Tool | Version |
|------|---------|
| Flutter | 3.41.2 (stable) |
| Dart | 3.11.0 |
| Node | v24.14.0 (local) / CI 22 |
| npm | 11.10.1 |
| Python | 3.13.3 |

## Command results

| Command | Working directory | Start | End | Exit | Result | Notes |
|---------|-------------------|-------|-----|------|--------|-------|
| `dart format --output=none --set-exit-if-changed lib test` | repo root | 2026-07-31 | 2026-07-31 | 0 | PASS | 315 files, 0 changed |
| `flutter analyze --no-fatal-infos --no-fatal-warnings` | repo root | 04:47:36 | 04:56:33 | 0 | PASS | 20 info/warning issues (pre-existing) |
| `flutter test` | repo root | 2026-07-31 | 2026-07-31 | 0 | PASS | 115 tests |
| `npm run lint` | functions | 2026-07-31 | 2026-07-31 | 0 | PASS | tsc --noEmit |
| `npm test` | functions | 2026-07-31 | 2026-07-31 | 0 | PASS | 181 tests |
| `pytest recsys/tests` | repo root | — | — | — | NOT_CONFIGURED | directory missing at baseline — to be created |
| `pytest tests/test_avatar_exact_replay_auth.py` | repo root | 2026-07-31 | 2026-07-31 | 1 | BLOCKED | local python lacked pytest initially; installed afterward |
| `firebase emulators:exec` (rules) | — | — | — | — | NOT_RUN_YET | CI job exists; local run pending |
| `flutter build apk --debug` | — | — | — | — | NOT_RUN_YET | scheduled later |
| `flutter build web` | — | — | — | — | NOT_RUN_YET | scheduled later |

## Existing failures (pre-change)

- Analyzer reports 20 non-fatal infos/warnings (unused fields, deprecated APIs, BuildContext async in community).
- No recsys offline-eval test suite at baseline.
- Local default Python needed `pip install pytest` before avatar pytest could run.

## Environment blockers

- Production deploy/enforce/App Check Firestore+Auth: external only.
- `omx state` CLI not reliably available in this shell PATH for Python subprocess; ultrawork proceeds without OMX state persistence.
- Broken symlink noise under `.tmp/pytest-full-*` can break recursive `rg`/glob; searches scoped accordingly.

## Protected scope baseline

See `21-protected-blind-meeting-scope.md`.

Exclusive protected file unchanged at baseline:

```text
lib/features/event/screens/random_mathcing_screen.dart
SHA256=94BA62403DB676CF495727F59BCC4B46A6F5620120770879ED3A0CB98E98849C
```
