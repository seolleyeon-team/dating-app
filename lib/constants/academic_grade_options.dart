/// 온보딩에서 사용하는 학년 선택지 (단일 소스).
///
/// 이 값은 Firestore `users/{uid}.onboarding.grade` 에 문자열 그대로 저장되고,
/// [CampusLifeZoneResolver] 가 같은 문자열로 생활권을 판정한다. 따라서 라벨을
/// 바꾸면 기존 데이터·생활권 분류가 함께 어긋난다. 변경 시 migration 필요.
///
/// 기존에는 basic_info_screen 안에 private 상수로만 있었다. 생활권 보충
/// (repair) 화면이 같은 선택지를 써야 해서 사본을 만드는 대신 여기로 옮겼다.
const List<String> academicGradeOptions = <String>[
  '1학년',
  '2학년',
  '3학년',
  '4학년',
  '5학년 이상',
];
