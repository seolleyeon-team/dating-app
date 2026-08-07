/**
 * Builds and syncs AUTHENTICATED_LIMITED_PROFILE documents under
 * publicProfiles/{uid}. Private users/{uid} fields must never appear here.
 */

import type {Firestore } from "firebase-admin/firestore";
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

  const status = asString(userData.status) ?? "active";
  const isWithdrawn = userData.isWithdrawn === true || status === "withdrawn";
  const profileVisible = userData.profileVisible !== false;

  // Withdrawn / invisible users leave no public profile surface.
  if (isWithdrawn || !profileVisible || status === "banned") {
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
    profileVisible: true,
    isStudentVerified: userData.isStudentVerified === true,
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
    schemaVersion: 1,
  };
}

export async function syncPublicProfileForUser(
  firestore: Firestore,
  uid: string,
  userData: Record<string, unknown> | null | undefined,
): Promise<"upserted" | "deleted"> {
  const ref = firestore.collection("publicProfiles").doc(uid);
  const payload = buildPublicProfileFromUser(uid, userData);
  if (!payload) {
    await ref.delete().catch(() => undefined);
    return "deleted";
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
