import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  withClearedDb,
} from "./helpers.mjs";

import {
  doc,
  getDoc,
  setDoc,
  Timestamp,
  updateDoc,
} from "firebase/firestore";

const REVIEW_FIXTURE_UID = "play-fixture-b-01";
const REVIEW_POST_ID = "recovery-review-post";
const CHAT_ROOM_ID = "recovery-chat-room";
const ACTIVE_CHAT_UID = "recovery-active-chat-user";
const SUSPENDED_CHAT_UID = "recovery-suspended-chat-user";
const INACTIVE_CHAT_UID = "recovery-inactive-chat-user";

async function authenticatedSession(uid, claims = {}) {
  const env = await getTestEnv();
  return env.authenticatedContext(uid, claims).firestore();
}

async function playReviewSession(uid = REVIEW_FIXTURE_UID) {
  return authenticatedSession(uid, {
    appSession: true,
    playReviewer: true,
    dataPartition: "play_review",
  });
}

async function seedReviewPost() {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "playReviewBambooPosts", REVIEW_POST_ID), {
      authorId: REVIEW_FIXTURE_UID,
      dataPartition: "play_review",
      content: "fixture",
      isDeleted: false,
    });
  });
}

async function seedChatRoom(uid, accountFields = {}, { seedUser = true } = {}) {
  await withClearedDb(async (db) => {
    if (seedUser) {
      await setDoc(doc(db, "users", uid), {
        kakaoUserId: uid,
        nickname: "chat user",
        ...accountFields,
      });
    }
    await setDoc(doc(db, "chat_rooms", CHAT_ROOM_ID), {
      participantIds: [uid, "recovery-other-user"],
      type: "one_to_one",
    });
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("LIVE-RECOVERY: approved Play Review fixture can read review data", async () => {
  await seedReviewPost();
  const db = await playReviewSession();

  await assertSucceeds(
    getDoc(doc(db, "playReviewBambooPosts", REVIEW_POST_ID))
  );
});

test("LIVE-RECOVERY: review claims without the fixture identity cannot read review data", async () => {
  await seedReviewPost();
  const db = await authenticatedSession("unapproved-review-user", {
    appSession: true,
    playReviewer: true,
    dataPartition: "play_review",
  });

  await assertFails(
    getDoc(doc(db, "playReviewBambooPosts", REVIEW_POST_ID))
  );
});

test("LIVE-RECOVERY: an active account can read a participant chat room", async () => {
  await seedChatRoom(ACTIVE_CHAT_UID, {
    isActive: true,
    loginDisabled: false,
    status: "active",
  });
  const db = await authenticatedSession(ACTIVE_CHAT_UID);

  await assertSucceeds(getDoc(doc(db, "chat_rooms", CHAT_ROOM_ID)));
});

test("LIVE-RECOVERY: suspended accounts cannot read a participant chat room", async () => {
  await seedChatRoom(SUSPENDED_CHAT_UID, {
    isActive: true,
    loginDisabled: false,
    status: "suspended",
  });
  const db = await authenticatedSession(SUSPENDED_CHAT_UID);

  await assertFails(getDoc(doc(db, "chat_rooms", CHAT_ROOM_ID)));
});

test("LIVE-RECOVERY: inactive accounts cannot read a participant chat room", async () => {
  await seedChatRoom(INACTIVE_CHAT_UID, {
    isActive: false,
    loginDisabled: false,
    status: "active",
  });
  const db = await authenticatedSession(INACTIVE_CHAT_UID);

  await assertFails(getDoc(doc(db, "chat_rooms", CHAT_ROOM_ID)));
});

const ACTIVE_CHAT_ACCOUNT_CASES = [
  {
    label: "active account is allowed",
    uid: "recovery-table-active",
    userFields: { isActive: true, loginDisabled: false, status: "active" },
    expected: "allow",
  },
  {
    label: "missing user document is denied",
    uid: "recovery-table-missing",
    seedUser: false,
    userFields: {},
    expected: "deny",
  },
  {
    label: "loginDisabled account is denied",
    uid: "recovery-table-login-disabled",
    userFields: { isActive: true, loginDisabled: true, status: "active" },
    expected: "deny",
  },
  {
    label: "inactive account is denied",
    uid: "recovery-table-inactive",
    userFields: { isActive: false, loginDisabled: false, status: "active" },
    expected: "deny",
  },
  ...["banned", "blocked", "deleted", "suspended", "withdrawn"].map(
    (status) => ({
      label: `${status} account is denied`,
      uid: `recovery-table-${status}`,
      userFields: { isActive: true, loginDisabled: false, status },
      expected: "deny",
    })
  ),
  {
    label: "missing status defaults to active",
    uid: "recovery-table-default-status",
    userFields: { isActive: true, loginDisabled: false },
    expected: "allow",
  },
];

for (const fixture of ACTIVE_CHAT_ACCOUNT_CASES) {
  test(`LIVE-RECOVERY: hasActiveChatAccount ${fixture.label}`, async () => {
    await seedChatRoom(fixture.uid, fixture.userFields, {
      seedUser: fixture.seedUser !== false,
    });
    const db = await authenticatedSession(fixture.uid);
    const read = getDoc(doc(db, "chat_rooms", CHAT_ROOM_ID));

    if (fixture.expected === "allow") {
      await assertSucceeds(read);
    } else {
      await assertFails(read);
    }
  });
}

test("LIVE-RECOVERY: review fixture login authority fields cannot be mutated by the client", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", REVIEW_FIXTURE_UID), {
      kakaoUserId: REVIEW_FIXTURE_UID,
      nickname: "fixture",
      dataPartition: "play_review",
      reviewFixtureEnabled: true,
      reviewFixtureLoginEnabled: true,
      reviewFixtureLoginActivatedAt: Timestamp.now(),
    });
  });
  const db = await playReviewSession();

  await assertFails(
    updateDoc(doc(db, "users", REVIEW_FIXTURE_UID), {
      reviewFixtureLoginEnabled: false,
    })
  );
  await assertFails(
    updateDoc(doc(db, "users", REVIEW_FIXTURE_UID), {
      reviewFixtureLoginActivatedAt: Timestamp.now(),
    })
  );
});
