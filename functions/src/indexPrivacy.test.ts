import assert from "node:assert/strict";
import test from "node:test";

import {
  buildKakaoUserShell,
  readSafePhotoUrl,
  verifiedYonseiEmailFromAuthToken,
} from "./index";

test("backend display resolver rejects unsafe approved avatar and onboarding fallback", () => {
  const unsafeApproved = readSafePhotoUrl({
    avatar: {
      status: "approved",
      approvedAvatarUrl:
        "https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/jobs/j/c.png?x-goog-signature=secret",
    },
    onboarding: {
      avatarUrls: [
        "https://storage.googleapis.com/public-bucket/users/u/source/src.jpg?X-Amz-Signature=secret",
        "https://cdn.example/safe-but-not-first.png",
      ],
    },
  });

  assert.equal(unsafeApproved, null);
});

test("backend display resolver rejects final private/temp buckets and encoded source paths", () => {
  for (const approvedAvatarUrl of [
    "https://storage.googleapis.com/seolleyeon-final-avatar-temp/users/u/jobs/j/c.png",
    "https://seolleyeon-final-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",
    "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",
    "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/c.png",
    "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat-profile/p.jpg",
    "https://firebasestorage.googleapis.com/v0/b/public/o/users%2Fu%2Fsource%2Fsrc.jpg?alt=media",
    "https://cdn.example/users%2Fu%2Fcandidates%2Fcand.png",
  ]) {
    assert.equal(
      readSafePhotoUrl({
        avatar: { status: "approved", approvedAvatarUrl },
      }),
      null,
      approvedAvatarUrl
    );
  }
});

test("backend display resolver allows safe approved avatar before safe onboarding fallback", () => {
  const resolved = readSafePhotoUrl({
    avatar: {
      status: "approved",
      approvedAvatarUrl: "https://cdn.example/avatar.png",
    },
    onboarding: {
      avatarUrls: ["https://cdn.example/fallback.png"],
    },
  });

  assert.equal(resolved, "https://cdn.example/avatar.png");
});

test("email fallback requires verified Yonsei auth email", () => {
  assert.equal(
    verifiedYonseiEmailFromAuthToken({
      email: "student@yonsei.ac.kr",
      email_verified: false,
    }),
    null
  );
  assert.equal(
    verifiedYonseiEmailFromAuthToken({
      email: "student@yonsei.ac.kr",
      email_verified: true,
    }),
    "student@yonsei.ac.kr"
  );
});

test("Kakao custom token bootstrap creates only a minimal user shell", () => {
  const shell = buildKakaoUserShell("4705828086");

  assert.equal(shell.kakaoUserId, "4705828086");
  assert.equal(shell.profileImageUrl, "");
  assert.equal(shell.profileImageMode, "avatar");
  assert.ok(Object.prototype.hasOwnProperty.call(shell, "createdAt"));
  assert.ok(Object.prototype.hasOwnProperty.call(shell, "lastLoginAt"));
  assert.deepEqual(Object.keys(shell).sort(), [
    "createdAt",
    "kakaoUserId",
    "lastLoginAt",
    "profileImageMode",
    "profileImageUrl",
  ]);
});
