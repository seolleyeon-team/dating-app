# 카카오 Android 키 해시 등록

`Android keyHash validation failed` 오류가 발생하면 아래 순서로 키 해시를 등록하세요.

## 1. 키 해시 확인 방법

### 방법 A: 앱에서 확인 (권장)
- 로그인 시도 후 오류가 나면 **키 해시 등록 필요** 다이얼로그가 표시됩니다.
- 표시된 키 해시를 길게 눌러 복사한 뒤, 아래 2번 단계로 등록하세요.

### 방법 B: 터미널에서 확인 (디버그 빌드)
```bash
keytool -exportcert -alias androiddebugkey -keystore ~/.android/debug.keystore -storepass android 2>/dev/null | openssl dgst -sha1 -binary | openssl base64
```

### 방법 C: 릴리즈 키 해시 (스토어 배포용)
릴리즈 keystore가 있다면:
```bash
keytool -exportcert -alias YOUR_ALIAS -keystore /path/to/your.keystore | openssl dgst -sha1 -binary | openssl base64
```

## 2. 카카오 개발자 콘솔에 등록

1. [카카오 개발자 콘솔](https://developers.kakao.com/console/app) 접속
2. 해당 앱 선택
3. **앱 설정** → **플랫폼** → **Android** 선택
4. **키 해시** 항목에 위에서 확인한 값을 추가
5. **저장** 클릭

## 3. 디버그용 기본 키 해시 (참고)

일반적인 Flutter 디버그 빌드의 키 해시 예시:
```
3VW3zKZZTlmgqgrBGdoYaMd911k=
```

※ 실제 사용 중인 keystore에 따라 값이 다를 수 있습니다. **앱에서 표시되는 값을 사용**하세요.
