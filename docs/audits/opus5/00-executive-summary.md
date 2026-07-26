# 00 — 총괄 요약 (Opus 5 감사)

작성 시각: 2026-07-27
감사 범위: 설레연(Seolleyeon) 저장소 전체 대상 정적 분석 (부분 커버리지)

## 전체 판정

```
BLOCKED
```

판정 근거는 두 가지다.

1. **검증 환경 부재.** 셸 실행이 불가하여 기준선 측정, 정적 분석, 테스트,
   에뮬레이터 기반 규칙 검증, 빌드를 **하나도 수행하지 못했다** (03-baseline-results.md).
   §19가 요구하는 "재현 테스트 → 수정 → 통과 확인" 절차를 밟을 수 없으므로
   보안 수정을 적용하지 않았다.
2. **P0 취약점 4건 미수정.** 그중 SEC-P0-01은 인증 없이 임의 사용자 계정을
   완전히 탈취할 수 있는 경로이며, 코드 근거상 확정적이다.

## 즉시 대응이 필요한 사항

### SEC-P0-01 — 비인증 임의 계정 탈취 (최우선)

`emailLinkTokens` 컬렉션에 누구나 임의 문서를 만들 수 있고
(`firestore.rules:12-21`, `request.auth` 검사 없음),
`createFirebaseCustomTokenFromEmailLinkToken`이 그 문서의 존재만으로
해당 `kakaoUserId`의 Firebase custom token을 발급한다
(`functions/src/index.ts:1498-1607`, 인증·App Check 없음).
게다가 `users` 컬렉션이 비인증 전체 조회 가능하므로
(`firestore.rules:433-434`) 공격에 필요한 피해자 UID와 `studentEmail`을
그대로 얻을 수 있다.

세 조건이 맞물려 **인증 없는 완전 계정 탈취**가 성립한다.
운영 프로젝트(`seolleyeon-final`)가 이 규칙과 함수로 동작 중이라면
현재 실사용자가 노출된 상태다.

상세: 04-security-findings.md의 SEC-P0-01.

### 나머지 P0

- **SEC-P0-02**: 비인증 상태로 임의 UID에 `users` 문서 생성 가능,
  `isStudentVerified: true` 직접 기입 가능 → 학교 인증 무력화.
- **SEC-P0-03**: 연세 이메일 보유자가 타인 문서의 `studentEmail`을 자신 것으로
  덮어써 소유권을 획득 가능 → 프로필 탈취.
- **SEC-P0-04**: `users` 컬렉션 전체 비인증 read/list → 학교 이메일·프로필·
  취향 벡터 대량 수집 가능.

네 건 모두 `firestore.rules`의 `users` 및 `emailLinkTokens` 블록에 집중되어 있다.
이 파일 하나가 현재 가장 큰 위험 표면이다.

## 이번 감사에서 실제로 수행한 것

- `firestore.rules` 전체 1011줄 정독 및 규칙별 악용 경로 분석
- `storage.rules` 전체 정독 (결과: 클라이언트 쓰기 전면 차단, 승인 아바타만 공개 읽기 — 설계가 견고함)
- Cloud Functions 35개 export 인벤토리 및 인증/App Check/검증/소유권 매트릭스 작성
- Python 추천 파이프라인 오케스트레이션·데이터 경로·후보 필터링 정확성 분석
- P0 승격 항목 전부 원문 재확인
- 감사 문서 4종 작성

## 이번 감사에서 수행하지 않은 것

- **코드 수정 전무.** 검증 수단이 없는 상태에서 보안 규칙과 인증 함수를
  고치는 것은 §29 금지 사항("테스트 없이 보안 수정 완료 주장")에 해당하고,
  잘못 고치면 전체 로그인이 막히는 등 더 큰 장애를 만든다.
- 기준선/테스트/빌드/에뮬레이터 검증
- Git 커밋 (셸 불가)
- 네이티브 설정, 의존성 CVE, 축제 웹, 운영 스크립트 조사 (02-read-coverage.md의 공백 목록)

## 다음 단계 (권장 순서)

1. **셸 환경 복구.** Cursor 터미널 재시작 후 `git status`가 동작하는지 확인.
2. **기준선 확보.** `flutter analyze`, `flutter test`, `functions` 빌드·테스트 실행.
   현재 실패가 있는지, 어디까지가 기존 실패인지 먼저 확정한다.
3. **에뮬레이터 기반 Rules 테스트 도입.** 현재 `firestoreRules.test.ts`는
   규칙 파일을 문자열로 grep하는 정적 테스트일 뿐 allow/deny를 평가하지 않는다.
   `@firebase/rules-unit-testing`을 도입해야 SEC-P0-01~04를 안전하게 고칠 수 있다.
4. **SEC-P0-01 수정.** 재현 테스트 → 규칙·함수 수정 → 통과 확인 → 커밋.
5. **SEC-P0-02/03/04 수정.** `users` 규칙 재설계. 앱 다수 화면에 영향을 주므로
   characterization test를 먼저 작성한다.
6. 이후 P1 순차 처리.

## Production Readiness

현 시점 판정은 **NOT_READY**다.
근거는 P0 4건 미수정과 검증 부재이며, 상세 항목별 판정은
셸 복구 후 12-production-readiness.md에 작성해야 한다 (현재 미작성).
