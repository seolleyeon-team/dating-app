import assert from "node:assert/strict";
import test from "node:test";

import { buildPublicProfileFromUser } from "./publicProfileSync";

test("public profile omits private PII and moderation internals", () => {
  const publicProfile = buildPublicProfileFromUser("u1", {
    nickname: "공개닉",
    email: "secret@example.com",
    studentEmail: "student@yonsei.ac.kr",
    preferenceVector: [1, 2, 3],
    privacySettings: { avoidSameDepartment: true },
    legalConsents: { termsOfService: true },
    notificationSettings: { push: true },
    loginDisabled: true,
    withdrawalReason: "x",
    status: "active",
    profileVisible: true,
    isStudentVerified: true,
    profileImageUrl:
      "https://storage.googleapis.com/seolleyeon-avatar-temp/users/u1/jobs/j/c.png?x-goog-signature=secret",
    avatar: {
      status: "approved",
      approvedAvatarUrl: "https://cdn.example/safe-avatar.png",
    },
    onboarding: {
      nickname: "공개닉",
      major: "컴공",
      university: "연세대학교",
      birthYear: "2003",
      bio: "hello",
      photoUrls: [
        "https://cdn.example/safe.png",
        "https://storage.googleapis.com/seolleyeon-final-private-source-photos/users/u1/source/a.jpg",
      ],
    },
  });

  assert.ok(publicProfile);
  assert.equal(publicProfile.nickname, "공개닉");
  assert.equal(publicProfile.isStudentVerified, true);
  assert.equal(publicProfile.profileImageUrl, "https://cdn.example/safe-avatar.png");
  assert.deepEqual(publicProfile.onboarding, {
    nickname: "공개닉",
    major: "컴공",
    university: "연세대학교",
    birthYear: "2003",
    bio: "hello",
    photoUrls: ["https://cdn.example/safe.png"],
  });
  assert.equal(publicProfile.email, undefined);
  assert.equal(publicProfile.studentEmail, undefined);
  assert.equal(publicProfile.preferenceVector, undefined);
  assert.equal(publicProfile.privacySettings, undefined);
  assert.equal(publicProfile.legalConsents, undefined);
  assert.equal(publicProfile.notificationSettings, undefined);
  assert.equal(publicProfile.loginDisabled, undefined);
  assert.equal(publicProfile.withdrawalReason, undefined);
});

test("withdrawn or invisible users produce no public profile", () => {
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "withdrawn",
      isWithdrawn: true,
      nickname: "gone",
    }),
    null,
  );
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "active",
      profileVisible: false,
      nickname: "hidden",
    }),
    null,
  );
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "banned",
      nickname: "banned",
    }),
    null,
  );
});
