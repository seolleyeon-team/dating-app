import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

/**
 * CANONICAL ADMISSION CONTRACT (final, 2026-09-05)
 *
 *   photo upload      -> no generation source lock, no job, no task
 *   generation submit -> exactly one admission authority
 *                        (beginAvatarGenerationFromOnboardingPhotos)
 *                        -> selection -> lock -> job -> task
 *
 * The legacy single-photo callable `uploadAvatarSourcePhoto` is RETIRED:
 * not exported, not registered, no factory in the tree, no rollback mode.
 * Existing legacy jobs stay readable; they can never spawn a new legacy
 * lock/job/task (their retry is refused; recovery is a new source set).
 */

const SRC = path.join(__dirname, "..", "src");

function readSource(file: string): string {
  const raw = readFileSync(path.join(SRC, file));
  if (raw[0] === 0xff && raw[1] === 0xfe) return raw.toString("utf16le");
  return raw.toString("utf8");
}

function exportedCallableNames(source: string): string[] {
  return [...source.matchAll(/export const ([A-Za-z0-9_]+)\s*=/g)].map((m) => m[1]);
}

test("uploadAvatarSourcePhoto is not exported and not registered", () => {
  const index = readSource("index.ts");
  assert.ok(!exportedCallableNames(index).includes("uploadAvatarSourcePhoto"));
  assert.ok(!index.includes("createUploadAvatarSourcePhotoFunction"));
  assert.ok(!index.includes("uploadAvatarSourcePhoto"));
});

test("the legacy single-photo factory and its upload-only helpers no longer exist", () => {
  const media = readSource("avatarMedia.ts");
  for (const symbol of [
    "createUploadAvatarSourcePhotoFunction",
    "enqueueUploadQueuePayloads",
    "savePrivateSourceObject",
    "planAvatarUploadState",
    "decideAvatarUploadRequest",
    "buildRetryAvatarJobPlan",
    "buildAvatarPayload(",
    "legacyAvatarGenerationStartAllowed",
    "legacy_first_photo",
  ]) {
    assert.ok(!media.includes(symbol), `${symbol} must be gone from avatarMedia.ts`);
  }
});

test("legacy jobs are read-only: retry of a non source-set job is refused, never re-dispatched", () => {
  const media = readSource("avatarMedia.ts");
  const start = media.indexOf("export function createRetryCurrentAvatarGenerationFunction");
  const end = media.indexOf("export function", start + 10);
  const retry = media.slice(start, end > 0 ? end : undefined);
  assert.ok(retry.includes("avatar_legacy_job_retry_retired"));
  assert.ok(retry.includes("isSourceSetAvatarJob(currentJobData)"));
  // The only dispatch in the retry callable is the source-set re-dispatch.
  assert.equal((retry.match(/enqueueQueuePayload\(/g) ?? []).length, 1);
  assert.ok(!retry.includes("buildRetryAvatarPayload"));
});

test("exactly one new-generation admission authority is registered", () => {
  const index = readSource("index.ts");
  const authorities = exportedCallableNames(index).filter(
    (name) => name === "beginAvatarGenerationFromOnboardingPhotos" || name === "uploadAvatarSourcePhoto",
  );
  assert.deepEqual(authorities, ["beginAvatarGenerationFromOnboardingPhotos"]);
  assert.equal((index.match(/createBeginAvatarGenerationFromOnboardingPhotosFunction\(/g) ?? []).length, 1);
});

test("per-photo onboarding upload never creates a job or takes a lock", () => {
  const source = readSource("onboardingPhotoUpload.ts");
  for (const marker of ["currentAvatarSourcePhotoId", "currentAvatarJobId", "avatarJobs", "createTask", "enqueue"]) {
    assert.ok(!source.includes(marker), `uploadOnboardingPhoto must not reference ${marker}`);
  }
});

test("source-set admission waits for server selection before locking a source", () => {
  const source = readSource("avatarSourceSetAdmission.ts");
  assert.ok(!source.includes("currentAvatarSourcePhotoId:"));
  assert.ok(source.includes('status: "pending"'));
  assert.ok(source.includes("parseOnboardingPhotoSourceSet(data.sourcePhotos)"));
});

test("no rollback selection mode survives in Functions sources", () => {
  for (const file of ["avatarSourceSelectionAdmission.ts", "avatarSourceSetAdmission.ts", "avatarSourceSetQueue.ts", "avatarMedia.ts"]) {
    assert.ok(!readSource(file).includes("legacy_first_photo"), `${file} must not mention legacy_first_photo`);
  }
});
