import assert from "node:assert/strict";
import test from "node:test";

import { HttpsError } from "firebase-functions/v2/https";

import {
  AVATAR_MINIMUM_PHOTOS_ERROR,
  AVATAR_PHOTO_EVIDENCE_UNAVAILABLE_ERROR,
  MIN_ONBOARDING_SOURCE_PHOTOS,
  assertMinimumOnboardingPhotoEvidence,
  countValidOnboardingPhotoFiles,
  onboardingPhotoStoragePrefix,
  type StoredOnboardingPhotoFile,
} from "./onboardingPhotoRequirement";

function validPhoto(
  userId: string,
  name: string,
  overrides: Partial<{
    size: number | string;
    contentType: string;
    ownerUid: string;
    uploadKind: string;
  }> = {},
): StoredOnboardingPhotoFile {
  return {
    name: `${onboardingPhotoStoragePrefix(userId)}${name}`,
    metadata: {
      size: overrides.size ?? 2048,
      contentType: overrides.contentType ?? "image/jpeg",
      metadata: {
        ownerUid: overrides.ownerUid ?? userId,
        uploadKind: overrides.uploadKind ?? "onboarding_profile_photo",
      },
    },
  };
}

function fakeBucket(files: StoredOnboardingPhotoFile[]) {
  const prefixes: string[] = [];
  return {
    prefixes,
    async getFiles(options: { prefix: string }) {
      prefixes.push(options.prefix);
      return [files] as [StoredOnboardingPhotoFile[]];
    },
  };
}

test("minimum onboarding photo requirement is two", () => {
  assert.equal(MIN_ONBOARDING_SOURCE_PHOTOS, 2);
});

test("counts only server-stamped, non-empty image objects", () => {
  const uid = "user_a";
  const files: StoredOnboardingPhotoFile[] = [
    validPhoto(uid, "p1.jpg"),
    validPhoto(uid, "p2.jpg"),
    validPhoto(uid, "empty.jpg", { size: 0 }),
    validPhoto(uid, "text.txt", { contentType: "text/plain" }),
    validPhoto(uid, "foreign.jpg", { ownerUid: "user_b" }),
    validPhoto(uid, "other-kind.jpg", { uploadKind: "chat_profile_photo" }),
    { name: `${onboardingPhotoStoragePrefix(uid)}no-metadata.jpg` },
  ];

  assert.equal(countValidOnboardingPhotoFiles(files, uid), 2);
});

test("zero and one valid photo refuse generation admission", async () => {
  const uid = "user_a";
  for (const files of [[], [validPhoto(uid, "p1.jpg")]]) {
    await assert.rejects(
      assertMinimumOnboardingPhotoEvidence({
        userId: uid,
        bucket: fakeBucket(files),
      }),
      (error: unknown) => {
        assert.ok(error instanceof HttpsError);
        assert.equal(error.code, "failed-precondition");
        assert.equal(error.message, AVATAR_MINIMUM_PHOTOS_ERROR);
        return true;
      },
    );
  }
});

test("client-side claims cannot satisfy the requirement without objects", async () => {
  // A client claiming photoCount=2 while only one real object exists must
  // still be refused: the server derives the count from storage alone.
  const uid = "user_a";
  const bucket = fakeBucket([validPhoto(uid, "only-one.jpg")]);

  await assert.rejects(
    assertMinimumOnboardingPhotoEvidence({ userId: uid, bucket }),
    (error: unknown) => {
      assert.ok(error instanceof HttpsError);
      assert.equal(error.code, "failed-precondition");
      return true;
    },
  );
  assert.deepEqual(bucket.prefixes, [onboardingPhotoStoragePrefix(uid)]);
});

test("two valid photos admit generation", async () => {
  const uid = "user_a";
  await assertMinimumOnboardingPhotoEvidence({
    userId: uid,
    bucket: fakeBucket([validPhoto(uid, "p1.jpg"), validPhoto(uid, "p2.jpg")]),
  });
});

test("evidence read failure fails closed, not open", async () => {
  await assert.rejects(
    assertMinimumOnboardingPhotoEvidence({
      userId: "user_a",
      bucket: {
        async getFiles() {
          throw new Error("storage unavailable");
        },
      },
    }),
    (error: unknown) => {
      assert.ok(error instanceof HttpsError);
      assert.equal(error.code, "internal");
      assert.equal(error.message, AVATAR_PHOTO_EVIDENCE_UNAVAILABLE_ERROR);
      return true;
    },
  );
});
