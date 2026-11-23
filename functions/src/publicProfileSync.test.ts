import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPublicProfileFromUser,
  publicProfileProjectionChanged,
  syncPublicProfileForUser,
} from "./publicProfileSync";

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
    initialSetupComplete: true,
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
  assert.equal(publicProfile.initialSetupComplete, true);
  assert.equal(publicProfile.isProfileComplete, true);
  assert.equal(publicProfile.schemaVersion, 2);
  assert.equal(publicProfile.recommendationPrivacyReady, false);
  assert.equal(publicProfile.profileVisible, true);
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

test("public profile exposes only the recommendation readiness gate", () => {
  const publicProfile = buildPublicProfileFromUser("u1", {
    nickname: "pending",
    recommendationPrivacyReady: false,
    kakaoFriendAvoidanceEnabled: true,
    kakaoFriendReconcileStatus: "syncing",
  });

  assert.ok(publicProfile);
  assert.equal(publicProfile.recommendationPrivacyReady, false);
  assert.equal(publicProfile.kakaoFriendAvoidanceEnabled, undefined);
  assert.equal(publicProfile.kakaoFriendReconcileStatus, undefined);
});

test("withdrawn users produce no public profile, while a pending visibility change keeps today's card renderable", () => {
  assert.equal(
    buildPublicProfileFromUser("operations", {
      accountType: "operations",
      status: "active",
      nickname: "운영팀",
    }),
    null,
  );
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "withdrawn",
      isWithdrawn: true,
      nickname: "gone",
    }),
    null,
  );
  const pendingHide = buildPublicProfileFromUser("u1", {
      status: "active",
      profileVisible: false,
      profileVisibleEffectiveDateKey: "20260902",
      profileVisibleBeforeEffectiveDate: true,
      nickname: "hidden-tomorrow",
    });
  assert.ok(pendingHide);
  assert.equal(pendingHide.profileVisible, false);
  assert.equal(pendingHide.profileVisibleBeforeEffectiveDate, true);
  assert.equal(pendingHide.profileVisibleEffectiveDateKey, "20260902");
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "banned",
      nickname: "banned",
    }),
    null,
  );
  for (const status of [
    "blocked",
    "deleted",
    "restricted_rejoin",
    "suspended",
  ]) {
    assert.equal(
      buildPublicProfileFromUser("u1", { status, nickname: status }),
      null,
    );
  }
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "active",
      isDeleted: true,
      nickname: "deleted-flag",
    }),
    null,
  );
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "active",
      isSuspended: true,
      nickname: "suspended-flag",
    }),
    null,
  );
  assert.equal(
    buildPublicProfileFromUser("u1", {
      status: "active",
      isActive: false,
      nickname: "inactive-flag",
    }),
    null,
  );
});

test("public profile trigger ignores user writes outside the public projection", () => {
  const before = {
    nickname: "same",
    status: "active",
    profileVisible: true,
    updatedAt: "old",
    privateCounter: 1,
  };
  const after = { ...before, updatedAt: "new", privateCounter: 2 };

  assert.equal(
    publicProfileProjectionChanged("u1", before, after),
    false,
  );
  assert.equal(
    publicProfileProjectionChanged("u1", before, { ...after, nickname: "changed" }),
    true,
  );
});

test("public profile sync does not rewrite an identical destination document", async () => {
  const userData = {
    nickname: "same",
    status: "active",
    profileVisible: true,
  };
  const existing = buildPublicProfileFromUser("u1", userData);
  let setCalls = 0;
  let deleteCalls = 0;
  const ref = {
    async get() {
      return { exists: true, data: () => ({ ...existing, updatedAt: "old" }) };
    },
    async set() {
      setCalls += 1;
    },
    async delete() {
      deleteCalls += 1;
    },
  };
  const firestore = {
    collection() {
      return { doc: () => ref };
    },
  } as never;

  const result = await syncPublicProfileForUser(firestore, "u1", userData);

  assert.equal(result, "unchanged");
  assert.equal(setCalls, 0);
  assert.equal(deleteCalls, 0);
});

test("public profile carries campusLifeZones for the recommendation serving guard", () => {
  // 클라이언트는 타인 문서를 publicProfiles 로만 읽는다. 이 필드가 빠지면
  // 생활권 serving guard 가 모든 후보를 fail-closed 로 제외해 1:1 피드가
  // 전원 빈 상태가 된다 (production 장애).
  const payload = buildPublicProfileFromUser("u1", {
    nickname: "nick",
    onboarding: {
      nickname: "nick",
      department: "언더우드국제대학",
      campusLifeZones: ["sinchon", "songdo"],
    },
  });
  assert.ok(payload != null);
  const onboarding = payload?.onboarding as Record<string, unknown>;
  assert.deepEqual(onboarding.campusLifeZones, ["sinchon", "songdo"]);
});

test("public profile omits campusLifeZones when the user has none", () => {
  const payload = buildPublicProfileFromUser("u2", {
    nickname: "nick",
    onboarding: { nickname: "nick", department: "" },
  });
  assert.ok(payload != null);
  const onboarding = payload?.onboarding as Record<string, unknown> | undefined;
  assert.equal(onboarding?.campusLifeZones, undefined);
});

// ---------------------------------------------------------------------------
// B-07 — the public image is server-approved data only
// ---------------------------------------------------------------------------

const B07_APPROVED =
  "https://firebasestorage.googleapis.com/v0/b/seolleyeon-final-approved-avatars/o/users%2Fu1%2Favatar%2Fa.png?alt=media&token=t";

function publicImageValues(profile: Record<string, unknown> | null): string[] {
  assert.ok(profile);
  const onboarding = (profile.onboarding ?? {}) as Record<string, unknown>;
  const avatar = (profile.avatar ?? {}) as Record<string, unknown>;
  return [
    profile.profileImageUrl,
    onboarding.representativeImageUrl,
    ...((onboarding.photoUrls as unknown[]) ?? []),
    ...((onboarding.avatarUrls as unknown[]) ?? []),
    avatar.approvedAvatarUrl,
  ].filter((value): value is string => typeof value === "string");
}

test("B-07: an arbitrary external representativeImageUrl never reaches the public profile", () => {
  for (const planted of [
    "https://attacker.example/track.png?victim=1",
    "http://203.0.113.7/pixel.gif",
    "https://storage.googleapis.com/attacker-bucket/users/u1/avatar/a.png",
    "https://firebasestorage.googleapis.com/v0/b/attacker.appspot.com/o/a.png?alt=media",
  ]) {
    // With an approved avatar: the avatar is public, the planted URL is not.
    const withAvatar = buildPublicProfileFromUser("u1", {
      nickname: "n",
      avatar: { status: "approved", approvedAvatarUrl: B07_APPROVED },
      onboarding: { nickname: "n", avatarUrls: [B07_APPROVED], representativeImageUrl: planted },
    });
    assert.deepEqual([...new Set(publicImageValues(withAvatar))], [B07_APPROVED]);
    // Without any server-written image: nothing is public at all.
    const without = buildPublicProfileFromUser("u1", {
      nickname: "n",
      onboarding: { nickname: "n", representativeImageUrl: planted },
    });
    assert.deepEqual(publicImageValues(without), []);
    assert.equal(JSON.stringify(without).includes(planted), false);
  }
});

test("B-07: an unapproved storage path never reaches the public profile", () => {
  for (const planted of [
    // Approved-avatar bucket, but another user's object / not the approved one.
    "https://firebasestorage.googleapis.com/v0/b/seolleyeon-final-approved-avatars/o/users%2Fother%2Favatar%2Fz.png?alt=media&token=t",
    // Candidate / job previews and private sources.
    "https://storage.googleapis.com/seolleyeon-final-avatar-temp/users/u1/jobs/j/candidates/c.png",
    "https://storage.googleapis.com/seolleyeon-final-private-source-photos/users/u1/source/a.jpg",
    "gs://seolleyeon-final-approved-avatars/users/u1/avatar/a.png",
  ]) {
    const profile = buildPublicProfileFromUser("u1", {
      nickname: "n",
      avatar: { status: "approved", approvedAvatarUrl: B07_APPROVED },
      onboarding: { nickname: "n", avatarUrls: [B07_APPROVED], representativeImageUrl: planted },
    });
    assert.equal(JSON.stringify(profile).includes(planted), false);
    assert.deepEqual([...new Set(publicImageValues(profile))], [B07_APPROVED]);
  }
  // An avatar that is not approved yet is not public either, and neither is
  // a representative URL that repeats it.
  const pending = buildPublicProfileFromUser("u1", {
    nickname: "n",
    avatar: { status: "approval_copying", approvedAvatarUrl: B07_APPROVED },
    onboarding: { nickname: "n", representativeImageUrl: B07_APPROVED },
  });
  assert.deepEqual(publicImageValues(pending), []);
});

test("B-07: the approved avatar is public, including a representative URL that repeats it", () => {
  const profile = buildPublicProfileFromUser("u1", {
    nickname: "n",
    profileImageMode: "avatar",
    avatar: { status: "approved", approvedAvatarUrl: B07_APPROVED, approvedAvatarStoragePath: "gs://x/y" },
    onboarding: { nickname: "n", avatarUrls: [B07_APPROVED], representativeImageUrl: B07_APPROVED },
  });
  assert.ok(profile);
  assert.equal(profile.profileImageUrl, B07_APPROVED);
  assert.deepEqual(profile.avatar, { status: "approved", approvedAvatarUrl: B07_APPROVED });
  const onboarding = profile.onboarding as Record<string, unknown>;
  assert.deepEqual(onboarding.avatarUrls, [B07_APPROVED]);
  assert.equal(onboarding.representativeImageUrl, B07_APPROVED);
});

test("B-07: a legacy user without an approved avatar keeps the existing server-written fallback", () => {
  const legacy = "https://k.kakaocdn.net/dn/legacy/profile.jpg";
  const legacyPhoto = "https://cdn.example/legacy-photo.png";
  const profile = buildPublicProfileFromUser("u1", {
    nickname: "legacy",
    profileImageUrl: legacy,
    onboarding: {
      nickname: "legacy",
      photoUrls: [legacyPhoto],
      representativeImageUrl: legacyPhoto,
    },
  });
  assert.ok(profile);
  assert.equal(profile.profileImageUrl, legacy);
  assert.equal(profile.avatar, null);
  const onboarding = profile.onboarding as Record<string, unknown>;
  assert.deepEqual(onboarding.photoUrls, [legacyPhoto]);
  assert.equal(onboarding.representativeImageUrl, legacyPhoto);
  // Fallback order without a top-level picture: avatarUrls, then photoUrls.
  const listOnly = buildPublicProfileFromUser("u1", {
    nickname: "legacy",
    onboarding: { nickname: "legacy", photoUrls: [legacyPhoto] },
  });
  assert.equal(listOnly?.profileImageUrl, legacyPhoto);
  // No image at all stays null (unchanged behaviour).
  assert.equal(buildPublicProfileFromUser("u1", { nickname: "none" })?.profileImageUrl, null);
});

test("B-07: planting or changing a representative URL does not change the projection (no sync write)", () => {
  const base = {
    nickname: "n",
    avatar: { status: "approved", approvedAvatarUrl: B07_APPROVED },
    onboarding: { nickname: "n", avatarUrls: [B07_APPROVED] },
  };
  const planted = {
    ...base,
    onboarding: { ...base.onboarding, representativeImageUrl: "https://attacker.example/track.png" },
  };
  assert.equal(publicProfileProjectionChanged("u1", base, planted), false);
});
