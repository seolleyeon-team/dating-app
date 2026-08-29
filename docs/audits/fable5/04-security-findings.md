# 04 — 보안 발견 (Fable 5 감사, 2026-08-28)

6개 도메인 병렬 감사(Flutter / Firebase rules+functions / recsys / avatar / ops+deps / fallback) 결과를 통합·중복제거하고, 상위 항목은 메인 에이전트가 코드로 재검증했다. 등급은 §6 기준. `[verified]` = 메인이 직접 코드 확인.

이전 감사(opus5)에서 해결된 항목은 재검증 후 제외했다. 여기 있는 것은 **오늘 코드에 살아있는 문제**다.

> **상태 갱신(Tier 1·2 이후)**: SEC-05/11/18 은 Tier 1 에서 working tree 수정
> 완료. SEC-03/08/09/P3-01 은 Tier 2 에서 source 수정 + 로컬 테스트 완료(미배포).
> SEC-04 는 재검증 CONFIRMED 이며 대규모 데이터 마이그레이션이 필요해 설계 +
> dry-run 스크립트만 산출(미적용, 사용자 결정 대기). 각 항목 상태는 아래 표
> 및 `09-change-log.md`(Tier 2) 참조. 여기 표의 "상태" 열은 **최초 발견 시점의
> CONFIRMED** 를 그대로 두되, 각주로 현재 상태를 덧붙인다.

## P0 — Critical

| ID | 영역 | 문제 | 증거 | 상태 |
|---|---|---|---|---|
| SEC-01 | 개인정보/git | 실 UID↔얼굴사진 매핑 동의 증빙 파일이 git 추적 중 (`mini_calibration_uid_photo_map.txt`, `mini_calibration_consent_map.txt` 각 10행, `smoke_conset.txt` 1행) — 과거 PII 사고 재발 클래스 | repo 루트, `git ls-files`로 확인 | CONFIRMED `[verified]` |
| SEC-02 | 개인정보/git | 실사용자 행동 데이터 CSV `functions/recEvents_export.csv` 추적 (27행: userId·targetUserId·eventType) | `git ls-files` | CONFIRMED |

> SEC-01의 파일들은 **동의 증빙이므로 파일 자체 삭제 금지**(메모리 규칙). 승인된 방향: `git rm --cached` + `.gitignore` 등재. history rewrite는 외부 승인 필요(§blocker).

## P1 — High

| ID | 영역 | 문제 | 증거 | 상태 |
|---|---|---|---|---|
| SEC-03 | festival/rules | **축제 티켓 탈취**: `ownsTicket`=`ticket.lastUid==auth.uid`이고 update가 `lastUid` 재바인딩을 허용 → 로그인 사용자가 6자 코드(200개 전부 `ticket_codes_seed.json`에 커밋됨)로 남의 티켓/프로필/추천/채팅 점유 | `festival_web/firestore.rules:20-25,243-260` | CONFIRMED `[verified]` ¹ |
| SEC-04 | 커뮤니티/프라이버시 | **대나무숲 익명성 붕괴**: 게시글에 실 `authorId==auth.uid` 저장 + `allow get,list: if isSignedIn()` → 누구나 authorId를 `publicProfiles`와 join해 학교인증 커뮤니티의 고백글 작성자 특정. UI는 "익명 보장" 표기 | `firestore_community_repository.dart:44`, `firestore.rules:1272-1273`, `publicProfiles get:isSignedIn`, `post_write_screen.dart:343` | CONFIRMED `[verified]` ² |
| SEC-05 | blindMeeting/functions | **fail-open 차단/제재 체크**: `loadBlockedUserIds` 실패 시 `[]`, `isRestricted` 실패 시 `false` 반환 → Firestore 오류 시 서로 차단한 사용자가 매칭되고 제재 사용자가 게이트 통과. 프로젝트 fail-closed 규칙 위반 | `blindMeeting/store.ts:193-205,226-241` | CONFIRMED `[verified]` |
| SEC-06 | FCM/프라이버시 | 로그아웃 시 `deviceTokens` 문서/토큰 미삭제 → 이전 계정의 채팅·매칭 푸시(내용 포함)가 기기에 계속 도착(기기 공유·계정 전환 시) | `auth_provider.dart:649-678`, `push_notification_service.dart:310-322` | CONFIRMED |
| SEC-07 | avatar/WIP | Azure 생성 claim에 만료·복구 경로 없음 → 워커 강제종료/unknown-outcome 시 job이 `needs_review`(terminal)로 영구 고착, 사용자는 재시도·재업로드 불가 | `worker.py:1251-1336,3592-3608`, `job_lease.py:414-491` | CONFIRMED (미커밋 델타) |

## P2 — Medium

| ID | 영역 | 문제 | 증거 | 상태 |
|---|---|---|---|---|
| SEC-08 | festival/storage | 로그인만 하면 모든 축제 프로필 사진 읽기 가능(참가자/소유 확인 없음) → 얼굴공개 이벤트 대량 스크래핑 | `festival_web/storage.rules:21-28` | CONFIRMED ³ |
| SEC-09 | festival/functions | 축제 관리자 HTTP 3종이 `invoker:public` + 소스에 하드코딩된 공유 시크릿만으로 보호 → 일정/공개시각 변경, 전체 푸시 발송, 임베딩 재시드 가능 | `festival_event_schedule.ts:144-153` 외 2개 | CONFIRMED ⁴ |
| SEC-10 | chat/rules | 1:1 채팅방 생성/메시지에 매칭·차단 관계 미검증 → 임의 UID로 방 생성·메시지 전송, 차단한 상대에게도 텍스트 도달(사진만 차단 검증) | `firestore.rules:987-993,1016-1022` | CONFIRMED (제품의도 확인 필요) |
| SEC-11 | functions/AppCheck | `blindMeetingAction`·`meetingIcebreakerAction` 디스패처만 App Check 미강제(다른 모든 callable은 강제) → 방어심층 손실 | `blindMeeting/runtime.ts:16`, `meetingIcebreaker/runtime.ts:15` | CONFIRMED `[verified]` |
| SEC-12 | recsys/정책 | 배치 정책이 앱의 `withdrawn`/`banned`/`loginDisabled` 상태를 미인식 → 인증·아바타 남은 banned 계정이 추천 후보에 잔존(클라 하이드레이션도 banned 미필터) | `seolleyeon_policy_state.py:14`, `ai_recommendation_service.dart:231-234` | CONFIRMED |
| SEC-13 | recsys/무결성 | `recEvents.createdAt/eventTime`가 클라 시계값이며 rules 미검증 → 이벤트 백데이팅/포워드데이팅으로 학습 윈도우·감쇠 조작 | `rec_event_service.dart:35,52-53`, `firestore.rules:848-885` | CONFIRMED |
| SEC-14 | 성인인증(제품결정) | `AdultVerificationService.isTemporarilyDisabled=true`가 릴리스 컴파일 → 20+ 연령 검증이 전원 우회, 자기신고만 수집 | `adult_verification_service.dart:42,57,64,151-159` | CONFIRMED `[verified]` — **의도적 토글, 사용자 결정 필요** |
| SEC-15 | 안전스탬프(제품결정) | 근접·위치 검증 하드코딩 OFF + 좌표 `0,0` 기록 → 안전스탬프가 릴리스에서 항상 즉시 "성공", 위조 데이터 저장 | `safety_stamp_verification_service.dart:18-20,261-268` | CONFIRMED — **의도적 토글, 사용자 결정 필요** |
| SEC-16 | avatar/worker | 워커 `cloud_run_iam` 모드가 OIDC 토큰(audience/issuer/SA) 검증 없이 env 플래그 2개만 신뢰 → IAM 태세 드리프트 시 유료 엔드포인트 개방(문서는 2계층 요구) | `worker_service.py:154-193` vs `docs/avatar_media_security.md:56-64` | CONFIRMED |
| SEC-17 | avatar/스테이징 | "staging" 배포가 프로덕션 얼굴사진 버킷을 바인딩하며 프로덕션 가드 비활성(dry_run/flux/QA bypass 허용 가능) | `scripts/staging_avatar_live_setup.ps1:284-310` | CONFIRMED (절차 활성 여부 확인 필요) |
| SEC-18 | 동의증빙 | 법적 동의 기록기가 누락/오류 값을 `fallback:true`(동의함)로 기록 → 증빙 무결성 약화 | `user_service.dart:118-158` | CONFIRMED |

## P3 (요약)

- SEC-P3-01 대나무숲 `score7d` + like/commentCount 클라 증분 → 랭킹 조작 (`firestore.rules` bamboo update 분기, `bambooPostCounterUpdateOk`) `[verified]` ⁵
- SEC-P3-02 season-meeting `photoBlurUnlocked` 참가자 단독 클라 쓰기 (`firestore.rules:954-964`)
- SEC-P3-03 `emailLinkTokens` world-readable(의도, PII-in-URL 경계) (`firestore.rules:41`)
- SEC-P3-04 avatar 승인이 `candidate.imageRef`의 uid 바인딩 미검증(방어심층) (`avatarApproval.ts:186-195`)
- SEC-P3-05 워커 shared-secret 비교가 비상수시간 `!=` (`worker_service.py:146-151`)
- SEC-P3-06 `/readyz` 무인증 운영정보 노출 (`worker_service.py:321-324`)
- SEC-P3-07 이메일링크 `expiresAt`가 클라 시계·rules 상한 없음 (`student_verification_screen.dart:340`)
- SEC-P3-08 CLIP cold-start 경로에서 Firestore 차단엣지 미로딩 (`seolleyeon_clip_train_export_v3.py:356-368`)
- SEC-P3-09 `FORCE_APP_CHECK_DEBUG` dart-define이 릴리스에서 debug provider 선택 가능(파이프라인만 가드) (`app_check_provider_policy.dart:31-45`)

### Tier 2 상태 각주 (현재 코드 기준)

- ¹ **SEC-03**: 규칙은 이미 `lastUid==request.auth.uid` 를 강제 → 타인 명의 위조
  불가. 잔여(공개 코드로 자기자신 재귀속)는 근본이 커밋된 bearer 코드이며,
  immutable-first-binding 은 익명 재입장 파손·pre-claim 그리핑을 유발해 회귀
  위험. 강제 가능한 불변식만 규칙 테스트 19건으로 고정. 근본 해소 = 입장코드
  회전(EXTERNAL, STOP #5). 참고: `festival_web/firestore.rules`
  `canUpdateFestivalTicket`(~253-260)가 최신 위치.
- ² **SEC-04**: CONFIRMED 유지. 규칙은 read 필드 마스킹 불가 → authorId 물리
  제거 필요. private 매핑 스키마 + "내가 쓴 글"/소유권/서버(계정삭제·댓글알림)
  재설계 + **기존 데이터 마이그레이션** + 구클라 강제업데이트가 얽힌 대규모
  breaking 변경(STOP #3). 설계 + dry-run 스크립트(`scripts/bamboo_anonymize_migration.mjs`,
  에뮬레이터 검증)만 산출. 미적용/미마이그레이션. `firestore_community_repository.dart`
  현재 라인: 게시 44, 소프트삭제 172-181.
- ³ **SEC-08**: SOURCE_FIXED. storage.rules read 를 소유자(uid==auth.uid)로 제한
  (storage 규칙 테스트 13건). 상대 사진 열람은 토큰 URL 로 회귀 없음. Firestore
  `festivalProfiles` 브로드 read 는 클라 라이브 추천 엔진 의존이라 미변경(감사
  범위 밖, SEC-03 근본에 종속). 미배포.
- ⁴ **SEC-09**: SOURCE_FIXED. 3종 `invoker: "private"` + 하드코딩 시크릿 제거
  (`admin_http_guard.ts`, env 주입). functions 테스트 9건. 배포·시크릿 회전은
  EXTERNAL(미수행). 하드코딩 시크릿 값은 이미 공개(커밋)로 간주.
- ⁵ **SEC-P3-01**: SOURCE_FIXED. 카운터 분기에 `bambooLikeCountBound`(like 문서
  전이 결합) + `bambooScore7dMovesWithCounters`(score7d 단독 이동 금지). rules
  테스트 15건. 잔여: commentCount 는 랜덤 id 로 결합 불가(±1 게이트 유지) →
  서버 트리거 후속. 미배포.

## 방어가 확인된(문제 아님) 주요 항목

users 문서 필드 allowlist(diff().hasOnly), 서버전용 컬렉션 deny-all, 아바타 원본 EXIF 제거·signed URL 부재·uid-bound refs·fail-closed QA·해시 로깅, PortOne/Kakao 고정 호스트(SSRF 없음), 추천 output에서 private/signed ref 거부·isSelf 게이트, 탈퇴 서버 오케스트레이션 fail-closed, 리포트+차단 서버 owned. 상세는 각 도메인 부록.
