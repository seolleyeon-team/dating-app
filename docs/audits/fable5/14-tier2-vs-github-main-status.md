# 14 — Tier 2 상태 재작성 (github/main 기준, 2026-08-29)

이전 Tier 2 보고서는 로컬 브랜치 HEAD 를 baseline 으로 썼다. 이 문서는 **canonical
`github` 리모트의 `main`** (`https://github.com/seolleyeon-team/dating-app.git`)을
baseline 으로 각 Tier 2 finding 을 재검증한다.

## 0. 결정적 사실 — 로컬 브랜치는 main 보다 45 커밋 뒤처져 있다

```
github/main            = 9d3a15c2   (canonical, 최신)
로컬 HEAD              = 9ac02bdd   (release/grok45-production-readiness-final)
merge-base             = 9ac02bdd   (= 로컬 HEAD)
github/main .. HEAD    = 0 commits   (로컬 HEAD 에만 있는 커밋 없음)
HEAD .. github/main    = 45 commits  (main 이 45커밋 앞섬)
```

즉 **로컬 HEAD 는 main 의 조상(ancestor)** 이다. main 히스토리에 다음이 이미 있다:
- `d59a5a2b Merge PR #57 ... release/grok45-production-readiness-final` — 이 release
  브랜치 작업이 이미 main 에 병합됨.
- `72163b38 fix(rules): protect bamboo ranking counters` — **SEC-P3-01 수정이 이미
  main 에 있음.**
- 이후 Kakao 친구 추천 프라이버시 등 추가 작업.

로컬 작업 트리 = **stale base(9ac02bdd) + 대규모 미커밋 WIP + festival 추출/은퇴
작업**. 따라서 "작업 트리 vs main" 단순 diff 는 노이즈가 크다. 아래는 finding 별
**main 실제 파일 내용** 기준 재검증 결과다.

## 1. Tier 2 finding 별 — github/main 실제 상태

| ID | github/main 상태 | 근거 (main 파일) |
|---|---|---|
| **SEC-P3-01** 대나무숲 카운터 | ✅ **이미 수정됨 (main)** | `firestore.rules` 에 `bambooLikeCountBound`/`bambooScore7dMovesWithCounters` 존재, `test/firestore_rules/bamboo_counter_rules.test.js` 존재 (commit 72163b38). 작업 트리 bamboo 섹션은 main 과 **동일**(diff 0) → 내 재적용은 중복. |
| **SEC-04** 대나무숲 익명성 | ❌ **여전히 취약 (main)** | `firestore.rules:1300` `bamboo_posts allow get,list: if isSignedIn()` + raw `authorId==auth.uid` 저장; `firestore_community_repository.dart` 여전히 raw authorId 저장·쿼리; `publicProfiles/{uid} get: if isSignedIn()` → join 역익명화 가능. |
| **SEC-03** 축제 티켓 재귀속 | ❌ **여전히 존재 (main)** | `festival_web/firestore.rules:24` `ownsTicket=lastUid==auth.uid`, `:253 canUpdateFestivalTicket` — bearer 코드 재바인딩 패턴 그대로. 근본 해소는 입장코드 회전(외부). |
| **SEC-08** 축제 사진 스크래핑 | ❌ **여전히 취약 (main)** | `festival_web/storage.rules:22` `allow read: if signedIn() && validTicketId(ticketId)` — 소유자 확인 없는 광범위 read. |
| **SEC-09** 축제 관리자 EP | ❌ **여전히 취약 (main)** | `festival_web/functions/src/festival_event_schedule.ts:15` `SEED_HTTP_KEY="seolleyeon-festival-clip-init"`(하드코딩), `:147 invoker:"public"`. |

## 2. 내 Tier 2 산출물이 지금 어디 있나 (중요)

이전 세션들에서 (a) Tier 2 수정, (b) **festival_web 을 레포 밖으로 추출**,
(c) festival 아바타 topology 은퇴를 순차 진행했다. 그 결과 main 대비 현재 위치:

| finding | 내가 한 것 | 현재 위치 | main 에 반영? |
|---|---|---|---|
| SEC-P3-01 | 카운터 가드 재적용 | 작업 트리 `firestore.rules` (main 과 동일) | **이미 main 에 있음** (중복) |
| SEC-04 | 설계 + dry-run 마이그레이션 스크립트(미적용) | 작업 트리 `scripts/bamboo_anonymize_migration.mjs` (main 에 없음) | ❌ 규칙/스키마 수정 미적용 |
| SEC-03 | festival rules 테스트 19 + 잔여 문서화 | **`festival_web_standalone/`** (레포 밖으로 추출됨) | ❌ main festival_web 은 원본 그대로 |
| SEC-08 | storage read 소유자 전용 + 테스트 13 | **`festival_web_standalone/`** (추출됨) | ❌ main festival_web 은 광범위 read 그대로 |
| SEC-09 | invoker private + 시크릿 env(`admin_http_guard.ts`) + 테스트 9 | **`festival_web_standalone/`** (추출됨) | ❌ main festival_web 은 public+하드코딩 그대로 |

**핵심 함의**: SEC-03/08/09 festival 수정은 `festival_web` 을 레포에서 분리하면서
함께 `festival_web_standalone/` 로 이동했다. 따라서 **canonical main 의 `festival_web`
사본은 여전히 취약**하다. 이 수정들은 (i) festival 을 그 standalone 폴더에서
배포할 때만 효력이 있고, (ii) main 의 `festival_web` 을 직접 고치거나 배포 경로를
standalone 으로 바꾸기 전까지 main 기준으로는 미반영이다.

## 3. 작업 트리 vs main — 실제 변경 카테고리

- **stale-base 격차(45커밋)**: main 이 추가/변경한 것(예: `dailyRecs`,
  `recommendationExclusions` 규칙, emailLinkTokens 재설계, Kakao 추천 프라이버시)이
  로컬 작업 트리에는 없다. 이는 "내 변경"이 아니라 **로컬이 낡아서 생긴 격차**다.
- **festival_web 삭제(9,869 파일)**: 추출 작업의 결과(미커밋).
- **미커밋 사용자 WIP**: 아바타 파이프라인 등 — 본 세션 미개입.
- **내 순수 신규 산출물(main 에 없음)**: `scripts/bamboo_anonymize_migration.mjs`,
  festival topology 은퇴(config/avatar-ops/*, 관련 scripts/tests),
  `docs/audits/production_cleanup/11–15`, 그리고 이 문서.

## 4. 재검증 결론 (main 기준)

```
SEC-P3-01 = RESOLVED_IN_MAIN            (조치 불필요; 로컬 중복)
SEC-04    = OPEN_IN_MAIN                (설계+dry-run 스크립트만; 규칙/데이터 마이그레이션 미적용 — STOP #3)
SEC-03    = OPEN_IN_MAIN                (bearer 코드 근본; 코드 회전 외부 필요; 수정본은 standalone)
SEC-08    = OPEN_IN_MAIN                (수정본은 standalone; main festival_web 미반영)
SEC-09    = OPEN_IN_MAIN                (수정본은 standalone; main festival_web 미반영; 노출 시크릿 회전 필요)
```

## 5. 권고 (증거 기반)

1. **로컬 브랜치 갱신**: 작업 전 `git fetch github && git rebase/merge github/main`
   (또는 새 브랜치를 main 에서 분기) — 45커밋 뒤처진 stale base 위에서 계속 작업하면
   main 이 이미 고친 것을 중복하거나 충돌한다. (커밋/rebase 는 사용자 승인 후.)
2. **festival 배포 소스 결정**: main 의 `festival_web` 을 은퇴시키고 `festival_web_standalone/`
   (SEC-03/08/09 수정 포함)을 정본으로 삼을지 결정. 그렇지 않으면 main 의
   festival_web 에 SEC-08(소유자 read)·SEC-09(invoker private+시크릿 env) 수정을
   직접 적용해야 한다.
3. **SEC-09 시크릿 회전**: 하드코딩 시크릿은 이미 공개(main 에 커밋됨) → 배포 시 회전.
4. **SEC-03 입장코드 회전**: 커밋된 bearer 코드 → 외부 회전.
5. **SEC-04**: 옵션 A(private authorId 매핑 + 데이터 마이그레이션) 결정 대기.
   dry-run 스크립트는 에뮬레이터 검증 완료, production 미실행.

본 문서 작성 중 실행한 원격 작업은 **`git fetch github main`(읽기 전용)** 뿐이다.
commit/push/deploy/데이터 변경 없음.
