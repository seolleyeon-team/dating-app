import assert from "node:assert/strict";
import test from "node:test";

import {
  isFreeBlindMeetingTestClient,
  isFreeBlindMeetingTestBuild,
  isFreeBlindMeetingTestWindow,
  isFreeBlindMeetingTestUser,
  readFreeBlindMeetingTestBuildConfig,
} from "./compatibility";

test("free flow requires an explicit server-side tester UID", () => {
  const allowedUsers = new Set(["tester-a"]);

  assert.equal(
    isFreeBlindMeetingTestUser("tester-a", allowedUsers),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestUser("tester-b", allowedUsers),
    false
  );
  assert.equal(isFreeBlindMeetingTestUser(" tester-a ", allowedUsers), true);
});

test("free build flow requires the exact build, expiry, and slot limit", () => {
  const env = {
    BLIND_MEETING_FREE_TEST_BUILD: "12",
    BLIND_MEETING_FREE_TEST_EXPIRES_AT: "2026-09-07T23:59:59+09:00",
    BLIND_MEETING_FREE_TEST_MAX_ACCOUNTS: "6",
  };
  const config = readFreeBlindMeetingTestBuildConfig(env);

  assert.equal(config.build, "12");
  assert.equal(config.maxAccounts, 6);
  assert.equal(
    isFreeBlindMeetingTestBuild(
      "12",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestBuild(
      "11",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    false
  );

  assert.equal(
    isFreeBlindMeetingTestWindow(
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestClient(
      "",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestClient(
      "",
      Date.parse("2026-09-08T00:00:00+09:00"),
      env
    ),
    false
  );
  assert.equal(
    isFreeBlindMeetingTestBuild(
      "12",
      Date.parse("2026-09-08T00:00:00+09:00"),
      env
    ),
    false
  );
  assert.equal(
    isFreeBlindMeetingTestBuild(
      "12",
      Date.parse("2026-09-01T00:00:00+09:00"),
      {
        ...env,
        BLIND_MEETING_FREE_TEST_MAX_ACCOUNTS: "",
      }
    ),
    false
  );
});

test("free build flow accepts every build in the server allowlist", () => {
  const env = {
    BLIND_MEETING_FREE_TEST_BUILD: "13, 17, 13",
    BLIND_MEETING_FREE_TEST_EXPIRES_AT: "2026-09-07T23:59:59+09:00",
    BLIND_MEETING_FREE_TEST_MAX_ACCOUNTS: "9",
  };
  const config = readFreeBlindMeetingTestBuildConfig(env);

  assert.equal(config.build, "13, 17, 13");
  assert.deepEqual(config.builds, ["13", "17"]);
  assert.equal(
    isFreeBlindMeetingTestClient(
      "13",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestClient(
      "17",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    true
  );
  assert.equal(
    isFreeBlindMeetingTestClient(
      "12",
      Date.parse("2026-09-01T00:00:00+09:00"),
      env
    ),
    false
  );
});
