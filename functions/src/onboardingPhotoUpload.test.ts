import assert from "node:assert/strict";
import test from "node:test";

import { HttpsError } from "firebase-functions/v2/https";
import sharp from "sharp";

import {
  MAX_OUTPUT_DIMENSION,
  cleanupReplacedSlotObjects,
  normalizeOnboardingImage,
} from "./onboardingPhotoUpload";

async function png(width: number, height: number): Promise<Buffer> {
  return sharp({ create: { width, height, channels: 3, background: { r: 200, g: 90, b: 120 } } }).png().toBuffer();
}

test("P1-9: a high-resolution photograph is bounded to the longest side, aspect kept, re-encoded as JPEG without metadata", async () => {
  const input = await png(4000, 3000);
  const out = await normalizeOnboardingImage(input);
  assert.equal(out.inputFormat, "png");
  assert.equal(out.width, MAX_OUTPUT_DIMENSION);
  assert.equal(out.height, 1536);
  const meta = await sharp(out.buffer).metadata();
  assert.equal(meta.format, "jpeg");
  assert.equal(meta.exif, undefined, "camera EXIF never reaches Storage");
  assert.equal(meta.icc, undefined);
  assert.equal(meta.xmp, undefined);
});

test("P1-9: a panorama is bounded on its long side; a small image is never enlarged", async () => {
  const pano = await normalizeOnboardingImage(await png(6000, 800));
  assert.equal(pano.width, MAX_OUTPUT_DIMENSION);
  assert.equal(pano.height, 273);
  const small = await normalizeOnboardingImage(await png(640, 480));
  assert.equal(small.width, 640);
  assert.equal(small.height, 480);
});

test("P1-9: EXIF orientation is applied (rotated frame comes out upright) and the tag is dropped", async () => {
  const landscape = await sharp({ create: { width: 300, height: 100, channels: 3, background: "#88aaff" } })
    .jpeg()
    .withMetadata({ orientation: 6 })
    .toBuffer();
  assert.equal((await sharp(landscape).metadata()).orientation, 6);
  const out = await normalizeOnboardingImage(landscape);
  assert.equal(out.width, 100, "rotated 90°: width/height swap");
  assert.equal(out.height, 300);
  assert.equal((await sharp(out.buffer).metadata()).orientation, undefined);
});

test("P1-9: malformed bytes, non-image formats and decompression bombs are refused with invalid-argument", async () => {
  const invalid = async (bytes: Buffer, options?: { maxInputPixels?: number }) =>
    assert.rejects(normalizeOnboardingImage(bytes, options), (e: unknown) => e instanceof HttpsError && e.code === "invalid-argument");
  await invalid(Buffer.from("not an image"));
  await invalid(Buffer.from("<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"));
  await invalid(Buffer.from("%PDF-1.4 ..."));
  // 1200×1200 = 1.44 MP against a 1 MP ceiling: refused before decoding.
  await invalid(await png(1200, 1200), { maxInputPixels: 1_000_000 });
});

test("P1-9: re-picking a slot deletes the earlier objects of that slot only, and never while an avatar workflow is active", async () => {
  const deleted: string[] = [];
  const file = (name: string, slotIndex: string, kind = "onboarding_profile_photo") => ({
    name,
    async getMetadata() {
      return [{ generation: "7", metadata: { slotIndex, uploadKind: kind } }] as [{ generation: string; metadata: Record<string, unknown> }];
    },
    async delete(options?: { ifGenerationMatch?: number }) {
      assert.equal(options?.ifGenerationMatch, 7);
      deleted.push(name);
    },
  });
  const bucket = {
    async getFiles(options: { prefix: string }) {
      assert.equal(options.prefix, "users/u1/onboarding/photos/");
      return [[
        file("users/u1/onboarding/photos/old_0_a.jpg", "0"),
        file("users/u1/onboarding/photos/old_0_b.jpg", "0"),
        file("users/u1/onboarding/photos/new_0_c.jpg", "0"),
        file("users/u1/onboarding/photos/other_1_d.jpg", "1"),
        file("users/u1/onboarding/photos/foreign_0_e.jpg", "0", "something_else"),
      ]] as [ReturnType<typeof file>[]];
    },
  };
  const result = await cleanupReplacedSlotObjects({
    bucket, userId: "u1", slotIndex: 0, keepPath: "users/u1/onboarding/photos/new_0_c.jpg", avatarWorkflowActive: false,
  });
  assert.deepEqual(result, { deleted: 2, skipped: "none" });
  assert.deepEqual(deleted.sort(), ["users/u1/onboarding/photos/old_0_a.jpg", "users/u1/onboarding/photos/old_0_b.jpg"]);

  deleted.length = 0;
  const locked = await cleanupReplacedSlotObjects({
    bucket, userId: "u1", slotIndex: 0, keepPath: "users/u1/onboarding/photos/new_0_c.jpg", avatarWorkflowActive: true,
  });
  assert.deepEqual(locked, { deleted: 0, skipped: "avatar_workflow_active" });
  assert.deepEqual(deleted, [], "a queued source-set job keeps its objects");
});
