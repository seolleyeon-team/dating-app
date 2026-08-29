import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/data/promise_campus_places.dart';
import 'package:seolleyeon/features/chat/models/promise_place.dart';

void main() {
  test('campus locations use the campus category', () {
    expect(PromiseCampusPlaces.options.map((place) => place.name), [
      '연돌',
      '진A 입구 앞',
      '기숙사 B동 우리은행 앞',
    ]);
    expect(
      PromiseCampusPlaces.options.every(
        (place) => place.category == PromisePlaceCategory.campus,
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
}
