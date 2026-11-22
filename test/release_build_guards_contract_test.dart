import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/adult_verification_service.dart';
import 'package:seolleyeon/shared/utils/app_check_provider_policy.dart';
import 'package:seolleyeon/shared/utils/release_build_guards.dart';

/// B-09: a release binary must not be able to enable a debug / QA bypass,
/// even when somebody passes the `--dart-define`.
///
/// The four switches: FORCE_APP_CHECK_DEBUG, ADULT_VERIFICATION_BYPASS,
/// SEOLLEYEON_QA_ALLOW_SCREEN_CAPTURE, APP_CHECK_DIAGNOSTIC_MODE (plus the
/// App Check debug tokens, which are credentials).
void main() {
  const guardsPath = 'lib/shared/utils/release_build_guards.dart';
  const adultPath = 'lib/services/adult_verification_service.dart';

  final dartSources = <String, String>{
    for (final entity in Directory('lib').listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart'))
        entity.path.replaceAll('\\', '/'): entity.readAsStringSync(),
  };

  /// Files that read `name` straight from the compile-time environment.
  Set<String> readersOf(String name) {
    final pattern = RegExp("fromEnvironment\\(\\s*'$name'");
    return {
      for (final entry in dartSources.entries)
        if (pattern.hasMatch(entry.value)) entry.key,
    };
  }

  final guards = dartSources[guardsPath]!;

  group('decision', () {
    test('a request is honoured only outside a release build', () {
      expect(
        ReleaseBuildGuards.resolve(isReleaseBuild: false, requested: true),
        isTrue,
      );
      expect(
        ReleaseBuildGuards.resolve(isReleaseBuild: true, requested: true),
        isFalse,
      );
      expect(
        ReleaseBuildGuards.resolve(isReleaseBuild: false, requested: false),
        isFalse,
      );
      expect(
        ReleaseBuildGuards.resolve(isReleaseBuild: true, requested: false),
        isFalse,
      );
    });

    test('every switch is off when its define is not passed', () {
      expect(ReleaseBuildGuards.forceAppCheckDebugProvider, isFalse);
      expect(ReleaseBuildGuards.appCheckDiagnosticMode, isFalse);
      expect(ReleaseBuildGuards.allowQaScreenCapture, isFalse);
      expect(ReleaseBuildGuards.androidAppCheckDebugToken, isEmpty);
      expect(ReleaseBuildGuards.webAppCheckDebugToken, isEmpty);
      expect(AdultVerificationService.isTemporarilyDisabled, isFalse);
    });

    test('a release build never selects an App Check debug provider', () {
      for (final force in [true, false]) {
        expect(
          shouldUseDebugAppCheckProvider(
            isWeb: false,
            isReleaseMode: true,
            forceDebugProvider: force,
          ),
          isFalse,
          reason: 'forceDebugProvider=$force',
        );
      }
    });
  });

  group('source contract', () {
    test('each guarded switch is `!kReleaseMode && requested`', () {
      const switches = {
        'forceAppCheckDebugProvider': '_forceAppCheckDebugRequested',
        'appCheckDiagnosticMode': '_appCheckDiagnosticRequested',
        'allowQaScreenCapture': '_qaScreenCaptureRequested',
      };
      for (final entry in switches.entries) {
        expect(
          guards,
          matches(
            RegExp(
              'static const bool ${entry.key} =\\s+'
              '!kReleaseMode && ${entry.value};',
            ),
          ),
          reason: entry.key,
        );
      }
    });

    test('debug tokens are compiled out of a release build', () {
      for (final name in [
        'androidAppCheckDebugToken',
        'webAppCheckDebugToken',
      ]) {
        expect(
          guards,
          matches(
            RegExp("static const String $name = kReleaseMode\\s+\\? ''\\s+: _"),
          ),
          reason: name,
        );
      }
    });

    test('App Check switches and tokens are read only through the guards', () {
      for (final name in [
        'FORCE_APP_CHECK_DEBUG',
        'APP_CHECK_DIAGNOSTIC_MODE',
        'APP_CHECK_ANDROID_DEBUG_TOKEN',
        'APP_CHECK_WEB_DEBUG_TOKEN',
      ]) {
        expect(readersOf(name), {guardsPath}, reason: name);
      }
      final main = dartSources['lib/main.dart']!;
      expect(main, contains('ReleaseBuildGuards.forceAppCheckDebugProvider'));
      expect(main, contains('ReleaseBuildGuards.appCheckDiagnosticMode'));
      expect(main, contains('ReleaseBuildGuards.androidAppCheckDebugToken'));
      expect(main, contains('ReleaseBuildGuards.webAppCheckDebugToken'));
      expect(main, isNot(contains('isDebugMode: true')));
    });

    test('the adult-verification bypass keeps its release guard', () {
      expect(readersOf('ADULT_VERIFICATION_BYPASS'), {adultPath});
      expect(
        dartSources[adultPath]!,
        contains('isTemporarilyDisabled = !kReleaseMode && _bypassRequested'),
      );
    });

    // Every reader of the QA screen-capture define goes through
    // `ReleaseBuildGuards.allowQaScreenCapture`. The set stays here, empty, so
    // that a NEW unguarded reader fails this test instead of being added to it.
    const pendingUnguardedQaCaptureReaders = <String>{};

    test('the QA screen-capture switch has no unguarded reader', () {
      expect(readersOf('SEOLLEYEON_QA_ALLOW_SCREEN_CAPTURE'), {
        guardsPath,
        ...pendingUnguardedQaCaptureReaders,
      });
      for (final path in [
        'lib/app.dart',
        'lib/shared/widgets/app_privacy_splash_overlay.dart',
        'lib/shared/widgets/capture_protected_image.dart',
      ]) {
        expect(
          dartSources[path]!,
          contains('ReleaseBuildGuards.allowQaScreenCapture'),
          reason: path,
        );
      }
    });
  });

  group('build pipeline', () {
    const forbidden = [
      'FORCE_APP_CHECK_DEBUG',
      'ADULT_VERIFICATION_BYPASS',
      'SEOLLEYEON_QA_ALLOW_SCREEN_CAPTURE',
      'APP_CHECK_DIAGNOSTIC_MODE',
      'APP_CHECK_ANDROID_DEBUG_TOKEN',
      'APP_CHECK_WEB_DEBUG_TOKEN',
    ];

    test('CI workflows never pass a debug switch', () {
      final workflows = Directory('.github/workflows')
          .listSync()
          .whereType<File>()
          .where((file) => file.path.endsWith('.yml'));
      expect(workflows, isNotEmpty);
      for (final file in workflows) {
        final source = file.readAsStringSync();
        for (final name in forbidden) {
          expect(source, isNot(contains(name)), reason: '${file.path}: $name');
        }
      }
    });

    test('Gradle and the store release script do not inject them', () {
      for (final path in [
        'android/app/build.gradle.kts',
        'android/gradle.properties',
        'scripts/build_android_portone_release.sh',
      ]) {
        final source = File(path).readAsStringSync();
        for (final name in forbidden) {
          expect(source, isNot(contains(name)), reason: '$path: $name');
        }
      }
    });
  });
}
