# 설레연 Android AAB 빌드 안내

이 문서는 Google Play에 올릴 **production AAB**를 새 업로드 키로 빌드하기 위한 안내입니다.

## 전달받아야 하는 것

1. `seolleyeon-upload-2026-08-29.jks`
2. `key.properties.friend.template`
3. 키스토어 비밀번호(`storePassword`) — 키 파일과 다른 채널로 전달받기
4. 키 비밀번호(`keyPassword`) — 키 파일과 다른 채널로 전달받기

`upload_certificate.pem`은 AAB 서명에 사용하지 않습니다.

## 파일 배치

1. `seolleyeon-upload-2026-08-29.jks`를 프로젝트의 `android/app/` 안에 넣습니다.
2. `android/key.properties.friend.template`을 `android/key.properties`로 복사합니다.
3. 새 `android/key.properties` 안의 비밀번호 자리 두 곳을 전달받은 실제 비밀번호로 바꿉니다.

`android/key.properties`와 `.jks` 파일은 Git에 커밋하거나 채팅에 올리지 마세요.

## AAB 빌드

프로젝트 최상위 폴더에서 실행합니다.

```bash
flutter pub get
flutter build appbundle --flavor production --release
```

정상적으로 만들어지면 파일 위치는 다음과 같습니다.

```text
build/app/outputs/bundle/productionRelease/app-production-release.aab
```

## 업로드 전 서명 확인

```bash
python3 scripts/verify_android_release_signing.py
```

Google Play에 등록된 새 업로드 키의 SHA-1은 다음 값입니다.

```text
09:70:03:EA:43:37:BD:D4:6E:47:6E:E9:04:E4:03:15:D5:25:54:C9
```

검사 결과가 `B2:82:...:AE`라면 기존 키로 잘못 서명된 것이므로 업로드하면 안 됩니다.

## Play Console 업로드

위 SHA-1로 서명된 `app-production-release.aab`만 업로드합니다. 버전 코드가 기존 업로드보다 커야 합니다.

