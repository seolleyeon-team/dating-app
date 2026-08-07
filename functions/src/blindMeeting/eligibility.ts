import { asStrArray } from "./types";

/** The only trusted representation of a completed school verification. */
export function isStrictStudentVerification(value: unknown): boolean {
  return value === true;
}

/** Blind-meeting applications require at least one stored interest. */
export function hasRequiredInterests(value: unknown): boolean {
  return asStrArray(value).length > 0;
}
