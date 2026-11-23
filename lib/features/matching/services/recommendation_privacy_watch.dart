import 'dart:async';

/// A comparable summary of everything on the viewer's side that decides which
/// recommendation cards may be shown: the viewer-document fields the feed
/// reads, and the uids excluded for this viewer.
///
/// The feed loader and the live watcher both produce it, from the same
/// inputs, so "did anything relevant change since this feed was built" is a
/// string comparison.
abstract final class RecommendationPrivacyFingerprint {
  static String combine(String viewerInputs, Iterable<String> excludedUids) {
    final sorted = excludedUids.toSet().toList()..sort();
    return '$viewerInputs#${sorted.join(',')}';
  }

  /// Order-independent text form of a Firestore value.
  static String canonical(Object? value) {
    if (value is Map) {
      final keys = value.keys.map((key) => key.toString()).toList()..sort();
      final entries = {
        for (final entry in value.entries) entry.key.toString(): entry.value,
      };
      return '{${keys.map((key) => '$key:${canonical(entries[key])}').join(',')}}';
    }
    if (value is Iterable) {
      return '[${value.map(canonical).join(',')}]';
    }
    return value.toString();
  }
}

/// Turns the three viewer-side sources into a stream of fingerprints.
///
/// Nothing is emitted until every source has delivered once, and a snapshot
/// that leaves the fingerprint unchanged is dropped. The viewer document is
/// rewritten constantly by fields the feed never reads (heart balance, last
/// active time, push token); each of those snapshots used to clear the cards
/// and reload the whole feed.
Stream<String> watchRecommendationPrivacyFingerprints({
  required Stream<String> viewerInputs,
  required Stream<Set<String>> pairExclusions,
  required Stream<Set<String>> departmentExclusions,
}) {
  late final StreamController<String> controller;
  final subscriptions = <StreamSubscription<Object?>>[];
  String? viewer;
  Set<String>? pairs;
  Set<String>? departments;
  String? lastEmitted;

  void publish() {
    final currentViewer = viewer;
    final currentPairs = pairs;
    final currentDepartments = departments;
    if (currentViewer == null ||
        currentPairs == null ||
        currentDepartments == null) {
      return;
    }
    final fingerprint = RecommendationPrivacyFingerprint.combine(
      currentViewer,
      {...currentPairs, ...currentDepartments},
    );
    if (fingerprint == lastEmitted) return;
    lastEmitted = fingerprint;
    controller.add(fingerprint);
  }

  controller = StreamController<String>(
    onListen: () {
      subscriptions
        ..add(
          viewerInputs.listen((value) {
            viewer = value;
            publish();
          }, onError: controller.addError),
        )
        ..add(
          pairExclusions.listen((value) {
            pairs = value;
            publish();
          }, onError: controller.addError),
        )
        ..add(
          departmentExclusions.listen((value) {
            departments = value;
            publish();
          }, onError: controller.addError),
        );
    },
    onCancel: () async {
      for (final subscription in subscriptions) {
        await subscription.cancel();
      }
    },
  );
  return controller.stream;
}

/// Decides whether a fingerprint from the watcher makes the displayed feed
/// stale.
///
/// The feed loader reports the fingerprint it built the feed on. A watcher
/// value equal to it changes nothing. This also covers the watcher's first
/// value, which describes the state the feed was just loaded from and used to
/// trigger a second full load on every start.
class RecommendationReloadGate {
  String? _feedFingerprint;
  String? _latest;
  String? _latestAtLoadStart;
  bool _loading = false;

  void loadStarted() {
    _loading = true;
    _latestAtLoadStart = _latest;
  }

  /// Call when a load ends. [feedFingerprint] is null when the load failed or
  /// ended before it read the exclusions. Returns whether the watcher moved
  /// during the load to a state that load did not see, so it must run again.
  bool loadFinished(String? feedFingerprint) {
    _loading = false;
    final latest = _latest;
    final movedDuringLoad = latest != _latestAtLoadStart;
    if (feedFingerprint == null) {
      _feedFingerprint = latest;
      // The first watcher value arriving mid-load is not a change.
      return movedDuringLoad && _latestAtLoadStart != null;
    }
    _feedFingerprint = feedFingerprint;
    return movedDuringLoad && latest != null && latest != feedFingerprint;
  }

  /// Call for every watcher value. Returns whether the feed must be reloaded
  /// now. While a load is running the answer is deferred to [loadFinished].
  bool onFingerprint(String fingerprint) {
    _latest = fingerprint;
    if (_loading) return false;
    final feedFingerprint = _feedFingerprint;
    if (feedFingerprint == null) {
      _feedFingerprint = fingerprint;
      return false;
    }
    return fingerprint != feedFingerprint;
  }
}
