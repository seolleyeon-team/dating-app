/// 연세대학교 2026학년도 모집요강 8-9페이지에 표시된 모집단위 기반 학과 목록.
///
/// 앱의 4개 계열 선택값(`MajorType.name`)에 맞춰 분류한다.
class YonseiDepartments {
  YonseiDepartments._();

  static const Map<String, String> majorLabels = {
    'liberalArts': '문과 계열',
    'science': '이과 계열',
    'medical': '메디컬 계열',
    'artsSports': '예체능 계열',
  };

  static const Map<String, String> majorSubtitles = {
    'liberalArts': '인문 / 사회 / 상경',
    'science': '자연 / 공학',
    'medical': '의치한약수 / 간호',
    'artsSports': '미술 / 음악 / 체육',
  };

  static const Map<String, String> majorEmojis = {
    'liberalArts': '📚',
    'science': '🧪',
    'medical': '🏥',
    'artsSports': '🎨',
  };

  static const Map<String, List<String>> byMajor = {
    'liberalArts': [
      '경제학부',
      '경영학과',
      '교육학부',
      '국어국문학과',
      '글로벌인재학부',
      '노어노문학과',
      '독어독문학과',
      '문헌정보학과',
      '문화인류학과',
      '불어불문학과',
      '사학과',
      '사회복지학과',
      '사회학과',
      '신학과',
      '심리학과',
      '아동·가족학과',
      '아시아학전공',
      '언더우드학부(인문·사회)',
      '언론홍보영상학부',
      '영어영문학과',
      '융합인문사회과학부(HASS)',
      '응용통계학과',
      '정치외교학과',
      '중어중문학과',
      '진리자유학부(인문)',
      '철학과',
      '행정학과',
    ],
    'science': [
      '건축공학과',
      '기계공학부',
      '대기과학과',
      '도시공학과',
      '디스플레이융합공학과',
      '모빌리티시스템전공',
      '물리학과',
      '사회환경시스템공학부',
      '산업공학과',
      '생명공학과',
      '생명과학부',
      '생화학과',
      '수학과',
      '시스템반도체공학과',
      '시스템생물학과',
      '식품영양학과',
      '실내건축학과',
      '언더우드학부(생명과학공학)',
      '의류환경학과',
      '융합과학공학부(ISE)',
      '전기전자공학부',
      '지구시스템과학과',
      '지능형반도체전공',
      '진리자유학부(자연)',
      '천문우주학과',
      '첨단컴퓨팅학부',
      '화공생명공학부',
      '화학과',
      'IT융합공학전공',
    ],
    'medical': ['간호학과', '약학과', '의예과', '치의예과'],
    'artsSports': ['스포츠응용산업학과', '음악대학(전 모집단위)', '체육교육학과', '통합디자인학과'],
  };

  static bool hasMajor(String? major) {
    return major != null && byMajor.containsKey(major);
  }

  static String labelFor(String? major) {
    return majorLabels[major] ?? '선택한 계열';
  }

  static String subtitleFor(String? major) {
    return majorSubtitles[major] ?? '선택한 계열';
  }

  static String emojiFor(String? major) {
    return majorEmojis[major] ?? '🎓';
  }

  static String heroTagFor(String major) {
    return 'onboarding-major-card-$major';
  }

  static List<String> departmentsFor(String? major) {
    return byMajor[major] ?? const [];
  }
}
