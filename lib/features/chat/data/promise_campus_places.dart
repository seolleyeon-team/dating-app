import '../models/promise_place.dart';
import '../../../constants/campus_life_zones.dart';

/// 신촌·송도 캠퍼스 안에서 약속 장소로 바로 고를 수 있는 기본 항목.
abstract final class PromiseCampusPlaces {
  static const double _songdoLatitude = 37.3769;
  static const double _songdoLongitude = 126.6341;
  static const double _sinchonLatitude = 37.5642;
  static const double _sinchonLongitude = 126.9368;

  static const List<PromisePlace> options = [
    PromisePlace(
      placeId: 'campus_yeondol',
      campusLifeZone: CampusLifeZones.songdo,
      name: '연돌',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _songdoLatitude,
      lng: _songdoLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -30,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'campus_jina_entrance',
      campusLifeZone: CampusLifeZones.songdo,
      name: '진A 입구 앞',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _songdoLatitude,
      lng: _songdoLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -29,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'campus_dorm_b_woori',
      campusLifeZone: CampusLifeZones.songdo,
      name: '기숙사 B동 우리은행 앞',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _songdoLatitude,
      lng: _songdoLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -28,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'sinchon_main_gate',
      campusLifeZone: CampusLifeZones.sinchon,
      name: '연세대학교 정문 앞',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _sinchonLatitude,
      lng: _sinchonLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -30,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'sinchon_student_union',
      campusLifeZone: CampusLifeZones.sinchon,
      name: '학생회관 앞',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _sinchonLatitude,
      lng: _sinchonLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -29,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'sinchon_baekyang_ro',
      campusLifeZone: CampusLifeZones.sinchon,
      name: '백양로',
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _sinchonLatitude,
      lng: _sinchonLongitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -28,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
  ];

  static PromisePlace? byId(String placeId) {
    for (final place in options) {
      if (place.placeId == placeId) return place;
    }
    return null;
  }

  static PromisePlace custom(String name) {
    return PromisePlace(
      placeId: PromisePlace.customCampusPlaceId,
      campusLifeZone: CampusLifeZones.songdo,
      name: name.trim(),
      category: PromisePlaceCategory.campus,
      description: '',
      address: '',
      lat: _songdoLatitude,
      lng: _songdoLongitude,
      thumbnailUrl: '',
      imageUrls: const [],
      isActive: true,
      sortOrder: -1,
      tags: const ['캠퍼스 안', '직접 입력'],
      externalLinks: const PromisePlaceExternalLinks(),
    );
  }
}
