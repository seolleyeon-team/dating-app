# 03 — 기준선 검증 결과 (Fable 5 감사, 2026-08-28)

working tree = 미커밋 아바타 WIP 포함 현재 상태. Flutter SDK 3.41.2, Node 22, Python 3.11(.venv).

| # | 명령 | 위치 | 결과 | 상태 | 비고 |
|---|---|---|---|---|---|
| 1 | `flutter analyze` | repo | No issues found (305s) | PASS | |
| 2 | `flutter test` | repo | 656 passed | PASS | |
| 3 | `npm test` (node --test) | functions | 431 passed / 0 fail (46 suites) | PASS | |
| 4 | `npm run lint` (tsc --noEmit) | functions | 통과 | PASS | eslint 아님, 타입체크만 |
| 5 | `npm run build` (tsc) | functions | 통과 | PASS | |
| 6 | `pytest recsys/tests` | .venv-recsys-tests | 181 passed (115s) | PASS | |
| 7 | `pytest tests/` | .venv | **921 passed / 16 failed** (353s) | FAIL | 실패 전부 미커밋 아바타 WIP 영역 |
| 8 | rules emulator (`firestore*.test.mjs` + `storage*`) | rules_tests | 72 passed | PASS | JDK 25 필요(기본 JDK17은 BLOCKED) |
| 9 | `flutter build apk` | repo | 미실행 | NOT_RUN | 최종 검증에서 실행 예정 |
| 10 | iOS build | — | BLOCKED | BLOCKED | Windows 환경 |
| 11 | festival_web rules emulator | — | NONE | NOT_CONFIGURED | 축제 프로젝트 rules 테스트 없음 |

## #7 실패 16건 — 미커밋 WIP에서 발생 (기존 실패 아님, WIP 델타가 원인)

- `tests/test_avatar_qa_cleanup.py` (5건) + `tests/test_avatar_queue_ops.py` (5건): `build_report() missing 1 required keyword-only argument: 'artifact_registry_location'` — 시그니처가 바뀌었는데 호출부/테스트 중 한쪽만 갱신됨.
- `tests/test_clip_job_handler.py` (2건): `ValueError: source photo bucket is not allowed: seolleyeon-private-source-photos` — `seolleyeon_clip_job_handler.py:157` 버킷 allowlist에 private-source 버킷 누락. WIP 진행 중 미완 상태.
- 그 외 `test_avatar_qa_cleanup` 4건 동일 계열.

이는 사용자의 진행 중 작업(WIP)이며, 본 감사는 이 WIP를 임의로 완성/되돌리지 않는다. 감사 결과에 **"작업 트리에 RED 테스트 존재 — 커밋/배포 차단 상태"**로 기록한다.

## 도구 부재 (NOT_CONFIGURED)

- semgrep / bandit / pip-audit / trivy / gitleaks(로컬): 로컬 미설치. gitleaks는 CI에서만 실행됨.
- 기본 Python 인터프리터에 pytest 없음 → 프로젝트 venv 사용.
