# Firestore 보안 규칙 테스트

`firestore.rules`를 **실제 규칙 엔진(Firebase Emulator Suite)** 에 로드해서
allow/deny를 평가하는 테스트다.

`functions/src/firestoreRules.test.ts`와 혼동하지 말 것. 그쪽은 규칙 파일을
문자열로 grep하는 정적 검사라서, 규칙이 문법적으로 존재하는지만 보고
"실제로 누가 무엇을 할 수 있는가"는 전혀 검증하지 못한다.

## 실행

Firestore 에뮬레이터는 JRE가 필요하다. Windows에서 별도 JDK가 없으면
Android Studio 번들 JBR을 쓰면 된다.

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio1\jbr"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

npm --prefix rules_tests install
firebase emulators:exec --only firestore --project seolleyeon-rules-test `
  "npm --prefix rules_tests test"
```

`--project seolleyeon-rules-test`는 운영 프로젝트(`seolleyeon-final`)에
절대 붙지 않게 하려는 것이다. 이 값을 실제 프로젝트 ID로 바꾸지 마라.

## 테스트가 표현하는 것

파일마다 두 종류의 테스트가 섞여 있다.

- `SEC-*` — 막혀 있어야 하는 공격 경로. 규칙이 느슨해지면 즉시 빨개진다.
- `legit:` / `cross-user:` — 앱이 실제로 수행하는 정상 동작의 특성화 테스트.
  규칙을 조이다가 앱을 망가뜨리면 여기가 빨개진다.

보안 수정 시 두 종류가 **모두** 초록이어야 한다.
