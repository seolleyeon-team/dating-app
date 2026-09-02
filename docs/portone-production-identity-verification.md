# 포트원 KG이니시스 통합인증 운영 설정

이 앱은 본인인증을 마친 뒤에만 카카오 로그인을 시작하고, 로그인 후
Firebase Callable Function이 포트원 API에서 인증 결과를 다시 확인한다.

## iOS Xcode 영구 설정

한 번만 아래 스크립트를 실행하면, 입력한 실 통합인증 채널 키가 Git에
포함되지 않는 `ios/Flutter/Local.xcconfig`에 저장할 수 있다. 이 파일은 이미
Debug, Profile, Release 설정 모두에서 불러오므로 그 다음부터는 Xcode에서
평소처럼 `Runner.xcworkspace`를 열어 Archive 하면 된다.

```bash
zsh scripts/configure_ios_portone_identity_channel.sh
```

프롬프트에 포트원 실 Channel Key만 입력한다. 입력 글자는 표시되지 않는 것이
정상이다. 운영 Channel Key는 앱 바이너리에 포함되는 공개 클라이언트 식별자이므로
`PortOneConfig`에도 휴대 가능한 기본값이 있으며, `Local.xcconfig`의 dart-define은
개발/스테이징 채널로 덮어쓸 때 사용한다. `Local.xcconfig` 또는 Xcode Build
Settings에 API Secret을 넣으면 안 된다.

## 다른 빌드 환경의 운영값 주입

앱 빌드에는 포트원 콘솔에서 만든 **실 통합인증 채널 키**를 전달한다.

```bash
flutter build ipa \
  --dart-define=PORTONE_KG_INICIS_IDENTITY_CHANNEL_KEY='실-채널-키'
```

Android 배포 빌드도 같은 `--dart-define` 값을 사용한다. Android Studio에서
실행할 때는 Run Configuration의 Additional run args에 동일한 define을 한 번
등록할 수 있다. 채널 키를 소스, 커밋, 또는 일반 로그에 넣지 않는다.

`PORTONE_STORE_ID`는 현재 포트원 대표 상점의 Store ID와 일치해야 한다.
다른 상점을 사용하면 동일한 방식으로 `--dart-define=PORTONE_STORE_ID=...`
를 전달한다.

## 서버 API Secret

포트원 V2 API Secret은 Firebase Secret Manager에만 보관한다.

```bash
npx -y firebase-tools@latest functions:secrets:set PORTONE_API_SECRET --project seolleyeon-final
firebase deploy --only functions:verifyAdultIdentityAfterLogin --project seolleyeon-final
```

명령 실행 중 Secret 값은 터미널 입력 프롬프트에서만 입력한다. 앱 코드,
`.env` 파일, Firebase 클라이언트 설정, Git에는 넣지 않는다.

## 배포 전 확인

1. 운영 채널 키로 빌드했는지 확인한다.
2. `PORTONE_API_SECRET`을 설정한 뒤 검증 함수를 배포한다.
3. 약관 동의 → 본인인증 → 카카오 로그인 → 서버 검증 흐름을 실기기에서 시험한다.
4. 인증 취소, 실패, 미성년, 동일 CI의 다른 카카오 계정 가입 시도를 확인한다.

`ADULT_VERIFICATION_BYPASS=true`는 로컬 디버그 확인 외에는 사용하지 않는다.
