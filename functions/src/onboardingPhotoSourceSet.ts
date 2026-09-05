export const MIN_AVATAR_SOURCE_PHOTOS = 2;
export const MAX_AVATAR_SOURCE_PHOTOS = 6;
export const AVATAR_ONBOARDING_SOURCE_SET_VERSION =
  "onboarding_normalized_jpeg_v1";

const SAFE_PHOTO_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$/;
const SAFE_PATH_SEGMENT = /^[A-Za-z0-9_-]+$/;
const ALLOWED_REF_FIELDS = new Set([
  "photoId",
  "slotIndex",
  "objectGeneration",
]);

export type OnboardingPhotoSourceRef = {
  photoId: string;
  slotIndex: number;
  objectGeneration: string;
};

export type StoredOnboardingPhotoMetadata = {
  name?: string;
  size?: string | number;
  contentType?: string;
  generation?: string | number;
  metadata?: Record<string, unknown>;
};

export function buildOnboardingPhotoUploadResponse(
  input: OnboardingPhotoSourceRef & { photoUrl: string },
): OnboardingPhotoSourceRef & { photoUrl: string } {
  return {
    photoUrl: input.photoUrl,
    photoId: input.photoId,
    slotIndex: input.slotIndex,
    objectGeneration: input.objectGeneration,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) throw new Error(`${field} is required`);
  return normalized;
}

function slotIndex(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed >= MAX_AVATAR_SOURCE_PHOTOS) {
    throw new Error("slotIndex must be between 0 and 5");
  }
  return parsed;
}

export function parseOnboardingPhotoSourceSet(
  value: unknown,
): OnboardingPhotoSourceRef[] {
  if (
    !Array.isArray(value) ||
    value.length < MIN_AVATAR_SOURCE_PHOTOS ||
    value.length > MAX_AVATAR_SOURCE_PHOTOS
  ) {
    throw new Error("avatar source set must contain 2 to 6 photos");
  }

  const photoIds = new Set<string>();
  const slots = new Set<number>();
  const parsed = value.map((item) => {
    if (!isRecord(item)) throw new Error("invalid onboarding photo ref");
    if (Object.keys(item).some((key) => !ALLOWED_REF_FIELDS.has(key))) {
      throw new Error("onboarding photo ref contains forbidden authority fields");
    }
    const photoId = requiredString(item.photoId, "photoId");
    if (!SAFE_PHOTO_ID.test(photoId)) throw new Error("photoId is unsafe");
    const index = slotIndex(item.slotIndex);
    const objectGeneration = requiredString(
      item.objectGeneration,
      "objectGeneration",
    );
    if (!/^[1-9][0-9]{0,30}$/.test(objectGeneration)) {
      throw new Error("objectGeneration must be a positive integer string");
    }
    if (photoIds.has(photoId) || slots.has(index)) {
      throw new Error("duplicate onboarding photo id or slot");
    }
    photoIds.add(photoId);
    slots.add(index);
    return { photoId, slotIndex: index, objectGeneration };
  });
  return parsed.sort((left, right) => left.slotIndex - right.slotIndex);
}

export function onboardingPhotoPath(userId: string, photoId: string): string {
  if (!SAFE_PATH_SEGMENT.test(userId) || !SAFE_PHOTO_ID.test(photoId)) {
    throw new Error("unsafe onboarding photo path segment");
  }
  return `users/${userId}/onboarding/photos/${photoId}.jpg`;
}

export function validateStoredOnboardingPhoto(
  source: OnboardingPhotoSourceRef,
  stored: StoredOnboardingPhotoMetadata,
  userId: string,
): void {
  const expectedPath = onboardingPhotoPath(userId, source.photoId);
  const custom = isRecord(stored.metadata) ? stored.metadata : {};
  const size = Number(stored.size ?? 0);
  if (stored.name !== expectedPath) throw new Error("onboarding photo path mismatch");
  if (!Number.isFinite(size) || size <= 0) throw new Error("onboarding photo is empty");
  if (stored.contentType !== "image/jpeg") {
    throw new Error("onboarding photo is not a normalized jpeg");
  }
  if (String(stored.generation ?? "") !== source.objectGeneration) {
    throw new Error("onboarding photo generation mismatch");
  }
  if (String(custom.ownerUid ?? "") !== userId) {
    throw new Error("onboarding photo owner mismatch");
  }
  if (custom.uploadKind !== "onboarding_profile_photo") {
    throw new Error("onboarding photo kind mismatch");
  }
  if (custom.uploadState !== "ready") {
    throw new Error("onboarding photo is not ready");
  }
  if (custom.normalization !== AVATAR_ONBOARDING_SOURCE_SET_VERSION) {
    throw new Error("onboarding photo normalization mismatch");
  }
  if (String(custom.slotIndex ?? "") !== String(source.slotIndex)) {
    throw new Error("onboarding photo slot mismatch");
  }
}
