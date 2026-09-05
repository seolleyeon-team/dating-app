import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/campus_life_zones.dart';
import 'package:seolleyeon/features/chat/data/promise_campus_places.dart';
import 'package:seolleyeon/features/chat/models/promise_place.dart';

void main() {
  test('campus locations use the campus category and zone', () {
    final songdoPlaces = PromiseCampusPlaces.options
        .where((place) => place.campusLifeZone == CampusLifeZones.songdo)
        .toList();
    final sinchonPlaces = PromiseCampusPlaces.options
        .where((place) => place.campusLifeZone == CampusLifeZones.sinchon)
        .toList();

    expect(songdoPlaces.map((place) => place.name), [
      '연돌',
      '진A 입구 앞',
      '기숙사 B동 우리은행 앞',
    ]);
    expect(sinchonPlaces.map((place) => place.name), [
      '연세대학교 정문 앞',
      '학생회관 앞',
      '백양로',
    ]);
    expect(
      PromiseCampusPlaces.options.every(
        (place) => place.category == PromisePlaceCategory.campus,
      ),
      isTrue,
    );
    expect(
      songdoPlaces.every(
        (place) => place.campusLifeZone == CampusLifeZones.songdo,
      ),
      isTrue,
    );
    expect(
      sinchonPlaces.every(
        (place) => place.campusLifeZone == CampusLifeZones.sinchon,
      ),
      isTrue,
    );
  });

  test('custom campus location remains identifiable after saving', () {
    final place = PromiseCampusPlaces.custom('학생회관 1층 앞');

    expect(place.placeId, PromisePlace.customCampusPlaceId);
    expect(place.isCustomInput, isTrue);
    expect(place.category, PromisePlaceCategory.campus);
    expect(place.name, '학생회관 1층 앞');
  });

  test('legacy place ids infer their campus life zone', () {
    final songdo = PromisePlace.fromMap(const {
      'name': '송도 장소',
    }, 'songdo_legacy_place');
    final sinchon = PromisePlace.fromMap(const {
      'name': '신촌 장소',
    }, 'sinchon_legacy_place');

    expect(songdo.campusLifeZone, CampusLifeZones.songdo);
    expect(sinchon.campusLifeZone, CampusLifeZones.sinchon);
  });

  test('explicit campusLifeZone takes precedence over the document id', () {
    final place = PromisePlace.fromMap(const {
      'name': '명시된 장소',
      'campusLifeZone': 'sinchon',
    }, 'songdo_misleading_prefix');

    expect(place.campusLifeZone, CampusLifeZones.sinchon);
  });
}
