import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/promise_place.dart';

/// Firestore 장소 카탈로그 + 버전 기반 로컬 캐시.
class PromisePlaceService {
  PromisePlaceService({
    FirebaseFirestore? firestore,
  }) : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  static const _keyVersion = 'place_catalog_cached_version';
  static const _keyPlacesJson = 'place_catalog_cached_places_json';

  static const _metaDocPath = 'place_catalog_meta/current';
  static const _itemsCollection = 'place_catalog_items';

  /// 메타 문서 `version`만 네트워크에서 읽는다 (항목 전체 목록보다 가벼움).
  Future<PlaceCatalogMeta?> fetchMetaRemote() async {
    try {
      final snap = await _firestore.doc(_metaDocPath).get();
      if (!snap.exists) return null;
      return PlaceCatalogMeta.fromMap(snap.data());
    } catch (_) {
      return null;
    }
  }

  Future<List<PromisePlace>> _fetchItemsRemote() async {
    final snap = await _firestore.collection(_itemsCollection).get();
    final list = <PromisePlace>[];
    for (final doc in snap.docs) {
      final p = PromisePlace.fromFirestoreDoc(doc);
      if (p.isActive && p.name.isNotEmpty) {
        list.add(p);
      }
    }
    list.sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
    return list;
  }

  Future<void> _saveCache(int version, List<PromisePlace> places) async {
    final sp = await SharedPreferences.getInstance();
    await sp.setInt(_keyVersion, version);
    final encoded = jsonEncode(PromisePlace.listToJsonList(places));
    await sp.setString(_keyPlacesJson, encoded);
  }

  /// `null`: 아직 이 버전으로 동기화한 캐시가 없음. `[]`: 동기화 결과 장소 0개.
  Future<List<PromisePlace>?> _readCache() async {
    final sp = await SharedPreferences.getInstance();
    if (!sp.containsKey(_keyPlacesJson)) return null;
    final raw = sp.getString(_keyPlacesJson);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return null;
      return PromisePlace.listFromJsonList(decoded);
    } catch (_) {
      return null;
    }
  }

  Future<int> _readCachedVersion() async {
    final sp = await SharedPreferences.getInstance();
    return sp.getInt(_keyVersion) ?? -1;
  }

  /// 1) `place_catalog_meta/current`의 `version`을 읽어 로컬 캐시 버전과 비교.
  /// 2) 같으면 `place_catalog_items`를 읽지 않고 캐시만 반환(빈 목록도 캐시됨).
  /// 3) 다르면 항목 컬렉션을 한 번 읽고 캐시 갱신.
  /// 4) 메타가 없거나 네트워크 실패 시: 마지막으로 성공한 캐시가 있으면 사용, 없으면 `[]`.
  /// 앱에 넣은 예시 장소(fallback)는 사용하지 않는다.
  Future<List<PromisePlace>> loadPlaces() async {
    final remoteMeta = await fetchMetaRemote();
    final cachedVersion = await _readCachedVersion();
    final cached = await _readCache();

    if (remoteMeta == null) {
      try {
        final remoteItems = await _fetchItemsRemote();
        await _saveCache(cachedVersion >= 0 ? cachedVersion : 0, remoteItems);
        return remoteItems;
      } catch (_) {
        return cached ?? [];
      }
    }

    // 버전이 같아도 "빈 캐시"면 items 를 한 번 더 읽는다.
    // (Firestore 에만 장소를 나중에 넣고 meta version 을 안 올린 경우 대응)
    final useCacheOnly = remoteMeta.version == cachedVersion &&
        cached != null &&
        cached.isNotEmpty;

    if (useCacheOnly) {
      return cached;
    }

    try {
      final remoteItems = await _fetchItemsRemote();
      await _saveCache(remoteMeta.version, remoteItems);
      return remoteItems;
    } catch (_) {
      return cached ?? [];
    }
  }

  /// 메타·항목을 다시 읽어 캐시를 덮어쓴다(새로고침 버튼).
  Future<List<PromisePlace>> refreshFromRemote() async {
    final remoteMeta = await fetchMetaRemote();
    if (remoteMeta == null) {
      try {
        final remoteItems = await _fetchItemsRemote();
        final cachedVersion = await _readCachedVersion();
        await _saveCache(cachedVersion >= 0 ? cachedVersion : 0, remoteItems);
        return remoteItems;
      } catch (_) {
        return (await _readCache()) ?? [];
      }
    }
    try {
      final remoteItems = await _fetchItemsRemote();
      await _saveCache(remoteMeta.version, remoteItems);
      return remoteItems;
    } catch (_) {
      return (await _readCache()) ?? [];
    }
  }
}
