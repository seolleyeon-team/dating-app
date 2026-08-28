# 학생 인증 메일 커스텀 발송 설정

학생 인증은 여전히 Firebase Auth의 이메일 링크를 사용한다. 다만 앱이 직접
`sendSignInLinkToEmail`을 호출하지 않고, `sendStudentVerificationEmail`
Cloud Function이 Firebase Admin SDK로 링크를 만든 다음 Resend로 보낸다.

## 배포 전 필수 설정

1. Resend에 서비스가 소유한 발신 서브도메인을 추가한다. 예:
   `notify.<서비스 도메인>`. Resend가 표시하는 SPF·DKIM·MX 레코드를 DNS에
   **그대로** 추가하고, 기존 SPF TXT 레코드가 있다면 두 SPF 정책이 공존하도록
   합친다. 확인 뒤에는 DMARC를 `p=none`부터 관찰하고 점진적으로 강화한다.
   구체적인 레코드 값은 도메인마다 다르므로 이 저장소에 적지 않는다.
2. Resend 대시보드에서 도메인 상태가 `Verified`인지 확인한다. 검증 전에는
   실사용자에게 발송하거나 배포하지 않는다.
3. Firebase Secret Manager에 Resend API 키를 추가한다. 이 키는 앱 코드,
   Firestore, 일반 환경 파일에 넣지 않는다.

```sh
npx -y firebase-tools@latest functions:secrets:set RESEND_API_KEY --project seolleyeon-final
```

4. `functions/.env.seolleyeon-final`에 발신 주소만 설정한다. 이 파일에는 비밀을
   넣지 않는다. 실제 도메인 인증 전에는 배포하지 않는다.

```dotenv
RESEND_FROM_EMAIL="설레연 <auth@notify.example.com>"
RESEND_REPLY_TO="support@example.com"
```

5. Firebase Console의 Android 앱(`com.seolleyeon.app`)에 실제 배포 서명 키의
   SHA-1 및 SHA-256 지문이 모두 등록되어 있는지 확인한다. Android 이메일 링크는
   `seolleyeon-final.firebaseapp.com`의 `/__/auth/links` 경로로 앱을 연다.
   Firebase Authentication의 모바일 링크 도메인도 이 Firebase Hosting 도메인으로
   설정하고, 실제로 생성된 인증 링크의 호스트가 동일한지 확인한다.
6. Functions, Firestore 규칙, Hosting을 배포한다.

```sh
npx -y firebase-tools@latest deploy --only functions:sendStudentVerificationEmail,firestore:rules,hosting --project seolleyeon-final
```

7. 배포 후 아래 URL이 리디렉션 없이 JSON을 반환하는지 확인한다. `assetlinks.json`의
   SHA-256은 Play App Signing을 쓴다면 로컬 디버그 키가 아니라 Play Console의
   **앱 서명 인증서** 지문이어야 한다.

```text
https://seolleyeon-final.firebaseapp.com/.well-known/assetlinks.json
```

## 운영 안전장치

- App Check와 Kakao-backed Firebase 세션이 모두 있어야 요청할 수 있다.
- 수신 이메일 주소별로 최근 1분 최대 2회, 최근 24시간 최대 10회만 발송한다.
  이 한도는 서버 트랜잭션으로 적용하며, IP 헤더처럼 위조 가능한 클라이언트 값은
  신뢰하지 않는다. 함수는 최대 3개 인스턴스·인스턴스당 동시 요청 10개로 제한된다.
- Firebase action link는 Resend API의 24시간 idempotency key와 함께 보낸다.
  네트워크 재시도가 같은 요청을 중복 메일로 만들지 않게 한다.
- 서버는 전송을 수락한 뒤 Firebase action link를 자체 요청 문서에서 즉시 삭제한다.
  로그에는 이메일·인증 링크·Resend 응답 본문을 남기지 않는다.
- Resend 대시보드에서 `email.bounced`, `email.complained`,
  `email.delivery_delayed`를 정기적으로 확인한다. 인증 메일의 클릭 추적·URL
  단축은 켜지 않는다. Firebase가 생성한 URL을 원본 그대로 버튼에 넣어야 한다.

## 출시 확인

1. 테스트용 `@yonsei.ac.kr` 주소로 발송해 제목이 `설레연에서 온 인증 메일`인지
   확인한다.
2. 테스트용 연세 메일함의 웹·모바일 메일 클라이언트에서 SPF/DKIM/DMARC 결과와
   스팸함 유입을 확인한다. 이 기능은 `@yonsei.ac.kr` 주소만 발송 대상이다.
3. Android 실기기에서 메일 버튼을 눌러
   `https://seolleyeon-final.firebaseapp.com/__/auth/links` 링크가 브라우저가 아닌
   앱을 열고 인증을 완료하는지 확인한다. 앱이 없는 기기에서는 기존
   `https://seolleyeon-final.web.app/auth/email-link` 웹 인증 화면으로 진행되는지도
   확인한다.
4. 1분 내 세 번째 재발송, 24시간 내 열한 번째 발송, App Check 없는 호출, 다른 Firebase 세션 호출이 모두
   거부되는지 확인한다.
