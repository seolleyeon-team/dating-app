# iOS 하트 IAP: Xcode StoreKit Local Testing

이 구현은 하트 상품만 `in_app_purchase`로 처리합니다. 3:3 매칭 예약 보증금을 포함한 다른 결제에는 사용하지 않습니다.

## 로컬 구성

1. `ios/Runner.xcworkspace`를 Xcode로 엽니다.
2. `Runner` scheme은 이미 `Runner/Configuration.storekit`에 연결돼 있습니다. Xcode에서 Product → Scheme → Edit Scheme → Run → Options의 **StoreKit Configuration**이 이 파일을 가리키는지만 확인합니다.
3. 이 파일에 있는 다섯 상품은 모두 Consumable입니다.
4. Debug iOS Simulator에서 앱을 실행합니다. Xcode의 StoreKit 구매 시트만 표시되며 실제 Apple 청구는 발생하지 않습니다.

Configuration 파일은 Scheme에 자동으로 고정하지 않았습니다. 개발자가 사용하는 Scheme에만 선택해야 하므로, 별도 scheme을 덮어쓰지 않고 Xcode UI에서 명시적으로 연결하는 편이 안전합니다.

| Product ID | 상품명 | 지급 하트 | StoreKit 테스트 가격 |
| --- | --- | ---: | ---: |
| `seolleyeon.heart.20` | 가볍게 | 20 | ₩3,900 |
| `seolleyeon.heart.40` | 핵심 | 40 | ₩6,900 |
| `seolleyeon.heart.100` | 활동 | 100 | ₩14,900 |
| `seolleyeon.heart.220` | 학기 | 220 | ₩29,900 |
| `seolleyeon.heart.first.50` | 첫 결제 특별 | 50 | ₩6,900 |

표의 가격은 `.storekit` 테스트 데이터입니다. 앱 UI는 가격을 하드코딩하지 않고 StoreKit의 `ProductDetails.price`만 표시합니다.

## Firebase Emulator로 전체 지급 흐름 테스트

StoreKit Configuration transaction은 Apple 운영 서버에서 검증할 수 없습니다. 따라서 Local Testing 전체 흐름은 Firebase Emulator에서만 test verifier를 켭니다.

1. `functions/.env.local.example`을 `functions/.env.local`로 복사합니다.
2. Firebase Emulator를 Firestore·Functions·Auth 대상으로 시작합니다. `firebase.json`은 Auth 9099, Firestore 8080, Functions 5001을 사용합니다.
3. 디버그 앱을 `flutter run --dart-define=USE_FIREBASE_EMULATORS=true`로 실행합니다. 이 define은 release build에서 무시됩니다.
4. Xcode StoreKit Configuration을 선택한 앱에서 하트 구매를 진행합니다.

> **중요:** 이 경로는 운영 Firestore와 분리된 Emulator Firestore를 사용합니다.
> 처음 로그인하면 `createFirebaseCustomToken`이 최소 사용자 문서를 만들 수 있지만,
> 지급 Callable은 학생 인증이 완료된 `users/{kakaoUserId}` 문서만 허용합니다.
> 따라서 실제 운영 사용자 문서나 개인정보를 자동 복사하지 말고, Emulator에
> `isStudentVerified: true`, 유효한 `studentEmail`, `heartBalance`를 가진 테스트
> 사용자 문서를 준비한 뒤 같은 Kakao ID로 로그인해야 전체 지급 흐름을 검증할 수 있습니다.
> 운영 사용자 잔액을 Local StoreKit transaction으로 변경하려면 안 됩니다.

### USB/Wi-Fi 실기기 테스트

실기기는 `127.0.0.1`의 Mac Emulator에 접근할 수 없습니다. Mac과 iPhone을 같은 Wi-Fi에 연결하고, Emulator가 LAN 연결을 받도록 설정한 뒤 Mac의 LAN IP를 build define으로 전달하세요. 예를 들어 Mac의 IP가 `192.168.0.20`이면 다음처럼 실행합니다.

```bash
flutter run --dart-define=USE_FIREBASE_EMULATORS=true \\
  --dart-define=FIREBASE_EMULATOR_HOST=192.168.0.20
```

Xcode로 실행할 때도 위 두 define이 필요합니다. Scheme → Run → Arguments에서
`DART_DEFINES` 환경 변수를 다음처럼 Base64로 설정합니다. 예시 IP가 `192.168.0.20`이면
값은 `VVNFX0ZJUkVCQVNFX0VNVUxBVE9SUz10cnVl,RklSRUJBU0VfRU1VTEFUT1JfSE9TVD0xOTIuMTY4LjAuMjA=`입니다.
IP는 각 Mac의 실제 LAN IP로 바꿔야 합니다.

이 경로에서도 StoreKit 구매 성공 → Functions `LocalStoreKitPurchaseVerifier` → Firestore transaction → `heartBalance` 증가 → `completePurchase` 순서로 처리됩니다. 클라이언트가 성공을 흉내 내거나 하트 수량을 직접 증가시키지 않습니다. `seolleyeon-final` 운영 Functions에는 `storekit_local` verifier를 배포하지 마세요.

`[IAP][IOS] server grant failed code=failed-precondition` 로그가 보이면 앱이
운영 Functions를 호출했거나 Emulator 사용자 문서가 아직 학생 인증 상태가 아닌
것입니다. `IAP_VERIFICATION_MODE=production`인 운영 Functions는 Local StoreKit
transaction을 의도적으로 거부합니다.

`IAP_VERIFICATION_MODE`의 기본값은 `production`이며, 운영 verifier는 Apple의 공식 App Store Server Library로 signed transaction JWS와 Apple 인증서 체인을 검증합니다. 운영/staging 배포 환경에 `storekit_local`을 넣지 마세요. 운영 배포 전 `APPLE_IAP_BUNDLE_ID`와 App Store Connect의 숫자 Apple ID(`APPLE_IAP_APPLE_ID`)가 실제 앱과 일치하는지 확인하세요. iOS 클라이언트는 로그인 계정에서 만든 UUID를 `applicationUserName`으로 전달하고, 서버는 JWS의 `appAccountToken`과 비교해 다른 계정의 구매를 거부합니다.

이 직접 JWS 검증 경로에는 App Store Connect에서 받은 `.p8` 파일이 필요하지 않습니다. `.p8`는 이후 App Store Server API 조회·환불·알림 관리 기능을 추가할 때만 Secret Manager에 등록하고, 저장소나 앱 번들에는 넣지 않습니다.

## 확인 시나리오

- 20/40/100/220 하트 상품을 각각 구매하면 `users/{kakaoUserId}.heartBalance`가 정확히 증가합니다.
- `seolleyeon.heart.first.50`은 `iapPurchaseCount == 0`인 계정의 첫 결제에만 지급되고, 이후 서버가 구매를 거절하며 앱 목록에서도 숨깁니다.
- 같은 상품을 다시 구매하면 새 Apple transaction으로 다시 지급됩니다.
- 취소/실패는 잔액을 바꾸지 않습니다. pending 동안 모든 상품 버튼이 비활성화됩니다.
- 같은 transaction이 다시 전달되면 `iapTransactions/{sha256(transactionId)}`의 Firestore transaction 기록 때문에 한 번만 지급되고, 필요한 경우 `completePurchase`만 다시 실행됩니다.
- 지급 전 앱이 종료되면 StoreKit이 다음 시작에서 unfinished transaction을 다시 전달합니다. 지급 실패 상태에서는 `completePurchase`를 호출하지 않습니다.

Debug 빌드에서만 `[IAP]` 로그가 출력되며 receipt 원문·인증 토큰·개인정보는 로그나 Firestore에 저장하지 않습니다.
