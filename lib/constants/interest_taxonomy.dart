// =============================================================================
// 관심사 taxonomy (단일 소스)
// 경로: lib/constants/interest_taxonomy.dart
//
// 온보딩 관심사 선택 화면과 블라인드 취향 미팅 매칭 알고리즘이 같은 taxonomy를
// 공유하기 위해 분리했다. 관심사 문자열 자체가 Firestore
// users/{uid}.onboarding.interests 에 저장되는 값이므로 라벨을 바꾸면
// 기존 데이터와 어긋난다. 라벨 변경 시 migration이 필요하다.
// =============================================================================

/// 관심사 카테고리 한 묶음.
class InterestCategory {
  final String id;
  final String emoji;
  final String title;
  final List<String> items;

  const InterestCategory({
    required this.id,
    required this.emoji,
    required this.title,
    required this.items,
  });
}

/// 온보딩에서 노출되는 카테고리 순서 그대로 유지한다.
const List<InterestCategory> interestCategories = [
  InterestCategory(
    id: 'indoor',
    emoji: '🏠',
    title: '실내 활동',
    items: [
      '넷플릭스',
      '홈트',
      '드라마 정주행',
      '온라인 쇼핑',
      '식물 가꾸기',
      '보드게임',
      '명상',
      '요가',
      '사우나',
      '유튜브',
      '먹방',
      '도서관',
      '노래',
      '시',
      '문학',
      '댄스',
      '독서',
      '카공',
      '공부',
    ],
  ),
  InterestCategory(
    id: 'outdoor',
    emoji: '⛺',
    title: '야외 활동',
    items: [
      '한강에서 치맥',
      '빈티지 쇼핑',
      '동네 산책',
      '만화 카페',
      '방탈출',
      '카페 탐방',
      '맛집 투어',
      '브런치',
      '수제 맥주',
      '바',
      '자동차 극장',
      '콘서트',
      '아쿠아리움',
      '쇼핑',
      '전시회',
      '연극',
      '롤러 스케이트',
      '노래방',
      '야경 보기',
      '캠핑',
      '서핑',
      '낚시',
      '피크닉',
      '다이빙',
      '여행',
      '오락실',
      '노상',
      '새벽 라면',
      '바다 보기',
      '사진',
      '스케이트',
    ],
  ),
  InterestCategory(
    id: 'food',
    emoji: '🍷',
    title: '음식',
    items: [
      '칵테일',
      '맥주',
      '빵',
      '양식',
      '스시',
      '일식',
      '해산물',
      '한식',
      '중식',
      '버블티',
      '차',
      '커피',
      '와인',
      'BBQ',
      '라면',
      '디저트',
      '아이스크림',
      '훠궈',
      '양꼬치',
      '붕어빵',
      '과일',
    ],
  ),
  InterestCategory(
    id: 'sports',
    emoji: '⚽️',
    title: '운동, 스포츠',
    items: [
      '야구',
      '축구',
      '스포츠',
      '배드민턴',
      '헬스장',
      '수영',
      '클라이밍',
      '피트니스',
      '필라테스',
      '농구',
      '러닝',
      '스케이트보드',
      '럭비',
      '크로스핏',
      '산책',
      '폴 댄스',
      '테니스',
      '복싱',
      '역도',
      '마라톤',
      '승마',
      '배구',
      '탁구',
      '당구',
      '사이클',
      '볼링',
      '사격',
      '스키',
      '스노우 보드',
    ],
  ),
  InterestCategory(
    id: 'screen',
    emoji: '🎬',
    title: '드라마, 영화',
    items: [
      'K-드라마',
      '애니메이션',
      '액션 영화',
      '드라마',
      '판타지 영화',
      'SF',
      '영화',
      '공포 영화',
      '로맨틱 코미디',
      '범죄 영화',
      '리얼리티 프로그램',
      '스릴러',
      '코미디',
    ],
  ),
  InterestCategory(
    id: 'music',
    emoji: '🎵',
    title: '음악',
    items: [
      '팝',
      '발라드',
      '락/밴드',
      '인디/얼터너티브',
      '힙합',
      'J-Pop',
      '일렉트로닉 음악',
      '클래식',
      '재즈/R&B',
      '헤비메탈',
      '마이너 음악',
    ],
  ),
  InterestCategory(
    id: 'game',
    emoji: '🎮',
    title: '게임',
    items: ['PC방', '롤', '오버워치', '플스', '닌텐도', '인디게임'],
  ),
  InterestCategory(
    id: 'creative',
    emoji: '🎨',
    title: '창작 활동',
    items: [
      '언어 교환',
      '악기',
      '창업',
      '패션',
      '블로그',
      '콘텐츠 제작',
      '메이크업',
      '요리',
      '글쓰기',
      '예술',
      '작곡',
      '베이킹',
      '드로잉',
    ],
  ),
  InterestCategory(
    id: 'social',
    emoji: '👥',
    title: '소셜',
    items: ['수다', '친구 만나기', '인스타그램', '브이로그', '소셜 미디어', '핀터레스트', '블로그'],
  ),
];

/// 관심사 라벨 → 카테고리 id 역인덱스.
///
/// 동일 라벨이 두 카테고리에 있는 경우(예: '블로그')는 먼저 정의된 카테고리를 쓴다.
final Map<String, String> interestCategoryIdByLabel = () {
  final map = <String, String>{};
  for (final category in interestCategories) {
    for (final item in category.items) {
      map.putIfAbsent(item, () => category.id);
    }
  }
  return Map<String, String>.unmodifiable(map);
}();

/// 알 수 없는(과거 taxonomy 또는 자유 입력) 관심사를 위한 카테고리 id.
const String unknownInterestCategoryId = 'other';

/// 관심사 라벨의 카테고리 id를 돌려준다. taxonomy에 없으면
/// [unknownInterestCategoryId] 를 반환한다.
String interestCategoryIdOf(String label) {
  final normalized = label.trim();
  if (normalized.isEmpty) return unknownInterestCategoryId;
  return interestCategoryIdByLabel[normalized] ?? unknownInterestCategoryId;
}
