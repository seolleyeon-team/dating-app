# 05 — App Store / Google Play Readiness

작성: 2026-07-31

## Status

PARTIAL → hardened in-repo; **no store submission performed**.

## App version

pubspec.yaml: 1.0.0+3

## Implemented this branch

| Item | Evidence |
|------|----------|
| Android release no debug signing fallback | ndroid/app/build.gradle.kts + test |
| key.properties example | ndroid/key.properties.example |
| iOS PrivacyInfo.xcprivacy | ios/Runner/PrivacyInfo.xcprivacy in Resources |
| Logout clears user-scoped prefs | StorageService.clearUserScopedSession |

## Still EXTERNAL / operator

- [ ] Create upload keystore + ndroid/key.properties (gitignored)
- [ ] Play App Signing enrollment
- [ ] AAB release build with production Firebase
- [ ] App Privacy / Data Safety form submission
- [ ] Reviewer demo account
- [ ] Screenshots / content rating
- [ ] Legal review of PrivacyInfo data types vs actual SDK inventory

Actual submit = EXTERNAL ACTION only.
