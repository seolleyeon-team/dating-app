/**
 * B-07 — the picture other members see is server-owned.
 *
 * users/{uid}.onboarding.representativeImageUrl and .profileImageUrl are read
 * by the server as a member's image (public profile projection, chat
 * participantInfo, friend snapshots) but were missing from the protected
 * onboarding keys, so a modified client could point them at any host.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  seedActiveUser,
  withClearedDb,
} from "./helpers.mjs";

import { deleteField, doc, getDoc, serverTimestamp, setDoc, updateDoc } from "firebase/firestore";

const USER = "kakao_user";
const NEW_USER = "kakao_new_user";
const APPROVED =
  "https://firebasestorage.googleapis.com/v0/b/seolleyeon-final-approved-avatars/o/users%2Fkakao_user%2Favatar%2Fa.png?alt=media&token=t";

async function seed(db) {
  await seedActiveUser(db, USER, {
    isStudentVerified: true,
    nickname: "user",
    onboarding: { nickname: "user", mbti: "INFP", avatarUrls: [APPROVED] },
    avatar: { status: "approved", approvedAvatarUrl: APPROVED },
    profileImageUrl: APPROVED,
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

for (const field of ["representativeImageUrl", "profileImageUrl"]) {
  test(`B-07: a client cannot plant an external URL in onboarding.${field}`, async () => {
    await withClearedDb(seed);
    const db = await kakaoSession(USER);
    await assertFails(updateDoc(doc(db, "users", USER), {
      [`onboarding.${field}`]: "https://attacker.example/track.png?victim=1",
    }));
    // Not even the approved avatar URL, a storage path or an empty value:
    // the field is server-owned, exactly like avatarUrls / photoUrls.
    await assertFails(updateDoc(doc(db, "users", USER), { [`onboarding.${field}`]: APPROVED }));
    await assertFails(updateDoc(doc(db, "users", USER), {
      [`onboarding.${field}`]: "gs://seolleyeon-final-approved-avatars/users/other/avatar/x.png",
    }));
    await assertFails(updateDoc(doc(db, "users", USER), { [`onboarding.${field}`]: "" }));
    // Smuggled next to a legitimate onboarding edit.
    await assertFails(updateDoc(doc(db, "users", USER), {
      "onboarding.mbti": "ENTP",
      [`onboarding.${field}`]: "https://attacker.example/a.png",
      onboardingUpdatedAt: serverTimestamp(),
    }));
    // Whole-map replacement carrying the field.
    await assertFails(updateDoc(doc(db, "users", USER), {
      onboarding: { nickname: "user", mbti: "INFP", avatarUrls: [APPROVED], [field]: "https://attacker.example/a.png" },
    }));
  });

  test(`B-07: a client cannot rewrite or remove a server-written onboarding.${field}`, async () => {
    await withClearedDb(async (db) => {
      await seed(db);
      await setDoc(doc(db, "users", USER), { onboarding: { [field]: APPROVED } }, { merge: true });
    });
    const db = await kakaoSession(USER);
    await assertFails(updateDoc(doc(db, "users", USER), {
      [`onboarding.${field}`]: "https://attacker.example/a.png",
    }));
    await assertFails(updateDoc(doc(db, "users", USER), { [`onboarding.${field}`]: deleteField() }));
    // Ordinary edits around it keep working.
    await assertSucceeds(updateDoc(doc(db, "users", USER), {
      "onboarding.mbti": "ENTP",
      onboardingUpdatedAt: serverTimestamp(),
    }));
    const after = await assertSucceeds(getDoc(doc(db, "users", USER)));
    assert.equal(after.data().onboarding[field], APPROVED);
  });

  test(`B-07: a client-created user shell cannot carry onboarding.${field}`, async () => {
    await withClearedDb(seed);
    const db = await kakaoSession(NEW_USER);
    await assertFails(setDoc(doc(db, "users", NEW_USER), {
      kakaoUserId: NEW_USER,
      nickname: "new",
      onboarding: { nickname: "new", [field]: "https://attacker.example/a.png" },
    }));
    await assertSucceeds(setDoc(doc(db, "users", NEW_USER), {
      kakaoUserId: NEW_USER,
      nickname: "new",
      onboarding: { nickname: "new" },
    }));
  });
}

test("B-07: the real onboarding step writes are unaffected (field-path updates of allow-listed keys)", async () => {
  await withClearedDb(seed);
  const db = await kakaoSession(USER);
  // user_service.dart saveOnboardingBasicInfo / Interests / Keywords / ProfileQa
  await assertSucceeds(updateDoc(doc(db, "users", USER), {
    "onboarding.gender": "female",
    "onboarding.height": 165,
    "onboarding.mbti": "ENFP",
    "onboarding.department": "컴퓨터과학과",
    "onboarding.campusLifeZones": ["sinchon"],
    "onboarding.campusLifeZoneLabels": ["신촌"],
    onboardingUpdatedAt: serverTimestamp(),
  }));
  await assertSucceeds(updateDoc(doc(db, "users", USER), {
    "onboarding.interests": ["music"],
    onboardingUpdatedAt: serverTimestamp(),
  }));
  await assertSucceeds(updateDoc(doc(db, "users", USER), {
    "onboarding.profileQa": [{ question: "q", answer: "a" }],
    onboardingUpdatedAt: serverTimestamp(),
  }));
  // The top-level picture and the approved avatar stay server-owned too.
  await assertFails(updateDoc(doc(db, "users", USER), { profileImageUrl: "https://attacker.example/a.png" }));
  await assertFails(updateDoc(doc(db, "users", USER), { "avatar.approvedAvatarUrl": "https://attacker.example/a.png" }));
  await assertFails(updateDoc(doc(db, "users", USER), { "onboarding.avatarUrls": ["https://attacker.example/a.png"] }));
  await assertFails(updateDoc(doc(db, "users", USER), { "onboarding.photoUrls": ["https://attacker.example/a.png"] }));
});
