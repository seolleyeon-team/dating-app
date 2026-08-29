import '../models/promise_place.dart';

/// 송도캠퍼스 안에서 약속 장소로 바로 고를 수 있는 기본 항목.
abstract final class PromiseCampusPlaces {
  static const String campusAddress = '인천광역시 연수구 아카데미로 119 인천대학교 송도캠퍼스';
  static const double _latitude = 37.3769;
  static const double _longitude = 126.6341;

  static const List<PromisePlace> options = [
    PromisePlace(
      placeId: 'campus_yeondol',
      name: '연돌',
      category: PromisePlaceCategory.campus,
      description: '인천대학교 송도캠퍼스 안 만남 장소',
      address: campusAddress,
      lat: _latitude,
      lng: _longitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -30,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'campus_jina_entrance',
      name: '진A 입구 앞',
      category: PromisePlaceCategory.campus,
      description: '인천대학교 송도캠퍼스 안 만남 장소',
      address: campusAddress,
      lat: _latitude,
      lng: _longitude,
      thumbnailUrl: '',
      imageUrls: [],
      isActive: true,
      sortOrder: -29,
      tags: ['캠퍼스 안'],
      externalLinks: PromisePlaceExternalLinks(),
    ),
    PromisePlace(
      placeId: 'campus_dorm_b_woori',
      name: '기숙사 B동 우리은행 앞',
      category: PromisePlaceCategory.campus,
      description: '인천대학교 송도캠퍼스 안 만남 장소',
      address: campusAddress,
      lat: _latitude,
      lng: _longitude,
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
      name: name.trim(),
      category: PromisePlaceCategory.campus,
      description: '직접 입력한 캠퍼스 안 장소',
      address: campusAddress,
      lat: _latitude,
      lng: _longitude,
      thumbnailUrl: '',
      imageUrls: const [],
      isActive: true,
      sortOrder: -1,
      tags: const ['캠퍼스 안', '직접 입력'],
      externalLinks: const PromisePlaceExternalLinks(),
    );
  }
}
