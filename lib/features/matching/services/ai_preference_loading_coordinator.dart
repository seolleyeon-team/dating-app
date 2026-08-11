import 'dart:math';

import '../models/ai_preference_models.dart';
import 'ai_preference_deck.dart';
import 'ai_profile_catalog_service.dart';
import 'ai_profile_storage_service.dart';

class AiPreferenceLoadedIdentity {
  AiPreferenceLoadedIdentity({
    required this.identityId,
    required Iterable<AiPreferenceImage> shots,
  }) : shots = List<AiPreferenceImage>.unmodifiable(shots);

  final String identityId;
  final List<AiPreferenceImage> shots;

  bool get isComplete => shots.every(
    (shot) => shot.downloadUrl != null && shot.downloadUrl!.isNotEmpty,
  );

  AiPreferenceLoadedIdentity withShots(Iterable<AiPreferenceImage> nextShots) {
    return AiPreferenceLoadedIdentity(identityId: identityId, shots: nextShots);
  }
}

class AiPreferenceIdentityLoadResult {
  const AiPreferenceIdentityLoadResult({
    required this.identity,
    required this.candidatesInspected,
    required this.skippedIdentities,
    required this.resolveDuration,
  });

  final AiPreferenceLoadedIdentity identity;
  final int candidatesInspected;
  final int skippedIdentities;
  final Duration resolveDuration;
}

/// Builds a bounded, lazy AI preference window from a real identity catalog.
///
/// Initialization performs no URL resolution. Loading a visible identity
/// resolves only its first shuffled shot; the remaining two shots are an
/// explicit background operation.
class AiPreferenceLoadingCoordinator {
  AiPreferenceLoadingCoordinator({
    required AiProfileCatalogService catalogService,
    required AiProfileStorageService storageService,
    Random? random,
    AiPreferenceDeckBuilder? deckBuilder,
  }) : _catalogService = catalogService,
       _storageService = storageService,
       _random = random ?? Random.secure(),
       _deckBuilder = deckBuilder ?? AiPreferenceDeckBuilder(random: random);

  final AiProfileCatalogService _catalogService;
  final AiProfileStorageService _storageService;
  final Random _random;
  final AiPreferenceDeckBuilder _deckBuilder;
  final List<AiPreferenceIdentity> _candidateBag = <AiPreferenceIdentity>[];
  final Set<String> _invalidIdentityIds = <String>{};
  int _candidateIndex = 0;

  int get invalidIdentityCount => _invalidIdentityIds.length;

  Future<AiProfileCatalogSnapshot> initialize({
    required String targetGender,
  }) async {
    final snapshot = await _catalogService.load(gender: targetGender);
    _candidateBag
      ..clear()
      ..addAll(snapshot.identities)
      ..shuffle(_random);
    _candidateIndex = 0;
    _invalidIdentityIds.clear();
    return snapshot;
  }

  Future<AiPreferenceIdentityLoadResult?> loadNextIdentity() async {
    var inspected = 0;
    var skipped = 0;
    final stopwatch = Stopwatch()..start();

    while (_candidateIndex < _candidateBag.length) {
      final candidate = _candidateBag[_candidateIndex++];
      if (_invalidIdentityIds.contains(candidate.identityId)) continue;
      inspected++;

      final orderedShots = _deckBuilder.expand(candidate);
      final firstShot = await _storageService.resolveImage(orderedShots.first);
      if (firstShot.downloadUrl == null || firstShot.downloadUrl!.isEmpty) {
        _invalidIdentityIds.add(candidate.identityId);
        skipped++;
        continue;
      }

      final shots = List<AiPreferenceImage>.of(orderedShots);
      shots[0] = firstShot;
      stopwatch.stop();
      return AiPreferenceIdentityLoadResult(
        identity: AiPreferenceLoadedIdentity(
          identityId: candidate.identityId,
          shots: shots,
        ),
        candidatesInspected: inspected,
        skippedIdentities: skipped,
        resolveDuration: stopwatch.elapsed,
      );
    }

    stopwatch.stop();
    return null;
  }

  Future<AiPreferenceLoadedIdentity> hydrateRemaining(
    AiPreferenceLoadedIdentity identity,
  ) async {
    final resolved = await Future.wait(
      identity.shots.map(
        (shot) => shot.downloadUrl != null && shot.downloadUrl!.isNotEmpty
            ? Future<AiPreferenceImage>.value(shot)
            : _storageService.resolveImage(shot),
      ),
    );
    return identity.withShots(resolved);
  }

  Future<AiPreferenceLoadedIdentity> resolveShot(
    AiPreferenceLoadedIdentity identity,
    int shotIndex,
  ) async {
    if (shotIndex < 0 || shotIndex >= identity.shots.length) {
      throw RangeError.index(shotIndex, identity.shots, 'shotIndex');
    }
    final current = identity.shots[shotIndex];
    if (current.downloadUrl != null && current.downloadUrl!.isNotEmpty) {
      return identity;
    }

    final shots = List<AiPreferenceImage>.of(identity.shots);
    shots[shotIndex] = await _storageService.resolveImage(current);
    return identity.withShots(shots);
  }
}
