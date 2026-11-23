/**
 * B-10 — a Kakao access token is accepted only when Kakao issued it for the
 * Seolleyeon Kakao app.
 *
 * `GET /v2/user/me` answers for ANY valid Kakao access token, whichever
 * Kakao app it was issued to, and the member number it returns is scoped to
 * that app. Verifying with it alone lets a token obtained by another Kakao
 * app (one a user merely logged in to, or one an attacker operates)
 * authenticate here, under whatever member number that app assigned.
 *
 * Kakao's token-info endpoint (`GET /v1/user/access_token_info`) returns the
 * `app_id` the token belongs to. It is compared with the server-configured
 * app id before the profile is trusted. Fail closed: no configured app id, a
 * token-info failure, a missing or different `app_id`, or a member number
 * that differs between the two answers all refuse the token.
 *
 * Configuration: KAKAO_APP_ID — the numeric app id shown in Kakao Developers
 * ("앱 ID"). It is not the native app key, the REST API key or the JavaScript
 * key, and it is not a secret.
 *
 * The access token is sent to kapi.kakao.com only and is never logged.
 */
import * as logger from "firebase-functions/logger";
import { HttpsError } from "firebase-functions/v2/https";

export const KAKAO_ACCESS_TOKEN_INFO_URL =
  "https://kapi.kakao.com/v1/user/access_token_info";
export const KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me";

const KAKAO_APP_ID_RE = /^[1-9][0-9]{0,18}$/;

export type KakaoAccessTokenVerifierDeps = {
  /** Injected in tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  /** Injected in tests; defaults to the KAKAO_APP_ID environment variable. */
  trustedAppId?: () => string | null | undefined;
};

/** The server-side trusted Kakao app id, or null when it is not configured. */
export function configuredKakaoAppId(): string | null {
  return normalizeKakaoAppId(process.env.KAKAO_APP_ID);
}

export function normalizeKakaoAppId(value: unknown): string | null {
  const text =
    typeof value === "number" && Number.isSafeInteger(value)
      ? String(value)
      : typeof value === "string"
        ? value.trim()
        : "";
  return KAKAO_APP_ID_RE.test(text) ? text : null;
}

function memberNumber(value: unknown): string | null {
  const text =
    typeof value === "number" && Number.isSafeInteger(value)
      ? String(value)
      : typeof value === "string"
        ? value.trim()
        : "";
  return text.length > 0 ? text : null;
}

function sessionError(): HttpsError {
  return new HttpsError(
    "unauthenticated",
    "카카오 로그인 세션을 확인할 수 없어요."
  );
}

async function kakaoGet(
  fetchImpl: typeof fetch,
  url: string,
  accessToken: string,
  step: string
): Promise<Record<string, unknown>> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch (error) {
    logger.warn("Kakao access token verification failed", {
      step,
      reason: "network",
      errorType: error instanceof Error ? error.name : "unknown",
    });
    throw sessionError();
  }
  if (!response.ok) {
    logger.warn("Kakao access token verification failed", {
      step,
      status: response.status,
    });
    throw sessionError();
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    logger.warn("Kakao access token verification failed", {
      step,
      reason: "malformed_response",
    });
    throw sessionError();
  }
  return body as Record<string, unknown>;
}

export async function verifyKakaoAccessTokenForApp(
  accessToken: string,
  deps: KakaoAccessTokenVerifierDeps = {}
): Promise<{ userId: string }> {
  const trustedAppId = normalizeKakaoAppId(
    deps.trustedAppId ? deps.trustedAppId() : configuredKakaoAppId()
  );
  if (!trustedAppId) {
    // Refused before the token leaves this process.
    logger.error("Kakao access token verification refused", {
      reason: "kakao_app_id_not_configured",
    });
    throw new HttpsError(
      "failed-precondition",
      "카카오 로그인 설정이 완료되지 않았어요."
    );
  }
  const fetchImpl = deps.fetchImpl ?? fetch;

  const tokenInfo = await kakaoGet(
    fetchImpl,
    KAKAO_ACCESS_TOKEN_INFO_URL,
    accessToken,
    "access_token_info"
  );
  const tokenAppId = normalizeKakaoAppId(tokenInfo.app_id);
  if (tokenAppId !== trustedAppId) {
    logger.warn("Kakao access token verification failed", {
      step: "access_token_info",
      reason: tokenAppId ? "issued_for_another_app" : "app_id_missing",
    });
    throw sessionError();
  }
  const tokenMember = memberNumber(tokenInfo.id);

  const profile = await kakaoGet(
    fetchImpl,
    KAKAO_USER_ME_URL,
    accessToken,
    "user_me"
  );
  const userId = memberNumber(profile.id);
  if (!userId) {
    throw new HttpsError(
      "unauthenticated",
      "카카오 사용자 정보를 확인할 수 없어요."
    );
  }
  if (!tokenMember || tokenMember !== userId) {
    logger.warn("Kakao access token verification failed", {
      step: "user_me",
      reason: "member_mismatch",
    });
    throw sessionError();
  }
  return { userId };
}
