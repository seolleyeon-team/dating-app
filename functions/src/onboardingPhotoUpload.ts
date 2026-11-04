import { randomBytes } from "crypto";
import { getFirestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";
import {
  HttpsError,
  onCall,
  type CallableOptions,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import sharp from "sharp";
import { hasActiveAvatarWorkflowState } from "./avatarMedia";
import { onboardingPhotoStoragePrefix } from "./onboardingPhotoRequirement";
import {
  AVATAR_ONBOARDING_SOURCE_SET_VERSION,
  buildOnboardingPhotoUploadResponse,
} from "./onboardingPhotoSourceSet";

export const MAX_IMAGE_BYTES = 12 * 1024 * 1024;
export const MAX_INPUT_PIXELS = 40_000_000;
/**
 * P1-9: longest side of the stored source photograph. Phone cameras produce
 * 12–50 MP frames; the avatar pipeline (source-set admission → image model)
 * and the profile UI never need more than this, and the base64 callable
 * payload stays well under the transport limit. JPEG quality is unchanged
 * (88) so the identity-fidelity contract of the avatar pipeline holds.
 */
export const MAX_OUTPUT_DIMENSION = 2048;
export const OUTPUT_JPEG_QUALITY = 88;
/** Formats the server decodes; anything else (SVG, PDF, HTML, …) is refused. */
export const ACCEPTED_INPUT_FORMATS: ReadonlySet<string> = new Set([
  "jpeg", "png", "webp", "heif", "avif", "tiff", "gif",
]);

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

export type NormalizeOptions = {
  maxInputPixels?: number;
  maxDimension?: number;
};

/**
 * P1-9: decode-validate, bound and re-encode the upload.
 *   - the real format is read from the bytes (never from the client);
 *   - `limitInputPixels` refuses decompression bombs before decoding;
 *   - EXIF orientation is applied, then the output is capped to
 *     MAX_OUTPUT_DIMENSION on the longest side (never enlarged);
 *   - the JPEG is written without metadata: EXIF (GPS, device, timestamps),
 *     ICC and XMP from the camera never reach Storage.
 */
export async function normalizeOnboardingImage(
  bytes: Buffer,
  options: NormalizeOptions = {},
): Promise<{ buffer: Buffer; width: number; height: number; inputFormat: string }> {
  const maxInputPixels = options.maxInputPixels ?? MAX_INPUT_PIXELS;
  const maxDimension = options.maxDimension ?? MAX_OUTPUT_DIMENSION;
  try {
    const probe = sharp(bytes, { limitInputPixels: maxInputPixels });
    const metadata = await probe.metadata();
    const format = String(metadata.format ?? "");
    if (!ACCEPTED_INPUT_FORMATS.has(format)) {
      throw new Error("unsupported_format");
    }
    const width = Number(metadata.width ?? 0);
    const height = Number(metadata.height ?? 0);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error("missing_dimensions");
    }
    if (width * height > maxInputPixels) {
      throw new Error("too_many_pixels");
    }
    const { data, info } = await sharp(bytes, { limitInputPixels: maxInputPixels })
      .rotate()
      .resize({
        width: maxDimension,
        height: maxDimension,
        fit: "inside",
        withoutEnlargement: true,
      })
      .jpeg({ quality: OUTPUT_JPEG_QUALITY })
      .toBuffer({ resolveWithObject: true });
    return { buffer: data, width: info.width, height: info.height, inputFormat: format };
  } catch {
    throw new HttpsError("invalid-argument", "invalid_onboarding_photo");
  }
}

async function normalizeImage(bytes: Buffer): Promise<Buffer> {
  return (await normalizeOnboardingImage(bytes)).buffer;
}

type SlotObjectLike = {
  name: string;
  getMetadata(): Promise<[{ generation?: string | number; metadata?: Record<string, unknown> }, ...unknown[]]>;
  delete(options?: { ifGenerationMatch?: number }): Promise<unknown>;
};

export type SlotCleanupBucketLike = {
  getFiles(options: { prefix: string; autoPaginate?: boolean }): Promise<[SlotObjectLike[], ...unknown[]]>;
};

/**
 * P1-9 / P1-5: a re-picked slot used to leave the previous photograph in
 * Storage until account deletion. After a successful upload the earlier
 * objects of the SAME slot are deleted — unless an avatar workflow is active
 * for the account, because a queued or running source-set job validates its
 * onboarding objects by generation and must not lose them (the client blocks
 * re-picking in that state as well; this is the server-side guard). Any
 * failure here is logged and never fails the upload.
 */
export async function cleanupReplacedSlotObjects(params: {
  bucket: SlotCleanupBucketLike;
  userId: string;
  slotIndex: number;
  keepPath: string;
  avatarWorkflowActive: boolean;
}): Promise<{ deleted: number; skipped: "none" | "avatar_workflow_active" }> {
  if (params.avatarWorkflowActive) return { deleted: 0, skipped: "avatar_workflow_active" };
  const [files] = await params.bucket.getFiles({
    prefix: onboardingPhotoStoragePrefix(params.userId),
    autoPaginate: true,
  });
  let deleted = 0;
  for (const file of files) {
    if (file.name === params.keepPath) continue;
    const [meta] = await file.getMetadata();
    const custom = isRecord(meta.metadata) ? meta.metadata : {};
    if (String(custom.slotIndex ?? "") !== String(params.slotIndex)) continue;
    if (custom.uploadKind !== "onboarding_profile_photo") continue;
    const generation = Number(meta.generation);
    await file.delete(Number.isFinite(generation) && generation > 0 ? { ifGenerationMatch: generation } : undefined);
    deleted += 1;
  }
  return { deleted, skipped: "none" };
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
            uploadState: "ready",
            normalization: AVATAR_ONBOARDING_SOURCE_SET_VERSION,
            slotIndex: String(slotIndex),
          },
        },
      });

      const [storedMetadata] = await file.getMetadata();
      const objectGeneration = String(storedMetadata.generation ?? "").trim();
      if (!objectGeneration) {
        throw new HttpsError("internal", "onboarding_photo_generation_missing");
      }

      // P1-9: replace, do not accumulate — see cleanupReplacedSlotObjects.
      try {
        const userSnap = await getFirestore().collection("users").doc(user.userId).get();
        const cleanup = await cleanupReplacedSlotObjects({
          bucket: bucket as unknown as SlotCleanupBucketLike,
          userId: user.userId,
          slotIndex,
          keepPath: storagePath,
          avatarWorkflowActive: hasActiveAvatarWorkflowState(userSnap.data()?.avatar),
        });
        if (cleanup.deleted > 0 || cleanup.skipped !== "none") {
          logger.info("onboarding photo slot cleanup", { slotIndex, ...cleanup });
        }
      } catch (error) {
        logger.warn("onboarding photo slot cleanup failed", {
          slotIndex,
          errorType: error instanceof Error ? error.name : typeof error,
        });
      }

      return buildOnboardingPhotoUploadResponse({
        photoUrl: buildDownloadUrl(bucket.name, storagePath, token),
        photoId,
        slotIndex,
        objectGeneration,
      });
    },
  );
}
