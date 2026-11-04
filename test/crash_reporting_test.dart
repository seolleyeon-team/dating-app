import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/core/error/crash_reporting.dart';

/// P1-6 — crash reporting is wired once, deduplicates, and never ships raw
/// exception messages.
void main() {
  setUp(() => CrashReporting.instance.resetForTest());

  test(
    'install is safe before Firebase is available and is idempotent',
    () async {
      final previousFlutterOnError = FlutterError.onError;
      try {
        await expectLater(CrashReporting.instance.install(), completes);
        expect(CrashReporting.instance.isInstalled, isTrue);
        expect(
          CrashReporting.instance.isCollectionEnabled,
          isFalse,
          reason: 'no Firebase app in tests → nothing can be uploaded',
        );
        expect(FlutterError.onError, isNot(same(previousFlutterOnError)));
        final afterFirst = FlutterError.onError;
        await CrashReporting.instance.install();
        expect(
          FlutterError.onError,
          same(afterFirst),
          reason: 'second install does not rebind',
        );
      } finally {
        FlutterError.onError = previousFlutterOnError;
      }
    },
  );

  test(
    'the same error object is reported once (framework + zone + explicit)',
    () {
      final error = StateError('boom');
      expect(CrashReporting.instance.claimReport(error), isTrue);
      expect(CrashReporting.instance.claimReport(error), isFalse);
      expect(
        CrashReporting.instance.claimReport(StateError('boom')),
        isTrue,
        reason: 'a different instance is a different report',
      );
    },
  );

  test(
    'what leaves the device carries the type and the privacy summary, never the message',
    () {
      final sanitized = SanitizedCrashError.from(
        FirebaseException(
          plugin: 'firebase_auth',
          code: 'invalid-email',
          message: 'student@yonsei.ac.kr is not valid, token=abc123',
        ),
      );
      expect(sanitized.errorType, 'FirebaseException');
      expect(
        sanitized.summary,
        'errorType=FirebaseException code=invalid-email',
      );
      expect(sanitized.toString(), isNot(contains('yonsei')));
      expect(sanitized.toString(), isNot(contains('abc123')));

      final plain = SanitizedCrashError.from(
        ArgumentError('phone 010-1234-5678'),
      );
      expect(plain.toString(), isNot(contains('010')));
      expect(SanitizedCrashError.from(plain), same(plain));
    },
  );

  test(
    'main wires every sink through the facade and gates collection on release builds',
    () {
      final main = File('lib/main.dart').readAsStringSync();
      expect(main, contains('CrashReporting.instance.install()'));
      expect(
        main,
        contains('CrashReporting.instance.recordZoneError(error, stack)'),
      );
      expect(main, contains('runZonedGuarded('));

      final facade = File(
        'lib/core/error/crash_reporting.dart',
      ).readAsStringSync();
      expect(facade, contains('FlutterError.onError = '));
      expect(facade, contains('PlatformDispatcher.instance.onError = '));
      expect(facade, contains('kReleaseMode && !kIsWeb'));
      expect(facade, contains('SanitizedCrashError.from(error)'));
      expect(
        facade,
        isNot(contains('error.toString()')),
        reason: 'raw exception text must never be forwarded',
      );

      final handler = File(
        'lib/core/error/error_handler.dart',
      ).readAsStringSync();
      expect(handler, contains('CrashReporting.instance.recordNonFatal('));
      expect(handler, isNot(contains('TODO')));

      final gradle = File('android/app/build.gradle.kts').readAsStringSync();
      expect(gradle, contains('id("com.google.firebase.crashlytics")'));
      final settings = File('android/settings.gradle.kts').readAsStringSync();
      expect(settings, contains('com.google.firebase.crashlytics'));
      final pubspec = File('pubspec.yaml').readAsStringSync();
      expect(pubspec, contains('firebase_crashlytics:'));
    },
  );
}
