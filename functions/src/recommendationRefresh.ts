/**
 * 1대1 설레연 "유료 추천 새로고침" (paid reveal).
 *
 * 오늘의 추천 순위를 다시 계산하지 않는다. 이미 생성된 modelRecs 세트에서
 * 클라이언트가 노출 window 를 [1..3] -> [4..6] 으로 바꿀 자격(entitlement)을
 * Heart 5개 차감과 함께 서버 트랜잭션으로 단 한 번만 발급한다.
 *
 * Payment invariant: "Heart 5개가 차감되면 refresh 후 표시 가능한 서로 다른
 * 추천 프로필 3명이 존재한다." raw item 수가 아니라, 클라이언트
 * AiRecommendationService._hydrateProfiles 와 같은 eligibility 필터(차단,
 * 추천 제외, 탈퇴/정지, 프로필 미완성, 표시 이미지 없음, 생활권 게이트)를
 * 통과한 후보가 rank 순으로 6명 이상일 때만 결제한다.
 *
 * 자격 문서(users/{uid}/recommendationRefreshes/{dateKey})가 곧 영수증이다.
 * 문서 ID 가 dateKey 라서 uid+dateKey+product 조합이 결정적 idempotency key 가
 * 되고, 재시도/중복 요청은 already_purchased 로 수렴하며 잔액을 다시 깎지
 * 않는다. Heart 잔액 갱신은 grantPurchasedHearts 와 같은 필드
 * (users/{uid}.heartBalance + heartBalanceUpdatedAt)를 사용한다.
 */

import { onCall, HttpsError } from "firebase-functions/v2/https";
import type { DocumentSnapshot, Firestore, Timestamp } from "firebase-admin/firestore";
import { FieldValue } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import { withAppCheck } from "./appCheckPolicy";
import {
  campusLifeZoneEnforcedFromConfig,
  loadCampusLifeZoneActivation,
  RECOMMENDATION_CONFIG_COLLECTION,
  RECOMMENDATION_CONFIG_DOC,
} from "./campusLifeZoneActivation";
import { readPersistedCampusLifeZones } from "./campusLifeZones";
import { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";

export const ONE_TO_ONE_REFRESH_PRODUCT = "one_to_one_daily_refresh";
export const ONE_TO_ONE_REFRESH_COST_HEARTS = 5;
/** 화면에 한 번에 노출되는 추천 카드 수. */
export const ONE_TO_ONE_WINDOW_SIZE = 3;
export const ONE_TO_ONE_REFRESH_DISPLAY_RANK_START = 4;
export const ONE_TO_ONE_REFRESH_DISPLAY_RANK_END = 6;
/** 결제 전제조건: initial + refreshed 두 window 를 채울 eligible 후보 수. */
export const ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE = ONE_TO_ONE_WINDOW_SIZE * 2;

/**
 * 클라이언트(AiRecommendationService.fetchMysteryFeed)와 동일한 소스 우선순위.
 * 순서를 바꾸면 결제된 세트와 화면에 보이는 세트가 어긋난다.
 */
export const MYSTERY_FEED_ALGO_PRIORITY: readonly string[] = [
  "rrf",
  "clip",
  "svd",
];

/** KST(UTC+9) 기준 YYYYMMDD. 클라이언트 _generateKstDateKey 와 동일 규칙. */
export function kstDateKeyOf(dateTime: Date): string {
  const kst = new Date(dateTime.getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear().toString();
  const m = (kst.getUTCMonth() + 1).toString().padStart(2, "0");
  const d = kst.getUTCDate().toString().padStart(2, "0");
  return `${y}${m}${d}`;
}

export type RefreshCandidate = {
  uid: string;
  /** 배치가 기록한 원본 model rank. 결제/노출 과정에서 재번호를 매기지 않는다. */
  rank: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * source doc items 에서 uid 가 있는 후보를 원본 rank 오름차순으로 뽑는다.
 * 클라이언트 _hydrateProfiles 의 정렬(rank ?? 999)과 동일하다.
 */
export function parseRefreshCandidates(items: unknown): RefreshCandidate[] {
  if (!Array.isArray(items)) return [];
  const candidates: RefreshCandidate[] = [];
  for (const item of items) {
    if (!isRecord(item)) continue;
    const uid = typeof item.uid === "string" ? item.uid.trim() : "";
    if (!uid) continue;
    const rawRank = item.rank;
    const rank =
      typeof rawRank === "number" && Number.isFinite(rawRank)
        ? Math.trunc(rawRank)
        : 999;
    candidates.push({ uid, rank });
  }
  return candidates.sort((a, b) => a.rank - b.rank);
}

function readMap(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

/**
 * publicProfiles 문서에서 클라이언트 ProfileDisplayImageResolver 와 같은
 * 우선순위(승인 아바타 -> onboarding.avatarUrls 첫 장)로 표시 이미지가 있는지
 * 확인한다. projection 이 이미 URL 을 위생 처리하지만 방어적으로 한 번 더
 * 서버 정책으로 거른다.
 */
export function hasDisplayableImage(profile: Record<string, unknown>): boolean {
  const avatar = readMap(profile.avatar);
  const approvedUrl =
    typeof avatar.approvedAvatarUrl === "string"
      ? avatar.approvedAvatarUrl.trim()
      : "";
  if (
    avatar.status === "approved" &&
    approvedUrl.length > 0 &&
    isSafePublicAvatarUrl(approvedUrl)
  ) {
    return true;
  }
  const onboarding = readMap(profile.onboarding);
  const avatarUrls = onboarding.avatarUrls;
  if (Array.isArray(avatarUrls) && avatarUrls.length > 0) {
    const first =
      typeof avatarUrls[0] === "string" ? avatarUrls[0].trim() : "";
    return first.length > 0 && isSafePublicAvatarUrl(first);
  }
  return false;
}

const BLOCKED_ACCOUNT_STATUSES: ReadonlySet<string> = new Set([
  "blocked",
  "deleted",
  "suspended",
]);

function isAccountActive(profile: Record<string, unknown>): boolean {
  const rawStatus = profile.status ?? profile.accountStatus;
  const status =
    typeof rawStatus === "string" ? rawStatus.toLowerCase() : null;
  if (status !== null && BLOCKED_ACCOUNT_STATUSES.has(status)) return false;
  if (profile.isDeleted === true) return false;
  if (profile.isSuspended === true) return false;
  return profile.isActive !== false;
}

function isProfileComplete(profile: Record<string, unknown>): boolean {
  if (typeof profile.isProfileComplete === "boolean") {
    return profile.isProfileComplete;
  }
  return profile.initialSetupComplete === true;
}

/** `users/{uid}` 또는 publicProfiles 문서에서 생활권 집합을 읽는다. */
export function campusLifeZonesOf(
  profile: Record<string, unknown> | null | undefined,
): Set<string> {
  if (!profile) return new Set();
  const onboarding = readMap(profile.onboarding);
  const raw =
    onboarding.campusLifeZones !== undefined
      ? onboarding.campusLifeZones
      : profile.campusLifeZones;
  return new Set(readPersistedCampusLifeZones(raw));
}

/**
 * 클라이언트 _hydrateProfiles 의 후보 필터를 서버에서 재현한다. 여기서 하나라도
 * 통과하지 못하는 후보는 결제 후 카드로 렌더링되지 않으므로 eligible 로 세지
 * 않는다. Dart 쪽 대응: RecommendationEligibility.isCandidateDisplayable +
 * passesCampusLifeZoneGate (lib/shared/utils/recommendation_eligibility.dart).
 */
export function isRefreshCandidateDisplayable(
  profile: Record<string, unknown> | null | undefined,
  options: {
    enforceCampusZone: boolean;
    viewerZones: ReadonlySet<string>;
  },
): boolean {
  if (!profile) return false; // 삭제/탈퇴로 public 문서가 없는 후보
  if (profile.recommendationPrivacyReady !== true) return false;

  const schemaVersionRaw = profile.schemaVersion;
  const schemaVersion =
    typeof schemaVersionRaw === "number" && Number.isFinite(schemaVersionRaw)
      ? Math.trunc(schemaVersionRaw)
      : 1;
  const displayable =
    schemaVersion >= 2
      ? isAccountActive(profile) &&
        profile.isStudentVerified === true &&
        isProfileComplete(profile) &&
        hasDisplayableImage(profile)
      : isAccountActive(profile) && profile.isStudentVerified === true;
  if (!displayable) return false;

  if (options.enforceCampusZone) {
    const candidateZones = campusLifeZonesOf(profile);
    if (options.viewerZones.size === 0 || candidateZones.size === 0) {
      return false; // 클라이언트와 동일하게 fail-closed
    }
    let overlaps = false;
    for (const zone of candidateZones) {
      if (options.viewerZones.has(zone)) {
        overlaps = true;
        break;
      }
    }
    if (!overlaps) return false;
  }
  return true;
}

/**
 * rank 순으로 eligibility 를 적용해 표시 가능한 후보만 남긴다. 원본 rank 를
 * 그대로 보존하며(재번호 없음), 화면 계약은 다음과 같다:
 *   initial window   = eligible[0..2]
 *   refreshed window = eligible[3..5]
 * 예: raw ranks [1,2,3,4,5,6,7] 에서 rank 3 이 차단이면
 *   initial = raw [1,2,4], refreshed = raw [5,6,7].
 */
export function selectEligibleRefreshCandidates(input: {
  candidates: readonly RefreshCandidate[];
  viewerUid: string;
  blockedUids: ReadonlySet<string>;
  profileByUid: ReadonlyMap<string, Record<string, unknown> | null>;
  enforceCampusZone: boolean;
  viewerZones: ReadonlySet<string>;
  limit?: number;
}): RefreshCandidate[] {
  const limit = input.limit ?? Number.POSITIVE_INFINITY;
  const eligible: RefreshCandidate[] = [];
  const seen = new Set<string>();
  for (const candidate of input.candidates) {
    if (eligible.length >= limit) break;
    if (candidate.uid === input.viewerUid) continue;
    if (seen.has(candidate.uid)) continue; // 같은 uid 중복 항목은 1명이다
    if (input.blockedUids.has(candidate.uid)) continue;
    const profile = input.profileByUid.get(candidate.uid) ?? null;
    if (
      !isRefreshCandidateDisplayable(profile, {
        enforceCampusZone: input.enforceCampusZone,
        viewerZones: input.viewerZones,
      })
    ) {
      continue;
    }
    seen.add(candidate.uid);
    eligible.push(candidate);
  }
  return eligible;
}

/** recommendationExclusions/{uid}/targets/{target} 문서의 활성 여부.
 * 클라이언트 _fetchRecommendationExcludedUids 와 동일 판정. */
export function isExclusionActive(
  data: Record<string, unknown> | null | undefined,
): boolean {
  if (!data) return false;
  if (data.active === true) return true;
  const enabledBy = data.enabledBy;
  return (
    isRecord(enabledBy) &&
    Object.values(enabledBy).some((value) => value === true)
  );
}

/** 트랜잭션 안에서 다시 읽은, 유료 노출 후보 1명의 commit 시점 상태. */
export type DisplayCandidateCommitState = {
  uid: string;
  /** publicProfiles/{uid} — 없으면 null (탈퇴/모더레이션). */
  profile: Record<string, unknown> | null;
  /** blocks/{viewer}/targets/{uid} 존재 여부. */
  blocked: boolean;
  /** recommendationExclusions/{viewer}/targets/{uid} 활성 여부. */
  exclusionActive: boolean;
};

/**
 * TOCTOU 방어의 핵심: Heart 를 차감하는 바로 그 트랜잭션이 읽은 snapshot 으로
 * "결제로 노출될 정확한 3명"이 지금도 eligible 한지 판정한다.
 *
 * pre-transaction 의 eligible 계산은 후보를 *고르는* 단계일 뿐이고(precheck),
 * 결제 가부는 이 함수가 트랜잭션 내부 읽기만으로 다시 정한다. 트랜잭션 밖에서
 * 계산된 값은 이 함수에 들어오지 않는다.
 */
export function areDisplayCandidatesStillEligible(input: {
  candidates: readonly DisplayCandidateCommitState[];
  viewerUid: string;
  enforceCampusZone: boolean;
  viewerZones: ReadonlySet<string>;
  expectedCount: number;
}): boolean {
  if (input.candidates.length !== input.expectedCount) return false;
  const seen = new Set<string>();
  for (const candidate of input.candidates) {
    if (!candidate.uid || candidate.uid === input.viewerUid) return false;
    if (seen.has(candidate.uid)) return false;
    seen.add(candidate.uid);
    if (candidate.blocked) return false;
    if (candidate.exclusionActive) return false;
    if (
      !isRefreshCandidateDisplayable(candidate.profile, {
        enforceCampusZone: input.enforceCampusZone,
        viewerZones: input.viewerZones,
      })
    ) {
      return false;
    }
  }
  return true;
}

export type RefreshPurchaseDecision =
  | { kind: "already_purchased" }
  | { kind: "stale" }
  | { kind: "stale_eligibility" }
  | { kind: "unavailable"; reason: string }
  | { kind: "insufficient_hearts" }
  | { kind: "charge"; balanceAfter: number };

/**
 * 트랜잭션 내부에서 읽은 상태만으로 결제 여부를 결정하는 순수 함수.
 * 순서가 중요하다: 이미 구매됨(멱등 성공) 판정이 다른 모든 검사보다 먼저다 —
 * 재시도가 stale/insufficient 로 실패하면 첫 결제가 성공했는데도 실패로 보인다.
 */
export function evaluateRefreshPurchase(input: {
  entitlementStatus: string | null;
  sourceStatus: string | null;
  /** eligibility 를 계산한 source snapshot 과 트랜잭션의 snapshot 이 동일한가. */
  sourceUnchanged: boolean;
  /**
   * 유료 노출 3명이 트랜잭션 내부 재읽기 기준으로도 eligible 한가
   * ([areDisplayCandidatesStillEligible] 결과). false 면 차감하지 않는다.
   */
  displayCandidatesStillEligible: boolean;
  /** 클라이언트 필터를 통과한 표시 가능 후보 수 (raw item 수가 아님). */
  eligibleCandidateCount: number;
  heartBalance: number;
}): RefreshPurchaseDecision {
  if (input.entitlementStatus === "completed") {
    return { kind: "already_purchased" };
  }
  if (input.entitlementStatus !== null) {
    // completed 이외의 상태는 v1 에서 만들지 않는다. 알 수 없는 상태를
    // 재결제로 덮어쓰면 이중 차감 위험이 있으므로 fail-closed.
    return { kind: "unavailable", reason: "entitlement_state_unknown" };
  }
  if (input.sourceStatus !== "ready") {
    return { kind: "unavailable", reason: "source_not_ready" };
  }
  if (!input.sourceUnchanged) {
    // eligibility 를 계산한 뒤 추천 세트가 교체됐다. 구 세트 기준으로
    // 결제하면 노출 보장이 깨지므로 차감 없이 거부한다.
    return { kind: "stale" };
  }
  if (!input.displayCandidatesStillEligible) {
    // TOCTOU: precheck 와 commit 사이에 3명 중 누군가의 상태가 바뀌었다
    // (차단/탈퇴/모더레이션 등). 차감·entitlement 생성 없이 거부하고,
    // 클라이언트는 피드를 다시 불러온 뒤 구매 가능 여부를 재계산한다.
    return { kind: "stale_eligibility" };
  }
  if (input.eligibleCandidateCount < ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE) {
    return { kind: "unavailable", reason: "not_enough_eligible_candidates" };
  }
  const balance =
    Number.isFinite(input.heartBalance) && input.heartBalance >= 0
      ? Math.floor(input.heartBalance)
      : 0;
  if (balance < ONE_TO_ONE_REFRESH_COST_HEARTS) {
    return { kind: "insufficient_hearts" };
  }
  return { kind: "charge", balanceAfter: balance - ONE_TO_ONE_REFRESH_COST_HEARTS };
}

type ResolveUser = (
  auth: { uid: string; token?: Record<string, unknown> } | undefined,
) => Promise<{ userId: string }>;

type ResolvedRecommendationSource = {
  dateKey: string;
  algo: string;
  snap: DocumentSnapshot;
};

function sourceDocRef(firestore: Firestore, uid: string, dateKey: string, algo: string) {
  return firestore
    .collection("modelRecs")
    .doc(uid)
    .collection("daily")
    .doc(dateKey)
    .collection("sources")
    .doc(algo);
}

/**
 * 클라이언트 _fetchRawRecs / fetchMysteryFeed 의 fallback 순서를 그대로 따라
 * 현재 유효한 추천 소스를 정한다: algo(rrf→clip→svd) 별로 오늘→어제.
 */
async function resolveActiveMysterySource(
  firestore: Firestore,
  uid: string,
  now: Date,
): Promise<ResolvedRecommendationSource | null> {
  const todayKey = kstDateKeyOf(now);
  const yesterdayKey = kstDateKeyOf(
    new Date(now.getTime() - 24 * 60 * 60 * 1000),
  );
  for (const algo of MYSTERY_FEED_ALGO_PRIORITY) {
    for (const dateKey of [todayKey, yesterdayKey]) {
      const snap = await sourceDocRef(firestore, uid, dateKey, algo).get();
      if (snap.exists && snap.get("status") === "ready") {
        return { dateKey, algo, snap };
      }
    }
  }
  return null;
}

/** 클라이언트 _fetchBlockedUids + _fetchRecommendationExcludedUids 의 서버판. */
async function fetchExcludedCandidateUids(
  firestore: Firestore,
  uid: string,
): Promise<Set<string>> {
  const [blocksSnap, exclusionsSnap] = await Promise.all([
    firestore.collection("blocks").doc(uid).collection("targets").get(),
    firestore
      .collection("recommendationExclusions")
      .doc(uid)
      .collection("targets")
      .get(),
  ]);
  const excluded = new Set<string>();
  for (const doc of blocksSnap.docs) excluded.add(doc.id);
  for (const doc of exclusionsSnap.docs) {
    if (isExclusionActive(doc.data() as Record<string, unknown>)) {
      excluded.add(doc.id);
    }
  }
  return excluded;
}

const PROFILE_READ_CHUNK = 10;
/** eligibility 판정을 위해 rank 순으로 스캔할 최대 후보 수 (read 상한). */
const MAX_CANDIDATE_SCAN = 60;

/**
 * rank 순으로 publicProfiles 를 chunk 단위로 읽으며 eligible 후보를 찾는다.
 * 필요 수(6명)를 채우면 더 읽지 않는다.
 */
async function findEligibleCandidates(
  firestore: Firestore,
  input: {
    candidates: RefreshCandidate[];
    viewerUid: string;
    blockedUids: Set<string>;
    enforceCampusZone: boolean;
    viewerZones: Set<string>;
  },
): Promise<RefreshCandidate[]> {
  const scannable = input.candidates.slice(0, MAX_CANDIDATE_SCAN);
  const profileByUid = new Map<string, Record<string, unknown> | null>();
  const eligible: RefreshCandidate[] = [];
  for (let start = 0; start < scannable.length; start += PROFILE_READ_CHUNK) {
    const chunk = scannable.slice(start, start + PROFILE_READ_CHUNK);
    const toRead = chunk.filter(
      (candidate) =>
        !profileByUid.has(candidate.uid) &&
        candidate.uid !== input.viewerUid &&
        !input.blockedUids.has(candidate.uid),
    );
    if (toRead.length > 0) {
      const snaps = await firestore.getAll(
        ...toRead.map((candidate) =>
          firestore.collection("publicProfiles").doc(candidate.uid),
        ),
      );
      snaps.forEach((snap, index) => {
        profileByUid.set(
          toRead[index].uid,
          snap.exists ? (snap.data() as Record<string, unknown>) : null,
        );
      });
    }
    const found = selectEligibleRefreshCandidates({
      candidates: scannable.slice(0, start + PROFILE_READ_CHUNK),
      viewerUid: input.viewerUid,
      blockedUids: input.blockedUids,
      profileByUid,
      enforceCampusZone: input.enforceCampusZone,
      viewerZones: input.viewerZones,
      limit: ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE,
    });
    eligible.length = 0;
    eligible.push(...found);
    if (eligible.length >= ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE) break;
  }
  return eligible;
}

export function createPurchaseRecommendationRefreshFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      const data = (request.data ?? {}) as Record<string, unknown>;
      // 클라이언트가 보고 있는 세트의 식별자. 가격/자격 판단에는 쓰지 않고,
      // 서버가 결정한 세트와 다르면 결제를 거부해 "보던 세트와 다른 세트에
      // 결제되는" race 를 막는 용도로만 쓴다.
      const expectedDateKey =
        typeof data.expectedDateKey === "string" && data.expectedDateKey.trim()
          ? data.expectedDateKey.trim()
          : null;
      const expectedAlgo =
        typeof data.expectedAlgo === "string" && data.expectedAlgo.trim()
          ? data.expectedAlgo.trim()
          : null;

      const resolved = await resolveActiveMysterySource(
        firestore,
        user.userId,
        new Date(),
      );
      if (!resolved) {
        throw new HttpsError("failed-precondition", "refresh_unavailable");
      }
      if (
        (expectedDateKey !== null && expectedDateKey !== resolved.dateKey) ||
        (expectedAlgo !== null && expectedAlgo !== resolved.algo)
      ) {
        // 결제 시점에 추천 세트가 교체됐다. 클라이언트는 피드를 다시 불러온다.
        throw new HttpsError("failed-precondition", "refresh_stale_feed");
      }

      const sourceData = (resolved.snap.data() ?? {}) as Record<string, unknown>;
      const sourceUpdateTime = resolved.snap.updateTime ?? null;
      const candidates = parseRefreshCandidates(sourceData.items);
      if (candidates.length < ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE) {
        throw new HttpsError("failed-precondition", "refresh_unavailable");
      }

      // 클라이언트와 같은 eligibility 근거를 모은다.
      const viewerRef = firestore.collection("users").doc(user.userId);
      const [viewerSnap, blockedUids, activation] = await Promise.all([
        viewerRef.get(),
        fetchExcludedCandidateUids(firestore, user.userId),
        loadCampusLifeZoneActivation(firestore),
      ]);
      if (!viewerSnap.exists) {
        throw new HttpsError("not-found", "user_missing");
      }
      const policy = readMap(sourceData.policy);
      const enforceCampusZone =
        policy.campusLifeZone === "enforced" || activation.state === "enforced";
      const viewerZones = campusLifeZonesOf(
        viewerSnap.data() as Record<string, unknown>,
      );

      const eligible = await findEligibleCandidates(firestore, {
        candidates,
        viewerUid: user.userId,
        blockedUids,
        enforceCampusZone,
        viewerZones,
      });
      if (eligible.length < ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE) {
        // raw 후보는 충분해도 실제 표시 가능한 후보가 6명 미만이면 결제하지
        // 않는다 — 5 Heart 를 내고 카드 3장을 못 받는 상황을 서버가 막는다.
        throw new HttpsError("failed-precondition", "refresh_unavailable");
      }
      const displayCandidates = eligible.slice(
        ONE_TO_ONE_WINDOW_SIZE,
        ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE,
      );

      const entitlementRef = viewerRef
        .collection("recommendationRefreshes")
        .doc(resolved.dateKey);
      const sourceRef = sourceDocRef(
        firestore,
        user.userId,
        resolved.dateKey,
        resolved.algo,
      );
      const configRef = firestore
        .collection(RECOMMENDATION_CONFIG_COLLECTION)
        .doc(RECOMMENDATION_CONFIG_DOC);
      // 유료 노출 3명의 commit 시점 재검증에 필요한 문서들. 여기까지의
      // eligible 계산은 후보 *선정*을 위한 precheck 일 뿐이고, 결제 가부는
      // 아래 트랜잭션이 이 문서들을 다시 읽어 판정한다 (TOCTOU 방어).
      const candidateCheckRefs = displayCandidates.flatMap((candidate) => [
        firestore.collection("publicProfiles").doc(candidate.uid),
        firestore
          .collection("blocks")
          .doc(user.userId)
          .collection("targets")
          .doc(candidate.uid),
        firestore
          .collection("recommendationExclusions")
          .doc(user.userId)
          .collection("targets")
          .doc(candidate.uid),
      ]);

      const result = await firestore.runTransaction(async (tx) => {
        const [entSnap, userSnap, sourceSnap, configSnap, ...candidateSnaps] =
          await tx.getAll(
            entitlementRef,
            viewerRef,
            sourceRef,
            configRef,
            ...candidateCheckRefs,
          );
        if (!userSnap.exists) {
          throw new HttpsError("not-found", "user_missing");
        }
        const currentRaw = userSnap.get("heartBalance");
        const currentBalance =
          typeof currentRaw === "number" &&
          Number.isFinite(currentRaw) &&
          currentRaw >= 0
            ? Math.floor(currentRaw)
            : 0;

        // campus-life 적용 여부와 viewer 생활권도 트랜잭션 snapshot 으로
        // 다시 정한다 — precheck 값이 아니라 commit 시점 canonical state.
        const txSourceData = (sourceSnap.data() ?? {}) as Record<string, unknown>;
        const txPolicy = readMap(txSourceData.policy);
        const txEnforceCampusZone =
          txPolicy.campusLifeZone === "enforced" ||
          campusLifeZoneEnforcedFromConfig(
            (configSnap.data() ?? null) as Record<string, unknown> | null,
          );
        const txViewerZones = campusLifeZonesOf(
          userSnap.data() as Record<string, unknown>,
        );
        const commitStates: DisplayCandidateCommitState[] =
          displayCandidates.map((candidate, index) => {
            const profileSnap = candidateSnaps[index * 3];
            const blockSnap = candidateSnaps[index * 3 + 1];
            const exclusionSnap = candidateSnaps[index * 3 + 2];
            return {
              uid: candidate.uid,
              profile: profileSnap.exists
                ? (profileSnap.data() as Record<string, unknown>)
                : null,
              blocked: blockSnap.exists,
              exclusionActive: isExclusionActive(
                exclusionSnap.exists
                  ? (exclusionSnap.data() as Record<string, unknown>)
                  : null,
              ),
            };
          });

        const txUpdateTime = sourceSnap.updateTime ?? null;
        const decision = evaluateRefreshPurchase({
          entitlementStatus: entSnap.exists
            ? String(entSnap.get("status") ?? "")
            : null,
          sourceStatus: sourceSnap.exists
            ? String(sourceSnap.get("status") ?? "")
            : null,
          // eligibility 는 트랜잭션 밖에서 계산했으므로, 그 근거가 된
          // snapshot 과 지금 커밋 대상 snapshot 이 같은 버전인지 확인한다.
          sourceUnchanged:
            sourceUpdateTime !== null &&
            txUpdateTime !== null &&
            sourceUpdateTime.isEqual(txUpdateTime as Timestamp),
          // "차감되는 commit 시점에 3명이 실제로 eligible" invariant.
          displayCandidatesStillEligible: areDisplayCandidatesStillEligible({
            candidates: commitStates,
            viewerUid: user.userId,
            enforceCampusZone: txEnforceCampusZone,
            viewerZones: txViewerZones,
            expectedCount: ONE_TO_ONE_WINDOW_SIZE,
          }),
          eligibleCandidateCount: eligible.length,
          heartBalance: currentBalance,
        });

        switch (decision.kind) {
          case "already_purchased": {
            // 재시도 응답은 이번 계산이 아니라 최초 결제가 확정한 identity 를
            // 돌려준다 — 두 응답이 서로 다른 3명을 가리키면 안 된다.
            const storedUids = entSnap.get("displayCandidateUids");
            const displayCandidateUids = Array.isArray(storedUids)
              ? storedUids.filter(
                  (uid): uid is string =>
                    typeof uid === "string" && uid.length > 0,
                )
              : displayCandidates.map((candidate) => candidate.uid);
            return {
              status: "already_purchased" as const,
              remainingHearts: currentBalance,
              displayCandidateUids,
            };
          }
          case "stale":
            throw new HttpsError("failed-precondition", "refresh_stale_feed");
          case "stale_eligibility":
            throw new HttpsError(
              "failed-precondition",
              "refresh_stale_eligibility",
            );
          case "unavailable":
            throw new HttpsError("failed-precondition", "refresh_unavailable");
          case "insufficient_hearts":
            throw new HttpsError("failed-precondition", "insufficient_hearts");
          case "charge":
            break;
        }

        tx.set(
          viewerRef,
          {
            heartBalance: decision.balanceAfter,
            heartBalanceUpdatedAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true },
        );
        // create: 동시 요청이 둘 다 여기 도달하면 한쪽 커밋이 실패하고,
        // 재시도 트랜잭션이 entitlement 를 읽어 already_purchased 로 끝난다.
        tx.create(entitlementRef, {
          product: ONE_TO_ONE_REFRESH_PRODUCT,
          dateKey: resolved.dateKey,
          algo: resolved.algo,
          costHearts: ONE_TO_ONE_REFRESH_COST_HEARTS,
          refreshIndex: 1,
          displayRankStart: ONE_TO_ONE_REFRESH_DISPLAY_RANK_START,
          displayRankEnd: ONE_TO_ONE_REFRESH_DISPLAY_RANK_END,
          // 결제 시점에 확정된 유료 노출 3명 (eligible 4~6번째, 원본 rank 보존).
          // 앱 재실행 시 이 identity 로 같은 결과를 복원한다.
          displayCandidateUids: displayCandidates.map((c) => c.uid),
          displayCandidateRanks: displayCandidates.map((c) => c.rank),
          // 결제된 추천 세트의 identity. 세트 교체/regeneration 감지용.
          algorithmVersion:
            typeof sourceData.algorithmVersion === "string"
              ? sourceData.algorithmVersion
              : null,
          sourceGeneratedAt: sourceData.generatedAt ?? null,
          sourceUpdateTimeMs: sourceUpdateTime
            ? sourceUpdateTime.toMillis()
            : null,
          status: "completed",
          heartBalanceAfter: decision.balanceAfter,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
        return {
          status: "purchased" as const,
          remainingHearts: decision.balanceAfter,
          displayCandidateUids: displayCandidates.map((c) => c.uid),
        };
      });

      logger.info("one-to-one recommendation refresh processed", {
        userId: user.userId,
        dateKey: resolved.dateKey,
        algo: resolved.algo,
        status: result.status,
        eligibleCandidateCount: eligible.length,
      });

      return {
        ok: true,
        status: result.status,
        product: ONE_TO_ONE_REFRESH_PRODUCT,
        dateKey: resolved.dateKey,
        algo: resolved.algo,
        costHearts: ONE_TO_ONE_REFRESH_COST_HEARTS,
        remainingHearts: result.remainingHearts,
        displayRankStart: ONE_TO_ONE_REFRESH_DISPLAY_RANK_START,
        displayRankEnd: ONE_TO_ONE_REFRESH_DISPLAY_RANK_END,
        displayCandidateUids: result.displayCandidateUids,
      };
    },
  );
}
