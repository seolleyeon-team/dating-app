import type { Auth } from "firebase-admin/auth";
import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { withAppCheck } from "./appCheckPolicy";

const YONSEI_EMAIL_RE = /^[^\s@]+@yonsei\.ac\.kr$/;
const TOKEN_ID_RE = /^[A-Za-z0-9_-]{1,128}$/;

export type EmailLinkCompletionRejection =
  | "malformed"
  | "email-mismatch"
  | "kakao-mismatch"
  | "expired"
  | "already-exchanged";

export type EmailLinkCompletionDecision =
  | { ok: true; kakaoUserId: string; email: string }
  | { ok: false; reason: EmailLinkCompletionRejection };

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function normalizeYonseiEmail(value: unknown): string | null {
  const email = asNonEmptyString(value)?.toLowerCase() ?? null;
  return email && YONSEI_EMAIL_RE.test(email) ? email : null;
}

function toDate(value: unknown): Date | null {
  if (value && typeof value === "object") {
    const maybeTimestamp = value as { toDate?: unknown };
    if (typeof maybeTimestamp.toDate === "function") {
      const date = maybeTimestamp.toDate();
      return date instanceof Date && !Number.isNaN(date.getTime())
        ? date
        : null;
    }
  }
  return value instanceof Date && !Number.isNaN(value.getTime()) ? value : null;
}

/**
 * Validates the mailbox-authenticated side of an emailLinkTokens exchange.
 * The token document is only a binding request; the Firebase email-link
 * session is the proof that the caller controls the Yonsei mailbox.
 */
export function evaluateEmailLinkCompletion(params: {
  tokenData: Record<string, unknown> | null | undefined;
  authenticatedEmail?: unknown;
  expectedKakaoUserId?: unknown;
  now: Date;
}): EmailLinkCompletionDecision {
  const tokenData = params.tokenData;
  if (!tokenData) return { ok: false, reason: "malformed" };

  const kakaoUserId = asNonEmptyString(tokenData.kakaoUserId);
  const email = normalizeYonseiEmail(tokenData.email);
  const authenticatedEmail = normalizeYonseiEmail(
    params.authenticatedEmail
  );
  if (
    !kakaoUserId ||
    kakaoUserId.length > 128 ||
    kakaoUserId.includes("/") ||
    !email ||
    !authenticatedEmail
  ) {
    return { ok: false, reason: "malformed" };
  }

  if (email !== authenticatedEmail) {
    return { ok: false, reason: "email-mismatch" };
  }

  const expectedKakaoUserId = asNonEmptyString(params.expectedKakaoUserId);
  if (expectedKakaoUserId && expectedKakaoUserId !== kakaoUserId) {
    return { ok: false, reason: "kakao-mismatch" };
  }

  const createdAt = toDate(tokenData.createdAt);
  const expiresAt = toDate(tokenData.expiresAt);
  const nowMs = params.now.getTime();
  if (
    !createdAt ||
    !expiresAt ||
    createdAt.getTime() > nowMs + 5 * 60 * 1000 ||
    expiresAt.getTime() <= nowMs
  ) {
    return { ok: false, reason: "expired" };
  }

  if (tokenData.exchangedAt != null) {
    return { ok: false, reason: "already-exchanged" };
  }

  return { ok: true, kakaoUserId, email };
}

function completionError(
  reason: EmailLinkCompletionRejection
): HttpsError {
  switch (reason) {
    case "email-mismatch":
      return new HttpsError(
        "permission-denied",
        "인증한 이메일과 요청한 이메일이 일치하지 않아요."
      );
    case "kakao-mismatch":
      return new HttpsError(
        "permission-denied",
        "현재 카카오 계정과 인증 링크의 계정이 달라요."
      );
    case "expired":
      return new HttpsError(
        "deadline-exceeded",
        "인증 링크가 만료됐어요. 새 인증 링크를 요청해주세요."
      );
    case "already-exchanged":
      return new HttpsError(
        "already-exists",
        "이미 처리된 인증 링크예요."
      );
    case "malformed":
      return new HttpsError(
        "failed-precondition",
        "인증 링크 정보를 확인할 수 없어요. 새 인증 링크를 요청해주세요."
      );
  }
}

export function createCompleteStudentEmailLinkFunction(
  db: Firestore,
  auth: Auth
) {
  return onCall(withAppCheck(), async (request) => {
    const authUid = asNonEmptyString(request.auth?.uid);
    if (!authUid) {
      throw new HttpsError("unauthenticated", "이메일 인증 세션이 필요해요.");
    }

    const authToken = request.auth?.token as
      | Record<string, unknown>
      | undefined;
    const authenticatedEmail = normalizeYonseiEmail(authToken?.email);
    if (!authenticatedEmail || authToken?.email_verified !== true) {
      throw new HttpsError(
        "failed-precondition",
        "연세 이메일 인증이 확인되지 않았어요."
      );
    }

    const authUser = await auth.getUser(authUid);
    const authUserEmail = normalizeYonseiEmail(authUser.email);
    if (!authUser.emailVerified || authUserEmail !== authenticatedEmail) {
      throw new HttpsError(
        "failed-precondition",
        "연세 이메일 인증이 확인되지 않았어요."
      );
    }

    const requestData = (request.data ?? {}) as Record<string, unknown>;
    const token = asNonEmptyString(requestData.token);
    if (!token || !TOKEN_ID_RE.test(token)) {
      throw new HttpsError("invalid-argument", "인증 링크 토큰이 필요해요.");
    }

    const expectedKakaoUserId = asNonEmptyString(
      requestData.expectedKakaoUserId
    );
    const tokenRef = db.collection("emailLinkTokens").doc(token);
    const completion = await db.runTransaction(async (transaction) => {
      const tokenSnapshot = await transaction.get(tokenRef);
      const decision = evaluateEmailLinkCompletion({
        tokenData: tokenSnapshot.exists ? tokenSnapshot.data() : null,
        authenticatedEmail,
        expectedKakaoUserId,
        now: new Date(),
      });
      if (!decision.ok) {
        throw completionError(decision.reason);
      }

      const userRef = db.collection("users").doc(decision.kakaoUserId);
      const userSnapshot = await transaction.get(userRef);
      if (!userSnapshot.exists) {
        throw new HttpsError(
          "failed-precondition",
          "가입된 카카오 계정을 찾을 수 없어요."
        );
      }

      const userData = (userSnapshot.data() ?? {}) as Record<string, unknown>;
      const storedKakaoUserId = asNonEmptyString(userData.kakaoUserId);
      if (storedKakaoUserId && storedKakaoUserId !== decision.kakaoUserId) {
        throw new HttpsError(
          "failed-precondition",
          "카카오 계정 정보를 확인할 수 없어요."
        );
      }

      const storedEmailValue = userData.studentEmail;
      const storedEmail = normalizeYonseiEmail(storedEmailValue);
      if (
        storedEmailValue != null &&
        asNonEmptyString(storedEmailValue) &&
        storedEmail !== decision.email
      ) {
        throw new HttpsError(
          "permission-denied",
          "이미 다른 연세 이메일로 인증된 계정이에요."
        );
      }

      transaction.set(
        userRef,
        {
          studentEmail: decision.email,
          isStudentVerified: true,
          studentVerifiedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      // Single-use guarantee: the binding document is consumed in the same
      // transaction as the verification write.
      transaction.delete(tokenRef);
      return decision;
    });

    const customToken = await auth.createCustomToken(completion.kakaoUserId, {
      kakaoUserId: completion.kakaoUserId,
    });

    logger.info("completeStudentEmailLink succeeded", {
      authUid,
      kakaoUserId: completion.kakaoUserId,
    });

    return {
      customToken,
      kakaoUserId: completion.kakaoUserId,
      email: completion.email,
    };
  });
}
