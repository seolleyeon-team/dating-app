> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md).
>

# 설레연 AI 아바타 프로필 변환 production 구현 결과

Date: 2026-07-28

## 1. 결론

- 상태: `PASS_PARTIAL`
- repository implementation/integration: `PASS`
- staging selective deployment: `PASS`
- production-ready: `false`
- public rollout executed: `false`
- final independent review: code `APPROVE`, architecture `CLEAR`

코드, 테스트, staging 배포는 현재 계약에 맞게 정리했다. 다만 exact-consent 10인 최신 QA calibration과 정상 App Check 실사용 호출 증거가 없으므로 production-ready로 판정하지 않는다.

## 2. 구현 상태

1. Flutter source selection/lock: 생성 시작 후 사진 교체·삭제를 차단하고 현재 job만 polling한다.
2. `uploadAvatarSourcePhoto`: 승인 lock/source lock을 서버에서 검사하고 private source와 current source-job 계약을 유지한다.
3. Worker: current source/job 검증, small-face fallback, primary selection, expanded crop, neutralized reference, trait extraction, FLUX 생성, QA/rerank를 수행한다.
4. Preview/approval: preview-safe 후보만 반환하고 승인 후보만 공개 bucket으로 복사한다.
5. Public display: 승인 아바타만 사용하며 private/temp/chat-photo URL과 `onboarding.photoUrls` fallback을 거부한다.
6. Privacy: raw landmarks/embeddings와 private refs를 Flutter/public docs에 노출하지 않는다.
7. Team meeting: callable-owned write, pair-level pending lock, protected read session을 적용했다.
8. Promise lifecycle: 원래 sender identity는 변경할 수 없다.

## 3. 확인된 문제와 수정

- final/festival 및 임의 prefix private URL 누락: 공통 backend 정책, Python runtime resolver, Flutter resolver, built-output scanner를 보강했다.
- 팀 미팅 pending 중복 race: 원자적 `eventTeamMeetingRequestLocks/{pairLockId}`를 추가했다.
- legacy/deterministic pending 복구 불일치: request와 lock 모두 같은 `pairLockId`로 self-heal한다.
- promise sender spoofing: lifecycle update에서 `senderId`를 변경 불가능하게 했다.
- client system sender write와 raw identity debug log를 제거했다.
- privacy scanner의 local redactor 자동 신뢰와 알려진 project prefix 의존성을 제거했다.
- Flutter test 장기 대기는 SDK cache lock/초기화 경계로 분리했고 전체 테스트가 정상 종료됨을 확인했다.

## 4. 검증 결과

- Flutter analyze: `PASS`, 0 issues.
- Flutter tests: `102/102 PASS`.
- Flutter web debug build: `PASS`.
- Functions build: `PASS`.
- Functions tests: `126/126 PASS`.
- Python tests: `545 passed, 6 skipped`.
- Privacy QA: `PASS`, 238 files, leakage 0.
- Client forbidden-marker grep: 0 matches.
- Diff check: `PASS` (line-ending warnings only).

## 5. Staging 배포

- 프로젝트: `seolleyeon-final`.
- Functions region: `asia-northeast3`.
- Firestore Rules: 최신 규칙 배포 완료.
- 최신 수정 함수: `createTeamMeetingRequest`, `ACTIVE`, update time `2026-07-27T20:42:19.625308346Z`.
- 앞서 선택 배포한 함수: `respondTeamMeetingRequest`, `getChatRealProfilePhoto`, `approveAvatarCandidate`.
- Avatar worker: 기존 revision `seolleyeon-avatar-worker-00047-9qx` 유지.
- Production/source project 변경: 없음.

## 6. 남은 blocker

- staging App Check token exchange 403을 정상 설정으로 해결하고 exact-consent fresh 10인 calibration을 재실행해야 한다.
- 최신 cohort에서 QA tier, trait coverage, text/logo watch item, payload, p50/p95 비용·시간을 확정해야 한다.
- Node.js 20 decommission 전에 Functions runtime과 `firebase-functions`를 별도 검증 PR로 업그레이드해야 한다.
- production rollout은 별도 승인과 production gate 검증 전까지 금지한다.

설레연 아바타 생성은 source upload부터 approved avatar lock까지 currentAvatarSourcePhotoId/currentAvatarJobId 계약을 기준으로 수행되며, hard-reject 후보와 private source 정보는 사용자에게 노출되지 않아야 한다.
