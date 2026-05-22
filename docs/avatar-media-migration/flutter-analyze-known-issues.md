# Flutter Analyze Known Issues

PR6.10 verification separated full-project analyzer behavior from the avatar
display resolver changes.

## Commands

```text
flutter analyze
```

Result: timed out after 304 seconds with no analyzer findings printed.

```text
flutter analyze --no-pub
```

Result: timed out after 184 seconds with no analyzer findings printed.

```text
flutter analyze --no-pub lib test
```

Result: pass. `No issues found! (ran in 40.2s)`.

```text
dart analyze lib test
```

Result: pass. `No issues found!`.

```text
flutter analyze --no-pub lib/shared/utils/profile_display_image_resolver.dart test/profile_display_image_resolver_test.dart
```

Result: pass. `No issues found! (ran in 3.4s)`.

```text
flutter test test/profile_display_image_resolver_test.dart
```

Result: pass. `7` resolver tests passed.

## Attribution

The PR6.10 avatar-display changes are not the cause of the full-project analyzer
timeout:

- The changed resolver and resolver test pass targeted `flutter analyze`.
- `lib` and `test` pass targeted `flutter analyze --no-pub`.
- Full-project analysis appears to traverse non-source project areas such as
  platform/build/generated directories. This needs a repo-level analyzer scope
  cleanup, not an avatar-pipeline repair.

Until that cleanup is done, use the targeted commands above for avatar media
repair verification.
