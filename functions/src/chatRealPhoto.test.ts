import assert from "node:assert/strict";
import test from "node:test";

import {
  evaluateChatRealPhotoAccess,
  resolveSafeApprovedAvatarUrl,
} from "./chatRealPhoto";

const activeRoom = {
  status: "active",
  participantIds: ["u1", "u2"],
};

const approvedUser = {
  avatar: {
    status: "approved",
    approvedAvatarUrl: "https://cdn.example/avatar.png",
  },
};

const consentedPrivateMedia = {
  photoConsent: {
    chatPartnerRealPhotoDisclosure: true,
    profileDisplayOriginalPhoto: false,
  },
  chatRealPhoto: {
    enabled: true,
    storageBucket: "seolleyeon-final-chat-profile-photos",
    storagePath: "users/u2/chat-profile/src_abc.jpg",
  },
};

test("approved avatar resolver rejects signed or private fallbacks", () => {
  assert.equal(
    resolveSafeApprovedAvatarUrl({
      avatar: {
        status: "approved",
        approvedAvatarUrl: "https://cdn.example/avatar.png?X-Goog-Signature=secret",
      },
      onboarding: {
        avatarUrls: ["https://cdn.example/fallback.png"],
      },
    }),
    "https://cdn.example/fallback.png"
  );

  assert.equal(
    resolveSafeApprovedAvatarUrl({
      onboarding: {
        avatarUrls: ["gs://seolleyeon-final-private-source-photos/users/u/source/src.jpg"],
      },
    }),
    ""
  );

  assert.equal(
    resolveSafeApprovedAvatarUrl({
      avatar: {
        status: "approved",
        approvedAvatarUrl:
          "https://seolleyeon-final-avatar-temp.storage.googleapis.com/users/u/candidates/cand.png",
      },
    }),
    ""
  );

  assert.equal(
    resolveSafeApprovedAvatarUrl({
      onboarding: {
        avatarUrls: [
          "https://firebasestorage.googleapis.com/v0/b/public/o/users%2Fu%2Fsource%2Fsrc.jpg?alt=media",
        ],
      },
    }),
    ""
  );
});

test("approved avatar resolver rejects Festival private-media buckets", () => {
  for (const url of [
    "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",
    "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png",
    "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg?token=secret",
  ]) {
    assert.equal(
      resolveSafeApprovedAvatarUrl({
        avatar: { status: "approved", approvedAvatarUrl: url },
      }),
      "",
      url
    );
  }
});

test("a text message plus valid chat participants and consent can use chat-profile photo asset", () => {
  const decision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  });

  assert.equal(decision.kind, "real_photo");
  if (decision.kind === "real_photo") {
    assert.equal(decision.storageBucket, "seolleyeon-final-chat-profile-photos");
    assert.equal(decision.storagePath, "users/u2/chat-profile/src_abc.jpg");
    assert.equal(decision.approvedAvatarUrl, "https://cdn.example/avatar.png");
  }
});

test("participants without a text message receive only the approved avatar", () => {
  const decision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: false,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  });

  assert.deepEqual(decision, {
    kind: "fallback",
    reason: "no_text_message",
    approvedAvatarUrl: "https://cdn.example/avatar.png",
  });
});

test("non-participants are denied", () => {
  const decision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u3",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  });

  assert.deepEqual(decision, {
    kind: "deny",
    code: "permission-denied",
    message: "requester is not a chat participant.",
  });
});

test("missing consent falls back to approved avatar", () => {
  const decision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: {
      photoConsent: { chatPartnerRealPhotoDisclosure: false },
      chatRealPhoto: consentedPrivateMedia.chatRealPhoto,
    },
  });

  assert.deepEqual(decision, {
    kind: "fallback",
    reason: "no_chat_real_photo_consent",
    approvedAvatarUrl: "https://cdn.example/avatar.png",
  });
});

test("private source bucket asset is never accepted for chat real photo", () => {
  const decision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: {
      photoConsent: { chatPartnerRealPhotoDisclosure: true },
      chatRealPhoto: {
        enabled: true,
        storageBucket: "seolleyeon-final-private-source-photos",
        storagePath: "users/u2/source/src_abc.jpg",
      },
    },
  });

  assert.deepEqual(decision, {
    kind: "fallback",
    reason: "invalid_chat_real_photo_asset",
    approvedAvatarUrl: "https://cdn.example/avatar.png",
  });
});

test("blocked or inactive chats are denied", () => {
  const blockedDecision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: true,
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  });
  assert.equal(blockedDecision.kind, "deny");

  const inactiveDecision = evaluateChatRealPhotoAccess({
    roomExists: true,
    roomData: { status: "deleted", participantIds: ["u1", "u2"] },
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    blockedBetweenParticipants: false,
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  });
  assert.equal(inactiveDecision.kind, "deny");
});

test("a block denies even when every other condition for a real photo holds", () => {
  const open = {
    roomExists: true,
    roomData: activeRoom,
    hasTextMessage: true,
    requesterUid: "u1",
    targetUid: "u2",
    targetUserData: approvedUser,
    privateMediaData: consentedPrivateMedia,
  };
  assert.equal(
    evaluateChatRealPhotoAccess({ ...open, blockedBetweenParticipants: false }).kind,
    "real_photo"
  );
  const blocked = evaluateChatRealPhotoAccess({ ...open, blockedBetweenParticipants: true });
  assert.equal(blocked.kind, "deny");
  // The legacy user-document fields are not a block source: nothing writes them.
  assert.equal(
    evaluateChatRealPhotoAccess({
      ...open,
      blockedBetweenParticipants: false,
      targetUserData: { ...approvedUser, blockedUserIds: ["u1"] },
    }).kind,
    "real_photo"
  );
});

test("moderated or withdrawn targets never get their real photo served", () => {
  for (const state of [
    { status: "banned" },
    { status: "suspended" },
    { status: "withdrawn" },
    { status: "restricted_rejoin" },
    { isActive: false },
    { isWithdrawn: true },
    { isDeleted: true },
  ]) {
    const decision = evaluateChatRealPhotoAccess({
      roomExists: true,
      roomData: activeRoom,
      hasTextMessage: true,
      requesterUid: "u1",
      targetUid: "u2",
      blockedBetweenParticipants: false,
      targetUserData: { ...approvedUser, ...state },
      privateMediaData: consentedPrivateMedia,
    });
    assert.equal(decision.kind, "fallback", JSON.stringify(state));
    assert.equal(
      decision.kind === "fallback" ? decision.reason : "",
      "target_inactive",
      JSON.stringify(state)
    );
  }
});
