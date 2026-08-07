# SEOLLEYEON Phase 6P-7C ignored-content audit

Status: `IGNORED_CONTENT_CLASSIFIED_22357`

## Scope and method

- Source worktree: `C:/Users/samsung/StudioProjects/semisemifinal-phase6p7b-quarantine-20260807-144545/.codex-worktrees/dead-code-cleanup-20260804`
- Enumeration: Git ignored/untracked paths plus filesystem metadata.
- Raw file contents, photo contents, EXIF, secret values, and credential values were not recorded.
- Classification is group-based by generated/cache/dependency/runtime-log/reparse ownership; no unknown group is accepted.
- The private calibration-photo preservation and Phase 6 document preservation are separate gates documented in `114a` and `114b`.

## Audit totals

- Ignored path count: `22,357`
- Physical record count: `22,357`
- Regular-file count: `22,346`
- Reparse/link count: `11`
- Missing physical records: `0`
- Unknown classification group: `0`
- Total regular-file bytes: `3,367,963,255`
- High-risk path-pattern matches (`.env`, key/keystore/certificate extensions, `local_secrets`, calibration-photo paths, service-account names): `0`

The high-risk result is a path/metadata gate only; no secret value is reproduced in this report. The ignored worktree contains no `.local_secrets` or calibration-photo path. The 11 unique calibration photos are handled only by the private, byte-exact preservation recorded in `114a`.

## Disposition rule

Every row below is classified as generated, cached, dependency-derived, runtime-log, generated reparse link, or an exact duplicate of the active local configuration. Therefore all `22,357` ignored records are eligible for removal with the quarantine root; none is designated unique user-created data or a secret-preservation exception. Active counterparts, where present, remain in the active repository and are not modified by this audit.

| Group | Items | Regular files | Bytes | Reparse | Classification | Active counterpart basis | Disposition | Gate |
|---|---:|---:|---:|---:|---|---|---|---|
| `.dart_tool` | 122 | 122 | 272262003 | 0 | GENERATED_REPRODUCIBLE | generated state; no preservation required | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `.flutter-plugins-dependencies` | 1 | 1 | 30810 | 0 | GENERATED_REPRODUCIBLE | generated Flutter metadata | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `.pytest_cache` | 4 | 4 | 3357 | 0 | CACHE_REPRODUCIBLE | test cache; no preservation required | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\.gradle` | 14 | 14 | 11663623 | 0 | GENERATED_BUILD_CACHE | 14/14 present; 3/14 SHA-equal; remaining generated differences | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\app` | 1 | 1 | 7086 | 0 | GENERATED_REPRODUCIBLE | 1/1 present; 1/1 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\gradle` | 1 | 1 | 53636 | 0 | GENERATED_REPRODUCIBLE | 1/1 present; 1/1 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\gradlew` | 1 | 1 | 4971 | 0 | GENERATED_REPRODUCIBLE | 1/1 present; 1/1 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\gradlew.bat` | 1 | 1 | 2404 | 0 | GENERATED_REPRODUCIBLE | 1/1 present; 1/1 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `android\\local.properties` | 1 | 1 | 152 | 0 | DUPLICATE_OF_ACTIVE_LOCAL_CONFIG | 1/1 present; 1/1 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `build` | 6467 | 6467 | 2832022272 | 0 | GENERATED_BUILD_OUTPUT | generated build/test output | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `firestore-debug.log` | 1 | 1 | 558091 | 0 | GENERATED_RUNTIME_LOG | runtime log; no preservation required | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `flutter_01.log` | 1 | 1 | 5740 | 0 | GENERATED_RUNTIME_LOG | runtime log; no preservation required | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `functions\\lib` | 176 | 176 | 1866285 | 0 | GENERATED_REPRODUCIBLE | 176/176 present; 160/176 SHA-equal; remaining generated differences | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `functions\\node_modules` | 7981 | 7981 | 144286353 | 0 | DEPENDENCY_REPRODUCIBLE | dependency install output | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `ios\\Flutter` | 4 | 4 | 2640 | 0 | GENERATED_REPRODUCIBLE | 4/4 present; 2/4 SHA-equal; remaining generated differences | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `ios\\Runner` | 2 | 2 | 6521 | 0 | GENERATED_REPRODUCIBLE | 2/2 present; 2/2 SHA-equal | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `lib\\ai_recommend_model` | 40 | 40 | 466732 | 0 | CACHE_REPRODUCIBLE | Python bytecode cache; no active copy required | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `linux\\flutter` | 11 | 0 | 0 | 11 | GENERATED_REPARSE_LINKS | generated Flutter plugin links | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `macos\\Flutter` | 2 | 2 | 1111 | 0 | GENERATED_REPRODUCIBLE | 2/2 present; generated differences | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `scripts\\__pycache__` | 1 | 1 | 2825 | 0 | CACHE_REPRODUCIBLE | Python bytecode cache | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `test\\firestore_rules\\firestore-debug.log` | 1 | 1 | 558091 | 0 | GENERATED_RUNTIME_LOG | 1/1 present; generated log differs | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `test\\firestore_rules\\node_modules` | 7523 | 7523 | 104065377 | 0 | DEPENDENCY_REPRODUCIBLE | dependency install output | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |
| `tests\\__pycache__` | 1 | 1 | 93175 | 0 | CACHE_REPRODUCIBLE | Python bytecode cache | REMOVE_WITH_QUARANTINE_RETIREMENT | PASS |

The machine-readable copy of this table is `114c-phase6p7c-ignored-content-audit.csv` in the same directory.

## Active-repository invariant

- No ignored item was copied into or modified in the active repository by this audit.
- The active `.local_secrets` tree was not edited or read for content.
- No remote mutation was performed.
- Quarantine deletion remains pending the final pre-delete lock and hard-gate recheck.
