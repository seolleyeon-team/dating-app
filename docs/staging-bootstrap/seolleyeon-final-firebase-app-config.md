# seolleyeon-final Firebase app config

Generated: 2026-05-19 KST

## SG-3 result

Status: `COMPLETE_FOR_ANDROID_IOS`

## App identifiers

| Platform | App identifier |
|---|---|
| Android applicationId | `com.yonsei.dating` |
| Android namespace | `com.yonsei.dating` |
| iOS bundle id | `com.yonsei.dating` |

## Firebase apps created

| Platform | Display name | Project | App id |
|---|---|---|---|
| Android | Seolleyeon Staging Android | `seolleyeon-final` | `1:810450765203:android:81ca13cb23027d875c9466` |
| iOS | Seolleyeon Staging iOS | `seolleyeon-final` | `1:810450765203:ios:7e51bb82970a77145c9466` |

## Config files

Backups were created before replacing local config:

- `android/app/google-services.json.backup-production-if-any`
- `ios/Runner/GoogleService-Info.plist.backup-production-if-any`
- `lib/firebase_options.dart.backup-production-if-any`

Generated staging config:

- `android/app/google-services.json`
- `ios/Runner/GoogleService-Info.plist`
- `lib/firebase_options.dart`
- Flutter metadata in `firebase.json`

The backup files are gitignored. They are local recovery artifacts only.

## Commands

```sh
firebase apps:create android "Seolleyeon Staging Android" --package-name com.yonsei.dating --project seolleyeon-final --json
firebase apps:create ios "Seolleyeon Staging iOS" --bundle-id com.yonsei.dating --project seolleyeon-final --json
firebase apps:sdkconfig ANDROID 1:810450765203:android:81ca13cb23027d875c9466 --project seolleyeon-final > android/app/google-services.json
firebase apps:sdkconfig IOS 1:810450765203:ios:7e51bb82970a77145c9466 --project seolleyeon-final > ios/Runner/GoogleService-Info.plist
dart pub global activate flutterfire_cli
flutterfire configure --project=seolleyeon-final --platforms=android,ios --android-package-name=com.yonsei.dating --ios-bundle-id=com.yonsei.dating --out=lib/firebase_options.dart --yes
flutter pub get
flutter analyze
flutter test test/profile_display_image_resolver_test.dart
```

Validation:

- `flutter pub get`: pass
- `flutter analyze`: pass
- `flutter test test/profile_display_image_resolver_test.dart`: pass

## Remaining config risk

`lib/firebase_options.dart` still contains the previous Web configuration because SG-3 generated Android/iOS only. This is acceptable for Android/iOS staging, but a web staging build must register a Web Firebase app and regenerate with `--platforms=android,ios,web` before use.

Do not print full config files in reports because they contain Firebase client API keys and app IDs.

## SG-3 handoff

```json
{
  "subagent": "SG-3",
  "status": "complete",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "firebase_apps": [
    "android:1:810450765203:android:81ca13cb23027d875c9466",
    "ios:1:810450765203:ios:7e51bb82970a77145c9466"
  ],
  "privacy_checks": [
    "No service account keys or private tokens generated.",
    "Firebase client config contents were not pasted into handoff."
  ],
  "remaining_risks": [
    "Web config remains old project until a Web staging app is registered."
  ]
}
```
