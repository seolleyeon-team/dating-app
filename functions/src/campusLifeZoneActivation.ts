import type { Firestore } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

/**
 * 생활권 hard filter 의 rollout activation.
 *
 * 최종 정책(생활권이 다르면 매칭 불가, 값이 없으면 fail-closed)은 고정이다.
 * 이 플래그는 "그 정책을 지금 production 경로에서 강제할 것인가"만 결정한다.
 * missing 사용자만 허용하거나 cross-zone 을 일부 허용하는 완화 모드가 아니다.
 *
 *   OFF -> 기존 매칭 정책 그대로 (생활권 조건 미적용)
 *   ON  -> 기존 매칭 정책 + 생활권 hard eligibility
 *
 * authoritative 위치는 Firestore `recommendationConfig/current` 문서다
 * (blindMeetingConfig/current 와 같은 관례). 서버 전용 write 이고,
 * 재배포 없이 한 번의 write 로 즉시 ON/OFF 할 수 있어 rollback 이 가장 빠르다.
 *
 * 상태는 3개다. "명시적으로 꺼져 있다" 와 "지금 상태를 모른다" 를 같은 false
 * 로 뭉개면, 활성화 이후의 일시적 조회 실패가 조용히 cross-zone 을 다시
 * 허용한다 (fail-open).
 *
 *   "off"      — 문서를 읽었고 활성화되지 않았다 (문서 없음 포함).
 *   "enforced" — 문서를 읽었고 boolean true 였다.
 *   "unknown"  — 조회 자체가 실패했고, 직전에 확인한 값도 없다.
 */
export const RECOMMENDATION_CONFIG_COLLECTION = "recommendationConfig";
export const RECOMMENDATION_CONFIG_DOC = "current";
export const CAMPUS_LIFE_ZONE_ENFORCED_FIELD = "campusLifeZoneEnforced";
export const CAMPUS_LIFE_ZONE_POLICY_VERSION_FIELD =
  "campusLifeZonePolicyVersion";

export type CampusLifeZoneActivationState = "off" | "enforced" | "unknown";

export type CampusLifeZoneActivation = {
  state: CampusLifeZoneActivationState;
  policyVersion: number;
  /** 이번 조회가 실패해 직전 값(last-known-good)을 그대로 쓴 경우 true. */
  staleFallback: boolean;
};

/** config 문서 내용으로 activation 상태를 정한다 (읽기는 성공한 상태). */
export function campusLifeZoneActivationFromConfig(
  config: Record<string, unknown> | null | undefined
): "off" | "enforced" {
  if (config == null) return "off";
  return config[CAMPUS_LIFE_ZONE_ENFORCED_FIELD] === true ? "enforced" : "off";
}

/** config 문서에서 activation 상태를 읽는다. 없으면 false (OFF). */
export function campusLifeZoneEnforcedFromConfig(
  config: Record<string, unknown> | null | undefined
): boolean {
  return campusLifeZoneActivationFromConfig(config) === "enforced";
}

/** 정책 세대. 세 런타임이 같은 정책 epoch 를 쓰는지 확인할 때 쓴다. */
export function campusLifeZonePolicyVersionFromConfig(
  config: Record<string, unknown> | null | undefined
): number {
  if (config == null) return 0;
  const raw = config[CAMPUS_LIFE_ZONE_POLICY_VERSION_FIELD];
  if (typeof raw !== "number" || !Number.isInteger(raw) || raw <= 0) return 0;
  return raw;
}

/**
 * Firestore 에서 activation 상태를 읽는다.
 *
 * 짧게 캐시한다. 매칭 한 번에 여러 번 호출되어도 read 가 늘지 않게 하되,
 * ON/OFF 전환이 오래 지연되지 않도록 TTL 을 작게 둔다.
 *
 * TTL 이 지난 뒤 조회가 실패하면 **직전에 확인한 값(last-known-good)을
 * 유지한다.** 활성화된 뒤의 일시적 장애가 정책을 조용히 끄면 안 되고,
 * 준비 단계의 일시적 장애가 정책을 갑자기 켜서도 안 된다. 인스턴스가 방금
 * 뜬 cold start 라 직전 값이 아예 없을 때만 "unknown" 이며, 그 처리는
 * 호출부가 각자의 안전한 방식으로 정한다.
 */
const CACHE_TTL_MS = 30_000;
let cachedState: "off" | "enforced" | null = null;
let cachedPolicyVersion = 0;
let cachedAtMs = 0;

export async function loadCampusLifeZoneActivation(
  db: Firestore,
  { now = Date.now() }: { now?: number } = {}
): Promise<CampusLifeZoneActivation> {
  if (cachedState !== null && now - cachedAtMs < CACHE_TTL_MS) {
    return {
      state: cachedState,
      policyVersion: cachedPolicyVersion,
      staleFallback: false,
    };
  }
  try {
    const snap = await db
      .collection(RECOMMENDATION_CONFIG_COLLECTION)
      .doc(RECOMMENDATION_CONFIG_DOC)
      .get();
    const data = (snap.data() ?? null) as Record<string, unknown> | null;
    cachedState = campusLifeZoneActivationFromConfig(data);
    cachedPolicyVersion = campusLifeZonePolicyVersionFromConfig(data);
    cachedAtMs = now;
    return {
      state: cachedState,
      policyVersion: cachedPolicyVersion,
      staleFallback: false,
    };
  } catch (error) {
    if (cachedState !== null) {
      // last-known-good 유지. 장애가 정책을 바꾸지 않는다.
      logger.warn("campus life zone activation read failed, keeping last known", {
        code: "campusLifeZoneActivationReadFailure",
        campusLifeZoneActivationState: cachedState,
        staleFallback: true,
      });
      return {
        state: cachedState,
        policyVersion: cachedPolicyVersion,
        staleFallback: true,
      };
    }
    logger.error("campus life zone activation unknown (cold start)", {
      code: "campusLifeZoneActivationReadFailure",
      campusLifeZoneActivationState: "unknown",
      staleFallback: false,
    });
    return { state: "unknown", policyVersion: 0, staleFallback: false };
  }
}

/**
 * boolean 이 필요한 호출부용 helper.
 *
 * `unknown` 을 어떻게 볼지는 **호출부가 반드시 명시한다.** 기본값을 두면
 * 그 기본값이 두 단계(준비/활성화) 중 한쪽에서 반드시 틀린다.
 *
 * - 매칭을 확정하거나 결과를 저장하는 경로: `unknown` 을 그대로 두고
 *   작업 자체를 중단하는 편이 안전하다 (이 helper 대신
 *   [loadCampusLifeZoneActivation] 을 쓰고 상태를 분기한다).
 * - 되돌릴 수 있는 표시(안내 문구 등)에만 `unknownAs: "off"` 를 쓴다.
 */
export async function loadCampusLifeZoneEnforced(
  db: Firestore,
  {
    now = Date.now(),
    unknownAs,
  }: { now?: number; unknownAs: "off" | "enforced" }
): Promise<boolean> {
  const activation = await loadCampusLifeZoneActivation(db, { now });
  if (activation.state === "unknown") return unknownAs === "enforced";
  return activation.state === "enforced";
}

/** 테스트 전용: 캐시를 비운다 (cold start 재현). */
export function resetCampusLifeZoneActivationCache(): void {
  cachedState = null;
  cachedPolicyVersion = 0;
  cachedAtMs = 0;
}
