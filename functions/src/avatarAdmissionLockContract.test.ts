import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  assertLegacyAvatarGenerationStartAllowed,
  legacyAvatarGenerationStartAllowed,
} from "./avatarMedia";

/**
 * CANONICAL ADMISSION CONTRACT (product decision, 2026-09-05)
 *
 *   photo upload      -> no generation source lock, no job, no task
 *   generation submit -> source selection -> source lock -> job -> task
 *
 * These assertions are real (no todo): the legacy single-photo callable is
 * gated closed before any Storage/Firestore/Tasks write unless the explicit
 * rollback mode is configured, so exactly one callable can own generation
 * admission at runtime.
 */

const SRC = path.join(__dirname, "..", "src");

function readSource(file: string): string {
  const raw = readFileSync(path.join(SRC, file));
  // avatarMedia.ts is stored as UTF-16LE.
  if (raw[0] === 0xff && raw[1] === 0xfe) return raw.toString("utf16le");
  return raw.toString("utf8");
}

const LOCK_FIELD_MARKERS = ["currentAvatarSourcePhotoId", "currentAvatarJobId"];

function uploadFactoryBody(): string {
  const source = readSource("avatarMedia.ts");
  const start = source.indexOf("export function createUploadAvatarSourcePhotoFunction");
  const end = source.indexOf("export function createGetCurrentAvatarGenerationStatusFunction");
  assert.ok(start > 0 && end > start, "upload factory boundaries must be locatable");
  return source.slice(start, end);
}

test("legacy upload path cannot acquire a new-generation source lock under canonical mode", () => {
  // Behavioural: the gate is closed by default and in the canonical mode.
  assert.equal(legacyAvatarGenerationStartAllowed({}), false);
  assert.equal(
    legacyAvatarGenerationStartAllowed({ AVATAR_SOURCE_SELECTION_MODE: "quality_selector_v1" }),
    false,
  );
  assert.throws(() => assertLegacyAvatarGenerationStartAllowed({}));

  // Structural: the gate runs before the first Storage/Firestore mutation in
  // the factory, so no lock field can be written when it throws.
  const body = uploadFactoryBody();
  const gateAt = body.indexOf("assertLegacyAvatarGenerationStartAllowed();");
  assert.ok(gateAt > 0, "the legacy gate must be invoked inside the upload factory");
  const firstMutation = Math.min(
    ...["savePrivateSourceObject(", "runTransaction(", ...LOCK_FIELD_MARKERS]
      .map((marker) => body.indexOf(marker))
      .filter((index) => index >= 0),
  );
  assert.ok(gateAt < firstMutation, "the gate must precede every lock/storage write");
});

test("legacy upload path cannot enqueue generation for new onboarding under canonical mode", () => {
  const body = uploadFactoryBody();
  const gateAt = body.indexOf("assertLegacyAvatarGenerationStartAllowed();");
  const enqueueAt = body.indexOf("enqueueUploadQueuePayloads(");
  assert.ok(enqueueAt > 0, "legacy enqueue must still exist for the rollback mode");
  assert.ok(gateAt > 0 && gateAt < enqueueAt, "the gate must precede the legacy enqueue");
});

test("exactly one un-gated generation admission entry point is registered", () => {
  const index = readSource("index.ts");
  assert.ok(
    index.includes("createBeginAvatarGenerationFromOnboardingPhotosFunction("),
    "the source-set admission callable must be registered",
  );
  // The legacy callable may stay registered for in-flight compatibility, but
  // only behind the gate proven above.
  const legacyRegistered = index.includes("createUploadAvatarSourcePhotoFunction(db");
  if (legacyRegistered) {
    assert.ok(
      uploadFactoryBody().includes("assertLegacyAvatarGenerationStartAllowed();"),
      "a registered legacy callable must be gated",
    );
  }
});

test("per-photo upload never creates a job or takes a lock", () => {
  const source = readSource("onboardingPhotoUpload.ts");
  for (const marker of [...LOCK_FIELD_MARKERS, "avatarJobs", "createTask", "enqueue"]) {
    assert.ok(!source.includes(marker), `uploadOnboardingPhoto must not reference ${marker}`);
  }
});

test("the source-set admission does not lock a source before the worker selects one", () => {
  // Phase A writes the job pointer only; the source pointer is written by the
  // worker in the same transaction that records the selection.
  const source = readSource("avatarSourceSetAdmission.ts");
  assert.ok(!source.includes("currentAvatarSourcePhotoId:"), "Phase A must not write the source pointer");
  assert.ok(source.includes('status: "pending"'), "Phase A must declare the pending selection state");
});
