import 'package:cloud_firestore/cloud_firestore.dart';

/// Kakao / Naver 등 외부 장소 ID (딥링크·검색 보조용).
class PromisePlaceExternalLinks {
  final String? kakaoPlaceId;
  final String? naverPlaceId;

  const PromisePlaceExternalLinks({
    this.kakaoPlaceId,
    this.naverPlaceId,
  });

  factory PromisePlaceExternalLinks.fromMap(Map<String, dynamic>? raw) {
    if (raw == null) return const PromisePlaceExternalLinks();
    return PromisePlaceExternalLinks(
      kakaoPlaceId: raw['kakaoPlaceId']?.toString(),
      naverPlaceId: raw['naverPlaceId']?.toString(),
    );
  }

  Map<String, dynamic> toMap() => {
        if (kakaoPlaceId != null && kakaoPlaceId!.isNotEmpty)
          'kakaoPlaceId': kakaoPlaceId,
        if (naverPlaceId != null && naverPlaceId!.isNotEmpty)
          'naverPlaceId': naverPlaceId,
      };
}

/// Firestore `place_catalog_items.category` — 소문자 키만 사용:
/// `cafe` → 카페, `restaurant` → 식당, `bar` → 술집/바, `extra` → 그 외 장소.
abstract final class PromisePlaceCategory {
  static const String cafe = 'cafe';
  static const String restaurant = 'restaurant';
  static const String bar = 'bar';
  static const String extra = 'extra';

  /// 저장·필터용 키로 통일. 예전 한글 `placeCategory` 문자열은 가능한 범위에서 키로 환산.
  static String normalize(String? raw) {
    if (raw == null || raw.trim().isEmpty) return extra;
    final t = raw.trim().toLowerCase();
    if (t == cafe || t == restaurant || t == bar || t == extra) return t;
    final o = raw.trim();
    if (o.contains('카페')) return cafe;
    if (o.contains('식당') || o.contains('맛집')) return restaurant;
    if (o.contains('술집') || o == '바' || o.contains('바')) return bar;
    return extra;
  }

  static String label(String keyOrRaw) {
    switch (normalize(keyOrRaw)) {
      case cafe:
        return '카페';
      case restaurant:
        return '식당';
      case bar:
        return '술집/바';
      case extra:
        return '그 외 장소';
      default:
        return '그 외 장소';
    }
  }

  /// UI용. 비어 있으면 빈 문자열 (약속에 카테고리 없을 때).
  static String labelOrEmpty(String? keyOrRaw) {
    if (keyOrRaw == null || keyOrRaw.trim().isEmpty) return '';
    return label(keyOrRaw);
  }
}

/// 송도 등 지역 약속 장소 카탈로그 항목.
class PromisePlace {
  final String placeId;
  final String name;
  final String category;
  final String description;
  final String address;
  final double lat;
  final double lng;
  final String thumbnailUrl;
  final List<String> imageUrls;
  final bool isActive;
  final int sortOrder;
  final List<String> tags;
  final PromisePlaceExternalLinks externalLinks;

  const PromisePlace({
    required this.placeId,
    required this.name,
    required this.category,
    required this.description,
    required this.address,
    required this.lat,
    required this.lng,
    required this.thumbnailUrl,
    required this.imageUrls,
    required this.isActive,
    required this.sortOrder,
    required this.tags,
    required this.externalLinks,
  });

  factory PromisePlace.fromFirestoreDoc(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    return PromisePlace.fromMap(data, doc.id);
  }

  factory PromisePlace.fromMap(Map<String, dynamic> data, String placeId) {
    final linksRaw = data['externalLinks'];
    Map<String, dynamic>? linksMap;
    if (linksRaw is Map<String, dynamic>) {
      linksMap = Map<String, dynamic>.from(linksRaw);
    } else if (linksRaw is Map) {
      linksMap = Map<String, dynamic>.from(linksRaw);
    }

    final imgs = data['imageUrls'];
    final List<String> urls = [];
    if (imgs is List) {
      for (final e in imgs) {
        final s = e?.toString() ?? '';
        if (s.isNotEmpty) urls.add(s);
      }
    }

    final tagList = data['tags'];
    final List<String> tagOut = [];
    if (tagList is List) {
      for (final e in tagList) {
        final s = e?.toString() ?? '';
        if (s.isNotEmpty) tagOut.add(s);
      }
    }

    double toD(dynamic v) {
      if (v is num) return v.toDouble();
      return double.tryParse(v?.toString() ?? '') ?? 0.0;
    }

    return PromisePlace(
      placeId: placeId,
      name: data['name']?.toString() ?? '',
      category: PromisePlaceCategory.normalize(data['category']?.toString()),
      description: data['description']?.toString() ?? '',
      address: data['address']?.toString() ?? '',
      lat: toD(data['lat']),
      lng: toD(data['lng']),
      thumbnailUrl: data['thumbnailUrl']?.toString() ?? '',
      imageUrls: urls,
      isActive: data['isActive'] != false,
      sortOrder: (data['sortOrder'] is num)
          ? (data['sortOrder'] as num).toInt()
          : int.tryParse(data['sortOrder']?.toString() ?? '') ?? 0,
      tags: tagOut,
      externalLinks: PromisePlaceExternalLinks.fromMap(linksMap),
    );
  }

  factory PromisePlace.fromJsonMap(Map<String, dynamic> json) {
    return PromisePlace.fromMap(json, json['placeId']?.toString() ?? '');
  }

  Map<String, dynamic> toJsonMap() => {
        'placeId': placeId,
        'name': name,
        'category': category,
        'description': description,
        'address': address,
        'lat': lat,
        'lng': lng,
        'thumbnailUrl': thumbnailUrl,
        'imageUrls': imageUrls,
        'isActive': isActive,
        'sortOrder': sortOrder,
        'tags': tags,
        'externalLinks': externalLinks.toMap(),
      };

  /// 로컬 캐시 / JSON 복원용 (placeId 필수).
  static List<PromisePlace> listFromJsonList(List<dynamic>? raw) {
    if (raw == null) return [];
    final out = <PromisePlace>[];
    for (final e in raw) {
      if (e is Map) {
        final m = Map<String, dynamic>.from(e);
        final id = m['placeId']?.toString() ?? '';
        if (id.isEmpty) continue;
        out.add(PromisePlace.fromMap(m, id));
      }
    }
    return out;
  }

  static List<Map<String, dynamic>> listToJsonList(List<PromisePlace> list) {
    return list.map((e) => e.toJsonMap()).toList();
  }
}

/// `place_catalog_meta/current` 문서.
class PlaceCatalogMeta {
  final int version;
  final String region;
  final DateTime? updatedAt;

  const PlaceCatalogMeta({
    required this.version,
    required this.region,
    this.updatedAt,
  });

  factory PlaceCatalogMeta.fromMap(Map<String, dynamic>? data) {
    if (data == null) {
      return const PlaceCatalogMeta(version: 0, region: '');
    }
    final v = data['version'];
    int ver = 0;
    if (v is num) {
      ver = v.toInt();
    } else {
      ver = int.tryParse(v?.toString() ?? '') ?? 0;
    }
    DateTime? u;
    final ua = data['updatedAt'];
    if (ua is Timestamp) u = ua.toDate();
    return PlaceCatalogMeta(
      version: ver,
      region: data['region']?.toString() ?? '',
      updatedAt: u,
    );
  }
}
