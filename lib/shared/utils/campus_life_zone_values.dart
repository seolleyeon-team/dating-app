import '../../constants/campus_life_zones.dart';

/// 저장된 생활권 값의 canonical 검증.
///
/// canonical 값은 온보딩의 [CampusLifeZoneResolver] 가 만드는 두 개
/// (`sinchon`, `songdo`) 뿐이다. 저장된 문서가 손상돼 그 밖의 토큰을 갖고
/// 있으면 생활권으로 인정하지 않는다 — 실제로 만날 수 없는 상대를 추천하는
/// 것보다 보충을 요구하는 편이 안전하다 (fail-closed).
///
/// Python(campus_life_zone_policy.py) / TypeScript(functions/src/campusLifeZones.ts)
/// 와 같은 계약을 쓴다.
class CampusLifeZoneValues {
  const CampusLifeZoneValues._();

  static const Set<String> canonical = <String>{
    CampusLifeZones.sinchon,
    CampusLifeZones.songdo,
  };

  /// Firestore 에 저장된 `campusLifeZones` 필드를 읽는다 (스키마 검증 포함).
  ///
  /// - canonical 스키마는 `List<String>` 이다. raw string `'sinchon'` 이나
  ///   숫자·null 은 손상으로 보고 빈 집합을 돌려준다.
  /// - canonical 이 아닌 토큰이 하나라도 있으면 **값 전체**를 무효로 본다
  ///   (`['sinchon', 'garbage']` 도 무효).
  static Set<String> readPersisted(dynamic raw) {
    if (raw is! List) return const <String>{};
    final zones = <String>{};
    for (final item in raw) {
      if (item is! String) return const <String>{};
      final zone = item.trim();
      if (!canonical.contains(zone)) return const <String>{};
      zones.add(zone);
    }
    return zones;
  }

  /// 이미 메모리에 있는 값 목록을 canonical 집합으로 정리한다.
  static Set<String> normalize(Iterable<String> zones) =>
      readPersisted(zones.toList());
}
