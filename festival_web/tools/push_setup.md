# Festival Web Push 설정

## 1. Firebase Console에 VAPID 키 등록

1. [Firebase Console](https://console.firebase.google.com/project/seolleyeon-festival/settings/cloudmessaging) → 프로젝트 설정 → Cloud Messaging
2. **웹 푸시 인증서** → 키 쌍 추가
3. `lib/push_config.dart`의 `kFestivalWebVapidKey`와 **동일한 공개 키**를 등록

현재 앱에 설정된 공개 키:

```
BGuEGPcYI67BRhMd0VZL-_hn3xpBxZXSL2dKE7mRl6LJC_G5BQT7IRNDYr8JAaDEO-1ZA1goewEfWjtYbsgkeCU
```

## 2. 배포

```bash
cd festival_web/functions && npm install && npm run build
cd .. && flutter build web --release
npx firebase-tools@latest deploy --only hosting,functions,firestore:rules
```

## 3. 동작 요약

| 환경 | 조건 |
|------|------|
| Android Chrome / Samsung Internet | 브라우저에서 알림 허용 시 푸시 수신 |
| iPhone Safari | **홈 화면에 추가한 PWA**에서만 푸시 수신 |

새 채팅 메시지가 저장되면 Cloud Function이 `새 메시지가 왔습니다` 푸시를 전송합니다.
