/**
 * Server-owned Yonsei student-verification email helpers.
 *
 * This module deliberately keeps the Firebase action link opaque: callers may
 * put it in an email, but must never log it or expose it through a client API.
 */

export const STUDENT_VERIFICATION_MINUTE_WINDOW_MS = 60 * 1000;
export const STUDENT_VERIFICATION_MAX_PER_MINUTE = 2;
export const STUDENT_VERIFICATION_DAY_WINDOW_MS = 24 * 60 * 60 * 1000;
export const STUDENT_VERIFICATION_MAX_PER_DAY = 10;

export type VerificationRateState = {
  minuteWindowStartedAtMs?: number | null;
  minuteRequestCount?: number | null;
  dayWindowStartedAtMs?: number | null;
  dayRequestCount?: number | null;
};

export type VerificationRateDecision =
  | {
      allowed: true;
      minuteWindowStartedAtMs: number;
      minuteRequestCount: number;
      dayWindowStartedAtMs: number;
      dayRequestCount: number;
    }
  | { allowed: false; retryAfterMs: number };

export function normalizeYonseiEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const email = value.trim().toLowerCase();
  // Keep the server validation intentionally no broader than the product's
  // Yonsei-only gate. The local part must not contain whitespace or another @.
  return /^[^@\s]+@yonsei\.ac\.kr$/.test(email) ? email : null;
}

export function decideStudentVerificationRateLimit(
  state: VerificationRateState,
  nowMs: number
): VerificationRateDecision {
  const minuteWindowStartedAtMs = state.minuteWindowStartedAtMs ?? 0;
  const inMinuteWindow =
    nowMs - minuteWindowStartedAtMs < STUDENT_VERIFICATION_MINUTE_WINDOW_MS;
  const minuteRequestCount = inMinuteWindow ? (state.minuteRequestCount ?? 0) : 0;
  if (minuteRequestCount >= STUDENT_VERIFICATION_MAX_PER_MINUTE) {
    return {
      allowed: false,
      retryAfterMs: Math.max(
        0,
        minuteWindowStartedAtMs + STUDENT_VERIFICATION_MINUTE_WINDOW_MS - nowMs
      ),
    };
  }

  const dayWindowStartedAtMs = state.dayWindowStartedAtMs ?? 0;
  const inDayWindow = nowMs - dayWindowStartedAtMs < STUDENT_VERIFICATION_DAY_WINDOW_MS;
  const dayRequestCount = inDayWindow ? (state.dayRequestCount ?? 0) : 0;
  if (dayRequestCount >= STUDENT_VERIFICATION_MAX_PER_DAY) {
    return {
      allowed: false,
      retryAfterMs: Math.max(
        0,
        dayWindowStartedAtMs + STUDENT_VERIFICATION_DAY_WINDOW_MS - nowMs
      ),
    };
  }

  return {
    allowed: true,
    minuteWindowStartedAtMs: inMinuteWindow ? minuteWindowStartedAtMs : nowMs,
    minuteRequestCount: minuteRequestCount + 1,
    dayWindowStartedAtMs: inDayWindow ? dayWindowStartedAtMs : nowMs,
    dayRequestCount: dayRequestCount + 1,
  };
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function buildStudentVerificationEmail(actionLink: string): {
  subject: string;
  html: string;
  text: string;
} {
  const safeLink = escapeHtml(actionLink);
  return {
    subject: "설레연에서 온 인증 메일",
    text: [
      "안녕하세요, 설레연입니다.",
      "",
      "연세대학교 이메일 인증을 완료하려면 아래 링크를 열어주세요.",
      actionLink,
      "",
      "인증 요청은 30분 안에 완료해 주세요.",
      "본인이 요청하지 않은 메일이라면 링크를 열지 말고 이 메일을 무시해 주세요.",
    ].join("\n"),
    html: `<!doctype html>
<html lang="ko">
  <body style="margin:0;background:#f6f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1f2024;">
    <div style="max-width:560px;margin:0 auto;padding:40px 20px;">
      <div style="background:#ffffff;border-radius:16px;padding:36px 32px;box-shadow:0 3px 14px rgba(0,0,0,.06);">
        <p style="margin:0 0 20px;font-size:24px;font-weight:700;letter-spacing:-.4px;">설레연</p>
        <h1 style="margin:0 0 16px;font-size:22px;line-height:1.4;">연세대학교 이메일 인증이 필요해요</h1>
        <p style="margin:0 0 26px;font-size:15px;line-height:1.7;color:#555963;">아래 버튼을 눌러 연세대학교 이메일 인증을 완료해 주세요.</p>
        <p style="margin:0 0 26px;"><a href="${safeLink}" style="display:inline-block;background:#FF6B8A;color:#ffffff;padding:14px 22px;border-radius:10px;text-decoration:none;font-weight:700;">이메일 인증하기</a></p>
        <p style="margin:0;font-size:13px;line-height:1.7;color:#777b84;">인증 요청은 30분 안에 완료해 주세요.<br />본인이 요청하지 않은 메일이라면 링크를 열지 말고 이 메일을 무시해 주세요.</p>
      </div>
    </div>
  </body>
</html>`,
  };
}
