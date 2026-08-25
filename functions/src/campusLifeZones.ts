/**
 * 생활권(campus life zone) canonical 값 검증.
 *
 * canonical 값은 온보딩 resolver(lib/constants/campus_life_zones.dart)가
 * 만드는 두 개뿐이다. 저장된 문서가 손상돼 그 밖의 토큰을 갖고 있으면
 * 생활권으로 인정하지 않는다 — 실제로 만날 수 없는 상대를 매칭하는 것보다
 * 보충을 요구하는 편이 안전하다 (fail-closed).
 *
 * Python(lib/ai_recommend_model/campus_life_zone_policy.py) / Dart
 * (lib/shared/utils/recommendation_eligibility.dart) 와 같은 계약을 쓴다.
 */

export const CAMPUS_LIFE_ZONE_SINCHON = "sinchon";
export const CAMPUS_LIFE_ZONE_SONGDO = "songdo";

export const CANONICAL_CAMPUS_LIFE_ZONES: ReadonlySet<string> = new Set([
  CAMPUS_LIFE_ZONE_SINCHON,
  CAMPUS_LIFE_ZONE_SONGDO,
]);

/**
 * Firestore 에 저장된 `campusLifeZones` 필드를 읽는다.
 *
 * canonical 스키마는 `List<String>` 이다.
 * - 배열이 아니면 (raw string `"sinchon"`, 숫자, null 등) 손상으로 보고 `[]`.
 * - canonical 이 아닌 토큰이 하나라도 있으면 **값 전체**를 무효로 보고 `[]`.
 *   (`["sinchon", "garbage"]` 도 무효)
 */
export function readPersistedCampusLifeZones(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const zones = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string") return [];
    const zone = item.trim();
    if (!CANONICAL_CAMPUS_LIFE_ZONES.has(zone)) return [];
    zones.add(zone);
  }
  return [...zones].sort();
}

/**
 * 이미 메모리에 있는 문자열 목록을 canonical 집합으로 정리한다.
 *
 * 저장된 문서를 읽을 때는 타입까지 검증하는
 * [readPersistedCampusLifeZones] 를 쓴다.
 */
export function normalizeCampusLifeZones(zones: readonly string[]): string[] {
  return readPersistedCampusLifeZones([...zones]);
}
