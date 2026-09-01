import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { doc, setDoc, updateDoc } from "firebase/firestore";

// ---------------------------------------------------------------------------
// Onboarding photo/avatar server-evidence fields must be server-only.
//
// The resume router and avatar flow read onboarding.sourcePhotoUploadCount,
// sourcePhotoUploadStatus, avatarGenerationJobId, avatarSourceSelectionVersion
// from users/{uid}. Only Cloud Functions (Admin SDK) may write them — a client
// forging them could spoof photo-step progress or attach itself to another
// generation job.
// ---------------------------------------------------------------------------

const USER = "kakao_photo_user_1";

function verifiedUserDoc(uid) {
  return {
    kakaoUserId: uid,
    isStudentVerified: true,
    studentEmail: "student@yonsei.ac.kr",
    nickname: "테스트",
    onboarding: { nickname: "테스트", birthYear: "2003", major: "컴퓨터과학" },
  };
}

async function seedUser() {
  return withClearedDb(async (db) => {
    await setDoc(doc(db, "users", USER), verifiedUserDoc(USER));
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

const FORGED_FIELDS = [
  ["sourcePhotoUploadCount", 2],
  ["sourcePhotoUploadStatus", "uploaded"],
  ["sourcePhotoLastQueuedAt", "2026-08-30T00:00:00Z"],
  ["avatarGenerationJobId", "avatar_job_forged_000000001"],
  ["avatarSourceSelectionVersion", 7],
];

for (const [field, value] of FORGED_FIELDS) {
  test(`client cannot forge onboarding.${field} on update`, async () => {
    await seedUser();
    const db = await kakaoSession(USER);

    await assertFails(
      updateDoc(doc(db, "users", USER), { [`onboarding.${field}`]: value })
    );
  });
}

test("client cannot seed forged photo-evidence fields on create", async () => {
  await withClearedDb();
  const db = await kakaoSession(USER);

  await assertFails(
    setDoc(doc(db, "users", USER), {
      ...verifiedUserDoc(USER),
      isStudentVerified: false,
      onboarding: {
        nickname: "테스트",
        sourcePhotoUploadCount: 2,
        sourcePhotoUploadStatus: "uploaded",
      },
    })
  );
});

test("ordinary onboarding updates still succeed with the guard in place", async () => {
  await seedUser();
  const db = await kakaoSession(USER);

  await assertSucceeds(
    updateDoc(doc(db, "users", USER), {
      "onboarding.selfIntroduction": "안녕하세요",
    })
  );
});
