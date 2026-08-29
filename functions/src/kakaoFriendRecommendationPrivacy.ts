const KAKAO_FRIENDS_ENDPOINT =
  "https://kapi.kakao.com/v1/api/talk/friends?limit=100";

export const MAX_KAKAO_FRIEND_SERVICE_USER_IDS = 5000;

export type FetchLike = (
  input: string | URL,
  init?: RequestInit,
) => Promise<Response>;

function asServiceUserId(value: unknown): string | null {
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value <= 0) return null;
    return String(value);
  }
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? trimmed : null;
}

export function isKakaoFriendAvoidanceEnabled(
  data: Record<string, unknown> | undefined,
): boolean {
  return data?.kakaoFriendAvoidanceEnabled === true;
}

export function hasActiveRecommendationExclusion(
  data: Record<string, unknown> | undefined,
): boolean {
  const enabledBy = data?.enabledBy;
  if (!enabledBy || typeof enabledBy !== "object" || Array.isArray(enabledBy)) {
    return false;
  }
  return Object.values(enabledBy as Record<string, unknown>).some(
    (value) => value === true,
  );
}

export function buildRecommendationExclusionPairId(
  userA: string,
  userB: string,
): string {
  return [userA, userB].sort().join("_");
}

function validateNextFriendsUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) return null;
  const parsed = new URL(value);
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "kapi.kakao.com" ||
    parsed.pathname !== "/v1/api/talk/friends"
  ) {
    throw new Error("unsafe_kakao_friends_pagination_url");
  }
  return parsed.toString();
}

/**
 * Loads the authoritative Kakao friend service-user IDs with the caller's
 * access token. Profile fields and UUIDs are deliberately ignored.
 */
export async function fetchKakaoFriendServiceUserIds(
  accessToken: string,
  fetchImpl: FetchLike = fetch,
): Promise<string[]> {
  const token = accessToken.trim();
  if (!token) throw new Error("missing_kakao_access_token");

  const ids = new Set<string>();
  const visitedUrls = new Set<string>();
  let nextUrl: string | null = KAKAO_FRIENDS_ENDPOINT;

  while (nextUrl && ids.size < MAX_KAKAO_FRIEND_SERVICE_USER_IDS) {
    if (!visitedUrls.add(nextUrl)) {
      throw new Error("repeated_kakao_friends_pagination_url");
    }

    const response = await fetchImpl(nextUrl, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const error = new Error(`kakao_friends_http_${response.status}`);
      Object.assign(error, { status: response.status });
      throw error;
    }

    const payload = (await response.json()) as Record<string, unknown>;
    const elements = Array.isArray(payload.elements) ? payload.elements : [];
    for (const rawFriend of elements) {
      if (!rawFriend || typeof rawFriend !== "object" || Array.isArray(rawFriend)) {
        continue;
      }
      const id = asServiceUserId(
        (rawFriend as Record<string, unknown>).id,
      );
      if (id) ids.add(id);
      if (ids.size >= MAX_KAKAO_FRIEND_SERVICE_USER_IDS) break;
    }

    nextUrl = validateNextFriendsUrl(payload.after_url ?? payload.afterUrl);
  }

  // Never report a successful reconciliation after silently truncating a
  // very large friend list. The caller remains recommendation-ineligible and
  // an operator can raise the bounded limit after reviewing the workload.
  if (nextUrl && ids.size >= MAX_KAKAO_FRIEND_SERVICE_USER_IDS) {
    throw new Error("kakao_friends_limit_exceeded");
  }

  return [...ids];
}
