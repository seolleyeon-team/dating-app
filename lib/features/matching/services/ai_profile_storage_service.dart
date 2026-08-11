import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter/foundation.dart';

import '../models/ai_preference_models.dart';

typedef AiProfileUrlResolver = Future<String?> Function(String storagePath);

class AiProfileStorageService {
  AiProfileStorageService({
    FirebaseStorage? storage,
    AiProfileUrlResolver? urlResolver,
    void Function(String message)? logger,
  }) : _storage = storage,
       _urlResolver = urlResolver,
       _logger = logger ?? debugPrint;

  static const String configuredProjectId = 'seolleyeon-final';
  static const String configuredStorageBucket =
      'seolleyeon-final.firebasestorage.app';

  final FirebaseStorage? _storage;
  final AiProfileUrlResolver? _urlResolver;
  final void Function(String message) _logger;
  final Map<String, Future<String?>> _urlCache = <String, Future<String?>>{};
  bool _storageSourceValidated = false;
  int _urlRequestCount = 0;
  int _cacheHitCount = 0;
  int _failedRequestCount = 0;
  int _missingObjectCount = 0;

  AiProfileStorageMetricsSnapshot get metrics =>
      AiProfileStorageMetricsSnapshot(
        urlRequestCount: _urlRequestCount,
        cacheHitCount: _cacheHitCount,
        failedRequestCount: _failedRequestCount,
        missingObjectCount: _missingObjectCount,
      );

  AiPreferenceIdentity buildIdentity({
    required String gender,
    required String profileId,
  }) {
    return AiPreferenceIdentity.create(gender: gender, profileId: profileId);
  }

  Future<AiPreferenceIdentity> resolveIdentity(
    AiPreferenceIdentity identity,
  ) async {
    final resolvedImages = await Future.wait(identity.images.map(resolveImage));
    return identity.withImages(resolvedImages);
  }

  Future<AiPreferenceImage> resolveImage(AiPreferenceImage image) async {
    _validateConfiguredStorageSource();
    return image.withDownloadUrl(await _resolveImageUrl(image));
  }

  Future<String?> _resolveImageUrl(AiPreferenceImage image) async {
    final cached = _urlCache[image.storagePath];
    if (cached != null) {
      _cacheHitCount++;
      return await cached;
    }

    final pending = _loadImageUrl(image);
    _urlCache[image.storagePath] = pending;
    try {
      return await pending;
    } catch (_) {
      if (identical(_urlCache[image.storagePath], pending)) {
        _urlCache.remove(image.storagePath);
      }
      rethrow;
    }
  }

  Future<String?> _loadImageUrl(AiPreferenceImage image) async {
    _urlRequestCount++;
    try {
      final resolver = _urlResolver;
      final url = resolver != null
          ? await resolver(image.storagePath)
          : await _configuredStorage.ref(image.storagePath).getDownloadURL();
      return url;
    } on FirebaseException catch (error) {
      _failedRequestCount++;
      if (error.code == 'object-not-found') {
        _missingObjectCount++;
        return null;
      }
      rethrow;
    } catch (error) {
      _failedRequestCount++;
      rethrow;
    }
  }

  void _validateConfiguredStorageSource() {
    if (_urlResolver != null || _storageSourceValidated) {
      return;
    }

    final storage = _configuredStorage;
    final projectId = storage.app.options.projectId;
    final bucket = storage.app.options.storageBucket;
    if (projectId != configuredProjectId || bucket != configuredStorageBucket) {
      throw StateError(
        'AI preference Storage must use the configured final Firebase app',
      );
    }
    _logger(
      '[ai_preference_storage] project=$projectId '
      'bucket=${bucket ?? '<unset>'}',
    );
    _storageSourceValidated = true;
  }

  FirebaseStorage get _configuredStorage =>
      _storage ?? FirebaseStorage.instance;
}

class AiProfileStorageMetricsSnapshot {
  const AiProfileStorageMetricsSnapshot({
    required this.urlRequestCount,
    required this.cacheHitCount,
    required this.failedRequestCount,
    required this.missingObjectCount,
  });

  final int urlRequestCount;
  final int cacheHitCount;
  final int failedRequestCount;
  final int missingObjectCount;
}
