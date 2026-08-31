/**
 * 관심사 taxonomy (서버 사본)
 * 경로: functions/src/blindMeeting/interestTaxonomy.ts
 *
 * 원본: lib/constants/interest_taxonomy.dart (앱 온보딩과 공유하는 단일 소스)
 * 두 사본의 일치는 양쪽 테스트에서 카테고리/라벨 개수 fingerprint로 검증한다.
 *   - Dart : test/features/blind_meeting/interest_taxonomy_parity_test.dart
 *   - TS   : functions/src/blindMeeting/__tests__/matching.test.ts
 * 라벨은 Firestore users/{uid}.onboarding.interests 에 저장되는 값이므로
 * 바꾸면 migration이 필요하다.
 */

export const UNKNOWN_INTEREST_CATEGORY_ID = "other";

export type InterestCategory = {
  id: string;
  items: string[];
};

export const INTEREST_CATEGORIES: InterestCategory[] = [
  {
    id: "indoor",
    items: [
      "넷플릭스",
      "홈트",
      "드라마 정주행",
      "온라인 쇼핑",
      "식물 가꾸기",
      "보드게임",
      "명상",
      "요가",
      "사우나",
      "유튜브",
      "먹방",
      "도서관",
      "노래",
      "시",
      "문학",
      "댄스",
      "독서",
      "카공",
      "공부",
    ],
  },
  {
    id: "outdoor",
    items: [
      "한강에서 치맥",
      "빈티지 쇼핑",
      "동네 산책",
      "만화 카페",
      "방탈출",
      "카페 탐방",
      "맛집 투어",
      "브런치",
      "수제 맥주",
      "바",
      "자동차 극장",
      "콘서트",
      "아쿠아리움",
      "쇼핑",
      "전시회",
      "연극",
      "롤러 스케이트",
      "노래방",
      "야경 보기",
      "캠핑",
      "서핑",
      "낚시",
      "피크닉",
      "다이빙",
      "여행",
      "오락실",
      "노상",
      "새벽 라면",
      "바다 보기",
      "사진",
      "스케이트",
    ],
  },
  {
    id: "food",
    items: [
      "칵테일",
      "맥주",
      "빵",
      "양식",
      "스시",
      "일식",
      "해산물",
      "한식",
      "중식",
      "버블티",
      "차",
      "커피",
      "와인",
      "BBQ",
      "라면",
      "디저트",
      "아이스크림",
      "훠궈",
      "양꼬치",
      "붕어빵",
      "과일",
    ],
  },
  {
    id: "sports",
    items: [
      "야구",
      "축구",
      "스포츠",
      "배드민턴",
      "헬스장",
      "수영",
      "클라이밍",
      "피트니스",
      "필라테스",
      "농구",
      "러닝",
      "스케이트보드",
      "럭비",
      "크로스핏",
      "산책",
      "폴 댄스",
      "테니스",
      "복싱",
      "역도",
      "마라톤",
      "승마",
      "배구",
      "탁구",
      "당구",
      "사이클",
      "볼링",
      "사격",
      "스키",
      "스노우 보드",
    ],
  },
  {
    id: "screen",
    items: [
      "K-드라마",
      "애니메이션",
      "일본 애니메이션",
      "액션 영화",
      "드라마",
      "판타지 영화",
      "SF",
      "영화",
      "공포 영화",
      "로맨틱 코미디",
      "범죄 영화",
      "리얼리티 프로그램",
      "스릴러",
      "코미디",
    ],
  },
  {
    id: "music",
    items: [
      "팝",
      "발라드",
      "락/밴드",
      "인디/얼터너티브",
      "힙합",
      "J-Pop",
      "일렉트로닉 음악",
      "클래식",
      "재즈/R&B",
      "헤비메탈",
      "마이너 음악",
    ],
  },
  {
    id: "game",
    items: ["PC방", "롤", "오버워치", "플스", "닌텐도", "인디게임"],
  },
  {
    id: "creative",
    items: [
      "언어 교환",
      "악기",
      "창업",
      "패션",
      "블로그",
      "콘텐츠 제작",
      "메이크업",
      "요리",
      "글쓰기",
      "예술",
      "작곡",
      "베이킹",
      "드로잉",
    ],
  },
  {
    id: "social",
    items: [
      "수다",
      "친구 만나기",
      "인스타그램",
      "브이로그",
      "소셜 미디어",
      "핀터레스트",
      "블로그",
    ],
  },
];

const categoryIdByLabel: Map<string, string> = (() => {
  const map = new Map<string, string>();
  for (const category of INTEREST_CATEGORIES) {
    for (const item of category.items) {
      if (!map.has(item)) map.set(item, category.id);
    }
  }
  return map;
})();

export function interestCategoryIdOf(label: string): string {
  const normalized = label.trim();
  if (normalized.length === 0) return UNKNOWN_INTEREST_CATEGORY_ID;
  return categoryIdByLabel.get(normalized) ?? UNKNOWN_INTEREST_CATEGORY_ID;
}

/** taxonomy 사본 일치 검증용 fingerprint */
export function interestTaxonomyFingerprint(): {
  categories: number;
  labels: number;
  perCategory: Record<string, number>;
} {
  const perCategory: Record<string, number> = {};
  let labels = 0;
  for (const category of INTEREST_CATEGORIES) {
    perCategory[category.id] = category.items.length;
    labels += category.items.length;
  }
  return {
    categories: INTEREST_CATEGORIES.length,
    labels,
    perCategory,
  };
}
