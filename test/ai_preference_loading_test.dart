import 'dart:async';
import 'dart:math';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_loading_coordinator.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_performance_trace.dart';
import 'package:seolleyeon/features/matching/services/ai_profile_catalog_service.dart';
import 'package:seolleyeon/features/matching/services/ai_profile_storage_service.dart';

void main() {
  group('AI preference catalog loading', () {
    test('normalizes real Storage prefixes and caches the catalog', () async {
      var listCalls = 0;
      final cache = AiProfileCatalogCache();
      final firstService = AiProfileCatalogService(
        cache: cache,
        prefixLister: (rootPath) async {
          listCalls++;
          expect(rootPath, 'ai_profiles/female');
          return <String>[
            'ai_profiles/female/104/',
            'ai_profiles/female/112',
            'ai_profiles/female/not-an-id/',
            'ai_profiles/female/104/',
          ];
        },
      );
      final secondService = AiProfileCatalogService(
        cache: cache,
        prefixLister: (_) async {
          listCalls++;
          return <String>[];
        },
      );

      final first = await firstService.load(gender: 'female');
      final second = await secondService.load(gender: 'female');

      expect(first.source, 'storage-prefix');
      expect(first.identities.map((identity) => identity.identityId), <String>[
        'female_104',
        'female_112',
      ]);
      expect(second.identities.map((identity) => identity.identityId), <String>[
        'female_104',
        'female_112',
      ]);
      expect(listCalls, 1);
    });
  });

  group('AI preference lazy loading', () {
    test(
      'a 100-identity catalog resolves only one URL before first card',
      () async {
        var urlCalls = 0;
        final catalog = AiProfileCatalogService(
          cache: AiProfileCatalogCache(),
          prefixLister: (_) async => <String>[
            for (var id = 1; id <= 100; id++)
              'ai_profiles/female/${id.toString().padLeft(3, '0')}/',
          ],
        );
        final storage = AiProfileStorageService(
          urlResolver: (path) async {
            urlCalls++;
            return 'https://cdn.example/$path';
          },
        );
        final coordinator = AiPreferenceLoadingCoordinator(
          catalogService: catalog,
          storageService: storage,
          random: _KeepOrderRandom(),
        );

        final snapshot = await coordinator.initialize(targetGender: 'female');
        expect(snapshot.identities, hasLength(100));
        expect(urlCalls, 0);

        final first = await coordinator.loadNextIdentity();

        expect(first, isNotNull);
        expect(first!.candidatesInspected, 1);
        expect(first.skippedIdentities, 0);
        expect(first.identity.shots, hasLength(3));
        expect(
          first.identity.shots.where((shot) => shot.downloadUrl != null),
          hasLength(1),
        );
        expect(urlCalls, 1);

        final hydrated = await coordinator.hydrateRemaining(first.identity);
        expect(hydrated.isComplete, isTrue);
        expect(urlCalls, 3);

        await coordinator.hydrateRemaining(hydrated);
        expect(urlCalls, 3);
      },
    );

    test(
      'a stale catalog entry costs one miss, not three, before moving on',
      () async {
        final requestedPaths = <String>[];
        final catalog = AiProfileCatalogService(
          cache: AiProfileCatalogCache(),
          prefixLister: (_) async => <String>[
            'ai_profiles/female/104/',
            'ai_profiles/female/105/',
          ],
        );
        final storage = AiProfileStorageService(
          urlResolver: (path) async {
            requestedPaths.add(path);
            if (path.contains('/104/')) {
              throw FirebaseException(
                plugin: 'firebase_storage',
                code: 'object-not-found',
              );
            }
            return 'https://cdn.example/$path';
          },
        );
        final coordinator = AiPreferenceLoadingCoordinator(
          catalogService: catalog,
          storageService: storage,
          random: _KeepOrderRandom(),
        );

        await coordinator.initialize(targetGender: 'female');
        final first = await coordinator.loadNextIdentity();

        expect(first, isNotNull);
        expect(first!.identity.identityId, 'female_105');
        expect(first.candidatesInspected, 2);
        expect(first.skippedIdentities, 1);
        expect(requestedPaths, hasLength(2));
        expect(
          requestedPaths.where((path) => path.contains('/104/')),
          hasLength(1),
        );
      },
    );
  });

  group('AI profile URL cache', () {
    test('concurrent requests share one URL future', () async {
      var calls = 0;
      final pending = Completer<String?>();
      final storage = AiProfileStorageService(
        urlResolver: (_) {
          calls++;
          return pending.future;
        },
      );
      final image = storage
          .buildIdentity(gender: 'male', profileId: '009')
          .images
          .first;

      final first = storage.resolveImage(image);
      final second = storage.resolveImage(image);
      expect(calls, 1);

      pending.complete('https://cdn.example/male-009-face');
      expect((await first).downloadUrl, isNotNull);
      expect((await second).downloadUrl, isNotNull);
      expect(calls, 1);
    });

    test(
      'object-not-found is negatively cached but transient failures are not',
      () async {
        final callsByPath = <String, int>{};
        final storage = AiProfileStorageService(
          urlResolver: (path) async {
            callsByPath.update(path, (count) => count + 1, ifAbsent: () => 1);
            if (path.contains('/104/')) {
              throw FirebaseException(
                plugin: 'firebase_storage',
                code: 'object-not-found',
              );
            }
            if (callsByPath[path] == 1) {
              throw FirebaseException(
                plugin: 'firebase_storage',
                code: 'retry-limit-exceeded',
              );
            }
            return 'https://cdn.example/$path';
          },
        );
        final missing = storage
            .buildIdentity(gender: 'female', profileId: '104')
            .images
            .first;
        final transient = storage
            .buildIdentity(gender: 'female', profileId: '105')
            .images
            .first;

        expect((await storage.resolveImage(missing)).downloadUrl, isNull);
        expect((await storage.resolveImage(missing)).downloadUrl, isNull);
        expect(callsByPath[missing.storagePath], 1);

        await expectLater(
          storage.resolveImage(transient),
          throwsA(isA<FirebaseException>()),
        );
        expect((await storage.resolveImage(transient)).downloadUrl, isNotNull);
        expect(callsByPath[transient.storagePath], 2);
      },
    );
  });

  test('normal startup performance logging is bounded to four summaries', () {
    final logs = <String>[];
    final trace = AiPreferencePerformanceTrace.begin(logger: logs.add);
    final identity = AiPreferenceLoadedIdentity(
      identityId: 'female_104',
      shots: AiProfileStorageService()
          .buildIdentity(gender: 'female', profileId: '104')
          .images,
    );
    final catalog = AiProfileCatalogSnapshot(
      source: 'storage-prefix',
      identities: const <AiPreferenceIdentity>[],
      loadDuration: const Duration(milliseconds: 12),
    );
    final first = AiPreferenceIdentityLoadResult(
      identity: identity,
      candidatesInspected: 1,
      skippedIdentities: 0,
      resolveDuration: const Duration(milliseconds: 40),
    );
    const metrics = AiProfileStorageMetricsSnapshot(
      urlRequestCount: 1,
      cacheHitCount: 0,
      failedRequestCount: 0,
      missingObjectCount: 0,
    );

    trace.markFirstBuild();
    trace.logCatalog(catalog);
    trace.logCatalog(catalog);
    trace.logFirstIdentity(first);
    trace.logFirstIdentity(first);
    trace.logFirstPaint(storageMetrics: metrics, invalidIdentityCount: 0);
    trace.logFirstPaint(storageMetrics: metrics, invalidIdentityCount: 0);

    expect(logs, hasLength(4));
    expect(logs[0], startsWith('[AI_PREF_PERF] catalog '));
    expect(logs[1], startsWith('[AI_PREF_PERF] firstIdentity='));
    expect(logs[2], contains('getDownloadURL=1 failed=0'));
    expect(logs[3], '[AI_PREF] invalidIdentities=0 missingObjects=0');
  });
}

class _KeepOrderRandom implements Random {
  @override
  bool nextBool() => false;

  @override
  double nextDouble() => 0;

  @override
  int nextInt(int max) => max - 1;
}
