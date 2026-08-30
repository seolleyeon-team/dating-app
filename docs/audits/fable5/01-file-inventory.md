# 01 — 파일 인벤토리 (Fable 5 감사, 2026-08-28)

기준: `git ls-files` (총 11,712 tracked 파일), 브랜치 `release/grok45-production-readiness-final`.

이전 감사(docs/audits/opus5, 2026-07-27~30)는 보존한다. 본 감사는 현재 상태 기준 fresh 재검증이다.

## Production 코드

| 영역 | 위치 | 규모 | 비고 |
|---|---|---|---|
| Flutter 앱 | `lib/` (screens, services, features, router, providers 등) | Dart 367개 | entry: `lib/main.dart`, `lib/app.dart` |
| Flutter 테스트 | `test/` | Dart 24개 파일 (82 항목) | |
| Cloud Functions | `functions/src/` | TS 36개(+co-located *.test.ts) | Node 22, entry `functions/src/index.ts` |
| 추천 시스템 | `recsys/` + `lib/ai_recommend_model/` | Python 250개(tests 포함) | CLIP/SVD/KNN/RRF, Cloud Run |
| 아바타 파이프라인 | `lib/ai_recommend_model/avatar_generation/` + `functions/src/avatar*.ts` | 위에 포함 | Cloud Run worker, 미커밋 WIP 존재 |
| Python 테스트 | `tests/`, `recsys/tests/` | 58 + 일부 | |
| 보안 규칙 | `firestore.rules`(1635줄), `storage.rules`(72줄) | | emulator 테스트: `rules_tests/` (7 suite) |
| Hosting | `public/` (13), `web/` (7) | | seolleyeon-final 사이트 |
| 축제 웹 | `festival_web/` | 9,869 파일 — 그중 **9,768개가 커밋된 node_modules** | 별도 Firebase project `seolleyeon-festival` |
| 플랫폼 | `android/`(77) `ios/`(49) `macos/` `windows/` `linux/` | | iOS 검증은 Windows에서 BLOCKED |
| 스크립트/도구 | `scripts/`(88), `tools/`(35), `infra/`(2) | | 스테이징 검증·QA·배포 보조 |
| CI/CD | `.github/workflows/`, `cloudbuild*.yaml`(3) | | |
| 문서 | `docs/`(210) | | 이전 감사·runbook 포함 |

## 저장소 위생 문제(추적되지만 production이 아님)

- `festival_web/functions/node_modules` 9,768개 파일이 git에 커밋됨.
- 테스트 임시 산출물 다수 추적: `tmp/`(117), `.tmp/`(47), `pytest_tmp_avatar_qa_escalated/`(45), `.g003_pytest_tmp/`(12), `.g002narrow/`(9), `g005_pytest_owned_escalated*/`(12), `2026-08-20/`.
- 디자인 원본 폴더: `설레연 프론트 ui 디자인/`(57), `AI에게 내 취향 알려주기/`(2), `seolleyeon-initial/`+`seolleyeon-iniitial/`(14).
- 루트 잡파일: `firestore-debug.log`, `smoke_conset.txt`, `mini_calibration_*_map.txt`, `g004-*-manifest.txt`, 이미지 png들.
- `.agents/`(114): 에이전트 세션 메타.
- 작업 트리에 5,868건 staged 삭제(tmp/codex 캐시 등) 대기 중 — 사용자(또는 이전 세션)가 스테이징한 정리 작업.

## 미커밋 작업 (보호 대상)

아바타 품질 작업 32개 파일 (+1,717/−279): `lib/ai_recommend_model/avatar_generation/*`, `functions/src/avatarMedia.ts`, `tests/test_avatar_*`, `scripts/staging_avatar_live_*`, `requirements_avatar_worker.txt`, `cloudbuild.avatar-worker.yaml`, 문서 2건. 본 감사는 이 working-tree 상태를 기준으로 검증한다.
