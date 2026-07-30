# G007 AI Slop Cleanup Report

Date: 2026-07-28

## Scope

G006/G007에서 실제로 변경된 통합 경계만 정리했다. 아바타 모델·QA 알고리즘은 검증 범위로 유지하고 확인되지 않은 구조 변경은 하지 않았다.

- 팀 미팅 callable, 읽기 세션, pair-level pending lock
- 승인 아바타 공개 URL 검증 경계
- Flutter 공개 프로필 이미지 resolver와 source lock UI
- 클라이언트 로그와 privacy scanner
- Firestore/Storage rules 및 필요한 indexes

## Behavior Lock

- 팀 미팅 쓰기는 callable만 수행하고 같은 팀 쌍의 pending 요청은 하나만 유지한다.
- deterministic/legacy pending 요청 모두 request와 pair lock이 같은 `pairLockId`로 복구된다.
- promise 메시지 lifecycle update는 원래 `senderId`를 변경할 수 없다.
- private source/temp/chat-photo URL은 프로젝트 prefix와 무관하게 공개 아바타로 사용하지 않는다.
- 승인 이후 아바타 변경·삭제를 계속 차단한다.
- hard-reject 후보와 private source 정보는 사용자에게 노출하지 않는다.

## Cleanup Passes

1. Dead code와 미사용 import/field를 제거했다.
2. Functions 공개 아바타 URL 검증을 `publicMediaUrlPolicy.ts`로 통합했다.
3. team pair-lock, Firebase read-session, client system-message writer 제거, raw identity log 제거를 적용했다.
4. festival/arbitrary-prefix private URL, pair-lock repair, session helper, log alias, widget smoke 회귀 테스트를 추가했다.
5. 중앙 error summary만 허용하고 index/chat/approval URL 정책 drift를 제거했다.
6. 최종 리뷰에서 발견된 sender spoofing, Python recommendation URL, deterministic legacy repair, built scanner prefix 문제를 수정했다.

## Post-cleaner Quality Gates

- Flutter analyze: `PASS`, 0 issues.
- Flutter full tests: `102/102 PASS`.
- Flutter web debug build: `PASS`.
- Functions TypeScript build: `PASS`.
- Functions tests: `126/126 PASS`.
- Python compileall: `PASS`.
- Python tests: `545 passed, 6 skipped`.
- Privacy QA: `PASS`, 238 files, leakage counters all zero.
- `git diff --check`: `PASS`; CRLF normalization warnings only.

## Staging Result

- Guard: account `seolleyeon.official@gmail.com`, gcloud/Firebase project `seolleyeon-final`.
- Firestore Rules: 최신 sender immutability 규칙까지 컴파일·배포 완료.
- `createTeamMeetingRequest`: 최신 pair-lock self-heal 수정 배포 후 `ACTIVE` (`asia-northeast3`).
- 앞서 선택 배포한 `respondTeamMeetingRequest`, `getChatRealProfilePhoto`, `approveAvatarCandidate`는 staging에 유지된다.
- Worker: `seolleyeon-avatar-worker-00047-9qx`, 이번 cleanup에서 미변경.
- Production/source project mutation: 없음.

## Remaining Risks

- exact-consent 10인 최신 QA calibration은 staging App Check token exchange 403 때문에 실행하지 못했다. App Check는 우회하지 않았다.
- Node.js 20 decommission 일정과 구버전 `firebase-functions`는 별도 호환성 PR이 필요하다.
- 독립 최종 판정: code review `APPROVE`, architecture review `CLEAR`.
- Production-ready는 `false`다.