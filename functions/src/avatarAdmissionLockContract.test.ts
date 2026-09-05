import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const SRC = path.join(__dirname, "..", "src");

function readSource(file: string): string {
  const raw = readFileSync(path.join(SRC, file));
  if (raw[0] === 0xff && raw[1] === 0xfe) return raw.toString("utf16le");
  return raw.toString("utf8");
}

function exportedCallableNames(source: string): string[] {
  return [...source.matchAll(/export const ([A-Za-z0-9_]+)\s*=/g)].map(
    (match) => match[1],
  );
}

test("single-photo upload endpoint cannot acquire a generation lock", () => {
  const index = readSource("index.ts");
  assert.ok(!exportedCallableNames(index).includes("uploadAvatarSourcePhoto"));
});

test("single-photo upload endpoint cannot create or enqueue a generation job", () => {
  const index = readSource("index.ts");
  assert.ok(!index.includes("createUploadAvatarSourcePhotoFunction"));
});

test("retired single-photo factory is a side-effect-free tombstone", () => {
  const source = readSource("avatarMedia.ts");
  const tombstone = source.match(
    /export function createUploadAvatarSourcePhotoFunction[\s\S]*?(?=async function currentPreviewCandidateAvailable)/,
  )?.[0];
  assert.ok(tombstone);
  assert.ok(tombstone.includes("avatar_single_photo_generation_retired"));
  for (const marker of ["runTransaction", "avatarJobs", "createTask", "save(", "set("]) {
    assert.ok(!tombstone.includes(marker), `tombstone must not contain ${marker}`);
  }
});

test("exactly one new-generation admission authority is registered", () => {
  const index = readSource("index.ts");
  const authorities = exportedCallableNames(index).filter((name) =>
    name === "beginAvatarGenerationFromOnboardingPhotos" ||
    name === "uploadAvatarSourcePhoto"
  );
  assert.deepEqual(authorities, ["beginAvatarGenerationFromOnboardingPhotos"]);
  assert.equal(
    (index.match(/createBeginAvatarGenerationFromOnboardingPhotosFunction\(/g) ?? []).length,
    1,
  );
});

test("per-photo onboarding upload never creates a job or takes a lock", () => {
  const source = readSource("onboardingPhotoUpload.ts");
  for (const marker of [
    "currentAvatarSourcePhotoId",
    "currentAvatarJobId",
    "avatarJobs",
    "createTask",
    "enqueue",
  ]) {
    assert.ok(!source.includes(marker), `uploadOnboardingPhoto must not reference ${marker}`);
  }
});

test("source-set admission waits for server selection before locking a source", () => {
  const source = readSource("avatarSourceSetAdmission.ts");
  assert.ok(!source.includes("currentAvatarSourcePhotoId:"));
  assert.ok(source.includes('status: "pending"'));
});
