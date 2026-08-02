import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import { withAppCheck } from "./appCheckPolicy";

// Compiled tests live under lib/; source under src/.
const indexSrc = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

test("withAppCheck always sets enforceAppCheck", () => {
  assert.equal(withAppCheck().enforceAppCheck, true);
  assert.equal(
    withAppCheck({ memory: "256MiB", timeoutSeconds: 30 }).enforceAppCheck,
    true
  );
  assert.equal(withAppCheck({ memory: "256MiB" }).memory, "256MiB");
});

test("index callables never use bare onCall without options", () => {
  // `onCall(async` means App Check cannot be configured on that callable.
  assert.doesNotMatch(indexSrc, /onCall\(\s*async\b/);
});

test("auth and bootstrap callables pass through withAppCheck", () => {
  const required = [
    "createFirebaseCustomToken",
    "verifyAdultIdentityAfterLogin",
    "createFriendInvite",
    "acceptFriendInvite",
    "ensureEventTeamSetup",
    "createEventTeamInvite",
    "respondEventTeamInvite",
    "spinSeasonMeetingRoulette",
    "syncContactBlocks",
    "syncKakaoTalkFriendBlocks",
    "saveUserPhoneHash",
  ];

  for (const name of required) {
    const pattern = new RegExp(
      `export const ${name} = onCall\\(\\s*withAppCheck\\(`
    );
    assert.match(
      indexSrc,
      pattern,
      `${name} must be declared as onCall(withAppCheck(...))`
    );
  }
});

test("removed email-link custom-token bridge stays absent", () => {
  assert.doesNotMatch(
    indexSrc,
    /export const createFirebaseCustomTokenFromEmailLinkToken\s*=/
  );
});
