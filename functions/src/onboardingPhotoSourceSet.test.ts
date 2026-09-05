import assert from "node:assert/strict";
import test from "node:test";

import {
  AVATAR_ONBOARDING_SOURCE_SET_VERSION,
  buildOnboardingPhotoUploadResponse,
  onboardingPhotoPath,
  parseOnboardingPhotoSourceSet,
  validateStoredOnboardingPhoto,
} from "./onboardingPhotoSourceSet";

const refs = [
  { photoId: "1700000000000_0_abcdef12", slotIndex: 0, objectGeneration: "101" },
  { photoId: "1700000000001_1_abcdef13", slotIndex: 1, objectGeneration: "102" },
];

test("accepts two to six unique server-issued onboarding photo refs", () => {
  const parsed = parseOnboardingPhotoSourceSet(refs);
  assert.equal(parsed.length, 2);
  assert.equal(parsed[0].photoId, refs[0].photoId);
  assert.equal(parsed[0].objectGeneration, "101");
});

test("rejects too few, too many, duplicate ids, and duplicate slots", () => {
  assert.throws(() => parseOnboardingPhotoSourceSet(refs.slice(0, 1)), /2 to 6/);
  assert.throws(
    () => parseOnboardingPhotoSourceSet([...refs, ...refs, ...refs, refs[0]]),
    /2 to 6/,
  );
  assert.throws(() => parseOnboardingPhotoSourceSet([refs[0], refs[0]]), /duplicate/);
  assert.throws(
    () => parseOnboardingPhotoSourceSet([refs[0], { ...refs[1], slotIndex: 0 }]),
    /duplicate/,
  );
});

test("rejects paths, urls, unsafe ids, and missing generations from clients", () => {
  for (const bad of [
    { ...refs[0], photoId: "../escape" },
    { ...refs[0], photoId: "https://example.test/photo.jpg" },
    { ...refs[0], objectGeneration: "" },
    { ...refs[0], objectGeneration: "not-a-number" },
    { ...refs[0], storagePath: "users/other/private.jpg" },
  ]) {
    assert.throws(() => parseOnboardingPhotoSourceSet([bad, refs[1]]));
  }
});

test("constructs the uid-scoped canonical object path on the server", () => {
  assert.equal(
    onboardingPhotoPath("user_1", refs[0].photoId),
    `users/user_1/onboarding/photos/${refs[0].photoId}.jpg`,
  );
});

test("stored object must match owner, kind, ready state, normalized jpeg and generation", () => {
  const valid = {
    name: onboardingPhotoPath("user_1", refs[0].photoId),
    size: "2048",
    contentType: "image/jpeg",
    generation: "101",
    metadata: {
      ownerUid: "user_1",
      uploadKind: "onboarding_profile_photo",
      uploadState: "ready",
      normalization: AVATAR_ONBOARDING_SOURCE_SET_VERSION,
      slotIndex: "0",
    },
  };
  assert.doesNotThrow(() => validateStoredOnboardingPhoto(refs[0], valid, "user_1"));
  for (const bad of [
    { ...valid, generation: "999" },
    { ...valid, contentType: "image/png" },
    { ...valid, size: "0" },
    { ...valid, metadata: { ...valid.metadata, ownerUid: "other" } },
    { ...valid, metadata: { ...valid.metadata, uploadKind: "other" } },
    { ...valid, metadata: { ...valid.metadata, uploadState: "pending" } },
    { ...valid, metadata: { ...valid.metadata, slotIndex: "5" } },
  ]) {
    assert.throws(() => validateStoredOnboardingPhoto(refs[0], bad, "user_1"));
  }
});

test("upload response carries an opaque server ref alongside the display URL", () => {
  assert.deepEqual(
    buildOnboardingPhotoUploadResponse({
      photoUrl: "https://display.invalid/tokenized",
      photoId: refs[0].photoId,
      slotIndex: 0,
      objectGeneration: "101",
    }),
    {
      photoUrl: "https://display.invalid/tokenized",
      photoId: refs[0].photoId,
      slotIndex: 0,
      objectGeneration: "101",
    },
  );
});
