import 'package:firebase_storage/firebase_storage.dart';

import '../models/ai_preference_models.dart';
import 'ai_profile_storage_service.dart';

typedef AiProfilePrefixLister =
    Future<Iterable<String>> Function(String rootPath);

class AiProfileCatalogSnapshot {
  const AiProfileCatalogSnapshot({
    required this.source,
    required this.identities,
    required this.loadDuration,
  });

  final String source;
  final List<AiPreferenceIdentity> identities;
  final Duration loadDuration;
}

/// App-process cache for the Storage prefix catalog.
///
/// A cache instance can be injected by tests. Production services share one
/// cache so reopening the screen does not repeat `listAll()`.
class AiProfileCatalogCache {
  final Map<String, Future<AiProfileCatalogSnapshot>> _pendingByGender =
      <String, Future<AiProfileCatalogSnapshot>>{};

  Future<AiProfileCatalogSnapshot> getOrLoad(
    String gender,
    Future<AiProfileCatalogSnapshot> Function() loader,
  ) {
    final cached = _pendingByGender[gender];
    if (cached != null) return cached;

    late final Future<AiProfileCatalogSnapshot> pending;
    pending = () async {
      try {
        return await loader();
      } catch (_) {
        if (identical(_pendingByGender[gender], pending)) {
          _pendingByGender.remove(gender);
        }
        rethrow;
      }
    }();
    _pendingByGender[gender] = pending;
    return pending;
  }
}

/// Discovers real AI identities from one gender prefix.
///
/// Storage listing is used only as a catalog operation. Image URLs are
/// resolved separately and lazily by [AiProfileStorageService].
class AiProfileCatalogService {
  AiProfileCatalogService({
    FirebaseStorage? storage,
    AiProfilePrefixLister? prefixLister,
    AiProfileCatalogCache? cache,
  }) : _storage = storage,
       _prefixLister = prefixLister,
       _cache = cache ?? _sharedCache;

  static final AiProfileCatalogCache _sharedCache = AiProfileCatalogCache();

  final FirebaseStorage? _storage;
  final AiProfilePrefixLister? _prefixLister;
  final AiProfileCatalogCache _cache;

  Future<AiProfileCatalogSnapshot> load({required String gender}) {
    _validateGender(gender);
    return _cache.getOrLoad(gender, () => _loadUncached(gender));
  }

  Future<AiProfileCatalogSnapshot> _loadUncached(String gender) async {
    final stopwatch = Stopwatch()..start();
    final rootPath = 'ai_profiles/$gender';
    final lister = _prefixLister;
    final rawPrefixes = lister != null
        ? await lister(rootPath)
        : await _listStoragePrefixes(rootPath);

    final profileIds = <String>{};
    for (final rawPrefix in rawPrefixes) {
      final normalized = rawPrefix
          .replaceAll('\\', '/')
          .replaceFirst(RegExp(r'/+$'), '');
      final profileId = normalized.split('/').last;
      if (RegExp(r'^\d+$').hasMatch(profileId)) {
        profileIds.add(profileId);
      }
    }

    final sortedProfileIds = profileIds.toList()
      ..sort((first, second) {
        final numeric = int.parse(first).compareTo(int.parse(second));
        return numeric != 0 ? numeric : first.compareTo(second);
      });
    stopwatch.stop();

    return AiProfileCatalogSnapshot(
      source: 'storage-prefix',
      identities: List<AiPreferenceIdentity>.unmodifiable(
        sortedProfileIds.map(
          (profileId) =>
              AiPreferenceIdentity.create(gender: gender, profileId: profileId),
        ),
      ),
      loadDuration: stopwatch.elapsed,
    );
  }

  Future<Iterable<String>> _listStoragePrefixes(String rootPath) async {
    final storage = _configuredStorage;
    final projectId = storage.app.options.projectId;
    final bucket = storage.app.options.storageBucket;
    if (projectId != AiProfileStorageService.configuredProjectId ||
        bucket != AiProfileStorageService.configuredStorageBucket) {
      throw StateError(
        'AI preference catalog must use the configured final Firebase app',
      );
    }

    final result = await storage.ref(rootPath).listAll();
    return result.prefixes.map((prefix) => prefix.fullPath);
  }

  FirebaseStorage get _configuredStorage =>
      _storage ?? FirebaseStorage.instance;
}

void _validateGender(String gender) {
  if (gender != 'male' && gender != 'female') {
    throw ArgumentError.value(gender, 'gender', 'must be male or female');
  }
}
