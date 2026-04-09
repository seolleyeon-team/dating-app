# 카카오 로그인 웹(Chrome) 설정 가이드

`javascript env validation failed` 오류는 **카카오 개발자 콘솔**에서 웹 도메인이 등록되지 않았을 때 발생합니다.

## 1. 카카오 개발자 콘솔 설정 (필수)

1. [카카오 개발자 콘솔](https://developers.kakao.com/console/app) 접속
2. 해당 앱 선택 → **앱 설정** → **플랫폼** → **웹** 선택
3. **플랫폼 키** → **JavaScript 키** → **키 설정** 클릭
4. **JavaScript SDK 도메인**에 아래를 추가:
   - 로컬 개발: `http://localhost:포트번호` (예: `http://localhost:8080`, `http://localhost:53573`)
   - Firebase Hosting: `https://seolleyeon.web.app`
   - 필요 시 추가: `https://seolleyeon.firebaseapp.com`
   - 커스텀 도메인 사용 시: `https://yourdomain.com`
5. **Redirect URI**에 아래를 추가:
   - `JS-SDK` (Flutter SDK 웹 로그인용)
   - 로컬: `http://localhost:포트번호/` (실제 사용 포트로 변경)
   - Firebase Hosting: `https://seolleyeon.web.app/`
   - 필요 시 추가: `https://seolleyeon.firebaseapp.com/`
   - 커스텀 도메인 사용 시: `https://yourdomain.com/`
6. **저장** 클릭

> ⚠️ Flutter 웹 실행 시 사용하는 포트를 확인하세요. (VS Code launch 설정: 57575, 기본: 8080 또는 터미널에 표시된 포트)

## 2. 웹 실행

Flutter 3.24+에서는 `--web-renderer` 옵션이 제거되었습니다. 기본 렌더러(CanvasKit)로 실행됩니다.

```bash
flutter run -d chrome
```

또는 빌드 시:

```bash
flutter build web
```

> 카카오 Flutter SDK가 CanvasKit과 호환성 이슈가 있다면, Flutter 및 kakao_flutter_sdk 최신 버전으로 업데이트해 보세요.

## 3. 포트 확인 방법

`flutter run -d chrome` 실행 시 터미널에 예시처럼 표시됩니다:

```
Launching lib/main.dart on Chrome in debug mode...
lib/main.dart is being served at http://localhost:53573
```

이 경우 **JavaScript SDK 도메인**에 `http://localhost:53573` 을,
**Redirect URI**에 `http://localhost:53573/` 을 등록하면 됩니다.
