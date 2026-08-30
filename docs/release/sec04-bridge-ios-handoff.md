# SEC-04 bridge — iOS 릴리스 핸드오프

이 문서는 **Mac + Xcode 환경에서 후속 실행**할 절차다. 작성 시점의 빌드
환경은 Windows 였고 iOS archive/signing 은 **실행하지 않았다**.

```
IOS_BUILD = NOT_RUN_ENVIRONMENT_WINDOWS
```

`NOT_RUN` 이지 `PASS` 가 아니다.

## 대상 소스

```
PINNED_SOURCE_SHA = <릴리스 PR 머지 SHA — 아래 "소스 확인" 참조>
```

`main` 의 최신이 아니라 **핀으로 고정된 SHA** 에서 빌드한다. 그 이후 main 에
들어온 커밋은 별도 검토 후 다시 핀을 잡아야 한다.

## 기대값

| 항목 | 값 | 출처 |
|---|---|---|
| Bundle identifier | `com.seolleyeon.app` | `ios/Runner.xcodeproj/project.pbxproj` |
| `CFBundleShortVersionString` | `1.0.0` | `$(FLUTTER_BUILD_NAME)` ← `pubspec.yaml` |
| `CFBundleVersion` | `15` | `$(FLUTTER_BUILD_NUMBER)` ← `pubspec.yaml` |
| Firebase iOS appId | `1:810450765203:ios:fddeea51ac71dc4e5c9466` | `lib/firebase_options.dart` |

`Info.plist` 는 두 값을 모두 Flutter 빌드 인자에서 받는다. Xcode 에서 직접
수정하지 않는다 — `pubspec.yaml` 이 단일 출처다.

## ⚠️ build number 는 App Store Connect 와 대조해야 한다

```
APPSTORE_HIGHEST_USED_BUILD = UNKNOWN
```

이 저장소에는 App Store 에 어떤 build 가 올라갔는지에 대한 증거가 없다.
Android 쪽 근거(Play 에 13개 업로드됨, 커밋 `9ac02bdd`)만 있다.

**업로드 전 App Store Connect 에서 확인할 것:**

- `com.seolleyeon.app` 에 이미 사용된 최대 `CFBundleVersion`
- 그 값이 **15 이상**이면 `pubspec.yaml` 의 build number 를 더 올리고
  Android 와 다시 맞춘다 (양쪽이 같은 번호를 쓰는 현재 contract 유지)

같은 build number 를 재사용하면 App Store Connect 가 거부한다.

## iOS 게이트 동작 조건 — 반드시 확인

iOS 프로젝트에는 flavor scheme 이 없다. `Runner` 하나, 번들 id 하나다.
따라서 iOS 릴리스는 `--flavor` 없이 빌드되고 `appFlavor` 는 null 이다.

그래서 게이트는 **iOS 에서 flavor 가 없으면 production 정책을 읽도록** 되어
있다(`compatibilityPolicyDocIdFor`). 이 동작이 없으면 iOS 에서 업데이트 게이트가
아예 동작하지 않는다.

빌드 후 확인:

- 앱이 `appCompatibilityConfig/production` 을 읽는가
- 정책이 없거나 읽기에 실패했을 때 **앱이 정상 진입하는가** (lockout 금지)

## 절차

```bash
# 1. 핀 고정된 소스에서 시작
git fetch origin --prune
git checkout <PINNED_SOURCE_SHA>
git status --short          # 반드시 비어 있어야 한다

# 2. 값 확인
grep '^version:' pubspec.yaml     # 1.0.0+15 이어야 한다

# 3. 의존성
flutter pub get
cd ios && pod install && cd ..

# 4. 게이트 재확인 (Mac 에서도 동일해야 한다)
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test

# 5. 아카이브
flutter build ipa --release
```

`flutter build ipa` 는 `build/ios/archive/Runner.xcarchive` 와
`build/ios/ipa/*.ipa` 를 만든다. Xcode Organizer 로 열어도 된다.

## Xcode 서명 확인

- Signing team 이 설레연 계정인지
- Provisioning profile 이 `com.seolleyeon.app` 용 App Store 배포 프로파일인지
- **Automatic signing 을 쓰는 경우** 실수로 다른 팀/번들이 잡히지 않았는지

인증서·프로파일·비밀번호는 이 문서에 넣지 않는다. Xcode / Keychain 에서
직접 확인한다.

## 아카이브 검증

Organizer → Validate App 으로 다음을 확인한다.

- 번들 id `com.seolleyeon.app`
- 버전 `1.0.0` / 빌드 `15`
- 누락 아이콘·권한 문자열 경고 없음

## 🛑 여기서 멈춘다

```
APPSTORE_UPLOAD = NOT_RUN
TESTFLIGHT_UPLOAD = NOT_RUN
```

**Validate 까지만 하고 업로드하지 않는다.** App Store Connect 업로드와
TestFlight 배포는 별도 승인 사항이다.

## 소스 확인

빌드 전에 이 두 가지가 소스에 들어 있는지 확인한다.

```bash
# SEC-04 Phase A 소유권 매핑
grep -r "bamboo_post_authors" lib/ firestore.rules

# bridge 호환성 게이트
grep -r "AppCompatibilityGate" lib/app.dart
```

둘 다 있어야 bridge 빌드다.

## 관련 문서

- `docs/security/sec04-bridge-cutover.md` — bridge 가 무엇을 하고 **무엇을 하지
  못하는지**. 특히 pre-bridge 클라이언트는 이 게이트를 모른다는 점.
