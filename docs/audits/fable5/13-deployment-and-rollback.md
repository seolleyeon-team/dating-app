# 13 — 배포·롤백 및 blocker 실행 절차 (Fable 5, 2026-08-28)

본 세션은 커밋/배포하지 않았다. 아래는 사용자가 실행할 절차.

## A. 이번 세션의 코드 수정 (working tree, 미커밋)

변경 파일:
- `functions/src/blindMeeting/runtime.ts`, `functions/src/meetingIcebreaker/runtime.ts` (App Check)
- `functions/src/blindMeeting/store.ts` (fail-closed)
- `lib/services/user_service.dart` (동의 fail-closed)
- 신규 테스트 4: `functions/src/blindMeeting/runtime.test.ts`, `functions/src/meetingIcebreaker/runtime.test.ts`, `functions/src/blindMeeting/store.failClosed.test.ts`, `test/services/legal_consent_resolver_test.dart`

**커밋 차단 사유**: 작업 트리에 사용자 WIP(아바타 32파일, RED 16) + staged 삭제 5,868건이 섞여 있어 논리적 단위 커밋 불가. 사용자가 WIP를 정리(별도 커밋/stash)한 뒤 아래처럼 이 수정만 분리 커밋 권장:

```bash
git add functions/src/blindMeeting/runtime.ts functions/src/meetingIcebreaker/runtime.ts functions/src/blindMeeting/runtime.test.ts functions/src/meetingIcebreaker/runtime.test.ts
# commit: fix(functions): enforce App Check on blind-meeting and icebreaker dispatchers
git add functions/src/blindMeeting/store.ts functions/src/blindMeeting/store.failClosed.test.ts
# commit: fix(blind-meeting): fail closed when block/restriction reads error
git add lib/services/user_service.dart test/services/legal_consent_resolver_test.dart
# commit: fix(consent): stop recording missing consents as agreed
```

롤백: 위 파일들을 `git checkout --` 또는 커밋 revert. 데이터 영향 없음(순수 코드/규칙-무관).

## B. SEC-01/02 PII git 추적 해제 (외부 승인 필요)

파일은 **동의 증빙이므로 디스크에서 삭제 금지**. git 추적만 해제:

```bash
# 1) .gitignore 에 추가 (WIP .gitignore 정리 후)
#    mini_calibration_*.txt
#    smoke_conset.txt
#    functions/recEvents_export.csv
#    node_modules/
# 2) 추적 해제(파일 보존)
git rm --cached mini_calibration_uid_photo_map.txt mini_calibration_consent_map.txt smoke_conset.txt functions/recEvents_export.csv
git rm -r --cached festival_web/functions/node_modules
```

**history rewrite**는 별도 승인 항목: 과거 residual(GitHub Support remediation) 이력이 있으므로 확립된 사고 절차대로. 본 에이전트는 수행하지 않음.

## C. 배포 전 조건 (외부 실행)

opus5 잔여(App Check Enforce, Node22 재배포, indexes, retention scheduler)는 `docs/audits/opus5/23-external-ops-checklist.md` 유효. 추가:
- SEC-11 적용본 배포는 App Check Enforce 상태와 함께 검증(Monitor 단계면 강제가 무해).
- festival(SEC-03/08/09)·익명성(SEC-04)은 배포 전 필수 수정 대상(NOT_READY).

## D. 금지(본 세션 미수행)
production 배포, firebase deploy, gcloud deploy, force push, history rewrite, Secret 교체, 운영 데이터 변경.

---

## E. Tier 2 변경 파일 (working tree, 미커밋)

festival(별도 프로젝트 `seolleyeon-festival`):
- `festival_web/functions/src/festival_event_schedule.ts` · `festival_embeddings.ts`
  · `festival_push_announcement.ts` (SEC-09: invoker private + 시크릿 env화)
- `festival_web/functions/src/admin_http_guard.ts`(신규) · `admin_http_guard.test.ts`(신규)
- `festival_web/functions/package.json` (test 스크립트 추가)
- `festival_web/storage.rules` (SEC-08: 소유자 read)
- `festival_web/test_rules/`(신규): `package.json`, `.gitignore`,
  `festival_ticket_rules.test.js`(SEC-03), `festival_storage_rules.test.js`(SEC-08)

메인:
- `firestore.rules` (SEC-P3-01: bamboo 카운터 결합/score7d 가드)
- `test/firestore_rules/bamboo_counter_rules.test.js`(신규)
- `test/firestore_rules/authz_hardening_rules.test.js`(좋아요 테스트 1건 정정)
- `scripts/bamboo_anonymize_migration.mjs`(신규, SEC-04 dry-run 마이그레이션, 미실행)

**참고(작업 트리 위생)**: festival functions 타입체크/테스트를 위해
`festival_web/functions` 와 `festival_web/test_rules` 에서 `npm install` 을
수행했다. 추적 중이던 node_modules `.bin` 셸 shim 18개가 재생성되어 변경으로
잡혔으나 `git checkout -- festival_web/functions/node_modules` 로 원복했다(의존성
아티팩트, 사용자 WIP·소스 아님). `test_rules/node_modules` 및 신규 설치분은
untracked 이며 tracked diff 를 오염시키지 않는다(`.gitignore` 추가). 근본적으로
node_modules 추적 해제는 기존 OPS 과제.

### 롤백(패치 단위, 대량 checkout 금지)
작업 트리에 사용자 WIP 가 많으므로 `git checkout .`/`git restore .`/`git clean`
**금지**. Tier 2 만 되돌리려면 위 파일을 개별 대상으로:
- 수정 파일: `git checkout -- <파일>` (해당 파일이 사용자 WIP 와 겹치지 않음을
  본 세션 preflight 로 확인함 — 모두 clean 이었음).
- 신규 파일: 파일 삭제(`rm`). 데이터 영향 없음(순수 소스/규칙/테스트).

## F. Tier 2 EXTERNAL 액션 (원격, 승인 후 별도 실행 — 본 세션 미수행)

1. **SEC-09 배포 + IAM + 시크릿**
   - festival functions 재배포로 `invoker: private` 반영(allUsers invoker 제거).
   - 운영자 curl 은 이제 identity token 필요:
     `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" <url>`.
     호출 principal 에 `roles/run.invoker`(함수 SA/사람 계정) 부여 필요 — 실제
     운영 caller 계정을 확인 후 최소권한 부여. (자동 정기 작업은 onSchedule 틱이
     담당하므로 HTTP endpoint caller 는 사람 운영자로 파악됨.)
   - (선택) `FESTIVAL_ADMIN_SEED_KEY` 를 Secret Manager 로 바인딩해 2차 방어.
   - **이미 커밋되어 공개된 과거 공유 시크릿은 노출된 것으로 간주 → 회전 필요**
     (배포 시 신규 값 사용, 구값 폐기).
2. **SEC-03 입장코드 회전** — `ticket_codes_seed.json` 200개가 커밋되어 공개.
   COMPROMISED_OR_PUBLIC_IDENTIFIER_REQUIRES_EXTERNAL_ROTATION: 새 코드 생성 +
   비커밋 소스(예: Secret Manager/오프라인 배포) + 기존 티켓 DB 회전. (권장:
   redemption 을 인증 서버 callable + 트랜잭션으로 이관해 코드 단독 의존 축소.)
   본 세션은 코드 회전·티켓 DB 변경·secret regeneration 미수행.
3. **SEC-04 데이터 마이그레이션** — 옵션 A(08 참조) 승인 시:
   rules→클라/함수 배포(구클라 강제업데이트)→백업→
   `node scripts/bamboo_anonymize_migration.mjs --project <id>`(dry-run)→
   `--apply --limit N`(카나리아)→전량. dry-run/apply/멱등은 에뮬레이터 검증 완료,
   **production 미실행**.
4. **App Check(SEC-11) 실기기 smoke** — 배포 전 정상 사용자 성공 확인(최근 debug
   403 관측). Enforce 전환 정합.
