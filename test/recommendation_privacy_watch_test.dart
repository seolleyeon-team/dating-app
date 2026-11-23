import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/services/recommendation_privacy_watch.dart';
import 'package:seolleyeon/services/ai_recommendation_service.dart';

Map<String, dynamic> _viewer({
  int heartBalance = 0,
  int lastActive = 0,
  String department = '컴퓨터과학과',
  List<String> zones = const ['sinchon'],
  bool avoidSameDepartment = false,
}) {
  return {
    'nickname': '민지',
    'heartBalance': heartBalance,
    'lastActiveAt': lastActive,
    'fcmToken': 'token-$lastActive',
    'onboarding': {'department': department, 'campusLifeZones': zones},
    'privacySettings': {'avoidSameDepartment': avoidSameDepartment},
  };
}

/// The three live sources, and a feed wired to them the way the mystery-card
/// screen wires it: every load reads the current server state, and the gate
/// decides which watcher values start another load.
class _Feed {
  final viewerDocs = StreamController<Map<String, dynamic>?>();
  final pairExclusions = StreamController<Set<String>>();
  final departmentExclusions = StreamController<Set<String>>();

  Map<String, dynamic>? serverViewer = _viewer();
  Set<String> serverExcluded = <String>{};

  final gate = RecommendationReloadGate();
  int loads = 0;
  int viewerSnapshots = 0;
  int watcherValues = 0;
  late final StreamSubscription<String> _subscription;

  void start() {
    gate.loadStarted();
    _subscription =
        watchRecommendationPrivacyFingerprints(
          viewerInputs: viewerDocs.stream.map((doc) {
            viewerSnapshots += 1;
            return AiRecommendationService.viewerRecommendationInputs(doc);
          }),
          pairExclusions: pairExclusions.stream,
          departmentExclusions: departmentExclusions.stream,
        ).listen((fingerprint) {
          watcherValues += 1;
          if (gate.onFingerprint(fingerprint)) load();
        });
  }

  String _serverFingerprint() => RecommendationPrivacyFingerprint.combine(
    AiRecommendationService.viewerRecommendationInputs(serverViewer),
    serverExcluded,
  );

  void load() {
    gate.loadStarted();
    loads += 1;
    if (gate.loadFinished(_serverFingerprint())) load();
  }

  void finishInitialLoad() {
    loads += 1;
    if (gate.loadFinished(_serverFingerprint())) load();
  }

  void pushViewer(Map<String, dynamic> doc) {
    serverViewer = doc;
    viewerDocs.add(doc);
  }

  Future<void> close() async {
    await _subscription.cancel();
    await viewerDocs.close();
    await pairExclusions.close();
    await departmentExclusions.close();
  }
}

Future<void> _flush() => Future<void>.delayed(Duration.zero);

void main() {
  group('viewer recommendation inputs', () {
    final base = AiRecommendationService.viewerRecommendationInputs(_viewer());

    test('ignore fields the feed never reads', () {
      expect(
        AiRecommendationService.viewerRecommendationInputs(
          _viewer(heartBalance: 37, lastActive: 99),
        ),
        base,
      );
    });

    test('change with every field the feed is filtered by', () {
      final changed = {
        'department': _viewer(department: '경영학과'),
        'campusLifeZones': _viewer(zones: const ['songdo']),
        'avoidSameDepartment': _viewer(avoidSameDepartment: true),
        'privacySettings': _viewer()
          ..['privacySettings'] = {
            'avoidSameDepartment': false,
            'excludeKakaoFriends': true,
          },
      };
      for (final entry in changed.entries) {
        expect(
          AiRecommendationService.viewerRecommendationInputs(entry.value),
          isNot(base),
          reason: entry.key,
        );
      }
    });

    test('do not depend on map key order', () {
      expect(
        RecommendationPrivacyFingerprint.canonical({'b': 1, 'a': 2}),
        RecommendationPrivacyFingerprint.canonical({'a': 2, 'b': 1}),
      );
    });
  });

  group('feed loads', () {
    test('N irrelevant viewer-document updates start no feed load', () async {
      const irrelevantUpdates = 20;
      final feed = _Feed()..start();
      addTearDown(feed.close);

      // Start-up: the three listeners deliver their first snapshot while the
      // first load is running.
      feed.viewerDocs.add(feed.serverViewer);
      feed.pairExclusions.add(<String>{});
      feed.departmentExclusions.add(<String>{});
      await _flush();
      feed.finishInitialLoad();

      for (var i = 1; i <= irrelevantUpdates; i++) {
        feed.pushViewer(_viewer(heartBalance: i, lastActive: i));
      }
      await _flush();

      // Before: every snapshot of every source called
      // `_invalidateAndReloadRecommendations`, i.e. one extra load for the
      // start-up snapshots and one per viewer-document update.
      const loadsBefore = 1 + 1 + irrelevantUpdates;
      expect(feed.viewerSnapshots, 1 + irrelevantUpdates);
      expect(feed.watcherValues, 1);
      expect(feed.loads, 1);
      expect(feed.loads, lessThan(loadsBefore));
    });

    test('a change the feed is filtered by reloads it once', () async {
      final feed = _Feed()..start();
      addTearDown(feed.close);
      feed.viewerDocs.add(feed.serverViewer);
      feed.pairExclusions.add(<String>{});
      feed.departmentExclusions.add(<String>{});
      await _flush();
      feed.finishInitialLoad();

      feed.pushViewer(_viewer(avoidSameDepartment: true));
      await _flush();
      expect(feed.loads, 2);

      // A new pair exclusion (Kakao friend) materialised by the server.
      feed.serverExcluded = {'friend-1'};
      feed.pairExclusions.add({'friend-1'});
      await _flush();
      expect(feed.loads, 3);

      // The same exclusion set delivered again changes nothing.
      feed.pairExclusions.add({'friend-1'});
      feed.pushViewer(_viewer(avoidSameDepartment: true, heartBalance: 5));
      await _flush();
      expect(feed.loads, 3);
    });

    test('a watcher error reaches the listener', () async {
      final viewer = StreamController<String>();
      final pairs = StreamController<Set<String>>();
      final departments = StreamController<Set<String>>();
      final errors = <Object>[];
      final subscription = watchRecommendationPrivacyFingerprints(
        viewerInputs: viewer.stream,
        pairExclusions: pairs.stream,
        departmentExclusions: departments.stream,
      ).listen((_) {}, onError: errors.add);

      pairs.addError(StateError('permission-denied'));
      await _flush();
      expect(errors, hasLength(1));

      await subscription.cancel();
      expect(viewer.hasListener, isFalse);
      expect(pairs.hasListener, isFalse);
      expect(departments.hasListener, isFalse);
      await viewer.close();
      await pairs.close();
      await departments.close();
    });
  });

  group('RecommendationReloadGate', () {
    test('the first watcher value arriving during the first load is not a '
        'change', () {
      final gate = RecommendationReloadGate()..loadStarted();
      expect(gate.onFingerprint('A'), isFalse);
      expect(gate.loadFinished('A'), isFalse);
      expect(gate.onFingerprint('A'), isFalse);
    });

    test('a change that lands while a load is running runs it again', () {
      final gate = RecommendationReloadGate()..loadStarted();
      expect(gate.onFingerprint('A'), isFalse);
      expect(gate.loadFinished('A'), isFalse);

      gate.loadStarted();
      // The load read state A, then the watcher moved to B.
      expect(gate.onFingerprint('B'), isFalse);
      expect(gate.loadFinished('A'), isTrue);

      gate.loadStarted();
      expect(gate.loadFinished('B'), isFalse);
    });

    test('a stale cached first value does not loop against the server', () {
      final gate = RecommendationReloadGate();
      // Cached snapshot (old) delivered before any load.
      expect(gate.onFingerprint('cached'), isFalse);
      gate.loadStarted();
      expect(gate.loadFinished('server'), isFalse);
      // The listener catches up with the server.
      expect(gate.onFingerprint('server'), isFalse);
      // A later real change still reloads.
      expect(gate.onFingerprint('changed'), isTrue);
    });

    test('a load without a fingerprint adopts the watcher state', () {
      final gate = RecommendationReloadGate()..loadStarted();
      expect(gate.onFingerprint('A'), isFalse);
      expect(gate.loadFinished(null), isFalse);
      expect(gate.onFingerprint('A'), isFalse);
      expect(gate.onFingerprint('B'), isTrue);

      gate.loadStarted();
      expect(gate.onFingerprint('C'), isFalse);
      expect(
        gate.loadFinished(null),
        isTrue,
        reason: 'a real change during a load that could not report its state',
      );
    });
  });
}
