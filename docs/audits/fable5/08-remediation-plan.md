# 08 — 리메디에이션 플랜 (Fable 5, 2026-08-28)

각 항목: 수정안 · 위험 · 테스트 · WIP 엉킴 여부 · 승인/blocker.

## Tier 0 — 즉시(저위험, WIP 무관)

- **SEC-01/02 PII git 추적해제**: `.gitignore`에 `mini_calibration_*.txt`, `smoke_conset.txt`, `functions/recEvents_export.csv`, `node_modules/` 추가 → `git rm --cached`(파일 보존). history rewrite는 **외부 승인 필요**(server-side residual 재발 이력). 파일 삭제 금지.
- **OPS node_modules(9,768)·개발잔재 추적해제**: `git rm -r --cached festival_web/functions/node_modules` 등.

## Tier 1 — 서버 fail-closed(저위험, 테스트 동반)

- **SEC-05 blindMeeting fail-open**: `store.ts` `loadBlockedUserIds`/`isRestricted` catch에서 rethrow(또는 "unknown→제외"). 테스트: Firestore 오류 주입 시 후보 제외 검증. RED→GREEN.
- **SEC-11 App Check 디스패처**: `BLIND_MEETING_CALLABLE_OPTIONS`·`MEETING_ICEBREAKER_CALLABLE_OPTIONS`에 `enforceAppCheck:true`. 위험: App Check가 프로덕션서 아직 미강제면 클라 차단 가능 → **App Check 강제 상태 확인 후** 적용. 테스트: functions 계약 테스트.
- **SEC-18 동의기록 fail-closed**: `_readConsentBool` `fallback:false`, 필수 동의 미명시 시 쓰기 거부. 테스트 동반.

## Tier 2 — festival + 커뮤니티(rules+테스트, 중위험) — **적용 상태 반영**

- **SEC-09 공개 관리자 엔드포인트** — ✅ SOURCE_FIXED, LOCAL_VERIFIED, NOT_DEPLOYED.
  3종 `invoker:"private"`(IAM) + 하드코딩 시크릿 제거→env(`admin_http_guard.ts`).
  functions 테스트 9. **EXTERNAL**: 배포로 IAM 반영 + 노출 시크릿 회전.
- **SEC-08 사진 스크래핑** — ✅ SOURCE_FIXED, STORAGE_RULES_TESTED, NOT_DEPLOYED.
  storage.rules read 를 소유자(uid==auth.uid)로 제한. storage 테스트 13. 상대
  사진 열람은 토큰 URL 이라 회귀 없음. (Firestore `festivalProfiles` 브로드 read
  는 클라 라이브 추천 엔진 의존 → 미변경, SEC-03 근본에 종속.)
- **SEC-03 티켓 탈취** — ⚠ PARTIAL. 규칙은 이미 `lastUid==auth.uid` 강제(위조
  불가). festival rules 테스트 19 신설(현재 0→19). **근본(공개 bearer 코드)은
  코드 회전(EXTERNAL, STOP #5)** — immutable-first-binding 은 익명 재입장 파손·
  pre-claim 그리핑으로 회귀 위험이라 규칙 강화 대신 불변식 테스트만 고정.
  redemption 서버 callable 이관은 회전과 함께 배포 시 권장(현재 미구현).
- **SEC-P3-01 score7d/카운터** — ✅ SOURCE_FIXED, RULES_TESTED, NOT_DEPLOYED.
  likeCount±1 을 like 문서 전이(`exists`/`existsAfter`)에 결합 + score7d 단독 이동
  금지. rules 테스트 15. 잔여 commentCount(랜덤 id 결합 불가)는 서버 트리거 후속.
- **SEC-04 대나무숲 익명성** — ⛔ DECISION / DATA_MIGRATION_REQUIRED (미적용, STOP #3).
  아래 옵션 참조.

### SEC-04 — 옵션과 권고 (사용자 결정 필요)

근본: public 문서의 raw authorId 는 규칙으로 마스킹 불가 → 물리 제거 필요.
서버(계정삭제·댓글알림)와 클라("내가 쓴 글")가 authorId 에 의존. 대규모 breaking.

- **옵션 A (권장) — private 매핑 분리 + 데이터 마이그레이션**
  - PUBLIC `bamboo_posts`/`comments` 에서 authorId 제거. PRIVATE
    `bamboo_post_authors/{postId}`·`bamboo_comment_authors/{...}` 매핑 신설.
  - "내가 쓴 글" = 매핑 query. 소유권/삭제 = 규칙이 매핑 get. 서버는 Admin SDK 로
    매핑 조회(계정삭제·댓글알림 갱신). 랜덤 pseudonym 불필요.
  - 필요: 새 rules + 클라/함수 배포(구클라 강제업데이트) + `scripts/bamboo_anonymize_migration.mjs`
    실행(dry-run 검증됨). 순서: rules→클라/함수→백업→--limit 카나리아→전량.
  - 트레이드오프: breaking, 강제업데이트/롤아웃 조율, "내가 쓴 글" 쿼리 2단계화
    (매핑→문서). 보안·익명성 정공법. 익명성+서버 accountability 동시 충족.
- **옵션 B — 마이그레이션 전 임시 fail-closed**
  - 새 rules 배포 즉시 legacy(authorId 잔존) 문서의 public read 를 DENY.
  - Firestore list 쿼리는 결과셋에 거부 문서가 하나라도 있으면 전체 실패 → 피드가
    마이그레이션 완료까지 사실상 다운. "잠깐 안 보이는 것"이 아니라 전체 중단.
  - 트레이드오프: 유출은 즉시 멈추나 UX 심각. 짧은 정지창으로 A 와 병행 시에만 의미.
- **옵션 C — 익명성 정의 재검토(비권장)**
  - "익명 보장" UI 표기를 내리고 실명 join 을 제품적으로 수용. 메모리
    (설레연 정체성: 신뢰형 관계 플랫폼)와 배치되어 비권장.

권고: **A** 를 준비하되 배포 창을 짧게. 규칙/클라/서버 변경은 사용자 승인 후
별도 세션에서 롤아웃 조율. 마이그레이션 스크립트는 dry-run 검증 완료.

## Tier 3 — 클라이언트 수명주기/정확성

- **SEC-06/COR-01 FCM**: 로그아웃 시 `deviceTokens/{token}` 삭제+`deleteToken()`; 로그인 부트스트랩 후 `syncFcmToken()` 호출. 테스트: 위젯/유닛.
- **SEC-10/COR 채팅 게이트**: 1:1 방 생성에 matches 존재+양방향 blocks 부재 요구. **제품의도 확인 필요**(무매칭 DM 허용 여부).
- **COR-04 프로필 공개 토글**: `_loadSettings`서 로드·`savePrivacySettings`로 저장(바로 아래 학과회피 토글과 동일 패턴). 또는 토글 제거.
- **COR-06 스플래시 제재검사**: 라우팅 전 `isRejoinRestricted` 검사(로그인 경로엔 이미 존재).

## Tier 4 — recsys 정책

- **SEC-12 banned 제외**: `_BLOCKED_ACCOUNT_STATUSES`에 withdrawn/banned/restricted 추가, 클라 하이드레이션에 banned/loginDisabled 필터. 테스트 신규(현재 withdrawn/banned 테스트 없음).
- **SEC-13 타임스탬프 위조**: rules에서 createdAt/eventTime을 request.time±ε로 클램프 또는 서버 스탬프.
- **COR-03 serving 불일치**: dailyRecs를 serving하거나(self-read rule 추가) 최근노출 dedup·단일소스 가드를 소스 문서로 이동. 설계 결정 필요.

## Tier 5 — avatar(WIP 소유자와 조율 필수)

- **SEC-07/COR-02**: generationClaim 만료(claimedAt+최대기간), lease sweeper가 만료 claim을 `retryable_failed`로 방출, `needs_review` 재시도 경로 또는 ops 리셋. **미커밋 WIP 영역 — 사용자와 조율 후.**
- **16 RED 테스트**: `build_report(artifact_registry_location=...)` 시그니처 정합, `seolleyeon_clip_job_handler.py:157` 버킷 allowlist에 private-source 추가 — 이것도 WIP이므로 소유자 의도 확인.

## Tier 6 — ops/CI(저위험)

- CI `pip install ... || true` 제거, 아바타 테스트 CI 게이트 추가, functions predeploy에 `npm test`, gitleaks `tmp/.*` allowlist 축소, Actions SHA 고정, alerting IaC 구현.

## 각 tier 커밋 원칙

기능·스타일 분리, RED→GREEN, 논리적 단위, 사용자 WIP 미포함. **단, 현재 작업 트리 상태에서는 깨끗한 커밋이 불가**(§00 Blocker) — 실행 모드는 사용자 결정 대기.
