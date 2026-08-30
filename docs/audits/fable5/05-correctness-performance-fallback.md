# 05 — 정확성·성능·fallback 발견 (Fable 5, 2026-08-28)

## 정확성 (correctness)

| ID | 등급 | 문제 | 증거 |
|---|---|---|---|
| COR-01 | P1 | 신규/재로그인 사용자가 FCM 토큰 미등록 → 앱 재시작 전까지 푸시 수신 불가. `syncFcmToken()`이 죽은 레거시 스텁에서만 호출됨 | `kakao_auth_screen.dart` 로그인 경로, `auth_provider.dart:522` |
| COR-02 | P1 | avatar `needs_review`가 검토 도구 없는 terminal dead-end → QA 모델 불가 시 사용자 영구 고착(계정삭제 외 탈출 없음) | `worker.py:135-143,682-719`, `avatarMedia.ts:1211-1215` (미커밋) |
| COR-03 | P2 | 추천 serving 경로 불일치: 클라가 `dailyRecs`(dedup·다중소스 융합)가 아닌 raw 단일소스 `sources/svd`를 직접 읽음 → min_sources=2 게이트·최근노출 dedup 미적용, 같은 프로필 매일 재노출 | `ai_recommendation_service.dart:339-352`, `daily_job.py`(dailyRecs 미소비) |
| COR-04 | P2 | 프로필 공개 토글이 로드·저장 안 됨(순수 UI 스텁) → 사용자가 비공개로 바꿔도 추천에 계속 노출, 화면 열 때마다 리셋 | `settings_screen.dart:36,243` |
| COR-05 | P2 | 채팅 읽음처리가 스냅샷마다 전체 메시지 히스토리 `.get()` + 단일 batch → 500건 초과 시 batch 예외로 읽음영수증 영구 실패, 읽기증폭 | `chat_room_screen.dart:937`, `chat_service.dart:362-393` |
| COR-06 | P2 | 스플래시가 정지/밴 계정 라우팅 검사 없이 main 진입 가능(제재 검사는 병렬 provider에서 레이스) | `splash_screen.dart:108-127` vs `auth_provider.dart:137-153` |
| COR-07 | P3 | 시작 시 Firebase 세션 브릿지 2중 호출(스플래시+authProvider) → 중복 custom-token 발급, 느린 네트워크서 세션 레이스 | `auth_provider.dart:109`, `splash_screen.dart:93` |
| COR-08 | P3 | 빈 export가 SVD/KNN에서 치명 실패(`ValueError("No events loaded.")`)로 분류돼 워크플로 abort(정상 skip 대신). CLIP은 우아하게 처리 | `main.py:classify_subprocess_result`, `seolleyeon_svd_train_export_v3.py:354` |
| COR-09 | P3 | RRF 최종 tie-break에 안정키(uid) 없음 → 소스 순서 변경 시 동점 재정렬(현재는 우연히 결정적) | `seolleyeon_rrf_export.py:263-270` |
| COR-10 | P3 | 학생인증 후 흐름 전체가 `catch (_) {}`로 감싸져 실패 시 사용자에게 오류·로그 없이 화면 정체 | `student_verification_screen.dart:214-229,315-327` |
| COR-11 | P3 | 하트 잔액 화면 하드코딩 `20`, ChatRoom 라우트에 placeholder 영문 정체성(`'Kim Min-jun'`/`"Seoul Nat'l Univ"`) — 구매 비활성이라 금전 위험 없음 | `heart_charge_screen.dart:65`, `app_router.dart:255-263` |

## 성능·비용

| ID | 등급 | 문제 | 증거 |
|---|---|---|---|
| PERF-01 | P2 | avatar cost guard가 admission마다(job당 2회) `avatarJobs` 전체 컬렉션 stream → O(N), 히스토리 증가 시 안전장치가 비용/지연 병목 | `cost.py:446-448,340-379` |
| PERF-02 | P2 | 채팅 읽음처리 읽기증폭(COR-05와 동일 근원) + `messagesStream` 무제한 | `chat_service.dart:44-51,362-393` |
| PERF-03 | P3 | 하트 화면들이 build 내부에서 hydration future 재생성 → 스냅샷마다 새 future, 리스트 깜빡임 | `sent_hearts_screen.dart:245`, `received_hearts_screen.dart:241` |

## Fallback 인벤토리 (결정)

REMOVE/REPLACE = 위험, KEEP = 정당한 운영 fallback(로깅·telemetry 확인됨).

| ID | 위치 | 동작 | 위험 | 결정 |
|---|---|---|---|---|
| FBK-01 | `blindMeeting/store.ts:193-241` | 차단·제재 로드 실패 시 `[]`/`false` | P1 fail-open | **REPLACE** (rethrow=후보 제외) → SEC-05 |
| FBK-02 | `adult_verification_service.dart:42` | `verified` 위조 상태 릴리스 컴파일 | P1 | **REPLACE**(서버/RemoteConfig 플래그) → SEC-14, 제품결정 |
| FBK-03 | `avatarCleanup.ts:788-800`, `publicProfileSync.ts:174` | publicProfiles delete `.catch(()=>undefined)` 후 `completed` 기록 | P2 | **REPLACE**(로그+retryable) — 삭제 실패해도 프로필 노출 지속 |
| FBK-04 | `student_verification_screen.dart:214-229` | 인증 후 흐름 `catch(_){}` | P3 | **REPLACE**(logCaughtError+오류상태) |
| FBK-05 | `ai_recommendation_service.dart:107-124` | 오늘 rec 없으면 어제 dateKey 라벨 표시, roster-scan fallback은 이미 제거됨 | P3 | **KEEP** (라벨·serving guard 확인) |
| FBK-06 | `qa_runtime.py:86-97`, `worker.py:650-663` | visual-risk 불가 시 `unavailable`로 라벨링, QA 근거 강등 | P3 | **KEEP** (fail-closed·라벨 확인) |
| FBK-07 | `blindMeeting/payments.ts:71-102` | 프로덕션 결제 미설정 시 `status:failed`+error 로그, sandbox는 emulator만 | P3 | **KEEP** (fail-closed) — `refund()`가 `refund_pending`+금액0 반환, ops 알림 필요 |
| FBK-08 | `store.ts:110-121`, `meetingIcebreaker/store.ts:53-69` | 정책 로드 실패 시 컴파일 기본값+로그 | P3 | **KEEP** (feature-flag rollback) |
| FBK-09 | `premium_chat_list_screen.dart` fake room, `terms_screen` fake_user_1, `MockAvatarGenerationClient` | mock/placeholder | — | **KEEP**(dev/test 게이트 확인) 단 `MockAvatarGenerationClient`는 production 소스에 존재 → MOVE_TO_TEST_ONLY 권장 |

## Codex/dead-code 정리 후보 (참조검증 완료)

- `lib/screens/**`(13파일 ~1600줄) + `lib/routes/app_router.dart`(289줄): live 라우터는 `lib/router/app_router.dart`. `lib/routes/*`는 doc comment 1곳 외 참조 없음 → 죽은 레거시 스텁.
- `lib/shared/utils/legacy_stub_policy.dart`: 자기 파일 외 참조 0, 가드가 실제로 호출되지 않음.
- 6개 죽은 skeleton provider `lib/features/{matching,chat,event,profile,auth,onboarding}/providers/*`(fake-work TODO). live는 `lib/providers/*`.
- `seolleyeon-iniitial/`+`seolleyeon-initial/`: 바이트동일 firebase-init 스캐폴드(오타 중복), 미사용.
- 추적된 pytest 산출물: `g005_pytest_owned_escalated{,_2}/`, `pytest_tmp_avatar_qa_escalated/`.
- **보호(삭제 금지)**: `lib/features/event/screens/random_mathcing_screen.dart` — live 라우터 `app_router.dart:106`에서 실제 참조.

> dead-code 삭제 판단은 메모리 규칙상 router·deep link·push·backend·tests·git history 확인 필수. 위 후보들은 참조검증만 완료했고 실제 삭제는 별도 승인 하에 진행.
