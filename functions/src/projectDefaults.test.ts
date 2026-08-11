import assert from "node:assert/strict";
import test from "node:test";

import { buildApprovedAvatarStoragePath } from "./avatarApproval";
import { isUidBoundCleanupRef } from "./avatarCleanup";
import { chatProfilePhotoBucket } from "./avatarMedia";

function withClearedMediaEnv<T>(callback: () => T): T {
  const names = [
    "SOURCE_PHOTO_BUCKET",
    "AVATAR_TEMP_BUCKET",
    "APPROVED_AVATAR_BUCKET",
    "CHAT_PROFILE_PHOTO_BUCKET",
  ];
  const previous = new Map<string, string | undefined>();
  for (const name of names) {
    previous.set(name, process.env[name]);
    delete process.env[name];
  }

  try {
    return callback();
  } finally {
    for (const name of names) {
      const value = previous.get(name);
      if (value === undefined) {
        delete process.env[name];
      } else {
        process.env[name] = value;
      }
    }
  }
}

test("runtime media defaults target seolleyeon-final buckets", () => {
  withClearedMediaEnv(() => {
    assert.equal(
      chatProfilePhotoBucket(),
      "seolleyeon-final-chat-profile-photos",
    );
    assert.equal(
      buildApprovedAvatarStoragePath("u1", "avatar_1"),
      "gs://seolleyeon-final-approved-avatars/users/u1/avatar/avatar_1.png",
    );
    assert.equal(
      isUidBoundCleanupRef(
        {
          bucket: "seolleyeon-final-private-source-photos",
          path: "users/u1/source/photo.jpg",
        },
        "u1",
      ),
      true,
    );
  });
});
