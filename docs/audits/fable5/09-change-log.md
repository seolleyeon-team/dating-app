# 09 — 실제 변경 로그 (Fable 5, 2026-08-28)

사용자 승인 범위: **"안전한 것부터 직접 수정(커밋 없음)"** + 성인인증·안전스탬프 토글은 **건드리지 않음**. 모든 변경은 working tree에만 있고 커밋하지 않았다(작업 트리 blocker). 각 항목 RED→GREEN.

## 적용한 코드 수정

### SEC-11 — blindMeeting/icebreaker 디스패처 App Check 강제 (P1/P2)
- `functions/src/blindMeeting/runtime.ts`: `BLIND_MEETING_CALLABLE_OPTIONS`에 `enforceAppCheck: true`.
- `functions/src/meetingIcebreaker/runtime.ts`: `MEETING_ICEBREAKER_CALLABLE_OPTIONS`에 `enforceAppCheck: true`.
- 테스트(신규): `blindMeeting/runtime.test.ts`, `meetingIcebreaker/runtime.test.ts` — 옵션에 App Check 강제 assert. RED(undefined)→GREEN.
- 영향: 두 디스패처(보증금·취소·안전스탬프·follow-up·아이스브레이커)가 이제 다른 모든 callable과 동일하게 App Check 요구. 상태 라벨: **SOURCE_FIXED / LOCAL_TESTED / DEPLOYMENT_REQUIRES_REAL_APP_CHECK_RUNTIME_VALIDATION**. 클라는 전역으로 App Check 토큰을 첨부하도록 되어 있으나 이를 "회귀 없음"으로 단정하지 않는다 — 최근 실제 Android debug 에서 App Check 403(attestation failure)이 관측되었으므로, 배포 전 **실기기 smoke(정상 사용자 성공)** 로 검증해야 한다. 프로덕션 App Check 가 Monitor 단계면 이 강제는 무해하며 Enforce 전환 시 함께 반영. 본 세션은 원격/런타임 검증을 수행하지 않았다.

### SEC-05 — blindMeeting 차단·제재 조회 fail-closed (P1)
- `functions/src/blindMeeting/store.ts`: `loadBlockedUserIds`/`loadRecentlyMetUserIds`/`isRestricted`의 `try/catch → return []/false`(fail-open) 제거. 오류를 전파(fail-closed)해 후보 로딩·매칭 실행을 중단하고 다음 tick 재시도. 세 함수를 export + `database` seam(기본 `db()`) 추가로 테스트 가능화. dna/user read도 이미 예외를 전파하므로 동작 일관.
- 테스트(신규): `blindMeeting/store.failClosed.test.ts` — 던지는 fake db 주입 시 세 함수가 reject하는지. RED(빈 배열/false 반환)→GREEN.
- 영향: Firestore 일시 오류 시 서로 차단·제재 사용자가 매칭되던 경로 제거. `buildCandidatePool`의 `Promise.all`이 reject→그날 매칭 abort(부분 매칭 생성 안 함). fail-closed 규칙 부합.

### SEC-18 — 법적 동의 기록 fail-closed (P2/증빙)
- `lib/services/user_service.dart`: `_readConsentBool(..., fallback: true)` → `@visibleForTesting static resolveRequiredConsent(value)`로 교체, 누락/형식오류 값을 `false`로(동의 위조 금지). 5개 필수 동의 모두 적용.
- 테스트(신규): `test/services/legal_consent_resolver_test.dart` — 명시적 true만 true, 누락/이상값은 false. GREEN.
- 회귀 안전: 실제 해피패스(`storage_service.savePendingLegalConsents`)는 5개 동의를 명시적 `true`로 저장하므로 실사용자 기록 불변. fallback은 `fake_user_1` dev 경로·손상 데이터에서만 발동하며 이제 정직하게 false 기록.

## 검증(변경분)
- functions `npm test`: 431→**436 pass / 0 fail**(신규 5), lint/build 통과.
- flutter `analyze lib/services/user_service.dart`: No issues.
- flutter 신규 동의 테스트: 2 pass. 전체 flutter test 회귀: (아래 10-verification 참조).
- firestore.rules **미변경** → rules emulator 72 그대로 유효.

## 미적용(범위 밖·blocker로 이관) — 아래는 수정하지 않음

- **SEC-14 성인인증 / SEC-15 안전스탬프**: 사용자가 "의도된 것 — 건드리지 마라"로 확정. 코드 불변, 감사 기록만.
- **SEC-01/02 PII git 추적**: 파일은 동의 증빙(삭제 금지). 실제 untrack은 인덱스/히스토리 조작이라 현재 대규모 미커밋 상태와 엉킴 → §13에 실행 준비 명령으로 이관. history rewrite는 외부 승인.
- **SEC-P3-01 대나무숲 score7d**: 서버 카운터 설계 의존(클라 write 차단 시 서버 대체 필요) → Tier 2.
- **SEC-03/04/08/09 festival·익명성**: rules 재설계+데이터 마이그레이션 → Tier 2.
- **SEC-07/COR-02 avatar 고착**: 미커밋 WIP 영역, 소유자 조율 필요.
- 기타 COR/PERF/OPS: 08-remediation-plan 참조.

---

## Tier 2 적용 (festival + 커뮤니티) — 후속 세션, 커밋 없음

Tier 1 이후 진행. 모든 변경은 working tree 에만 있고 커밋/배포하지 않았다. 각
항목 RED→GREEN. festival(별도 프로젝트 `seolleyeon-festival`)에는 규칙 테스트가
0건이었으므로 테스트 인프라를 신설했다. 상태 라벨: SOURCE_FIXED / LOCAL_VERIFIED
/ NOT_DEPLOYED / EXTERNAL_ACTION_REQUIRED / DATA_MIGRATION_REQUIRED.

### SEC-09 — 축제 관리자 HTTP 엔드포인트 (P2) — SOURCE_FIXED, LOCAL_VERIFIED, NOT_DEPLOYED
- 대상 3종: `setFestivalEventScheduleHttp`(festival_event_schedule.ts),
  `seedFestivalEmbeddingsHttp`(festival_embeddings.ts),
  `sendFestivalRevealAnnouncementHttp`(festival_push_announcement.ts).
- `invoker: "public"` → `invoker: "private"` (Cloud Run IAM 게이트. onRequest v2
  는 invoker 미지정 시 기본 public 이므로 명시적 private 필요).
- 하드코딩 공유 시크릿(`SEED_HTTP_KEY = "..."`) 3곳 제거 → 신설
  `admin_http_guard.ts` 의 `adminHttpSecretAllows()` 로 대체: 시크릿은
  `FESTIVAL_ADMIN_SEED_KEY` 환경변수(Secret Manager 바인딩)로만 주입, 미설정 시
  IAM-only. 상수시간 비교.
- 테스트(신규): `admin_http_guard.test.ts` 9케이스, festival functions 에
  `test` 스크립트 신설(`node --test lib/**/*.test.js`, 메인 저장소 관례 미러).
- 검증: festival functions `npm run lint`(tsc --noEmit) PASS, `npm test` 9 PASS.
- 호출자: 3종 모두 운영자 수동 curl(주석 "use once")이며 정기 작업은 별도
  onSchedule 틱이 담당 → private 전환이 자동 caller 를 끊지 않는다.
- **EXTERNAL**: 배포(invoker IAM 반영) + 이미 노출된 시크릿 회전은 미수행.

### SEC-08 — 축제 프로필 사진 접근제어 (P2) — SOURCE_FIXED, STORAGE_RULES_TESTED, NOT_DEPLOYED
- `festival_web/storage.rules`: `festivalProfiles/{ticketId}/{uid}/{fileName}`
  read 를 `signedIn() && validTicketId` → `+ uid == request.auth.uid`(소유자 전용)로.
- 회귀 없음 근거: 참가자 간 상대 사진 열람은 앱이 저장한 getDownloadURL() 토큰
  URL(규칙 우회)로 이뤄지고, 서버 추천/임베딩은 Admin SDK. 규칙 기반 임의 경로
  read/열거(스크래핑)만 차단.
- 테스트(신규): `festival_web/test_rules/festival_storage_rules.test.js` 13 PASS.
  RED 확인: 이전 broad rule 로 되돌리면 "무관 사용자 read"/"경로 추측" 2건 실패.
- **관련 잔여**: Firestore `festivalProfiles` list/get 은 클라 라이브 추천 엔진
  (`festival_recommendation_engine.dart` 의 `where('gender').get()`)이 의존하므로
  좁히지 않았다(제품 회귀 위험, SEC-08 감사 범위 밖). 이는 공개 bearer 코드
  (SEC-03) 근본 문제에 종속 — 근본 해소 시 재검토.

### SEC-03 — 축제 티켓 소유권/재귀속 (P1) — PARTIAL: 강제 불변식 SOURCE-CONFIRMED + LOCAL_RULES_TESTED, 근본 해소 EXTERNAL
- 재검증 결과: 규칙은 이미 `lastUid == request.auth.uid` 를 강제해 **타인 명의로
  바인딩(위조)은 불가**하다. 잔여 위험은 "공개된 입장코드를 아는 공격자가 lastUid
  를 자기자신으로 재귀속"하는 것이며, 이는 익명 인증 + `ticket_codes_seed.json`에
  커밋된 200개 코드(= 공개 bearer)라는 근본 원인에서 온다.
- 규칙 계층에서 immutable-first-binding 으로 막으면 (a) 익명 재입장(기기 변경 시
  새 uid)이 깨지고 (b) 공격자 pre-claim 그리핑(200코드 선점 → 전체 잠금)을
  유발해 오히려 회귀·위험 증가. 그래서 규칙을 강화하지 않고 **강제 가능한
  불변식만 테스트로 고정**했다.
- 테스트(신규): `festival_web/test_rules/festival_ticket_rules.test.js` 19 PASS —
  비로그인 redeem 거부 / lastUid 타인바인딩 거부(create·update) / 비활성 티켓
  거부 / code-ticketId 불일치 거부 / 세션문서 격리(타인 생성·읽기 거부) / 프로필
  쓰기 ownsTicket / 정상 최초 redeem·동일소유자 멱등 재redeem. 잔여
  (rebind-to-self 허용)는 `[RESIDUAL]` 테스트로 현재 동작을 명시적으로 문서화.
- **EXTERNAL / STOP #5**: 입장코드는 이미 공개(커밋)이므로
  COMPROMISED_OR_PUBLIC_IDENTIFIER_REQUIRES_EXTERNAL_ROTATION. 코드 회전 +
  비커밋 코드 소스 + (권장) redemption 서버 callable 이관은 원격/배포 작업으로 미수행.

### SEC-P3-01 — 대나무숲 score7d / 카운터 무결성 (P3) — SOURCE_FIXED, RULES_TESTED, NOT_DEPLOYED
- `firestore.rules`(메인): bamboo_posts update 카운터 분기에
  `bambooLikeCountBound(postId)` + `bambooScore7dMovesWithCounters()` 추가.
  - likeCount 변경은 요청자 like 문서(`likes/{uid}`)의 생성/삭제 전이와 결합
    (`exists`+`existsAfter`). 이미 좋아요한 사용자의 이중 증가 차단.
  - score7d 는 like/comment 카운터와 같은 부호로 함께 바뀔 때만 이동 → score7d
    단독 +1 반복(직접 랭킹 조작) 차단.
- 기존 클라 트랜잭션(togglePostLike/addComment/softDeleteComment)은 카운터와 소스
  문서를 한 원자 커밋으로 쓰므로 회귀 없음(테스트로 확인).
- 테스트(신규): `test/firestore_rules/bamboo_counter_rules.test.js` 15 PASS.
  기존 `authz_hardening_rules.test.js` 의 "likeCount +1 허용"이 취약 동작(무-like
  증가)을 인코딩하고 있어 안전 흐름(원자 batch)으로 정정. RED 확인: 가드 제거 시
  정확히 4개 신규-벡터 테스트만 실패.
- **잔여**: commentCount 는 랜덤 commentId 라 getAfter 결합 불가 → ±1 게이트만
  유지(문서 없이 반복 증가 가능). 완전 해소는 서버 트리거(카운터 서버 소유)로
  가능하나 배포된 구클라 카운터 쓰기와 충돌 → 후속 과제.

### SEC-04 — 대나무숲 익명성 붕괴 (P1) — DECISION / DATA_MIGRATION_REQUIRED (미적용)
- 재검증(CONFIRMED): public `bamboo_posts/{postId}` 에 raw authorId(UID) 저장 +
  `allow get,list: if isSignedIn()`, `publicProfiles/{uid}` 은 `get: if isSignedIn()`
  → authorId join 으로 "익명 보장"(post_write_screen.dart:343 UI 표기) 작성자 특정.
  댓글도 동일 클래스. 서버 의존: 계정삭제 소셜정리(`accountDeletionSocialCleanup.ts:248`
  `where('authorId'==uid)`), 댓글 알림 트리거(`index.ts:3086,3098` post.authorId).
  클라 "내가 쓴 글"은 `where('authorId'==uid)`.
- 규칙은 read 응답의 개별 필드를 마스킹할 수 없음 → authorId 를 문서에서
  물리적으로 제거해야 함. 이는 (private 매핑 스키마 + 클라 "내가 쓴 글"/소유권
  재설계 + 서버 트리거/계정삭제 매핑 전환 + 기존 문서 데이터 마이그레이션 +
  구클라 강제업데이트)를 요구하는 대규모 breaking migration → **STOP #3**.
- 본 세션 산출물: (1) 권장 설계(private `bamboo_post_authors`/`bamboo_comment_authors`
  매핑), (2) DRY-RUN 마이그레이션 스크립트 `scripts/bamboo_anonymize_migration.mjs`
  (기본 dry-run, --apply+--project 필수, 멱등, 롤백 메타, 배치). 에뮬레이터에서
  dry-run/apply/멱등 검증 완료(MIGRATION_DRY_RUN_VERIFIED). production 미실행.
- 옵션·권고는 `08-remediation-plan.md`(SEC-04) 및 최종 보고 참조. 규칙/클라/서버
  breaking 변경은 사용자 결정 대기로 **미적용**.

## Tier 2 검증 요약(변경분)
- festival functions: lint PASS, `npm test` 9 PASS.
- festival rules(신규): firestore 19 PASS, storage 13 PASS (JDK21 emulator).
- 메인 rules 전체: 197 PASS / 0 fail (bamboo 15 신규 + authz 1 정정 포함).
- 메인 functions `npm test`: 436 PASS / 0 fail(미변경, 회귀 없음 재확인).
- 메인 Dart/Flutter: **변경 없음**(SEC-04 미적용) → 658 그대로 유효(재실행 불필요).
- bamboo 마이그레이션 dry-run/apply/멱등: 에뮬레이터 검증 OK.
