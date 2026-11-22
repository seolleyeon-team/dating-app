import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/firebase_emulator_config.dart';
import 'package:seolleyeon/services/firebase_runtime.dart';

class _RecordingBinder implements FirebaseEmulatorBinder {
  _RecordingBinder({this.failOn});

  final String? failOn;
  final List<String> calls = [];

  Future<void> _bind(String service, String host, int port) async {
    if (service == failOn) throw StateError('bind failed');
    calls.add('$service@$host:$port');
  }

  @override
  Future<void> bindAuth(String host, int port) => _bind('auth', host, port);

  @override
  Future<void> bindFirestore(String host, int port) =>
      _bind('firestore', host, port);

  @override
  Future<void> bindFunctions(String host, int port) =>
      _bind('functions', host, port);

  @override
  Future<void> bindStorage(String host, int port) =>
      _bind('storage', host, port);
}

/// B-18: a run against the Emulator Suite must route EVERY backend service
/// there (Storage used to stay on the production bucket), a release build
/// must never be routed, and a partial routing must stop start-up.
void main() {
  group('routing', () {
    test('all four services are routed together', () async {
      final binder = _RecordingBinder();
      final used = await configureFirebaseEmulators(
        requested: true,
        isReleaseBuild: false,
        host: ' 10.0.2.2 ',
        binder: binder,
      );
      expect(used, isTrue);
      expect(binder.calls, [
        'auth@10.0.2.2:9099',
        'firestore@10.0.2.2:8080',
        'functions@10.0.2.2:5001',
        'storage@10.0.2.2:9199',
      ]);
    });

    test('nothing is routed when the emulators were not requested', () async {
      final binder = _RecordingBinder();
      expect(
        await configureFirebaseEmulators(
          requested: false,
          isReleaseBuild: false,
          host: '127.0.0.1',
          binder: binder,
        ),
        isFalse,
      );
      expect(binder.calls, isEmpty);
    });

    test('a release build is never routed, even when requested', () async {
      final binder = _RecordingBinder();
      expect(
        await configureFirebaseEmulators(
          requested: true,
          isReleaseBuild: true,
          host: '127.0.0.1',
          binder: binder,
        ),
        isFalse,
      );
      expect(binder.calls, isEmpty);
      expect(
        shouldUseFirebaseEmulators(requested: true, isReleaseBuild: true),
        isFalse,
      );
    });

    for (final service in ['auth', 'firestore', 'functions', 'storage']) {
      test('a failed $service binding aborts instead of mixing', () async {
        final binder = _RecordingBinder(failOn: service);
        await expectLater(
          configureFirebaseEmulators(
            requested: true,
            isReleaseBuild: false,
            host: '127.0.0.1',
            binder: binder,
          ),
          throwsA(
            isA<FirebaseEmulatorRoutingError>().having(
              (error) => error.failed,
              'failed',
              service,
            ),
          ),
        );
      });
    }

    test('an empty host is refused before anything is routed', () async {
      final binder = _RecordingBinder();
      await expectLater(
        configureFirebaseEmulators(
          requested: true,
          isReleaseBuild: false,
          host: '  ',
          binder: binder,
        ),
        throwsA(isA<FirebaseEmulatorRoutingError>()),
      );
      expect(binder.calls, isEmpty);
    });
  });

  group('source contract', () {
    final main = File('lib/main.dart').readAsStringSync();
    final config = File(
      'lib/services/firebase_emulator_config.dart',
    ).readAsStringSync();
    final dartSources = <String, String>{
      for (final entity in Directory('lib').listSync(recursive: true))
        if (entity is File && entity.path.endsWith('.dart'))
          entity.path.replaceAll('\\', '/'): entity.readAsStringSync(),
    };

    test('ports match the firebase.json emulators block', () {
      final emulators =
          (jsonDecode(File('firebase.json').readAsStringSync())
                  as Map<String, dynamic>)['emulators']
              as Map<String, dynamic>;
      int port(String name) =>
          (emulators[name] as Map<String, dynamic>)['port'] as int;
      expect(FirebaseEmulatorPorts.auth, port('auth'));
      expect(FirebaseEmulatorPorts.firestore, port('firestore'));
      expect(FirebaseEmulatorPorts.functions, port('functions'));
      expect(FirebaseEmulatorPorts.storage, port('storage'));
    });

    test('main routes before any other Firebase service is touched', () {
      final init = main.indexOf('await Firebase.initializeApp(');
      final routing = main.indexOf('await configureFirebaseEmulators(');
      expect(init, isNonNegative);
      expect(routing, greaterThan(init));
      for (final later in [
        'CrashReporting.instance.install()',
        'FirebaseAppCheck.instance.activate(',
        'IapService.instance.initialize()',
        'runApp(',
      ]) {
        expect(main.indexOf(later), greaterThan(routing), reason: later);
      }
      expect(main, contains('isReleaseBuild: kReleaseMode'));
    });

    test('emulator bindings exist only in the routing module', () {
      final binding = RegExp(
        r'use(Auth|Firestore|Functions|Storage)Emulator\(',
      );
      final users = {
        for (final entry in dartSources.entries)
          if (binding.hasMatch(entry.value)) entry.key,
      };
      expect(users, {'lib/services/firebase_emulator_config.dart'});
      for (final call in [
        'useAuthEmulator(',
        'useFirestoreEmulator(',
        'useFunctionsEmulator(',
        'useStorageEmulator(',
      ]) {
        expect(config, contains(call));
      }
    });

    test('every callable region and bucket in use is a routed one', () {
      // Only the default instance and firebaseFunctionsRegion are bound, so
      // a callable in any other region would silently hit production.
      final regionArgument = RegExp(
        r'FirebaseFunctions\.instanceFor\(\s*region:\s*([^,)\s]+)',
      );
      final regionConstant = RegExp(r"_(?:functionsR|r)egion\s*=\s*'([^']*)'");
      const routedExpressions = {
        "'asia-northeast3'",
        'firebaseFunctionsRegion',
        '_region',
        '_functionsRegion',
      };
      var callableInstances = 0;
      for (final entry in dartSources.entries) {
        if (entry.value.contains('FirebaseFunctions')) {
          for (final match in regionArgument.allMatches(entry.value)) {
            callableInstances += 1;
            expect(
              routedExpressions,
              contains(match.group(1)),
              reason: '${entry.key}: ${match.group(0)}',
            );
          }
          for (final match in regionConstant.allMatches(entry.value)) {
            expect(
              match.group(1),
              firebaseFunctionsRegion,
              reason: '${entry.key}: ${match.group(0)}',
            );
          }
        }
        // Only FirebaseStorage.instance (the default bucket) is bound.
        expect(
          entry.value,
          isNot(contains('FirebaseStorage.instanceFor(')),
          reason: entry.key,
        );
        expect(
          entry.value,
          isNot(contains('FirebaseFirestore.instanceFor(')),
          reason: entry.key,
        );
      }
      expect(callableInstances, greaterThan(10));
    });
  });
}
