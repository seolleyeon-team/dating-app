import { HttpsError } from "firebase-functions/v2/https";

/**
 * Conservative server-side admission filter for text that is visible to other
 * members. It intentionally rejects contact details and obvious abuse rather
 * than trying to rewrite a member's words. Operations can review reports for
 * anything this deterministic first pass cannot classify.
 */
const PHONE_OR_EMAIL = /(?:\+?82[-.\s]?)?01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const URL_OR_HANDLE = /(?:https?:\/\/|www\.)\S+|(?:카톡|kakao|텔레그램|telegram|인스타|instagram)\s*(?:id|아이디)?\s*[:：@]/i;
const PROHIBITED_TERMS = [
  "자살해", "죽어라", "죽어", "강간", "성폭행", "아동포르노", "nudes", "누드사진",
];

export function normalizedUserText(value: unknown, field: string, maxLength: number): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) throw new HttpsError("invalid-argument", `${field} is required.`);
  if (text.length > maxLength) {
    throw new HttpsError("invalid-argument", `${field} must be at most ${maxLength} characters.`);
  }
  return text;
}

export function assertSafeMemberText(value: unknown, field: string, maxLength: number): string {
  const text = normalizedUserText(value, field, maxLength);
  const compact = text.replace(/\s+/g, "").toLowerCase();
  if (PHONE_OR_EMAIL.test(text) || URL_OR_HANDLE.test(text)) {
    throw new HttpsError("invalid-argument", "연락처·외부 링크는 공개 콘텐츠에 올릴 수 없어요.");
  }
  if (PROHIBITED_TERMS.some((term) => compact.includes(term.replace(/\s+/g, "")))) {
    throw new HttpsError("invalid-argument", "안전 정책에 맞지 않는 표현이 포함되어 있어요.");
  }
  return text;
}
