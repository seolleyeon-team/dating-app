import 'package:flutter/foundation.dart';

import '../models/ai_preference_models.dart';
import 'ai_preference_loading_coordinator.dart';
import 'ai_profile_catalog_service.dart';
import 'ai_profile_storage_service.dart';

class AiPreferencePerformanceTrace {
  AiPreferencePerformanceTrace._({
    required Duration? tapToRouteStart,
    required void Function(String message) logger,
  }) : _tapToRouteStart = tapToRouteStart,
       _logger = logger,
       _routeStopwatch = Stopwatch()..start();

  static Stopwatch? _pendingLaunch;

  static void markLaunchTap() {
    _pendingLaunch = Stopwatch()..start();
  }

  static AiPreferencePerformanceTrace begin({
    void Function(String message)? logger,
  }) {
    final pendingLaunch = _pendingLaunch;
    _pendingLaunch = null;
    return AiPreferencePerformanceTrace._(
      tapToRouteStart: pendingLaunch?.elapsed,
      logger: logger ?? debugPrint,
    );
  }

  final Duration? _tapToRouteStart;
  final void Function(String message) _logger;
  final Stopwatch _routeStopwatch;
  Duration? _firstBuild;
  Duration? _firstUrlResolvedAt;
  bool _catalogLogged = false;
  bool _firstIdentityLogged = false;
  bool _firstPaintLogged = false;

  void markFirstBuild() {
    _firstBuild ??= _routeStopwatch.elapsed;
  }

  void logCatalog(AiProfileCatalogSnapshot snapshot) {
    if (_catalogLogged || kReleaseMode) return;
    _catalogLogged = true;
    _logger(
      '[AI_PREF_PERF] catalog source=${snapshot.source} '
      'identities=${snapshot.identities.length} '
      'loadMs=${snapshot.loadDuration.inMilliseconds} '
      'tapToRouteMs=${_tapToRouteStart?.inMilliseconds ?? -1} '
      'routeToFirstBuildMs=${_firstBuild?.inMilliseconds ?? -1}',
    );
  }

  void logFirstIdentity(AiPreferenceIdentityLoadResult result) {
    if (_firstIdentityLogged || kReleaseMode) return;
    _firstIdentityLogged = true;
    _firstUrlResolvedAt = _routeStopwatch.elapsed;
    final firstShot = result.identity.shots.first;
    final shotOrder = result.identity.shots
        .map((shot) => aiPreferenceShotTypeName(shot.shotType))
        .join(',');
    _logger(
      '[AI_PREF_PERF] firstIdentity=${result.identity.identityId} '
      'firstShot=${aiPreferenceShotTypeName(firstShot.shotType)} '
      'shotOrder=$shotOrder '
      'resolveMs=${result.resolveDuration.inMilliseconds} '
      'candidates=${result.candidatesInspected} '
      'skipped=${result.skippedIdentities}',
    );
  }

  void logFirstPaint({
    required AiProfileStorageMetricsSnapshot storageMetrics,
    required int invalidIdentityCount,
  }) {
    if (_firstPaintLogged || kReleaseMode) return;
    _firstPaintLogged = true;
    final routeToPaint = _routeStopwatch.elapsed;
    final firstUrlResolvedAt = _firstUrlResolvedAt;
    final imageFrameDuration = firstUrlResolvedAt == null
        ? null
        : routeToPaint - firstUrlResolvedAt;
    final tapToRouteStart = _tapToRouteStart;
    final totalFromTap = tapToRouteStart == null
        ? null
        : tapToRouteStart + routeToPaint;
    _logger(
      '[AI_PREF_PERF] firstPaintMs=${routeToPaint.inMilliseconds} '
      'tapToFirstPaintMs=${totalFromTap?.inMilliseconds ?? -1} '
      'imageFetchDecodePaintMs=${imageFrameDuration?.inMilliseconds ?? -1} '
      'getDownloadURL=${storageMetrics.urlRequestCount} '
      'failed=${storageMetrics.failedRequestCount}',
    );
    _logger(
      '[AI_PREF] invalidIdentities=$invalidIdentityCount '
      'missingObjects=${storageMetrics.missingObjectCount}',
    );
  }
}
