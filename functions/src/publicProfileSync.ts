/**
 * Builds and syncs AUTHENTICATED_LIMITED_PROFILE documents under
 * publicProfiles/{uid}. Private users/{uid} fields must never appear here.
 */

import { isDeepStrictEqual } from "node:util";
import type { Firestore } from "firebase-admin/firestore";
import { FieldValue } from "firebase-admin/firestore";

import { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";

const PUBLIC_ONBOARDING_KEYS = [
  "nickname",
  "major",
  "university",
  "department",
  "college",
  "birthYear",
  "bio",
  "selfIntroduction",
  "gender",
  "mbti",
  "height",
  "keywords",
  "interests",
  "profileQa",
  // 추천 serving guard(생활권 hard eligibility)가 후보 판정에 쓴다.
  // 클라이언트는 타인 문서를 publicProfiles 로만 읽을 수 있으므로
  // 이 필드가 없으면 모든 후보가 fail-closed 로 제외된다.
  // grade/department 는 이미 공개 필드라 노출 증분은 없다.
  "campusLifeZones",
] as const;

function asString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asString(item))
    .filter((item): item is string => item != null);
}

function asDateKey(value: unknown): string | null {
  const text = asString(value);
  return text && /^\d{8}$/.test(text) ? text : null;
}

function pickSafePhotoUrls(values: unknown): string[] {
  return asStringList(values).filter((url) => isSafePublicAvatarUrl(url));
}

function readMap(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function pickPublicOnboarding(
  onboardingRaw: unknown,
): Record<string, unknown> | null {
  const onboarding = readMap(onboardingRaw);
  if (Object.keys(onboarding).length === 0) return null;

  const publicOnboarding: Record<string, unknown> = {};
  for (const key of PUBLIC_ONBOARDING_KEYS) {
    if (onboarding[key] !== undefined) {
      publicOnboarding[key] = onboarding[key];
    }
  }

  const photoUrls = pickSafePhotoUrls(onboarding.photoUrls);
  const avatarUrls = pickSafePhotoUrls(onboarding.avatarUrls);
  if (photoUrls.length > 0) publicOnboarding.photoUrls = photoUrls;
  if (avatarUrls.length > 0) publicOnboarding.avatarUrls = avatarUrls;

  const representative = asString(onboarding.representativeImageUrl);
  if (representative && isSafePublicAvatarUrl(representative)) {
    publicOnboarding.representativeImageUrl = representative;
  }

  return Object.keys(publicOnboarding).length > 0 ? publicOnboarding : null;
}

function resolvePublicPhotoUrl(userData: Record<string, unknown>): string | null {
  const avatar = readMap(userData.avatar);
  const approved = asString(avatar.approvedAvatarUrl);
  if (avatar.status === "approved" && approved && isSafePublicAvatarUrl(approved)) {
    return approved;
  }

  const profileImageUrl = asString(userData.profileImageUrl);
  if (profileImageUrl && isSafePublicAvatarUrl(profileImageUrl)) {
    return profileImageUrl;
  }

  const onboarding = readMap(userData.onboarding);
  const fromLists = [
    ...pickSafePhotoUrls(onboarding.avatarUrls),
    ...pickSafePhotoUrls(onboarding.photoUrls),
  ];
  return fromLists[0] ?? null;
}

/** Pure builder — unit-tested without Firestore. */
export function buildPublicProfileFromUser(
  uid: string,
  userData: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  if (!userData) return null;

  // Operations staff may chat with members but must never become a public
  // recommendation candidate.  Returning null also removes an older public
  // projection when an account is converted to operations.
  if (userData.accountType === "operations") return null;

  const status = asString(userData.status) ?? "active";
  const inactiveStatuses = new Set([
    "banned",
    "blocked",
    "deleted",
    "restricted_rejoin",
    "suspended",
    "withdrawn",
  ]);
  const isInactive =
    inactiveStatuses.has(status) ||
    userData.isWithdrawn === true ||
    userData.isDeleted === true ||
    userData.isSuspended === true ||
    userData.isActive === false;
  // A member's recommendation visibility is date-scoped and resolved by the
  // daily server job. Keep today's public projection intact so a change made
  // during the day cannot retroactively remove already-issued cards.
  if (isInactive) {
    return null;
  }

  const nickname =
    asString(userData.nickname) ??
    asString(readMap(userData.onboarding).nickname) ??
    null;

  const publicOnboarding = pickPublicOnboarding(userData.onboarding);
  const photoUrl = resolvePublicPhotoUrl(userData);
  const avatar = readMap(userData.avatar);
  const approvedAvatarUrl = asString(avatar.approvedAvatarUrl);

  return {
    uid,
    kakaoUserId: uid,
    nickname,
    profileImageUrl: photoUrl,
    status: "active",
    isWithdrawn: false,
    // Candidate visibility is a KST-date-scoped setting. These three fields
    // are intentionally public so the app can defend against serving an old
    // fallback feed after the next-day transition has taken effect.
    profileVisible: userData.profileVisible !== false,
    profileVisibleBeforeEffectiveDate:
      userData.profileVisibleBeforeEffectiveDate !== false,
    profileVisibleEffectiveDateKey: asDateKey(
      userData.profileVisibleEffectiveDateKey,
    ),
    isStudentVerified: userData.isStudentVerified === true,
    initialSetupComplete: userData.initialSetupComplete === true,
    isProfileComplete: userData.initialSetupComplete === true,
    // This boolean contains no friend information. It only prevents a profile
    // from entering 1:1 recommendation surfaces before privacy reconciliation.
    // Missing is not ready. Legacy accounts must complete the same verified
    // reconciliation as new accounts before becoming recommendation-visible.
    recommendationPrivacyReady: userData.recommendationPrivacyReady === true,
    onboarding: publicOnboarding,
    avatar:
      avatar.status === "approved" &&
      approvedAvatarUrl &&
      isSafePublicAvatarUrl(approvedAvatarUrl)
        ? {
            status: "approved",
            approvedAvatarUrl,
          }
        : null,
    schemaVersion: 2,
  };
}

export function publicProfileProjectionChanged(
  uid: string,
  beforeData: Record<string, unknown> | null | undefined,
  afterData: Record<string, unknown> | null | undefined,
): boolean {
  return !isDeepStrictEqual(
    buildPublicProfileFromUser(uid, beforeData),
    buildPublicProfileFromUser(uid, afterData),
  );
}

export async function syncPublicProfileForUser(
  firestore: Firestore,
  uid: string,
  userData: Record<string, unknown> | null | undefined,
): Promise<"upserted" | "deleted" | "unchanged"> {
  const ref = firestore.collection("publicProfiles").doc(uid);
  const payload = buildPublicProfileFromUser(uid, userData);
  const current = await ref.get();
  if (!payload) {
    if (!current.exists) return "unchanged";
    await ref.delete().catch(() => undefined);
    return "deleted";
  }

  if (current.exists) {
    const currentData = current.data() ?? {};
    const { updatedAt: _updatedAt, ...currentProjection } = currentData;
    if (isDeepStrictEqual(currentProjection, payload)) return "unchanged";
  }

  await ref.set(
    {
      ...payload,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: false },
  );
  return "upserted";
}
