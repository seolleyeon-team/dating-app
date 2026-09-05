import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

/**
 * RULES contract for the canonical source-set admission (section 19).
 *
 *   - selection fields are server-owned: the client can never write or forge
 *     the generation lock, the selected source, or the job pointer
 *   - private source material is never client-readable
 *
 * Static assertions over firestore.rules / storage.rules, same style as
 * firestoreRules.test.ts.
 */

const rules = readFileSync(resolve(__dirname, "../../firestore.rules"), "utf8");
const compactRules = rules.replace(/\s+/g, " ");
const storageRules = readFileSync(resolve(__dirname, "../../storage.rules"), "utf8");
const compactStorage = storageRules.replace(/\s+/g, " ");

function assertContains(source: string, description: string, expected: string): void {
  assert.ok(source.includes(expected), description);
}

test("selection state, job pointers and candidates are server-only collections", () => {
  assertContains(
    compactRules,
    "userPrivateMedia (currentAvatarJobId, currentAvatarSourcePhotoId, avatarSourceSelection, sourcePhotos) must deny every client op",
    "match /userPrivateMedia/{userId} { allow read, write: if false; }",
  );
  assertContains(
    compactRules,
    "avatarJobs (selectedSource, sourceSelection, generationClaim) must deny every client op",
    "match /avatarJobs/{jobId} { allow read, write: if false; }",
  );
  assertContains(
    compactRules,
    "avatarCandidates must deny every client op",
    "match /avatarCandidates/{candidateId} { allow read, write: if false; }",
  );
});

test("the client can never forge the generation lock on users/{uid}", () => {
  // `avatar` (status, sourcePhotoId, sourceJobId, generationReplacementCount,
  // replacedByClientRequestId, ...) must not appear in any users allowlist.
  const usersBlockStart = compactRules.indexOf("match /users/{kakaoUserId} {");
  assert.ok(usersBlockStart > 0, "users block must exist");
  const nextTopLevel = compactRules.indexOf("match /", usersBlockStart + 30);
  const usersBlock = compactRules.slice(usersBlockStart, nextTopLevel > 0 ? nextTopLevel : undefined);
  assert.ok(
    !/hasOnly\(\[[^\]]*'avatar'[^\]]*\]\)/.test(usersBlock),
    "'avatar' must not be in any users create/update allowlist",
  );

  // Onboarding pointers that the server writes must be immutable from the client.
  for (const field of [
    "avatarGenerationJobId",
    "avatarSourceSelectionVersion",
    "sourcePhotoUploadStatus",
    "sourcePhotoUploadCount",
    "sourcePhotoLastQueuedAt",
    "sourcePhotos",
    "sourcePhotoIds",
    "sourcePhotoRefs",
  ]) {
    const guard = compactRules.slice(
      compactRules.indexOf("function onboardingAvatarPhotoFieldsUnchanged()"),
    );
    assert.ok(guard.includes(`'${field}'`), `${field} must be in onboardingAvatarPhotoFieldsUnchanged`);
  }
  assertContains(
    compactRules,
    "every users update must pass the onboarding avatar-field guard",
    "allow update: if onboardingAvatarPhotoFieldsUnchanged() && (",
  );
});

test("private source photos and candidate scratch objects are never client-readable", () => {
  for (const marker of ["/source/", "/onboarding/photos/", "/candidates/"]) {
    assert.ok(
      compactStorage.includes(marker),
      `storage.rules must address ${marker}`,
    );
  }
  assertContains(
    compactStorage,
    "avatar temp objects must stay client-denied",
    "match /avatar_temp/{userId}/{allPaths=**} { allow read, write: if false; }",
  );
});
