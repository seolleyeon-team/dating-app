import { getStorage } from "firebase-admin/storage";
import { HttpsError } from "firebase-functions/v2/https";

/**
 * Server-side onboarding photo requirement.
 *
 * Avatar generation admission must not trust any client-supplied photo count.
 * The only accepted evidence is server-written onboarding photo objects
 * (created by the `uploadOnboardingPhoto` callable, which validates auth,
 * App Check, ownership, and image decodability before writing the object).
 *
 * Fail-closed: if the evidence cannot be read, admission is refused rather
 * than assumed satisfied.
 */
export const MIN_ONBOARDING_SOURCE_PHOTOS = 2;

export const AVATAR_MINIMUM_PHOTOS_ERROR = "avatar_minimum_photos_required";
export const AVATAR_PHOTO_EVIDENCE_UNAVAILABLE_ERROR =
  "avatar_photo_evidence_unavailable";

const ONBOARDING_PHOTO_UPLOAD_KIND = "onboarding_profile_photo";

export function onboardingPhotoStoragePrefix(userId: string): string {
  return `users/${userId}/onboarding/photos/`;
}

type StoredFileMetadata = {
  size?: string | number;
  contentType?: string;
  metadata?: Record<string, unknown>;
};

export type StoredOnboardingPhotoFile = {
  name?: string;
  metadata?: StoredFileMetadata;
};

type PhotoEvidenceBucket = {
  getFiles(options: {
    prefix: string;
  }): Promise<[StoredOnboardingPhotoFile[]]>;
};

function fileSizeBytes(file: StoredOnboardingPhotoFile): number {
  const raw = file.metadata?.size;
  const parsed = typeof raw === "number" ? raw : Number(raw ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Counts server-validated onboarding photo objects for one user.
 *
 * A file counts only when it is non-empty, is an image, and carries the
 * server-stamped owner/kind metadata written by `uploadOnboardingPhoto`.
 * Ownership is double-checked against the object metadata even though the
 * prefix is already uid-scoped.
 */
export function countValidOnboardingPhotoFiles(
  files: readonly StoredOnboardingPhotoFile[],
  userId: string,
): number {
  let valid = 0;
  for (const file of files) {
    if (fileSizeBytes(file) <= 0) continue;
    const contentType = String(file.metadata?.contentType ?? "");
    if (!contentType.startsWith("image/")) continue;
    const custom = file.metadata?.metadata ?? {};
    if (String(custom.ownerUid ?? "") !== userId) continue;
    if (String(custom.uploadKind ?? "") !== ONBOARDING_PHOTO_UPLOAD_KIND) {
      continue;
    }
    valid += 1;
  }
  return valid;
}

export async function countValidOnboardingPhotos(options: {
  userId: string;
  bucket?: PhotoEvidenceBucket;
}): Promise<number> {
  const bucket =
    options.bucket ?? (getStorage().bucket() as unknown as PhotoEvidenceBucket);
  const [files] = await bucket.getFiles({
    prefix: onboardingPhotoStoragePrefix(options.userId),
  });
  return countValidOnboardingPhotoFiles(files ?? [], options.userId);
}

/**
 * Refuses avatar generation admission unless the user already has at least
 * {@link MIN_ONBOARDING_SOURCE_PHOTOS} server-validated onboarding photos.
 */
export async function assertMinimumOnboardingPhotoEvidence(options: {
  userId: string;
  bucket?: PhotoEvidenceBucket;
}): Promise<void> {
  let validCount: number;
  try {
    validCount = await countValidOnboardingPhotos(options);
  } catch {
    throw new HttpsError("internal", AVATAR_PHOTO_EVIDENCE_UNAVAILABLE_ERROR, {
      reason: AVATAR_PHOTO_EVIDENCE_UNAVAILABLE_ERROR,
    });
  }
  if (validCount < MIN_ONBOARDING_SOURCE_PHOTOS) {
    throw new HttpsError("failed-precondition", AVATAR_MINIMUM_PHOTOS_ERROR, {
      reason: AVATAR_MINIMUM_PHOTOS_ERROR,
      requiredPhotos: MIN_ONBOARDING_SOURCE_PHOTOS,
      validPhotos: validCount,
    });
  }
}
