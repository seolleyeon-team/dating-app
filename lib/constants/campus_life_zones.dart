class CampusLifeZones {
  CampusLifeZones._();

  static const String sinchon = 'sinchon';
  static const String songdo = 'songdo';

  static const Map<String, String> labels = {
    sinchon: '신촌 생활권',
    songdo: '송도 생활권',
  };
}

class CampusLifeZoneResult {
  final List<String> zones;
  final List<String> labels;

  const CampusLifeZoneResult({required this.zones, required this.labels});
}

class CampusLifeZoneResolver {
  CampusLifeZoneResolver._();

  static CampusLifeZoneResult? resolve({
    required String? grade,
    required String? department,
    required bool isRa,
  }) {
    final normalizedDepartment = department?.trim() ?? '';
    if (normalizedDepartment.isEmpty) return null;

    final zoneSet = <String>{};

    if (_isMusicDepartment(normalizedDepartment)) {
      zoneSet.add(CampusLifeZones.sinchon);
    } else if (_isAlwaysSongdoDepartment(normalizedDepartment)) {
      zoneSet.add(CampusLifeZones.songdo);
    } else if (_isFirstYear(grade)) {
      zoneSet.add(CampusLifeZones.songdo);
    } else if (_isSecondYearOrAbove(grade)) {
      if (_isDualCampusDepartment(normalizedDepartment)) {
        zoneSet
          ..add(CampusLifeZones.sinchon)
          ..add(CampusLifeZones.songdo);
      } else {
        zoneSet.add(CampusLifeZones.sinchon);
      }
    }

    if (isRa) {
      zoneSet.add(CampusLifeZones.songdo);
    }

    if (zoneSet.isEmpty) return null;

    final orderedZones = <String>[
      if (zoneSet.contains(CampusLifeZones.sinchon)) CampusLifeZones.sinchon,
      if (zoneSet.contains(CampusLifeZones.songdo)) CampusLifeZones.songdo,
    ];

    return CampusLifeZoneResult(
      zones: orderedZones,
      labels: orderedZones
          .map((zone) => CampusLifeZones.labels[zone] ?? zone)
          .toList(),
    );
  }

  static bool _isFirstYear(String? grade) {
    return grade?.trim() == '1학년';
  }

  static bool _isSecondYearOrAbove(String? grade) {
    final normalizedGrade = grade?.trim() ?? '';
    return normalizedGrade == '2학년' ||
        normalizedGrade == '3학년' ||
        normalizedGrade == '4학년' ||
        normalizedGrade == '5학년 이상';
  }

  static bool _isMusicDepartment(String department) {
    return department.contains('음악대학');
  }

  static bool _isAlwaysSongdoDepartment(String department) {
    return department == '약학과' || department.contains('첨단융합공학부');
  }

  static bool _isDualCampusDepartment(String department) {
    return department.contains('언더우드') ||
        department.contains('HASS') ||
        department.contains('ISED') ||
        department.contains('ISE') ||
        department.contains('아시아학');
  }
}
