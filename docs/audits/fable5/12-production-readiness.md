# 12 — Production Readiness (Fable 5, 2026-08-28)

판정: READY / READY_WITH_CONDITIONS / NOT_READY / NOT_ASSESSED. 각 판정은 오늘 코드·기준선 근거.

> **상태 갱신(Tier 1·2 이후)**: 이 표의 일부 행은 최초(수정 전) 스냅샷이다.
> Tier 1(SEC-05/11/18)·Tier 2(SEC-03/08/09/P3-01) source 수정이 working tree 에
> 적용되었고(미커밋·미배포) 로컬 검증됨. 아래 "festival"·"Firestore Rules"·
> "Cloud Functions"·"개인정보" 행에 각주로 현재 상태를 덧붙인다. 정본은
> `09`/`10`. **배포·IAM·시크릿회전·코드회전·SEC-04 마이그레이션은 미수행**이므로
> 어떤 대상도 "PRODUCTION_REMEDIATED" 로 승격하지 않는다.
>
> - **festival 웹/참가권**: 최초 NOT_READY 유지. SEC-08/09 는 source 수정+로컬
>   테스트(미배포), SEC-03 는 규칙이 위조는 차단하나 근본(공개 bearer 코드)은
>   코드 회전 필요(EXTERNAL). festival rules 테스트 0→32(firestore 19+storage 13).
>   배포·코드회전 전까지 NOT_READY.
> - **Firestore Rules(main)**: SEC-P3-01 카운터 무결성 source 수정+테스트(197 pass).
>   SEC-04(익명성)는 미해결(데이터 마이그레이션 대기) → 개인정보 트랙 NOT_READY 유지.
> - **Cloud Functions**: SEC-11(App Check 2 디스패처)·SEC-05(fail-closed) Tier 1
>   완료, 436 pass. 배포 전 App Check 실기기 smoke 필요(09 참조).
> - **개인정보 보호**: SEC-18 Tier 1 완료. SEC-01/02(git 추적)·SEC-04(익명성) 미해결
>   → NOT_READY 유지.

| 대상 | 판정 | 근거 / 배포 전 조건 |
|---|---|---|
| Flutter Android | READY_WITH_CONDITIONS | analyze 0, test 656 pass. 조건: FCM 수명주기(SEC-06/COR-01), 성인인증/안전스탬프 토글(SEC-14/15) 결정, apk 빌드 최종검증 |
| Flutter iOS | NOT_ASSESSED | Windows 환경 BLOCKED |
| Flutter Web | READY_WITH_CONDITIONS | XSS 표면 없음. 라우트 가드 dead-code(방어심층) |
| Firebase Auth / 학교인증 | READY | 이메일링크 원자적·서버 재검증, 구 bearer 경로 제거 확인 |
| Firestore Rules (main) | READY_WITH_CONDITIONS | 72 emulator pass. 조건: 채팅 차단/매칭 게이트(SEC-10), score7d(SEC-P3-01), recEvents 타임스탬프(SEC-13) |
| Storage Rules (main) | READY | deny-all 기반, IDOR 테스트 통과 |
| Cloud Functions | READY_WITH_CONDITIONS | 431 pass. 조건: App Check 2 디스패처(SEC-11), blindMeeting fail-open(SEC-05), 삭제 fail-open(FBK-03) |
| Cloud Run 추천 | READY_WITH_CONDITIONS | 181+정책테스트 pass. 조건: banned 제외(SEC-12), serving 경로(COR-03) |
| AI 아바타 파이프라인 | NOT_READY | 미커밋 WIP에 RED 16, claim 고착(SEC-07)·needs_review dead-end(COR-02). WIP 완료 필요 |
| 1:1 추천 | READY_WITH_CONDITIONS | COR-03 serving 불일치 |
| 채팅 | READY_WITH_CONDITIONS | SEC-10 차단게이트, COR-05 읽음처리 스케일 |
| 무물(asks) | READY | rules 참여자 스코프, 트리거 테스트 존재 |
| 신고·차단 | READY | reportAndBlockUser 서버 owned, 양방향 |
| 연락처 차단 | READY | 정규화 해시만 전송 |
| 개인정보 보호 | NOT_READY | SEC-01/02 PII git 추적, SEC-04 익명성 붕괴, SEC-18 동의기록 |
| **festival 웹/참가권** | NOT_READY | SEC-03 티켓 탈취, SEC-08 사진 스크래핑, SEC-09 공개 관리자 EP, rules 테스트 0 |
| 운영 모니터링 | NOT_READY | alerting 미구현(문서만 초안, OPS-09) |
| 백업·복구 | NOT_ASSESSED | repo 밖 |
| CI/CD | READY_WITH_CONDITIONS | 게이트 대체로 fail-fast. 조건: `||true` 제거, 아바타 테스트 게이트, predeploy 테스트 |
| dependency security | READY_WITH_CONDITIONS | 클라 공개키만, 하드코딩 서버 시크릿 미발견. node_modules 추적·미고정 의존성 |
| abuse prevention | READY_WITH_CONDITIONS | App Check 광범위. SEC-11 갭 |
| 관리자 기능 | READY | custom claims/서버전용 문서 기반(클라 필드 미의존) |
| 결제/가입권한 | READY_WITH_CONDITIONS | 결제 fail-closed(미설정 시 failed). PortOne production 여부는 코드 밖 |

## 전체

핵심 앱(Flutter+main Firebase+recsys)은 **조건부 준비**, festival 웹과 avatar 파이프라인·개인정보 트랙은 **NOT_READY**. 근거 없는 READY 없음. 실제 배포·App Check 강제·history rewrite는 외부 승인 항목.
