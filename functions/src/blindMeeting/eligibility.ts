import {
  DRINKING_LEVELS,
  SMOKING_STATUSES,
  asStrArray,
  isRecord,
  oneOfOrNull,
} from "./types";

/** The only trusted representation of a completed school verification. */
export function isStrictStudentVerification(value: unknown): boolean {
  return value === true;
}

/** Blind-meeting applications require at least one stored interest. */
export function hasRequiredInterests(value: unknown): boolean {
  return asStrArray(value).length > 0;
}

/** 음주·흡연 정보가 모두 canonical 값으로 저장되어 있는지 확인한다. */
export function hasRequiredLifestyle(onboardingValue: unknown): boolean {
  if (!isRecord(onboardingValue)) return false;
  const lifestyle = onboardingValue.lifestyle;
  if (!isRecord(lifestyle)) return false;
  return (
    oneOfOrNull(DRINKING_LEVELS, lifestyle.drinking) != null &&
    oneOfOrNull(SMOKING_STATUSES, lifestyle.smoking) != null
  );
}
