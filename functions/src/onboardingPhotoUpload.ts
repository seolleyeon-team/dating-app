import { randomBytes } from "crypto";
import { getStorage } from "firebase-admin/storage";
import {
  HttpsError,
  onCall,
  type CallableOptions,
} from "firebase-functions/v2/https";
import sharp from "sharp";

const MAX_IMAGE_BYTES = 12 * 1024 * 1024;
const MAX_INPUT_PIXELS = 40_000_000;

export const ONBOARDING_PHOTO_UPLOAD_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 120,
  memory: "1GiB",
  invoker: "public",
  enforceAppCheck: true,
};

type UploadAuth = {
  uid?: string;
  token?: Record<string, unknown>;
} | null | undefined;

type ResolveOnboardingPhotoUser = (
  auth: UploadAuth,
) => Promise<{ userId: string }>;

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireSlotIndex(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 5) {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo_slot");
  }
  return parsed;
}

function requireImageBytes(data: Record<string, unknown>): Buffer {
  const encoded = asString(data.imageBase64);
  if (!encoded || encoded.length > Math.ceil(MAX_IMAGE_BYTES * 1.4)) {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo");
  }

  let bytes: Buffer;
  try {
    bytes = Buffer.from(encoded, "base64");
  } catch {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo");
  }
  if (bytes.length === 0 || bytes.length > MAX_IMAGE_BYTES) {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo");
  }
  return bytes;
}

async function normalizeImage(bytes: Buffer): Promise<Buffer> {
  try {
    return await sharp(bytes, { limitInputPixels: MAX_INPUT_PIXELS })
      .rotate()
      .jpeg({ quality: 88 })
      .toBuffer();
  } catch {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo");
  }
}

function buildDownloadUrl(
  bucketName: string,
  storagePath: string,
  token: string,
): string {
  return `https://firebasestorage.googleapis.com/v0/b/${encodeURIComponent(
    bucketName,
  )}/o/${encodeURIComponent(storagePath)}?alt=media&token=${encodeURIComponent(
    token,
  )}`;
}

export function createUploadOnboardingPhotoFunction(
  resolveUser: ResolveOnboardingPhotoUser,
) {
  return onCall(
    ONBOARDING_PHOTO_UPLOAD_CALLABLE_OPTIONS,
    async (request) => {
      const user = await resolveUser(request.auth);
      const data = isRecord(request.data) ? request.data : {};
      const requestedUid = asString(data.uid);
      if (requestedUid && requestedUid !== user.userId) {
        throw new HttpsError(
          "permission-denied",
          "uid does not match authenticated user.",
        );
      }

      const slotIndex = requireSlotIndex(data.slotIndex);
      const normalizedImage = await normalizeImage(requireImageBytes(data));
      const token = randomBytes(16).toString("hex");
      const photoId = `${Date.now()}_${slotIndex}_${randomBytes(8).toString(
        "hex",
      )}`;
      const storagePath = `users/${user.userId}/onboarding/photos/${photoId}.jpg`;
      const bucket = getStorage().bucket();
      const file = bucket.file(storagePath);

      await file.save(normalizedImage, {
        resumable: false,
        metadata: {
          contentType: "image/jpeg",
          metadata: {
            firebaseStorageDownloadTokens: token,
            ownerUid: user.userId,
            uploadKind: "onboarding_profile_photo",
          },
        },
      });

      return {
        photoUrl: buildDownloadUrl(bucket.name, storagePath, token),
        slotIndex,
      };
    },
  );
}
