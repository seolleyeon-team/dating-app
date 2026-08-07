# 설레연 App Store·Google Play 출시 필수 파일 조사 보고서

| 항목 | 값 |
|---|---|
| 조사 기준일 | 2026-07-31 |
| 저장소 | `C:/Users/samsung/StudioProjects/semisemifinal` |
| 브랜치 | `kakao-message` |
| 조사 방식 | Read-only (본 보고서 작성 시점 기준 조사 결과 정리) |
| Apple 공식 문서 확인일 | 2026-07-31 |
| Google 공식 문서 확인일 | 2026-07-31 |
| 완료 판정 | `REPORT_COMPLETE_WITH_UNVERIFIED_EXTERNAL_ITEMS` |

---

## A. 조사 결과 요약

```text
App Store 실제 업로드 파일 수: 4
Google Play 실제 업로드 파일 수: 5
공통 release build 필수 경로 수: 12
Android build 필수 경로 수: 14
iOS build 필수 경로 수: 16
스토어 listing 필수 asset 수: 7 (저장소 내 준비된 규격 asset: 0)
외부 서명 자료 수: 8
누락된 필수 파일 수: 8
조건부 확인 필요 수: 11
```

### 핵심 판정

- 스토어에 올릴 **binary·listing asset은 아직 생성/준비되지 않음**
- 저장소에는 release 재현용 소스·네이티브 설정이 대부분 있음
- **Android release 서명이 debug로 고정**되어 있어 출시 빌드가 막힌 상태
- App Store Connect / Play Console의 실제 앱 레코드·서명 등록 상태는 **외부 확인 필요**

### 분류 코드

| 코드 | 의미 |
|---|---|
| A | `STORE_UPLOAD_REQUIRED` — 스토어에 실제 업로드하는 파일 |
| B | `RELEASE_BUILD_REQUIRED` — 업로드 파일을 재현 가능하게 빌드하는 저장소 파일 |
| C | `STORE_LISTING_ASSET_REQUIRED` — 스토어 등록 화면 업로드 이미지·영상 |
| D | `REVIEW_OR_COMPLIANCE_REQUIRED` — 심사·개인정보·법률·앱 접근 자료 |
| E | `CONDITIONAL_REQUIRED` — 특정 기능·권한·SDK 사용 시에만 필요 |
| F | `SIGNING_OR_CREDENTIAL_REQUIRED_EXTERNAL` — 출시 필요하지만 저장소 평문 금지 |
| G | `RUNTIME_REQUIRED_NOT_STORE_UPLOAD` — 앱 파일에는 없지만 서비스 운영 필요 |
| H | `DEVELOPMENT_ONLY_NOT_RELEASE_REQUIRED` — 개발·테스트용, release binary 직접 불필요 |
| I | `GENERATED_OR_CACHE` — 다시 생성 가능 |
| J | `UNKNOWN_NEEDS_VERIFICATION` — 코드만으로 확정 불가 |

> `H`/`I`라고 해서 삭제 가능하다는 뜻이 아니다. 삭제 판정은 이 보고서 범위 밖이다.

---

## B. 실제 스토어에 올리는 파일만

소스 코드, `pubspec.yaml`, `Info.plist` 등은 이 목록에 포함하지 않는다.

### B-1. Apple App Store

| 번호 | 업로드 항목 | 형식 | 저장소 존재 | 상태 | 비고 |
|---:|---|---|---|---|---|
| 1 | App Store Connect용 iOS build | `.ipa` / Xcode Archive | 없음 (빌드 산출물) | `GENERATED_AT_RELEASE` | 2026-04-28부터 Xcode 26 + iOS 26 SDK 이상 |
| 2 | iPhone 스크린샷 | `.jpeg` / `.jpg` / `.png` | 없음 | `MISSING_REQUIRED` | 디바이스 크기별 1–10장 |
| 3 | App Preview 영상 | `.mov` / `.m4v` / `.mp4` | 없음 | `MISSING_CONDITIONAL` | 선택 |
| 4 | 심사 첨부·데모 자료 | 노트·계정·첨부 | 없음 | `EXTERNAL_REQUIRED` | App Store Connect / 심사 노트 |

### B-2. Google Play

| 번호 | 업로드 항목 | 형식 | 저장소 존재 | 상태 | 비고 |
|---:|---|---|---|---|---|
| 1 | 서명된 Android App Bundle | `.aab` | 없음 (빌드 산출물) | `GENERATED_AT_RELEASE` | 신규 앱 AAB 필수 + Play App Signing |
| 2 | Play high-res 아이콘 | 512×512 PNG | 없음 | `MISSING_REQUIRED` | 앱 내 launcher 아이콘과 별개 |
| 3 | Feature graphic | 1024×500 JPEG/PNG | 없음 | `MISSING_REQUIRED` | listing 게시 필수 |
| 4 | 스크린샷 | JPEG/PNG | 없음 | `MISSING_REQUIRED` | 최소 2장 (권장 4장·1080px+) |
| 5 | deobfuscation / native symbols | `mapping.txt` / native symbols | 없음 | `MISSING_CONDITIONAL` | R8/native 사용 시 |

---

## C. 재현 가능한 release build 최소 저장소 파일

### C-1. 공통 Flutter

| 경로 | 필수 이유 | 존재 | 상태 |
|---|---|---|---|
| `pubspec.yaml` | 버전 `1.0.0+3`, 의존성·asset·fonts | 예 | `PRESENT_NEEDS_REVIEW` |
| `pubspec.lock` | 재현 가능한 의존성 pin | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/main.dart` | release entry (`FLUTTER_TARGET`) | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/app.dart` | 앱 루트 위젯 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/router/` | 라우팅 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/features/` | feature UI·플로우 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/services/` | 인증·채팅·푸시·추천 등 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/providers/` | 상태 관리 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/shared/` | 공통 유틸·위젯 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/config/` | 환경·PortOne 등 설정 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/constants/` | 상수·약관 텍스트 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/data/` | 데이터 계층 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/screens/` | 레거시/공용 스크린 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/ai_recommend_model/` | 추천 모델 관련 | 예 | `PRESENT_NEEDS_REVIEW` |
| `lib/firebase_options.dart` | Firebase 클라이언트 초기화 | 예 | `PRESENT_NEEDS_REVIEW` |
| `mainlogo.png` | pubspec asset | 예 | `PRESENT_NEEDS_REVIEW` |
| `cherrysticker.png` | pubspec asset | 예 | `PRESENT_NEEDS_REVIEW` |
| `aiprofile.png` | pubspec asset | 예 | `PRESENT_NEEDS_REVIEW` |
| `postit.png` | pubspec asset | 예 | `PRESENT_NEEDS_REVIEW` |
| `sketchbook.png` | pubspec asset | 예 | `PRESENT_NEEDS_REVIEW` |
| `public/legal/terms.html` | 앱 asset으로 번들 | 예 | `PRESENT_NEEDS_REVIEW` |
| `assets/fonts/` | NanumSquareRound / Pretendard / Noto Sans KR / LeeSeoyun | 예 | `PRESENT_NEEDS_REVIEW` |

#### Flutter 코드 범위 구분

| 구분 | 경로 패턴 |
|---|---|
| 필수 앱 진입점 | `lib/main.dart` |
| 필수 공통 코드 | `lib/app.dart`, `lib/router/`, `lib/providers/`, `lib/shared/`, `lib/firebase_options.dart` |
| 실제 연결된 feature 코드 | `lib/features/`, `lib/services/`, `lib/screens/`, `lib/data/`, `lib/config/`, `lib/constants/` |
| 조건부 feature 코드 | `lib/features/profile/screens/heart_charge_screen.dart` (`ENABLE_IN_APP_PURCHASE` 기본 `false`) |
| dead / 미참조 코드 | 이 조사에서 전체 미사용 판정하지 않음 (`UNKNOWN_NEEDS_VERIFICATION`) |

### C-2. Android

| 경로 | 필수 이유 | 존재 | 상태 |
|---|---|---|---|
| `android/settings.gradle.kts` | AGP / Flutter / Google Services 플러그인 | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/build.gradle.kts` | 루트 Gradle | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/build.gradle.kts` | `applicationId`, SDK, signing | 예 | `PRESENT_NEEDS_REVIEW` (**release=debug**) |
| `android/gradle.properties` | Gradle 속성 | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/gradle/wrapper/gradle-wrapper.properties` | Gradle 8.12 | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/src/main/AndroidManifest.xml` | 권한·딥링크·카카오 | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/src/main/kotlin/com/yonsei/dating/MainActivity.kt` | 호스트 Activity | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/src/main/res/` | launcher / splash | 예 | `PRESENT_NEEDS_REVIEW` (아이콘 용량 매우 작음) |
| `android/app/google-services.json` | Firebase Android | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/src/debug/AndroidManifest.xml` | debug manifest | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/app/src/profile/AndroidManifest.xml` | profile manifest | 예 | `PRESENT_NEEDS_REVIEW` |
| `android/key.properties` | release 서명 설정 | **없음** | `EXTERNAL_REQUIRED` |
| `*.jks` / `*.keystore` | upload keystore | **없음** | `EXTERNAL_REQUIRED` |
| `android/app/proguard-rules.pro` | 커스텀 R8 | **없음** | `NOT_APPLICABLE` / 조건부 |

#### Android 식별값 (조사 시점)

| 항목 | 값 |
|---|---|
| `applicationId` / `namespace` | `com.yonsei.dating` |
| `compileSdk` / `targetSdk` / `minSdk` | Flutter 기본값 기준 **36 / 36 / 24** |
| `versionName` / `versionCode` | `pubspec.yaml` 기준 `1.0.0` / `3` |
| release signing | `signingConfigs.getByName("debug")` 로 고정 |

### C-3. iOS

| 경로 | 필수 이유 | 존재 | 상태 |
|---|---|---|---|
| `ios/Podfile` | CocoaPods, `platform :ios, '16.0'` | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Podfile.lock` | Pod 버전 pin | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner.xcodeproj/` | Bundle ID, Team, entitlements 연결 | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner.xcworkspace/` | Archive workspace | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Flutter/` | Flutter xcconfig | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Info.plist` | 권한 문구·URL schemes·background | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/AppDelegate.swift` | native entry | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/CaptureProtectedImagePlatformView.swift` | 캡처 보호 native view | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Runner.entitlements` | push·associated domains | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/RunnerDebug.entitlements` | debug entitlements | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/RunnerRelease.entitlements` | release entitlements | 예 | `PRESENT_NEEDS_REVIEW` (**aps=development**) |
| `ios/Runner/GoogleService-Info.plist` | Firebase iOS | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Assets.xcassets/AppIcon.appiconset/` | 앱 아이콘 (1024 포함) | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Assets.xcassets/LaunchImage.imageset/` | 런치 이미지 | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Base.lproj/LaunchScreen.storyboard` | 런치 스크린 | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/Base.lproj/Main.storyboard` | 메인 스토리보드 | 예 | `PRESENT_NEEDS_REVIEW` |
| `ios/Runner/PrivacyInfo.xcprivacy` | Privacy manifest | **없음** | `MISSING_CONDITIONAL` / HIGH |
| Apple Distribution certificate / provisioning profile / API key | 코드서명·업로드 | 저장소 외 | `EXTERNAL_REQUIRED` |

#### iOS 식별값 (조사 시점)

| 항목 | 값 |
|---|---|
| `PRODUCT_BUNDLE_IDENTIFIER` | `com.yonsei.dating` |
| `DEVELOPMENT_TEAM` | `29ZU3S9H2G` |
| `IPHONEOS_DEPLOYMENT_TARGET` (pbxproj) | `13.0` |
| Podfile platform | `16.0` |
| Associated Domains | `applinks:seolleyeon.web.app` |
| `aps-environment` (Release 포함) | `development` |

---

## D. 스토어 등록용 이미지 파일

### D-1. App Store

| 자료 | 공식 규격 | 필수 여부 | 저장소 경로 | 상태 |
|---|---|---|---|---|
| App Icon (binary 내) | Asset Catalog, 1024×1024 PNG | 필수 | `ios/Runner/Assets.xcassets/AppIcon.appiconset/` | `PRESENT_NEEDS_REVIEW` |
| iPhone 스크린샷 | jpeg/png, alpha 없음 | 필수 | 없음 (`fastlane/`, `screenshots/`, `store_assets/` 미존재) | `MISSING_REQUIRED` |
| iPad 스크린샷 | iPad 실행 시 필수 | 조건부 | 없음 | `MISSING_CONDITIONAL` |
| App Preview | 15–30초 영상 | 선택 | 없음 | `MISSING_CONDITIONAL` |

### D-2. Google Play

| 자료 | 공식 규격 | 필수 여부 | 저장소 경로 | 상태 |
|---|---|---|---|---|
| High-res icon | 512×512, 32-bit PNG(alpha), ≤1024KB | 필수 | 없음 | `MISSING_REQUIRED` |
| Feature graphic | 1024×500, JPEG 또는 24-bit PNG(no alpha) | 필수 | 없음 | `MISSING_REQUIRED` |
| Phone screenshots | 최소 2장; 권장 4장·≥1080px, 9:16/16:9 | 필수(최소 2) | 없음 | `MISSING_REQUIRED` |
| Launcher icon (앱 내) | mipmap | 빌드용 | `android/app/src/main/res/mipmap-*/ic_launcher.png` | `PRESENT_NEEDS_REVIEW` (`mipmap-xxxhdpi` ≈1.4KB → placeholder 의심) |

### D-3. 스토어 asset 폴더 검색 결과

다음 이름의 전용 폴더는 **저장소 루트에 없음**:

```text
fastlane/
metadata/
store_assets/
app_store/
play_store/
screenshots/
marketing/
release/
distribution/
icons/
feature_graphic/
```

관련은 있으나 스토어 listing 전용은 아닌 경로:

```text
public/legal/          # 약관 HTML
public/privacy.html    # 개인정보처리방침 HTML
ios/Runner/Assets.xcassets/AppIcon.appiconset/
android/app/src/main/res/mipmap-*/
```

---

## E. 서명 및 인증 자료

| 플랫폼 | 자료 | 저장소 포함 | 권장 보관 위치 | 현재 상태 |
|---|---|---|---|---|
| Android | Upload keystore (`.jks` / `.keystore`) | 아니오 (`android/.gitignore` 대상) | CI Secret / 보안 금고 | `EXTERNAL_REQUIRED` |
| Android | `android/key.properties` | 아니오 | CI Secret | `EXTERNAL_REQUIRED` |
| Android | Play App Signing enrollment | Console | Play Console | 외부 확인 필요 |
| Android | release `signingConfig` | 코드상 **debug로 고정** | — | **BLOCKER** |
| iOS | Apple Distribution certificate + private key | 아니오 | Keychain / CI | `EXTERNAL_REQUIRED` |
| iOS | App Store provisioning profile | 아니오 | Apple Developer / CI | `EXTERNAL_REQUIRED` |
| iOS | App Store Connect API key (`.p8`) | 아니오 | CI Secret | `EXTERNAL_REQUIRED` |
| iOS | Team ID `29ZU3S9H2G` | `ios/Runner.xcodeproj/project.pbxproj` | — | `PRESENT_NEEDS_REVIEW` |
| 공통 | Firebase Admin / service account | `.gitignore`로 차단 | Secret Manager | 저장소 평문 금지 |

### Secret 발견 시 표기 규칙 (실제 값 미출력)

```text
발견: android/key.properties
분류: Android 서명 설정
민감도: SECRET
내용 출력: 금지
권장 보관: 저장소 외부 또는 CI Secret
존재: 없음
```

Firebase 클라이언트 파일(`android/app/google-services.json`, `ios/Runner/GoogleService-Info.plist`, `lib/firebase_options.dart`)은 일반 서버 Secret과 성격이 다르나, **API key 실값은 이 문서에 복사하지 않음**.

---

## F. 개인정보·심사 관련 필수 파일 또는 자료

| 플랫폼 | 항목 | 형태 | 필수 여부 | 현재 확인 결과 |
|---|---|---|---|---|
| 공통 | 개인정보처리방침 | 공개 URL + 앱 내 | 필수 | 로컬 `public/privacy.html` 존재. 호스팅 예: `https://seolleyeon.web.app/privacy.html` — Console 등록·배포 상태 외부 확인 필요 |
| 공통 | 이용약관 | 로컬 파일 + 앱 내 | 필수에 가까움 | `public/legal/terms.html`, `lib/constants/legal_texts.dart` |
| Apple | App Privacy 설문 | Console 직접 입력 | 필수 | 외부 확인 필요 |
| Apple | 계정 삭제 | 앱 내 기능 | 필수(계정 생성 앱) | `lib/features/profile/screens/account_management_screen.dart` + `lib/services/user_service.dart` (`withdrawAccount`) 존재 |
| Apple | Sign in with Apple | 앱 기능 + entitlement | 조건부 (Guideline 4.8) | Kakao 로그인만 확인, SIWA 미구현 |
| Apple | 암호화/수출 규정 | Console 문답 | 필수 | `ITSAppUsesNonExemptEncryption` 미설정 → Console 처리 필요 |
| Apple | 심사 계정·연락처 | 심사 노트 | 권장/조건부 | 외부 준비 필요 (소셜/데이팅·UGC) |
| Google | Data safety form | Console 직접 입력 | 필수 | 외부 확인 필요 |
| Google | 계정 삭제 URL | Console URL 필드 | 필수(계정 생성 앱) | 앱 내 탈퇴는 있음. 웹 전용 삭제 경로 URL은 미확인 |
| Google | 개인정보처리방침 URL | Console | 필수 | 외부 확인 필요 |
| Google | 콘텐츠 등급 / 광고 선언 | Console | 필수 | 광고 SDK 미사용으로 보임. 등급 설문 외부 |
| Google | 앱 액세스(테스터 계정) | Console | 조건부 | 로그인 필수 앱 → 심사용 계정 필요 |
| Google | 개인 계정 closed test | Console 프로세스 | 조건부 | 신규 개인계정(2023-11-13 이후): 12명 × 14일 |

### 파일이 아닌 필수 제출 정보

```text
- App Store Connect / Play Console 직접 입력값
- 개인정보처리방침·계정삭제 공개 URL
- 심사 노트·데모 계정
- Data safety / App Privacy 설문 응답
- 콘텐츠 등급·광고 여부 선언
- 암호화/수출 규정 문답
```

---

## G. 기능별 조건부 필요 파일

| 기능 | 플랫폼 | 필요한 파일·설정 | 실제 사용 | 상태 |
|---|---|---|---|---|
| Firebase | 공통 | `android/app/google-services.json`, `ios/Runner/GoogleService-Info.plist`, `lib/firebase_options.dart` | 사용 | `PRESENT_NEEDS_REVIEW` |
| Push (FCM) | Android/iOS | `POST_NOTIFICATIONS`, `UIBackgroundModes=remote-notification`, `aps-environment` | 사용 | iOS Release가 `development` → 출시 전 production 필요 |
| App Check | 공통 | Play Integrity / App Attest (`lib/main.dart`) | 사용 | `PRESENT_NEEDS_REVIEW` |
| Kakao 로그인 | 공통 | URL schemes, intent-filter, Kakao SDK | 사용 | `PRESENT_NEEDS_REVIEW` |
| Sign in with Apple | iOS | entitlement + UI | **미사용** | Guideline 4.8로 필요 가능 |
| 사진(갤러리) | iOS/Android | `NSPhotoLibrary*`, `image_picker` (gallery) | 사용 | 카메라 권한 문구 없음(카메라 미사용으로 보임) |
| 연락처 | 공통 | `READ_CONTACTS`, `NSContactsUsageDescription` | 사용(차단) | `PRESENT_NEEDS_REVIEW` |
| 위치 | 공통 | FINE/COARSE, `NSLocationWhenInUseUsageDescription` | 사용(안전도장) | `PRESENT_NEEDS_REVIEW` |
| Bluetooth LE | 공통 | BT 권한, `NSBluetoothPeripheralUsageDescription` | 사용(안전도장) | `PRESENT_NEEDS_REVIEW` |
| Deep / App / Universal Links | 공통 | `AndroidManifest.xml` intent-filter, entitlements, `public/assetlinks.json`, `public/.well-known/apple-app-site-association` | 사용 | fingerprint↔출시키 일치 외부 확인 |
| 인앱결제/하트 | 공통 | Store IAP 연동 | 기본 비활성 (`ENABLE_IN_APP_PURCHASE=false`) | 켜면 Store 결제·심사 필요 |
| PortOne 본인인증 | 공통 | queries schemes, WebView | 사용 | `PRESENT_NEEDS_REVIEW` |
| UGC·신고·차단 | 공통 | 앱 기능 + 정책 고지 | 사용 (`lib/features/reports/issue_report_screen.dart` 등) | `REVIEW_OR_COMPLIANCE_REQUIRED` |
| Privacy Manifest | iOS | `ios/Runner/PrivacyInfo.xcprivacy` | 앱 레벨 파일 없음 | `MISSING_CONDITIONAL` |
| ATT / 광고 ID | 공통 | ATT / `AD_ID` | 광고·추적 SDK 미확인 | Console 선언은 필요 |

---

## H. 스토어 업로드는 아니지만 서비스 운영에 필요한 파일

| 경로 | 역할 | 스토어 업로드 | 운영 필요성 |
|---|---|---|---|
| `functions/` | Cloud Functions (인증·추천·아바타 등) | 아니오 | 예 |
| `firestore.rules` | Firestore 보안 규칙 | 아니오 | 예 |
| `firestore.indexes.json` | Firestore 인덱스 | 아니오 | 예 |
| `storage.rules` | Storage 보안 규칙 | 아니오 | 예 |
| `firebase.json` | Firebase 프로젝트 배선 | 아니오 | 예 |
| `.firebaserc` | 기본 프로젝트 `seolleyeon` | 아니오 | 예 |
| `public/` | Hosting·정책·딥링크·초대 페이지 | 아니오 | 예 |
| `public/privacy.html` | 개인정보처리방침 페이지 | 아니오 | 예 |
| `public/legal/terms.html` | 이용약관 페이지 | 아니오 | 예 |
| `public/assetlinks.json` | Android App Links 검증 | 아니오 | 예 |
| `public/.well-known/apple-app-site-association` | iOS Universal Links | 아니오 | 예 |
| `lib/ai_recommend_model/` | 추천 관련 | 아니오 | 예(간접) |
| `festival_web/ai_recommend_model/` | 웹/추천 관련 | 아니오 | 예(간접) |
| `.github/workflows/ci.yml` | CI | 아니오 | 개발/배포 품질 |
| `docs/` | 문서·감사 | 아니오 | 품질/복구 |
| `scripts/` | 운영·점검 스크립트 | 아니오 | 품질/복구 |
| `test/` | 단위/위젯 테스트 | 아니오 | 품질 |

이 파일들을 “불필요한 파일”로 부르지 않는다.  
스토어 업로드 파일에는 포함되지 않으며, release binary 생성에는 직접 필요하지 않을 수 있으나, 테스트·운영·복구·CI에 필요할 수 있으므로 삭제 여부는 별도 검토가 필요하다.

---

## I. 누락·불일치·위험 항목

| ID | 심각도 | 플랫폼 | 문제 | 영향 | 후속 확인 |
|---|---|---|---|---|---|
| B01 | BLOCKER | Android | `android/app/build.gradle.kts`의 release `signingConfig`가 debug | Play 업로드용 정상 서명 AAB 불가/거부 위험 | upload key + release signingConfig 구성 |
| B02 | BLOCKER | Android | `android/key.properties` / keystore 부재 | release 서명 재현 불가 | 외부 Secret 준비 |
| B03 | HIGH | iOS | `ios/Runner/RunnerRelease.entitlements`의 `aps-environment=development` | 프로덕션 푸시 실패/심사 이슈 | production profile/entitlement |
| B04 | HIGH | iOS | `ios/Runner/PrivacyInfo.xcprivacy` 부재 | Required Reason API 미선언 시 업로드/심사 거부 가능 | archive 검증 후 앱/SDK manifest 확인 |
| B05 | HIGH | iOS | Kakao 로그인만 있고 SIWA 없음 | Guideline 4.8 거부 가능 | 심사 전략 또는 SIWA 추가 |
| B06 | HIGH | Listing | App Store/Play 스크린샷·Play feature graphic·512 아이콘 없음 | listing 게시 불가 | 규격 자산 제작 |
| B07 | HIGH | Google | 계정 삭제 웹 URL 불명확 | Data safety / User Data 정책 위반 위험 | 탈퇴 요청 웹 경로 확정·Console 등록 |
| B08 | MEDIUM | Android | `android/app/google-services.json`에 `com.example.dating_app`와 `com.yonsei.dating` 공존 | 혼동·잘못된 앱 연결 위험 | production 앱 항목만 유지하는지 검토 |
| B09 | MEDIUM | Android | `android/app/src/main/res/mipmap-*/ic_launcher.png` 용량 극소 + adaptive icon 없음 | 런처/브랜딩 품질 리스크 | 정식 아이콘 교체 |
| B10 | MEDIUM | 공통 | `pubspec.yaml` versionCode `+3` vs 로컬 Generated/local.properties `+1` | 업로드 버전 혼선 | release 시 `--build-number` 일관화 |
| B11 | MEDIUM | Android | `public/assetlinks.json` fingerprint가 출시 키와 일치하는지 미검증 | App Links 검증 실패 | 출시 인증서 SHA-256 일치 확인 |
| B12 | MEDIUM | 공통 | 인앱결제 기본 비활성 | 하트 충전 UI가 미완성 기능으로 노출될 수 있음 | 출시 범위에서 UI/플래그 확정 |
| B13 | INFO | Console | App Store Connect / Play Console 실제 앱 레코드 | package/bundle 등록 여부 불명 | 외부 확인 필요 |
| B14 | INFO | Google | 개인 계정이면 closed test 12×14일 | production 잠금 가능 | 계정 유형 확인 |

---

## J. 최소 출시 파일 체크리스트

### Apple

```text
[ ] Xcode 26 + iOS 26 SDK로 Archive/IPA 생성·업로드
[ ] Bundle ID com.yonsei.dating App Store Connect 앱 레코드
[ ] Distribution cert + App Store profile (aps production)
[ ] ios/Runner/PrivacyInfo.xcprivacy / Required Reason API 검증
[ ] 필수 iPhone 스크린샷 업로드
[ ] App Privacy 설문 + 개인정보처리방침 URL
[ ] 암호화/수출 규정 문답
[ ] 계정 삭제(앱 내) 동작 검증 + 심사 계정
[ ] Guideline 4.8 (Kakao → SIWA 등) 대응
[ ] 연령 등급·데이팅/UGC 심사 노트
```

### Google Play

```text
[ ] upload key로 서명한 AAB
[ ] Play App Signing 등록
[ ] targetSdk 36 충족 확인 (조사 시점 Flutter 기본 36)
[ ] 512 아이콘 + 1024×500 feature graphic + 스크린샷 ≥ 2
[ ] Data safety + 광고 선언 + 콘텐츠 등급
[ ] 개인정보처리방침 URL + 계정 삭제 웹 URL
[ ] 앱 액세스용 테스트 계정
[ ] (해당 시) 개인계정 closed test 12명/14일
[ ] (해당 시) mapping / native symbols
[ ] Data safety와 권한(위치·연락처·사진·BT·알림) 정합
```

---

## K. 최종 핵심 두 목록

### K-1. `STORE_UPLOAD_FILES_ONLY`

```text
Apple:
1. App Store Connect에 업로드하는 iOS build (.ipa / archive)
2. App Store 스크린샷 (필수)
3. App Preview (선택)
4. 심사 첨부/노트용 자료 (조건부)

Google:
1. 서명된 Android App Bundle (.aab)
2. Play high-res icon (512×512 PNG)
3. Feature graphic (1024×500)
4. Play 스크린샷 (최소 2)
5. mapping / native debug symbols (조건부)
```

### K-2. `REPRODUCIBLE_RELEASE_BUILD_MINIMUM`

```text
Common:
1. pubspec.yaml
2. pubspec.lock
3. lib/
4. lib/firebase_options.dart
5. mainlogo.png
6. cherrysticker.png
7. aiprofile.png
8. postit.png
9. sketchbook.png
10. public/legal/terms.html
11. assets/fonts/

Android:
1. android/settings.gradle.kts
2. android/build.gradle.kts
3. android/app/build.gradle.kts
4. android/gradle.properties
5. android/gradle/wrapper/
6. android/app/src/main/AndroidManifest.xml
7. android/app/src/main/kotlin/com/yonsei/dating/
8. android/app/src/main/res/
9. android/app/google-services.json
10. (external) upload keystore + android/key.properties

iOS:
1. ios/Podfile
2. ios/Podfile.lock
3. ios/Runner.xcodeproj/
4. ios/Runner.xcworkspace/
5. ios/Flutter/
6. ios/Runner/Info.plist
7. ios/Runner/Runner.entitlements
8. ios/Runner/RunnerDebug.entitlements
9. ios/Runner/RunnerRelease.entitlements
10. ios/Runner/AppDelegate.swift
11. ios/Runner/GoogleService-Info.plist
12. ios/Runner/Assets.xcassets/
13. ios/Runner/Base.lproj/
14. (external) Apple Distribution cert / profile
15. (missing/conditional) ios/Runner/PrivacyInfo.xcprivacy
```

---

## L. 업로드 불필요하지만 삭제 판단을 보류해야 하는 영역

```text
경로: functions/
스토어 업로드 불필요 이유: 모바일 binary에 포함되지 않음
삭제 판단을 보류해야 하는 이유: 인증·푸시·추천·아바타 등 런타임 백엔드

경로: firestore.rules / storage.rules / firestore.indexes.json
스토어 업로드 불필요 이유: 스토어 artifact 아님
삭제 판단을 보류해야 하는 이유: 보안·운영 필수

경로: public/
스토어 업로드 불필요 이유: Play/App Store binary 업로드 대상 아님
삭제 판단을 보류해야 하는 이유: 정책 URL·Universal/App Links·초대 플로우

경로: test/ , docs/ , scripts/ , .github/
스토어 업로드 불필요 이유: release binary 직접 입력 아님
삭제 판단을 보류해야 하는 이유: CI·감사·복구·품질 보증

경로: dating-app/ , .tmp/ , festival_web/
스토어 업로드 불필요 이유: 루트 모바일 release entry와 별개/임시
삭제 판단을 보류해야 하는 이유: 복제·마이그레이션·웹/추천 자산일 수 있음
```

---

## M. 공식 근거

| 요구사항 | 공식 문서 | 확인일 |
|---|---|---|
| App Store SDK/Xcode 최소 (Xcode 26, iOS 26 SDK, 2026-04-28~) | [Submitting](https://developer.apple.com/app-store/submitting/), [Upcoming SDK minimum requirements](https://developer.apple.com/news/?id=ueeok6yw) | 2026-07-31 |
| Privacy manifest / Required Reason API | [Privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files), [Describing use of required reason API](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api) | 2026-07-31 |
| 계정 삭제(앱 내) | [Offering account deletion in your app](https://developer.apple.com/support/offering-account-deletion-in-your-app) | 2026-07-31 |
| Login Services / SIWA | [App Review Guidelines 4.8](https://developer.apple.com/app-store/review/guidelines/) | 2026-07-31 |
| App Store 스크린샷 규격 | [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/) | 2026-07-31 |
| Play target API (2026-08-31부터 API 36) | [Target API level](https://developer.android.com/google/play/requirements/target-sdk), [Play Console Help](https://support.google.com/googleplay/android-developer/answer/11926878) | 2026-07-31 |
| AAB 필수 | [About Android App Bundles](https://developer.android.com/guide/app-bundle) | 2026-07-31 |
| Play App Signing | [Use Play App Signing](https://support.google.com/googleplay/android-developer/answer/9842756) | 2026-07-31 |
| Play listing graphics | [Add preview assets](https://support.google.com/googleplay/android-developer/answer/9866151) | 2026-07-31 |
| Data safety | [Data safety section](https://support.google.com/googleplay/android-developer/answer/10787469) | 2026-07-31 |
| 계정 삭제(인앱+웹) | [Account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111) | 2026-07-31 |
| 신규 개인계정 closed test | [App testing requirements](https://support.google.com/googleplay/android-developer/answer/14151465) | 2026-07-31 |

---

## N. 일관성 검사 요약

### Android

| 항목 | 값 / 결과 |
|---|---|
| `applicationId` | `com.yonsei.dating` |
| Firebase Android package | `com.yonsei.dating` 포함 (구 `com.example.dating_app`도 공존) |
| deep link host | `seolleyeon.web.app` |
| Play Console package | 외부 확인 필요 |
| release signing | debug fallback → **불일치/위험** |
| launcher icon | `android/app/src/main/res/mipmap-*/ic_launcher.png` 존재, 품질 검토 필요 |

### iOS

| 항목 | 값 / 결과 |
|---|---|
| Bundle Identifier | `com.yonsei.dating` |
| Firebase iOS bundle ID | `com.yonsei.dating` (일치) |
| Associated Domains | `applinks:seolleyeon.web.app` |
| Sign in with Apple entitlement | 없음 |
| push entitlement | 있음, 값이 `development` |
| App icon | `ios/Runner/Assets.xcassets/AppIcon.appiconset/` 존재 |
| App Store Connect app record | 외부 확인 필요 |

### 공통

| 항목 | 결과 |
|---|---|
| 앱 이름 | iOS display name `설레연`, Android label `seolleyeon` |
| 개인정보처리방침 | `public/privacy.html` 존재, Console URL 등록은 외부 확인 |
| 계정 삭제 | 앱 내 있음 / Play 웹 URL 불명확 |
| 사용 SDK | Firebase, Kakao, image_picker, contacts, geolocator, BLE, PortOne 등 |

---

## O. 문서 정보

| 항목 | 값 |
|---|---|
| 파일 경로 | `docs/store-release-file-audit-20260731.md` |
| 원조사 방식 | Read-only 저장소 조사 + Apple/Google 공식 문서 |
| Secret 취급 | keystore 비밀번호, API key, `.p8` 등 실값 미수록 |
| 삭제 권고 | 없음 |
