# 온보딩 관심사 손상 점검 및 복구 처리

## 목적

키워드 저장 과정에서 `onboarding.interests`가 빈 배열로 저장된 기존 사용자 규모를
읽기 전용으로 확인한다. 점검 스크립트는 `users` 문서를 조회만 하며, Firestore
데이터를 수정하거나 사용자 ID·관심사 원문을 출력하지 않는다.

## 탐지 조건

다음 조건을 모두 만족하는 문서를 영향 후보로 센다.

1. `onboarding.keywords` 필드가 존재하거나 `initialSetupComplete == true`
2. `onboarding.interests`가 누락·`null`·빈 배열이거나 배열이 아닌 잘못된 타입

출력 카운터의 `missingInterests`, `emptyInterests`, `invalidInterests`는 후보 중
각 상태의 개수다. `hasKeywords`와 `onboardingCompleted`는 전체 스캔 문서 기준이다.

## 실행

기본 실행은 에뮬레이터에서만 허용된다.

```powershell
firebase emulators:exec --only firestore --project seolleyeon-onboarding-audit-test `
  "node scripts/audit_onboarding_interests.mjs --project seolleyeon-onboarding-audit-test"
```

운영 데이터는 프로젝트 ID, Admin 서비스 계정 파일, 읽기 전용 조회 허용 플래그를
모두 명시해야 한다. 기본값은 에뮬레이터 전용이며, 서비스 계정 파일의 내용이나
사용자 ID는 출력하지 않는다. 페이지네이션·재시도·오류 카운터도 결과에 포함된다.

```powershell
node scripts/audit_onboarding_interests.mjs `
  --project seolleyeon-final `
  --credentials C:\\path\\service-account.json `
  --allow-production-read
```

운영 데이터에 대해 실제 실행한 적은 없다.

## 기존 사용자 처리

이미 `interests`가 빈 배열로 덮인 경우 현재 코드만으로 원래 선택값을 복원할 수
없다. 자동 추정·자동 복구를 하지 않고, 로그인 후
`AuthService.getOnboardingNextRoute()`가 관심사 선택 화면으로 보내 사용자가 다시
선택하도록 한다. 관심사를 저장하면 이후 키워드 저장은 `onboarding.keywords`만
갱신하므로 재손실되지 않는다.
